"""Conversations API endpoints."""
from fastapi import APIRouter, Depends, Query
from typing import Dict, Any, List
from app.dependencies import TenantContext, get_tenant_context
from app.memory.repository import MemoryRepository, get_memory_repository
from app.errors import ResourceNotFoundError

router = APIRouter(prefix="/v1/conversations", tags=["Conversations"])


@router.get("")
def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: TenantContext = Depends(get_tenant_context),
    repo: MemoryRepository = Depends(get_memory_repository),
) -> List[Dict[str, Any]]:
    """List conversations for the current tenant, newest first.

    Returns id, created_at, preview (first user message ≤ 80 chars), and turn_count.
    Scoped strictly to the authenticated tenant.
    """
    return repo.list_conversations(context, limit=limit, offset=offset)


@router.get("/{conversation_id}/turns")
def get_conversation_turns(
    conversation_id: str,
    context: TenantContext = Depends(get_tenant_context),
    repo: MemoryRepository = Depends(get_memory_repository),
) -> List[Dict[str, Any]]:
    """Return all turns for a conversation in chronological order.

    Scoped strictly to the authenticated tenant — cannot be used to read
    another tenant's turns even if the conversation_id is known.
    """
    turns = repo.get_conversation_turns(context, conversation_id)
    if not turns:
        # Check whether the conversation itself exists; if not, 404.
        conv = repo.get_conversation(context, conversation_id)
        if not conv:
            raise ResourceNotFoundError(f"Conversation '{conversation_id}' not found for tenant")
    return turns


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: str,
    context: TenantContext = Depends(get_tenant_context),
    repo: MemoryRepository = Depends(get_memory_repository),
) -> Dict[str, Any]:
    conv = repo.get_conversation(context, conversation_id)
    if not conv:
        raise ResourceNotFoundError(f"Conversation '{conversation_id}' not found for tenant")
    return conv.model_dump()
