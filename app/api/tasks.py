"""Tasks API endpoint."""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query
from app.dependencies import TenantContext, get_tenant_context
from app.memory.repository import MemoryRepository, get_memory_repository
from app.errors import ResourceNotFoundError

router = APIRouter(prefix="/v1/tasks", tags=["Tasks"])


@router.get("")
def list_tasks(
    status: Optional[str] = Query(None),
    context: TenantContext = Depends(get_tenant_context),
    repo: MemoryRepository = Depends(get_memory_repository)
) -> List[Dict[str, Any]]:
    tasks = repo.list_tasks(context, status=status)
    return [t.model_dump() for t in tasks]


@router.get("/{task_id}")
def get_task(
    task_id: str,
    context: TenantContext = Depends(get_tenant_context),
    repo: MemoryRepository = Depends(get_memory_repository)
) -> Dict[str, Any]:
    task = repo.get_task(context, task_id)
    if not task:
        raise ResourceNotFoundError(f"Task '{task_id}' not found")
    return task.model_dump()
