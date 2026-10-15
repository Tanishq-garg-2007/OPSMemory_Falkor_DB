"""Security tests for strict tenant boundary enforcement."""
import pytest
from app.dependencies import TenantContext
from app.errors import TenantIsolationError
from app.memory.models import EntityModel
from app.core.ids import entity_id


def test_tenant_context_boundary_assertion(context_acme):
    # Context must raise TenantIsolationError if asked to assert on another tenant
    with pytest.raises(TenantIsolationError):
        context_acme.assert_same_tenant("beta")

    # Succeeds on matching tenant
    context_acme.assert_same_tenant("acme")


def test_repository_tenant_isolation(repo, context_acme, context_beta):
    # Create entity in Acme
    ent_acme = EntityModel(
        id=entity_id("service", "acme-internal-service"),
        kind="service",
        name="acme-internal-service",
        tenant_id="acme"
    )
    repo.upsert_entity(context_acme, ent_acme)

    # Beta context must not be able to retrieve Acme's entity
    retrieved = repo.get_entity(context_beta, ent_acme.id)
    assert retrieved is None

    # Beta listing entities must not include Acme's entity
    beta_entities = repo.list_entities(context_beta)
    assert not any(e.id == ent_acme.id for e in beta_entities)


def test_cross_tenant_upsert_blocked(repo, context_acme):
    # Trying to save an entity with tenant_id="beta" using context_acme must fail
    ent_mismatch = EntityModel(
        id=entity_id("service", "mismatch-service"),
        kind="service",
        name="mismatch-service",
        tenant_id="beta"
    )
    with pytest.raises(TenantIsolationError):
        repo.upsert_entity(context_acme, ent_mismatch)
