"""Vector candidate retrieval (disabled by default, zero external cost)."""
from typing import List, Tuple, Optional
from app.config import Settings, get_settings
from app.dependencies import TenantContext
from app.memory.models import MemoryModel


class VectorSearcher:
    """Optional local dense retrieval."""
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.enabled = self.settings.ENABLE_EMBEDDINGS

    def search(
        self,
        context: TenantContext,
        query: str,
        limit: int = 10
    ) -> List[Tuple[MemoryModel, float]]:
        if not self.enabled:
            return []
        # Disabled by default as mandated
        return []
