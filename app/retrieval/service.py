"""Retrieval service orchestrating query understanding, candidate retrieval, fusion, and RAG."""
import hashlib
from typing import Optional
from app.dependencies import TenantContext
from app.retrieval.router import RetrievalRouter
from app.retrieval.graph_search import GraphSearcher
from app.retrieval.fts import FTSSearcher
from app.retrieval.vector import VectorSearcher
from app.retrieval.fusion import RankFusion
from app.retrieval.evidence import RAGEngine, AnswerResponse
from app.retrieval.grounding import is_degenerate_query, has_grounding
from app.memory.repository import MemoryRepository, get_memory_repository
from app.core.cache import get_cache
from app.core.concurrency import get_limiter, get_coalescer


class RetrievalService:
    def __init__(self, repo: Optional[MemoryRepository] = None):
        self.repo = repo or get_memory_repository()
        self.router = RetrievalRouter()
        self.graph_searcher = GraphSearcher(self.repo)
        self.fts_searcher = FTSSearcher(self.repo)
        self.vector_searcher = VectorSearcher(self.repo)
        self.fusion = RankFusion()
        self.rag_engine = RAGEngine()
        self.cache = get_cache()
        self.limiter = get_limiter()
        self.coalescer = get_coalescer()

    async def retrieve_and_answer(self, context: TenantContext, query: str) -> AnswerResponse:
        # Check cache
        q_hash = hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()[:16]
        cached = self.cache.get(context.tenant_id, q_hash)
        if cached:
            return cached

        # Single-flight coalescing for concurrent identical queries
        coalesce_key = f"{context.tenant_id}:{q_hash}"
        return await self.coalescer.execute(coalesce_key, lambda: self._execute_retrieval(context, query, q_hash))

    def _gather(self, context: TenantContext, query: str):
        """Retrieval without any LLM call: anchors -> route -> graph/FTS/vector -> fusion."""
        anchors = self.repo.find_anchor_entities(context, query, limit=5)
        intent = self.router.route_query(query, anchor_entities=[a.name for a in anchors])
        graph_paths = self.graph_searcher.get_dependency_paths(context, intent)
        reasoning_paths = self.graph_searcher.get_reasoning_paths(context, intent)
        graph_candidates = self.graph_searcher.search(context, intent, limit=20)
        fts_candidates = self.fts_searcher.search(context, query, limit=20)
        vector_candidates = self.vector_searcher.search(context, query, limit=10)
        ranked = self.fusion.fuse(intent, graph_candidates, fts_candidates, vector_candidates)
        return intent, ranked, graph_paths, reasoning_paths

    async def retrieve_evidence(self, context: TenantContext, query: str):
        """Evidence only (no answer LLM call). Used by the resolver to avoid a wasted LLM round trip."""
        import asyncio
        _, ranked, _, _ = await asyncio.to_thread(self._gather, context, query)
        return self.rag_engine.packer.pack_evidence(ranked)

    async def _execute_retrieval(self, context: TenantContext, query: str, q_hash: str) -> AnswerResponse:
        import asyncio
        if is_degenerate_query(query):
            return self._abstain("Please provide a valid question.")

        async with self.limiter.retrieval_semaphore:
            # Blocking FalkorDB calls run in a worker thread so the event loop stays free.
            intent, ranked, graph_paths, reasoning_paths = await asyncio.to_thread(self._gather, context, query)

            # Grounding gate: only entities the question actually names count.
            q_low = query.lower()
            named = {e for e in intent.target_entities if e in q_low or e.replace("-", " ") in q_low}
            top = [mem for mem, _ in ranked[:20]]
            entity_hit = any(e in named for mem in top for e in mem.entities)
            if not has_grounding(query, (f"{m.title} {m.summary}" for m in top), entity_hit=entity_hit):
                return self._abstain("Would you like to record this information in OpsMemory?")

            async with self.limiter.llm_semaphore:
                response = await self.rag_engine.generate_answer(
                    query, ranked, graph_paths=graph_paths, reasoning_paths=reasoning_paths
                )

            self.cache.set(context.tenant_id, q_hash, response, ttl=60.0)
            return response


    @staticmethod
    def _abstain(follow_up: str) -> AnswerResponse:
        return AnswerResponse(
            answer="I do not have sufficient recorded evidence in OpsMemory to answer this question accurately.",
            citations=[],
            confidence="low",
            abstained=True,
            follow_ups=[follow_up],
            evidence=[],
            reasoning_paths=[],
        )


_retrieval_service: Optional[RetrievalService] = None


def get_retrieval_service() -> RetrievalService:
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service