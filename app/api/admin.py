"""Admin API endpoints for seeding demo fixtures and resetting tenant data.

Every route here requires the X-Admin-Key header (see ADMIN_API_KEY in settings).
"""
from fastapi import APIRouter, Depends, Query
from typing import Dict, Any
from app.config import Settings, get_settings
from app.dependencies import TenantContext, require_admin
from app.errors import OpsMemoryError
from app.memory.repository import MemoryRepository, get_memory_repository

router = APIRouter(prefix="/v1/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


def _admin_context(tenant_id: str, settings: Settings) -> TenantContext:
    try:
        graph_name = settings.tenant_graph_name(tenant_id)
    except ValueError as e:
        raise OpsMemoryError(str(e), status_code=422)
    return TenantContext(tenant_id=tenant_id, graph_name=graph_name)


@router.post("/seed")
async def seed_data(
    tenant_id: str = Query("acme"),
    repo: MemoryRepository = Depends(get_memory_repository),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Seed deterministic test fixtures for a tenant."""
    from eval.dataset.fixtures import seed_fixtures_for_tenant
    stats = seed_fixtures_for_tenant(_admin_context(tenant_id, settings), repo)
    return {"status": "seeded", "tenant_id": tenant_id, "stats": stats}


@router.post("/reset")
async def reset_data(
    tenant_id: str = Query("acme"),
    repo: MemoryRepository = Depends(get_memory_repository),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Delete all stored data for a tenant."""
    count = repo.delete_all_tenant_data(_admin_context(tenant_id, settings))
    return {"status": "reset", "tenant_id": tenant_id, "deleted_records": count}