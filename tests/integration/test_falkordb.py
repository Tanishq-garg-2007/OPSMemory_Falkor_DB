"""Integration tests for FalkorDB as the single source of truth (requires a running FalkorDB)."""
import pytest
from app.config import Settings
from app.errors import DatabaseUnavailableError
from app.memory.repository import MemoryRepository
from app.memory.models import EntityModel, MemoryModel
from app.core.ids import entity_id, memory_id


def _unreachable_repo() -> MemoryRepository:
    # Port 1 is never a FalkorDB; connect fails fast.
    return MemoryRepository(settings=Settings(
        REAL_LLM=0, LLM_PROVIDER="mock",
        FALKORDB_HOST="127.0.0.1", FALKORDB_PORT=1, FALKORDB_TIMEOUT_SECONDS=0.5,
    ))


def test_health_reports_native_falkordb(repo):
    health = repo.check_health()
    assert health["ok"] is True
    assert health["mode"] == "falkordb_native"
    assert "sqlite" not in health


def test_entity_roundtrip_lives_in_graph(repo, context_acme):
    ent = EntityModel(
        id=entity_id("service", "test-resilience", tenant_id="acme"),
        kind="service", name="test-resilience", tenant_id="acme",
    )
    saved = repo.upsert_entity(context_acme, ent)
    assert saved.id == ent.id and saved.version == 1
    assert repo.upsert_entity(context_acme, ent).version == 2

    # The node is physically in the tenant graph (no secondary store exists).
    graph = repo.graph_for(context_acme)
    res = graph.query("MATCH (e:Entity {id: $id}) RETURN e.name", {"id": ent.id})
    assert res.result_set[0][0] == "test-resilience"


def test_no_sqlite_artifacts_in_repository(repo):
    assert not hasattr(repo, "_get_sqlite_con")
    assert not hasattr(repo, "db_path")


def test_valid_to_survives_status_update_without_valid_to(repo, context_acme):
    mem = MemoryModel(
        id=memory_id("semantic", "acme", "fact", "valid-to keeps value"),
        tenant_id="acme", memory_type="semantic", subtype="fact",
        title="valid-to keeps value", summary="s", valid_to="2030-01-01T00:00:00Z",
        idempotency_key="idem-valid-to",
    )
    repo.save_memory(context_acme, mem)
    updated = repo.update_memory_status(context_acme, mem.id, "conflicted")
    assert updated.status == "conflicted"
    assert updated.valid_to == "2030-01-01T00:00:00Z"


def test_unreachable_falkordb_gives_503_not_silent_fallback(context_acme):
    repo = _unreachable_repo()
    assert repo.check_health()["ok"] is False
    with pytest.raises(DatabaseUnavailableError) as exc:
        repo.list_memories(context_acme)
    assert exc.value.status_code == 503
    with pytest.raises(DatabaseUnavailableError):
        repo.save_memory(context_acme, MemoryModel(
            id="mem_x", tenant_id="acme", memory_type="semantic", subtype="fact",
            title="t", summary="s", idempotency_key="k",
        ))


def test_invalid_relationship_type_rejected(repo, context_acme):
    from app.errors import ValidationError
    with pytest.raises(ValidationError):
        repo.add_relationship(context_acme, "ent_a", "ent_b", "X]->() DETACH DELETE n //")