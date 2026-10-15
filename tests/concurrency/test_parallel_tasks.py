"""Concurrency and race condition tests."""
import pytest
import asyncio
from app.tasks.task_board import TaskBoard
from app.memory.models import MemoryModel
from app.core.ids import memory_id
from app.core.hashing import memory_idempotency_key


@pytest.mark.asyncio
async def test_concurrent_lease_claiming(repo, context_acme):
    board = TaskBoard(repo=repo)
    task = board.post_task(context_acme, "RESOLVE_INCIDENT", "race-task-1", {"job": 1})

    results = []

    async def claim_worker(worker_id: str):
        c = board.claim_task(context_acme, task.id, worker_id, lease_seconds=15)
        results.append((worker_id, bool(c)))

    # Run 10 parallel claims
    await asyncio.gather(*[claim_worker(f"worker_{i}") for i in range(10)])

    winners = [w for w, won in results if won]
    assert len(winners) == 1, f"Expected exactly 1 claim winner, got {len(winners)}"


@pytest.mark.asyncio
async def test_concurrent_memory_version_updates(repo, context_acme):
    mid = memory_id("semantic", "acme", "fact", "concurrency version test")
    idemp = memory_idempotency_key("acme", "src1", "semantic", "fact", "concurrency version test", "v1")

    mem = MemoryModel(
        id=mid,
        tenant_id="acme",
        memory_type="semantic",
        subtype="fact",
        title="concurrency version test",
        summary="Initial version statement",
        idempotency_key=idemp
    )
    repo.save_memory(context_acme, mem)

    # Attempt concurrent updates with expected_version=1
    success_count = 0
    conflict_count = 0

    def update_task(status_label: str):
        nonlocal success_count, conflict_count
        try:
            repo.update_memory_status(
                context_acme, mid, new_status=status_label, expected_version=1
            )
            success_count += 1
        except Exception:
            conflict_count += 1

    # Run updates in parallel threads
    await asyncio.gather(
        asyncio.to_thread(update_task, "superseded"),
        asyncio.to_thread(update_task, "expired")
    )

    # Exactly one CAS update must succeed
    assert success_count == 1
    assert conflict_count == 1
