"""Curator worker logic for consolidation, deduplication, and expiration."""
from typing import Optional, Dict, Any, List
from app.dependencies import TenantContext
from app.memory.repository import MemoryRepository, get_memory_repository
from app.memory.conflicts import detect_semantic_conflict
from app.core.time import utc_now_iso, is_past
from app.core.logging import get_logger

logger = get_logger("curator")


class MemoryCurator:
    """Performs background memory curation, conflict resolution, and pruning."""
    def __init__(self, repo: Optional[MemoryRepository] = None):
        self.repo = repo or get_memory_repository()

    def curate_tenant(self, context: TenantContext) -> Dict[str, Any]:
        """Run a curation cycle for a tenant."""
        active_memories = self.repo.list_memories(context, status="active")
        superseded_count = 0
        expired_count = 0

        # 1. Check for expired memories (valid_to is in the past)
        for mem in active_memories:
            if mem.valid_to and is_past(mem.valid_to):
                self.repo.update_memory_status(
                    context, mem.id, new_status="expired", expected_version=mem.version
                )
                expired_count += 1

        # 2. Re-check active memories for unresolved conflicts / supersession
        now = utc_now_iso()
        for i in range(len(active_memories)):
            for j in range(i + 1, len(active_memories)):
                m1 = active_memories[i]
                m2 = active_memories[j]
                if detect_semantic_conflict(m1, m2):
                    if m1.confidence > m2.confidence:
                        self.repo.update_memory_status(
                            context, m2.id, new_status="superseded", valid_to=now,
                            expected_version=m2.version, superseded_by=m1.id
                        )
                        superseded_count += 1
                    elif m2.confidence > m1.confidence:
                        self.repo.update_memory_status(
                            context, m1.id, new_status="superseded", valid_to=now,
                            expected_version=m1.version, superseded_by=m2.id
                        )
                        superseded_count += 1

        return {
            "tenant_id": context.tenant_id,
            "expired_memories": expired_count,
            "superseded_memories": superseded_count
        }
