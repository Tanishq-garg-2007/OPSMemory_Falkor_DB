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
from app.core.cache import get_cache
from app.core.concurrency import get_limiter, get_coalescer


class RetrievalService:
    def __init__(self):
        self.router = RetrievalRouter()
        self.graph_searcher = GraphSearcher()
        self.fts_searcher = FTSSearcher()
        self.vector_searcher = VectorSearcher()
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
        async with self.limiter.retrieval_semaphore:
            # 1. Route query
            intent = self.router.route_query(query)

            # 2. Retrieve candidates
            graph_candidates = self.graph_searcher.search(context, intent, limit=20)
            fts_candidates = self.fts_searcher.search(context, query, limit=20)
            vector_candidates = self.vector_searcher.search(context, query, limit=10)

            # 3. Fuse candidates
            ranked = self.fusion.fuse(intent, graph_candidates, fts_candidates, vector_candidates)

            # 4. Generate answer
            async with self.limiter.llm_semaphore:
                response = await self.rag_engine.generate_answer(query, ranked)

            # Cache response
            self.cache.set(context.tenant_id, q_hash, response, ttl=60.0)
            return response


_retrieval_service: Optional[RetrievalService] = None


def get_retrieval_service() -> RetrievalService:
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service
