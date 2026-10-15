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

    async def _execute_retrieval(self, context: TenantContext, query: str, q_hash: str) -> AnswerResponse:
        if is_degenerate_query(query):
            return self._abstain("Please provide a valid question.")

        async with self.limiter.retrieval_semaphore:
            # 1. Sub-millisecond Dynamic Semantic Vector Anchoring in FalkorDB
            anchors = self.repo.find_anchor_entities(context, query, limit=5)
            anchor_names = [a.name for a in anchors]

            # 2. Route query dynamically with anchored entities
            intent = self.router.route_query(query, anchor_entities=anchor_names)

            # 3. Retrieve candidates and materialized graph paths
            graph_paths = self.graph_searcher.get_dependency_paths(context, intent)
            reasoning_paths = self.graph_searcher.get_reasoning_paths(context, intent)
            graph_candidates = self.graph_searcher.search(context, intent, limit=20)
            fts_candidates = self.fts_searcher.search(context, query, limit=20)
            vector_candidates = self.vector_searcher.search(context, query, limit=10)

            # 3. Fuse candidates
            ranked = self.fusion.fuse(intent, graph_candidates, fts_candidates, vector_candidates)

            # Grounding gate: nothing we remember relates to this question, so do not let the LLM improvise.
            # Only entities the question actually names count; vector anchors always return nearest
            # neighbours, even for nonsense, so they say nothing about whether the question is grounded.
            q_low = query.lower()
            named = {e for e in intent.target_entities if e in q_low or e.replace("-", " ") in q_low}
            top = [mem for mem, _ in ranked[:20]]
            entity_hit = any(e in named for mem in top for e in mem.entities)
            if not has_grounding(query, (f"{m.title} {m.summary}" for m in top), entity_hit=entity_hit):
                return self._abstain("Would you like to record this information in OpsMemory?")

            # 4. Generate answer
            async with self.limiter.llm_semaphore:
                response = await self.rag_engine.generate_answer(
                    query, ranked, graph_paths=graph_paths, reasoning_paths=reasoning_paths
                )

            # Cache response
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