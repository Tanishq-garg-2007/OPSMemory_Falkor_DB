"""Entities API endpoints."""
from typing import List, Dict, Any
from fastapi import APIRouter, Depends
from app.dependencies import TenantContext, get_tenant_context
from app.memory.repository import MemoryRepository, get_memory_repository
from app.errors import ResourceNotFoundError

router = APIRouter(prefix="/v1/entities", tags=["Entities"])


@router.get("/{entity_id}/timeline")
async def get_entity_timeline(
    entity_id: str,
    context: TenantContext = Depends(get_tenant_context),
    repo: MemoryRepository = Depends(get_memory_repository),
) -> List[Dict[str, Any]]:
    """Return memory timeline for an entity linked through ABOUT, ordered by valid_from."""
    timeline = repo.get_entity_timeline(context, entity_id=entity_id)
    if timeline is None:
        raise ResourceNotFoundError(f"Entity '{entity_id}' not found for tenant")
    return timeline
