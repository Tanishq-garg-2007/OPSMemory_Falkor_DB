"""Unit tests for task board, leases, idempotency, and recovery."""
from app.tasks.task_board import TaskBoard
from app.core.time import utc_now_iso


def test_task_idempotency(repo, context_acme):
    board = TaskBoard(repo=repo)
    t1 = board.post_task(context_acme, "RESOLVE_INCIDENT", "target-A", {"key": "val"})
    t2 = board.post_task(context_acme, "RESOLVE_INCIDENT", "target-A", {"key": "val"})
    assert t1.id == t2.id
    assert t1.idempotency_key == t2.idempotency_key


def test_lease_claiming_and_completion(repo, context_acme):
    board = TaskBoard(repo=repo)
    task = board.post_task(context_acme, "RESOLVE_INCIDENT", "target-B", {"item": "data"})
    assert task.status == "pending"

    # Worker 1 claims
    claimed = board.claim_task(context_acme, task.id, "worker_1", lease_seconds=10)
    assert claimed is not None
    assert claimed.status == "claimed"
    assert claimed.lease_owner == "worker_1"

    # Worker 2 tries to claim same task -> should fail (return None)
    contested = board.claim_task(context_acme, task.id, "worker_2", lease_seconds=10)
    assert contested is None

    # Worker 1 completes
    done = board.complete_task(context_acme, task.id, "worker_1", {"resolution": "ok"})
    assert done.status == "done"
    assert done.lease_owner is None
