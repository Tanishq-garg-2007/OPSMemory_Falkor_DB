"""Curator Agent: Claims curation tasks and performs deduplication & conflict resolution."""
from typing import Optional, Dict, Any
from app.dependencies import TenantContext
from app.tasks.task_board import TaskBoard, get_task_board
from app.memory.curator import MemoryCurator
from app.core.logging import get_logger

logger = get_logger("curator_agent")


class CuratorAgent:
    def __init__(
        self,
        task_board: Optional[TaskBoard] = None,
        curator: Optional[MemoryCurator] = None,
        worker_id: str = "curator_worker_1"
    ):
        self.task_board = task_board or get_task_board()
        self.curator = curator or MemoryCurator()
        self.worker_id = worker_id

    async def claim_and_curate_task(
        self,
        context: TenantContext,
        task_id: str
    ) -> Optional[Dict[str, Any]]:
        claimed = self.task_board.claim_task(context, task_id, self.worker_id, lease_seconds=30)
        if not claimed:
            return None

        # Execute curation
        stats = self.curator.curate_tenant(context)
        self.task_board.complete_task(context, task_id, self.worker_id, stats)
        return stats
