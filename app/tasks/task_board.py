"""Task board with lease-based claiming, idempotency, and failure recovery."""
import json
from typing import Optional, List
from app.dependencies import TenantContext
from app.memory.models import TaskModel
from app.memory.repository import MemoryRepository, get_memory_repository
from app.core.ids import task_id
from app.core.hashing import task_idempotency_key
from app.core.time import utc_now_iso


class TaskBoard:
    def __init__(self, repo: Optional[MemoryRepository] = None):
        self.repo = repo or get_memory_repository()

    def post_task(
        self,
        context: TenantContext,
        task_type: str,
        target_id_or_context: str,
        payload: dict
    ) -> TaskModel:
        """Post a task to the shared board idempotently."""
        idemp = task_idempotency_key(context.tenant_id, task_type, target_id_or_context, state_version=1)
        tid = task_id(task_type, target_id_or_context, version=1)

        task = TaskModel(
            id=tid,
            tenant_id=context.tenant_id,
            task_type=task_type,
            status="pending",
            payload_json=json.dumps(payload),
            idempotency_key=idemp,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso()
        )
        return self.repo.create_task(context, task)

    def claim_task(
        self,
        context: TenantContext,
        task_id: str,
        worker_id: str,
        lease_seconds: int = 30
    ) -> Optional[TaskModel]:
        return self.repo.claim_task(context, task_id, worker_id, lease_seconds)

    def complete_task(
        self,
        context: TenantContext,
        task_id: str,
        worker_id: str,
        result: dict
    ) -> Optional[TaskModel]:
        return self.repo.complete_task(context, task_id, worker_id, json.dumps(result))

    def fail_task(
        self,
        context: TenantContext,
        task_id: str,
        worker_id: str,
        reason: str
    ) -> Optional[TaskModel]:
        return self.repo.fail_task(context, task_id, worker_id, reason)

    def list_pending_tasks(self, context: TenantContext, task_type: Optional[str] = None) -> List[TaskModel]:
        tasks = self.repo.list_tasks(context, status="pending")
        if task_type:
            return [t for t in tasks if t.task_type == task_type]
        return tasks

    def recover_stale_tasks(self, context: TenantContext) -> int:
        return self.repo.recover_expired_leases(context)


_board: Optional[TaskBoard] = None


def get_task_board() -> TaskBoard:
    global _board
    if _board is None:
        _board = TaskBoard()
    return _board
