"""Resolver Agent: Claims incident tasks, gathers evidence/runbooks, and writes resolution proposals."""
import json
from typing import Optional, Dict, Any, List
from app.dependencies import TenantContext
from app.tasks.task_board import TaskBoard, get_task_board
from app.retrieval.service import RetrievalService, get_retrieval_service
from app.llm import get_llm_client
from app.llm.prompts import RESOLVER_SYSTEM_PROMPT
from app.core.logging import get_logger

logger = get_logger("resolver_agent")


class ResolverAgent:
    def __init__(
        self,
        task_board: Optional[TaskBoard] = None,
        retrieval_service: Optional[RetrievalService] = None,
        worker_id: str = "resolver_worker_1"
    ):
        self.task_board = task_board or get_task_board()
        self.retrieval_service = retrieval_service or get_retrieval_service()
        self.worker_id = worker_id

    async def claim_and_resolve_task(
        self,
        context: TenantContext,
        task_id: str
    ) -> Optional[Dict[str, Any]]:
        """Claim a specific task using a lease and execute resolution."""
        claimed = self.task_board.claim_task(context, task_id, self.worker_id, lease_seconds=45)
        if not claimed:
            logger.info(f"Could not claim task {task_id} (already claimed or completed)")
            return None

        payload = json.loads(claimed.payload_json or "{}")
        title = payload.get("title", "")
        summary = payload.get("summary", "")
        entities = payload.get("entities", [])

        # Retrieve relevant runbooks and previous incident decisions
        query = f"runbook procedure for rollback {title} {' '.join(entities)}"
        retrieval_response = await self.retrieval_service.retrieve_and_answer(context, query)

        citations = retrieval_response.citations
        evidence_text = "\n".join(f"- {e.title}: {e.summary}" for e in retrieval_response.evidence)

        # Build resolution proposal
        llm = get_llm_client()
        prompt = f"Incident: {title}\nSummary: {summary}\n\nEvidence & Runbooks:\n{evidence_text}"

        try:
            llm_result = await llm.generate_json(prompt, RESOLVER_SYSTEM_PROMPT)
            action_plan = llm_result.get("action_plan", ["Assess logs", "Execute verified rollback procedure"])
            recommendation = llm_result.get("recommendation", f"Follow runbook and notify on-call.")
        except Exception:
            action_plan = ["Check telemetry", "Execute rollback if degradation exceeds threshold"]
            recommendation = "Standard incident containment procedure."

        result = {
            "worker_id": self.worker_id,
            "action_plan": action_plan,
            "recommendation": recommendation,
            "citations": citations,
            "status": "resolved"
        }

        # Complete task on board
        self.task_board.complete_task(context, task_id, self.worker_id, result)
        return result
