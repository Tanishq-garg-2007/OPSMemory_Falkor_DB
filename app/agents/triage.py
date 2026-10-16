"""Triage Agent: Extracts candidates, persists initial memories, and creates follow-up tasks."""
from typing import List, Dict, Any, Optional
from app.dependencies import TenantContext
from app.memory.lifecycle import MemoryLifecycle
from app.memory.signals import is_inquiry
from app.memory.extraction import MemoryExtractor, ExtractionResult
from app.memory.models import MemoryModel, TaskModel
from app.tasks.task_board import TaskBoard, get_task_board
from app.core.logging import get_logger

logger = get_logger("triage_agent")


class TriageAgent:
    def __init__(self, lifecycle: Optional[MemoryLifecycle] = None, task_board: Optional[TaskBoard] = None):
        self.lifecycle = lifecycle or MemoryLifecycle()
        self.extractor = MemoryExtractor()
        self.task_board = task_board or get_task_board()

    async def triage_message(
        self,
        context: TenantContext,
        message: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Triage input message: extract candidates, persist, and dispatch tasks."""
        # 1. Record source provenance
        source = self.lifecycle.record_source(
            context=context,
            conversation_id=conversation_id,
            message_id=message_id,
            source_type="conversation",
            raw_text=message
        )

        created_memories: List[MemoryModel] = []
        created_tasks: List[TaskModel] = []
        self.lifecycle.last_superseded = []

        # Salience filter: questions and requests for information are never stored as memories.
        if is_inquiry(message):
            return {
                "source_id": source.id,
                "created_memories": [],
                "created_tasks": [],
                "superseded_memories": [],
                "missing_info": []
            }

        # 2. Extract candidates
        # Service names come from this tenant's graph, not a built-in list (None when the graph can't be read).
        try:
            known_services = [e.name for e in self.lifecycle.repo.list_entities(context, kind="service")]
        except Exception as e:
            logger.warning(f"Could not load known services: {e}")
            known_services = None
        extracted: ExtractionResult = await self.extractor.extract_candidates(message, known_services=known_services)

        # 3. Persist episodic memories
        for epi in extracted.episodic_memories:
            mem = self.lifecycle.store_memory(
                context=context,
                memory_type="episodic",
                subtype=epi.subtype,
                title=epi.title,
                summary=epi.summary,
                entity_names=epi.entity_names,
                source_id=source.id,
                confidence_basis="user_explicit"
            )
            created_memories.append(mem)

            # If incident detected, trigger RESOLVE_INCIDENT task
            if epi.subtype == "incident":
                task = self.task_board.post_task(
                    context=context,
                    task_type="RESOLVE_INCIDENT",
                    target_id_or_context=mem.id,
                    payload={
                        "memory_id": mem.id,
                        "title": mem.title,
                        "summary": mem.summary,
                        "entities": mem.entities,
                        "severity": epi.severity
                    }
                )
                created_tasks.append(task)
                self.lifecycle.repo.record_agent_handoff(
                    context=context,
                    from_agent="agent_triage",
                    to_agent="agent_resolver",
                    task_id=task.id,
                    reason=f"incident_triage_{epi.severity}",
                    shared_state={"memory_id": mem.id, "title": mem.title, "severity": epi.severity},
                    memory_id=mem.id
                )

        # 4. Persist semantic facts
        for sem in extracted.semantic_facts:
            title = f"{sem.subject_entity} {sem.predicate}: {sem.object_value}"
            summary = f"{sem.subject_entity} {sem.predicate} is {sem.object_value}"
            mem = self.lifecycle.store_memory(
                context=context,
                memory_type="semantic",
                subtype=sem.subtype,
                title=title,
                summary=summary,
                entity_names=[sem.subject_entity],
                source_id=source.id,
                confidence_basis=sem.confidence_basis
            )
            created_memories.append(mem)

        # 5. Persist procedural requests
        for proc in extracted.procedural_requests:
            title = f"Procedure for {proc.trigger}"
            mem = self.lifecycle.store_memory(
                context=context,
                memory_type="procedural",
                subtype=proc.subtype,
                title=title,
                summary=proc.trigger,
                entity_names=proc.entity_names,
                source_id=source.id,
                confidence_basis="user_explicit"
            )
            created_memories.append(mem)

        # If multiple memories created, dispatch CURATE_MEMORY task
        if len(created_memories) > 1:
            curate_task = self.task_board.post_task(
                context=context,
                task_type="CURATE_MEMORY",
                target_id_or_context=f"curate_{source.id}",
                payload={"source_id": source.id, "count": len(created_memories)}
            )
            created_tasks.append(curate_task)

        return {
            "source_id": source.id,
            "created_memories": created_memories,
            "created_tasks": created_tasks,
            "superseded_memories": list(self.lifecycle.last_superseded)
        }