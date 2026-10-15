"""Full-text search candidate retrieval using derived SQLite FTS5 index."""
from typing import List, Tuple, Optional
from app.dependencies import TenantContext
from app.memory.models import MemoryModel
from app.memory.repository import MemoryRepository, get_memory_repository


class FTSSearcher:
    """Retrieves memory candidates using SQLite FTS5."""
    def __init__(self, repo: Optional[MemoryRepository] = None):
        self.repo = repo or get_memory_repository()

    def search(
        self,
        context: TenantContext,
        query: str,
        limit: int = 20
    ) -> List[Tuple[MemoryModel, float]]:
        return self.repo.search_fts(context, query, limit=limit)
