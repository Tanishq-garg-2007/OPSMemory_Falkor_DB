"""Unit tests for memory lifecycle: creation, deduplication, supersession, deletion."""
import pytest
from app.memory.lifecycle import MemoryLifecycle
from app.dependencies import TenantContext


def test_memory_creation_and_idempotency(repo, context_acme):
    lifecycle = MemoryLifecycle(repo=repo)
    m1 = lifecycle.store_memory(
        context=context_acme,
        memory_type="semantic",
        subtype="fact",
        title="auth-service port 8080",
        summary="auth-service listens on port 8080",
        entity_names=["auth-service"],
        confidence_basis="user_explicit"
    )
    assert m1.id is not None
    assert m1.status == "active"

    # Duplicate creation with same data must return existing
    m2 = lifecycle.store_memory(
        context=context_acme,
        memory_type="semantic",
        subtype="fact",
        title="auth-service port 8080",
        summary="auth-service listens on port 8080",
        entity_names=["auth-service"],
        confidence_basis="user_explicit"
    )
    assert m1.id == m2.id
    assert m1.idempotency_key == m2.idempotency_key


def test_temporal_supersession(repo, context_acme):
    lifecycle = MemoryLifecycle(repo=repo)

    # 1. Store old version
    m_old = lifecycle.store_memory(
        context=context_acme,
        memory_type="semantic",
        subtype="fact",
        title="payments-api version v2.0",
        summary="payments-api current version is v2.0",
        entity_names=["payments-api"],
        confidence_basis="user_explicit"
    )
    assert m_old.status == "active"

    # 2. Store updated version with correction
    m_new = lifecycle.store_memory(
        context=context_acme,
        memory_type="semantic",
        subtype="fact",
        title="payments-api version v2.1",
        summary="payments-api current version is v2.1",
        entity_names=["payments-api"],
        confidence_basis="user_correction"
    )
    assert m_new.status == "active"

    # 3. Check old memory is now superseded
    refreshed_old = repo.get_memory(context_acme, m_old.id)
    assert refreshed_old.status == "superseded"
    assert refreshed_old.valid_to is not None
    assert refreshed_old.superseded_by == m_new.id


def test_deletion_removes_from_fts(repo, context_acme):
    lifecycle = MemoryLifecycle(repo=repo)
    m = lifecycle.store_memory(
        context=context_acme,
        memory_type="episodic",
        subtype="incident",
        title="Test unique deletion keyword xyz987",
        summary="Outage occurred due to unique deletion keyword xyz987",
        entity_names=["payments-api"]
    )
    # Search FTS should find it
    fts_res = repo.search_fts(context_acme, "xyz987")
    assert len(fts_res) > 0

    # Soft delete
    lifecycle.forget_memory(context_acme, m.id, hard_delete=False)
    mem_after = repo.get_memory(context_acme, m.id)
    assert mem_after.status == "deleted"

    # Search FTS should not find it
    fts_res_after = repo.search_fts(context_acme, "xyz987")
    assert len(fts_res_after) == 0
