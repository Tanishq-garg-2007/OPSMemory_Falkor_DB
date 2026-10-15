"""Graph inspection API endpoint for judges and UI."""
from fastapi import APIRouter, Depends
from typing import Dict, Any
from app.dependencies import TenantContext, get_tenant_context
from app.memory.repository import MemoryRepository, get_memory_repository

router = APIRouter(prefix="/v1/graph", tags=["Graph"])


@router.get("/context")
async def get_graph_context(
    context: TenantContext = Depends(get_tenant_context),
    repo: MemoryRepository = Depends(get_memory_repository)
) -> Dict[str, Any]:
    """Inspect active FalkorDB graph state: active nodes, edges, turns, agent handoffs, and indexes."""
    return repo.get_graph_context(context)
