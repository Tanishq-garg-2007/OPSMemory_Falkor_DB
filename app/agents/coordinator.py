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


class LearnedCreatedItem(BaseModel):
    id: str
    title: str


class LearnedSupersededItem(BaseModel):
    old_id: str
    new_id: str
    title: str


class LearnedTaskItem(BaseModel):
    id: str
    task_type: str


class LearnedData(BaseModel):
    created: List[LearnedCreatedItem] = Field(default_factory=list)
    superseded: List[LearnedSupersededItem] = Field(default_factory=list)
    tasks_created: List[LearnedTaskItem] = Field(default_factory=list)


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
    learned: LearnedData = Field(default_factory=LearnedData)


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
                    "status": "resolved" if resolve_res else "not_run",
                    "result": resolve_res
                })
            elif task.task_type == "CURATE_MEMORY":
                stats = await self.curator_agent.claim_and_curate_task(context, task.id)
                if stats is not None:
                    self.repo.record_agent_handoff(
                        context=context, from_agent="agent_triage", to_agent="agent_curator",
                        task_id=task.id, reason="memory_curation", shared_state=stats,
                        conversation_id=effective_conv_id,
                    )
                resolved_task_info.append({
                    "task_id": task.id, "task_type": task.task_type,
                    "status": "done" if stats is not None else task.status, "result": stats,
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

        # 5. Handoffs are recorded by the agents that actually did the work (triage -> resolver in
        #    TriageAgent, resolver -> curator in ResolverAgent / above). Nothing is fabricated here.

        # 6. Pack final response
        learned_created = [{"id": m.id, "title": m.title} for m in triage_res.get("created_memories", [])]
        for task_info in resolved_task_info:
            res_dict = task_info.get("result")
            if isinstance(res_dict, dict) and "created_memory" in res_dict:
                learned_created.append(res_dict["created_memory"])

        learned_superseded = triage_res.get("superseded_memories", [])
        learned_tasks = [{"id": t.id, "task_type": t.task_type} for t in created_tasks]

        learned = LearnedData(
            created=[LearnedCreatedItem(**c) for c in learned_created],
            superseded=[LearnedSupersededItem(**s) for s in learned_superseded],
            tasks_created=[LearnedTaskItem(**t) for t in learned_tasks],
        )

        recent_handoffs = self.repo.get_recent_handoffs(context, conversation_id=effective_conv_id, limit=10)
        return ChatResponse(
            conversation_id=effective_conv_id,
            answer=rag_response.answer,
            citations=rag_response.citations,
            evidence=[e.model_dump() for e in rag_response.evidence],
            tasks=resolved_task_info,
            abstained=rag_response.abstained,
            confidence=rag_response.confidence,
            reasoning_paths=rag_response.reasoning_paths,
            agent_handoffs=recent_handoffs,
            learned=learned
        )


_coordinator: Optional[Coordinator] = None


def get_coordinator() -> Coordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = Coordinator()
    return _coordinator
