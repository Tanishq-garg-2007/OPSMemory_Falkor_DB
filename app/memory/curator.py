"""Curator worker logic for consolidation, deduplication, and expiration."""
from typing import Optional, Dict, Any, List
from app.dependencies import TenantContext
from app.memory.repository import MemoryRepository, get_memory_repository
from app.memory.conflicts import detect_semantic_conflict
from app.core.time import utc_now_iso, is_past
from app.core.logging import get_logger
from app.errors import ConflictError

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
        still_active = []
        for mem in active_memories:
            if mem.valid_to and is_past(mem.valid_to):
                try:
                    self.repo.update_memory_status(
                        context, mem.id, new_status="expired", expected_version=mem.version
                    )
                    expired_count += 1
                except ConflictError:
                    pass
            else:
                still_active.append(mem)
        active_memories = still_active

        # 2. Re-check active memories for unresolved conflicts / supersession
        now = utc_now_iso()
        for i in range(len(active_memories)):
            for j in range(i + 1, len(active_memories)):
                m1 = active_memories[i]
                m2 = active_memories[j]
                if detect_semantic_conflict(m1, m2):
                    loser = winner = None
                    if m1.confidence > m2.confidence:
                        loser, winner = m2, m1
                    elif m2.confidence > m1.confidence:
                        loser, winner = m1, m2
                    if loser is not None:
                        try:
                            self.repo.update_memory_status(
                                context, loser.id, new_status="superseded", valid_to=now,
                                expected_version=loser.version, superseded_by=winner.id
                            )
                            superseded_count += 1
                        except ConflictError:
                            logger.info(f"Curator skipped {loser.id}: changed concurrently")

        return {
            "tenant_id": context.tenant_id,
            "expired_memories": expired_count,
            "superseded_memories": superseded_count
        }
