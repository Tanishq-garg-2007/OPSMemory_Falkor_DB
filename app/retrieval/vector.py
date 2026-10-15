"""Vector candidate retrieval using FalkorDB native vector index."""
from typing import List, Tuple, Optional
from app.config import Settings, get_settings
from app.dependencies import TenantContext
from app.memory.models import MemoryModel
from app.memory.repository import MemoryRepository, get_memory_repository


class VectorSearcher:
    """FalkorDB native dense vector retrieval."""
    def __init__(self, repo: Optional[MemoryRepository] = None, settings: Optional[Settings] = None):
        self.repo = repo or get_memory_repository()
        self.settings = settings or get_settings()

    def search(
        self,
        context: TenantContext,
        query: str,
        limit: int = 10
    ) -> List[Tuple[MemoryModel, float]]:
        if not self.settings.ENABLE_EMBEDDINGS:
            return []
        return self.repo.search_vector(context, query, limit=limit)

