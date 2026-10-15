"""Security tests for memory isolation between tenants."""
import pytest
from app.memory.models import MemoryModel
from app.errors import TenantIsolationError
from app.core.ids import memory_id
from app.core.hashing import memory_idempotency_key


def test_memory_tenant_isolation(repo, context_acme, context_beta):
    mid = memory_id("semantic", "acme", "fact", "acme-isolated-fact")
    idemp = memory_idempotency_key("acme", "src1", "semantic", "fact", "acme-isolated-fact", "data")

    mem_acme = MemoryModel(
        id=mid,
        tenant_id="acme",
        memory_type="semantic",
        subtype="fact",
        title="acme-isolated-fact",
        summary="Confidential Acme technical specification.",
        idempotency_key=idemp
    )
    repo.save_memory(context_acme, mem_acme)

    # Beta cannot retrieve it
    beta_mem = repo.get_memory(context_beta, mid)
    assert beta_mem is None

    # Saving cross-tenant memory raises TenantIsolationError
    with pytest.raises(TenantIsolationError):
        repo.save_memory(context_beta, mem_acme)
