"""Chat API endpoint."""
import time
from collections import defaultdict, deque
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.dependencies import TenantContext, get_tenant_context
from app.agents.coordinator import Coordinator, get_coordinator, ChatResponse
from app.errors import OpsMemoryError

router = APIRouter(prefix="/v1", tags=["Chat"])

MAX_MESSAGE_CHARS = 4000
RATE_LIMIT_PER_MIN = 30
_hits = defaultdict(deque)


def _rate_limit(tenant_id: str) -> None:
    """Per-tenant sliding window (in-memory, per process). Protects the LLM quota."""
    now = time.monotonic()
    q = _hits[tenant_id]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT_PER_MIN:
        raise OpsMemoryError("Rate limit exceeded: try again in a minute", status_code=429)
    q.append(now)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    conversation_id: Optional[str] = Field(default=None, max_length=100)
    session_id: Optional[str] = Field(default=None, max_length=100)


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest,
    context: TenantContext = Depends(get_tenant_context),
    coordinator: Coordinator = Depends(get_coordinator)
) -> ChatResponse:
    """Handle chat message, extract memories, coordinate tasks, and generate evidence-grounded response."""
    _rate_limit(context.tenant_id)
    sess_id = req.session_id or req.conversation_id
    return await coordinator.handle_user_message(
        context=context,
        message=req.message,
        conv_id=sess_id
    )
