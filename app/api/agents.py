"""Agent coordination and handoffs API."""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query
from app.dependencies import TenantContext, get_tenant_context
from app.memory.repository import MemoryRepository, get_memory_repository

router = APIRouter(prefix="/v1/agents", tags=["Agents"])


@router.get("/handoffs")
def get_agent_handoffs(
    conversation_id: Optional[str] = Query(None),
    limit: int = Query(default=10, ge=1, le=100),
    context: TenantContext = Depends(get_tenant_context),
    repo: MemoryRepository = Depends(get_memory_repository),
) -> List[Dict[str, Any]]:
    """Get recent agent handoffs, optionally filtered by conversation_id."""
    return repo.get_recent_handoffs(context, conversation_id=conversation_id, limit=limit)
