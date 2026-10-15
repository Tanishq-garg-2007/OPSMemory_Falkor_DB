"""Chat API endpoint."""
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.dependencies import TenantContext, get_tenant_context
from app.agents.coordinator import Coordinator, get_coordinator, ChatResponse

router = APIRouter(prefix="/v1", tags=["Chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest,
    context: TenantContext = Depends(get_tenant_context),
    coordinator: Coordinator = Depends(get_coordinator)
) -> ChatResponse:
    """Handle chat message, extract memories, coordinate tasks, and generate evidence-grounded response."""
    sess_id = req.session_id or req.conversation_id
    return await coordinator.handle_user_message(
        context=context,
        message=req.message,
        conv_id=sess_id
    )
