"""Memories API endpoint."""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query
from app.dependencies import TenantContext, get_tenant_context
from app.memory.repository import MemoryRepository, get_memory_repository
from app.errors import ResourceNotFoundError

router = APIRouter(prefix="/v1/memories", tags=["Memories"])


@router.get("")
async def list_memories(
    status: Optional[str] = Query(None),
    memory_type: Optional[str] = Query(None),
    context: TenantContext = Depends(get_tenant_context),
    repo: MemoryRepository = Depends(get_memory_repository)
) -> List[Dict[str, Any]]:
    memories = repo.list_memories(context, status=status, memory_type=memory_type)
    return [m.model_dump() for m in memories]


@router.get("/{memory_id}")
async def get_memory(
    memory_id: str,
    context: TenantContext = Depends(get_tenant_context),
    repo: MemoryRepository = Depends(get_memory_repository)
) -> Dict[str, Any]:
    memory = repo.get_memory(context, memory_id)
    if not memory:
        raise ResourceNotFoundError(f"Memory '{memory_id}' not found")
    # Include related graph entities
    related_entities = repo.get_related_entities(context, memory_id)
    res = memory.model_dump()
    res["related_entities"] = [e.model_dump() for e in related_entities]
    return res


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    hard: bool = Query(False),
    context: TenantContext = Depends(get_tenant_context),
    repo: MemoryRepository = Depends(get_memory_repository)
) -> Dict[str, Any]:
    ok = repo.delete_memory(context, memory_id, hard_delete=hard)
    return {"success": ok, "memory_id": memory_id, "deleted": True}
