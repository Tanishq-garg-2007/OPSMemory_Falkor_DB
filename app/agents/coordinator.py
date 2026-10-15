"""Deterministic coordinator orchestrating triage, retrieval, workers, and response synthesis."""
import uuid
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from app.dependencies import TenantContext
from app.agents.triage import TriageAgent
from app.agents.resolver import ResolverAgent
from app.agents.curator_agent import CuratorAgent
from app.retrieval.service import RetrievalService, get_retrieval_service
from app.memory.repository import MemoryRepository, get_memory_repository
from app.memory.models import ConversationModel
from app.core.ids import conversation_id
from app.core.time import utc_now_iso
from app.core.logging import get_logger

logger = get_logger("coordinator")


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    citations: List[str] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    abstained: bool = False
    confidence: str = "medium"
    reasoning_paths: List[List[str]] = Field(default_factory=list)
    agent_handoffs: List[Dict[str, Any]] = Field(default_factory=list)


class Coordinator:
    """Deterministic orchestrator managing user interactions across sessions."""

    def __init__(
        self,
        repo: Optional[MemoryRepository] = None,
        retrieval_service: Optional[RetrievalService] = None
    ):
        self.repo = repo or get_memory_repository()
        self.retrieval_service = retrieval_service or get_retrieval_service()
        self.triage_agent = TriageAgent(task_board=None)
        self.resolver_agent = ResolverAgent(retrieval_service=self.retrieval_service)
        self.curator_agent = CuratorAgent()

    async def handle_user_message(
        self,
        context: TenantContext,
        message: str,
        conv_id: Optional[str] = None
    ) -> ChatResponse:
        msg_id = f"msg_{uuid.uuid4().hex[:8]}"

        # 1. Manage Conversation state across requests/sessions
        effective_conv_id = conv_id or conversation_id()
        conv = self.repo.get_conversation(context, effective_conv_id)
        if not conv:
            conv = ConversationModel(
                id=effective_conv_id,
                tenant_id=context.tenant_id,
                title=message[:40].strip(),
                status="active",
                created_at=utc_now_iso(),
                updated_at=utc_now_iso()
            )
            self.repo.save_conversation(context, conv)

        user_turn_id = f"turn_{uuid.uuid4().hex[:12]}"

        # 2. Triage & Extraction: capture episodic/semantic/procedural memories
        triage_res = await self.triage_agent.triage_message(
            context=context,
            message=message,
            conversation_id=effective_conv_id,
            message_id=msg_id
        )

        created_memories = [m.id for m in triage_res.get("created_memories", [])]
        self.repo.record_session_turn(
            context=context,
            session_id=effective_conv_id,
            turn_id=user_turn_id,
            role="user",
            content=message,
            memory_ids=created_memories
        )

        created_tasks = triage_res["created_tasks"]

        # 3. Process any urgent RESOLVE_INCIDENT task immediately via Resolver worker
        resolved_task_info = []
        for task in created_tasks:
            if task.task_type == "RESOLVE_INCIDENT":
                resolve_res = await self.resolver_agent.claim_and_resolve_task(context, task.id)
                resolved_task_info.append({
                    "task_id": task.id,
                    "task_type": task.task_type,
                    "status": "resolved" if resolve_res else "claimed",
                    "result": resolve_res
                })
            else:
                resolved_task_info.append({
                    "task_id": task.id,
                    "task_type": task.task_type,
                    "status": task.status
                })

        # 4. Retrieval & RAG response generation
        rag_response = await self.retrieval_service.retrieve_and_answer(context, message)

        asst_turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        self.repo.record_session_turn(
            context=context,
            session_id=effective_conv_id,
            turn_id=asst_turn_id,
            role="assistant",
            content=rag_response.answer
        )

        # 5. Pack final response
        recent_handoffs = self.repo.get_recent_handoffs(context, limit=10)
        return ChatResponse(
            conversation_id=effective_conv_id,
            answer=rag_response.answer,
            citations=rag_response.citations,
            evidence=[e.model_dump() for e in rag_response.evidence],
            tasks=resolved_task_info,
            abstained=rag_response.abstained,
            confidence=rag_response.confidence,
            reasoning_paths=rag_response.reasoning_paths,
            agent_handoffs=recent_handoffs
        )


_coordinator: Optional[Coordinator] = None


def get_coordinator() -> Coordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = Coordinator()
    return _coordinator
