"""Integration test for multi-agent coordination and task handoffs."""
import pytest
from app.agents.triage import TriageAgent
from app.agents.resolver import ResolverAgent
from app.tasks.task_board import TaskBoard


@pytest.mark.asyncio
async def test_agent_coordination_and_handoff(seeded_repo, context_acme):
    board = TaskBoard(repo=seeded_repo)
    triage = TriageAgent(task_board=board)
    resolver = ResolverAgent(task_board=board)

    # 1. Triage receives an incident report
    message = "CRITICAL OUTAGE: payments-api upgrade failed, checkout is broken"
    triage_result = await triage.triage_message(context_acme, message, "conv_test", "msg_test_1")

    created_tasks = triage_result["created_tasks"]
    assert len(created_tasks) > 0

    incident_task = next((t for t in created_tasks if t.task_type == "RESOLVE_INCIDENT"), None)
    assert incident_task is not None
    assert incident_task.status == "pending"

    # 2. Resolver claims the task and writes result
    res = await resolver.claim_and_resolve_task(context_acme, incident_task.id)
    assert res is not None
    assert res["status"] == "resolved"
    assert len(res["action_plan"]) > 0

    # 3. Verify task on board is now done
    task_after = board.repo.get_task(context_acme, incident_task.id)
    assert task_after.status == "done"
    assert task_after.result_json is not None
