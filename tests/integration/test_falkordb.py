"""Integration tests for FalkorDB persistence and graceful degradation."""
import pytest
from app.config import Settings
from app.memory.repository import MemoryRepository
from app.dependencies import TenantContext
from app.memory.models import EntityModel
from app.core.ids import entity_id


def test_falkordb_graceful_degradation(test_settings, context_acme):
    """Verify repository detects connection state and handles unavailability gracefully."""
    repo = MemoryRepository(settings=test_settings)
    health = repo.check_health()
    assert health["ok"] is True
    assert "mode" in health

    # Ensure writing and reading entities succeeds gracefully even if FalkorDB port is offline
    ent = EntityModel(
        id=entity_id("service", "test-resilience"),
        kind="service",
        name="test-resilience",
        tenant_id=context_acme.tenant_id
    )
    saved = repo.upsert_entity(context_acme, ent)
    assert saved.id == ent.id

    retrieved = repo.get_entity(context_acme, ent.id)
    assert retrieved is not None
    assert retrieved.name == "test-resilience"


def test_real_falkordb_or_blocked(test_settings, context_acme):
    """Explicitly verify real FalkorDB if connected, otherwise record as environment-blocked."""
    repo = MemoryRepository(settings=test_settings)
    health = repo.check_health()
    if not health.get("falkordb_connected"):
        pytest.skip("ENVIRONMENT-BLOCKED: Real FalkorDB service is not reachable on localhost:6379 (Docker daemon offline)")

    # If connected to real FalkorDB, execute live Cypher test
    graph = repo._falkor_client.select_graph(context_acme.graph_name)
    res = graph.query("RETURN 1 as val")
    assert len(res.result_set) == 1
