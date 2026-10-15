"""Auth regression tests: admin protection, no fake tenant keys, strict tenant ids."""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.config import get_settings
from app.memory.repository import get_memory_repository

ADMIN = {"X-Admin-Key": "test-admin-key"}


@pytest.fixture
async def client():
    get_settings().ADMIN_API_KEY = "test-admin-key"
    repo = get_memory_repository()
    repo.register_tenant("acme", "key_acme_secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_admin_requires_key(client):
    assert (await client.post("/v1/admin/reset?tenant_id=acme")).status_code == 401
    assert (await client.post("/v1/admin/reset?tenant_id=acme", headers={"X-Admin-Key": "nope"})).status_code == 401
    # A valid *tenant* key must not grant admin access
    assert (await client.post("/v1/admin/reset?tenant_id=acme", headers={"X-Tenant-Key": "key_acme_secret"})).status_code == 401


async def test_admin_disabled_when_not_configured(client):
    get_settings().ADMIN_API_KEY = None
    r = await client.post("/v1/admin/seed?tenant_id=acme", headers=ADMIN)
    assert r.status_code == 403


async def test_admin_rejects_bad_tenant_id(client):
    r = await client.post("/v1/admin/reset?tenant_id=Acme.Corp", headers=ADMIN)
    assert r.status_code == 422


@pytest.mark.parametrize("key", [
    "tenant_key_victimcorp", "test_competitor_key", "tenant_key_", "dev-key-acme", "test_acme_key", "",
])
async def test_fake_tenant_keys_rejected(client, key):
    r = await client.get("/v1/graph/context", headers={"X-Tenant-Key": key})
    assert r.status_code == 401


async def test_registered_key_accepted(client):
    r = await client.get("/v1/graph/context", headers={"X-Tenant-Key": "key_acme_secret"})
    assert r.status_code == 200


@pytest.mark.parametrize("bad", ["acme-corp", "Acme", "acme corp", "Acme.Corp", "", "a" * 49])
def test_tenant_graph_name_is_strict(bad):
    with pytest.raises(ValueError):
        get_settings().tenant_graph_name(bad)


def test_tenant_graph_names_do_not_collide():
    s = get_settings()
    assert s.tenant_graph_name("acme") == "tenant_acme"
    assert s.tenant_graph_name("acme_corp") != s.tenant_graph_name("acmecorp")


async def test_auth_returns_503_when_falkordb_down(client, monkeypatch):
    from app.errors import DatabaseUnavailableError
    repo = get_memory_repository()

    def boom():
        raise DatabaseUnavailableError("down")
    monkeypatch.setattr(repo, "_client", boom)
    r = await client.get("/v1/graph/context", headers={"X-Tenant-Key": "key_acme_secret"})
    assert r.status_code == 503