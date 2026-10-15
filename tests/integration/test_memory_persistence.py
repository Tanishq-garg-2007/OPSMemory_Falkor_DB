"""Integration test: Memory survives repository reinitialization and genuine restart."""
from app.memory.repository import MemoryRepository
from app.memory.models import MemoryModel
from app.core.ids import memory_id
from app.core.hashing import memory_idempotency_key


def test_persistence_survives_restart(test_settings, context_acme):
    # Step 1: Open repository session 1 and write memory
    repo_1 = MemoryRepository(settings=test_settings)
    mid = memory_id("semantic", context_acme.tenant_id, "fact", "restart survival fact")
    idemp = memory_idempotency_key(context_acme.tenant_id, "direct", "semantic", "fact", "restart survival fact", "test")

    mem = MemoryModel(
        id=mid,
        tenant_id=context_acme.tenant_id,
        memory_type="semantic",
        subtype="fact",
        title="restart survival fact",
        summary="This fact must survive complete process restart.",
        idempotency_key=idemp,
        entities=["payments-api"]
    )
    repo_1.save_memory(context_acme, mem)
    del repo_1

    # Step 2: Open brand-new repository session 2 on the exact same database file
    repo_2 = MemoryRepository(settings=test_settings)
    retrieved = repo_2.get_memory(context_acme, mid)

    assert retrieved is not None
    assert retrieved.title == "restart survival fact"
    assert retrieved.summary == "This fact must survive complete process restart."
    assert "payments-api" in retrieved.entities
