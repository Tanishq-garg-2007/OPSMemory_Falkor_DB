"""Conversations API endpoint."""
from fastapi import APIRouter, Depends
from typing import Dict, Any
from app.dependencies import TenantContext, get_tenant_context
from app.memory.repository import MemoryRepository, get_memory_repository
from app.errors import ResourceNotFoundError

router = APIRouter(prefix="/v1/conversations", tags=["Conversations"])


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    context: TenantContext = Depends(get_tenant_context),
    repo: MemoryRepository = Depends(get_memory_repository)
) -> Dict[str, Any]:
    conv = repo.get_conversation(context, conversation_id)
    if not conv:
        raise ResourceNotFoundError(f"Conversation '{conversation_id}' not found for tenant")
    return conv.model_dump()
