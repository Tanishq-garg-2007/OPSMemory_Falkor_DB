"""Admin API endpoints for seeding demo fixtures and resetting local tenant data."""
from fastapi import APIRouter, Depends, Query
from typing import Dict, Any
from app.dependencies import TenantContext, get_tenant_context
from app.memory.repository import MemoryRepository, get_memory_repository

router = APIRouter(prefix="/v1/admin", tags=["Admin"])


@router.post("/seed")
async def seed_data(
    tenant_id: str = Query("acme"),
    repo: MemoryRepository = Depends(get_memory_repository)
) -> Dict[str, Any]:
    """Seed deterministic test fixtures for a tenant."""
    from eval.dataset.fixtures import seed_fixtures_for_tenant
    ctx = TenantContext(tenant_id=tenant_id, graph_name=f"tenant_{tenant_id}")
    stats = seed_fixtures_for_tenant(ctx, repo)
    return {"status": "seeded", "tenant_id": tenant_id, "stats": stats}


@router.post("/reset")
async def reset_data(
    tenant_id: str = Query("acme"),
    repo: MemoryRepository = Depends(get_memory_repository)
) -> Dict[str, Any]:
    """Reset local test data for tenant."""
    from eval.dataset.fixtures import reset_tenant_data
    ctx = TenantContext(tenant_id=tenant_id, graph_name=f"tenant_{tenant_id}")
    count = reset_tenant_data(ctx, repo)
    return {"status": "reset", "tenant_id": tenant_id, "deleted_records": count}
