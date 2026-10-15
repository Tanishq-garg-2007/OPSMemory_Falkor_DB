"""Unit tests for core utilities: hashing, IDs, time, cache, concurrency."""
import time
from app.core.hashing import slugify, memory_idempotency_key, task_idempotency_key
from app.core.ids import entity_id, memory_id, task_id, source_id
from app.core.time import utc_now_iso, parse_iso, is_past
from app.core.cache import TenantVersionedCache


def test_slugify():
    assert slugify("Payments API v2.4!") == "payments-api-v24"
    assert slugify("  Auth_Service  ") == "auth-service"


def test_idempotency_keys():
    k1 = memory_idempotency_key("acme", "src1", "semantic", "fact", "Title One", "Statement")
    k2 = memory_idempotency_key("acme", "src1", "semantic", "fact", "title one", "statement")
    assert k1 == k2

    t1 = task_idempotency_key("acme", "RESOLVE_INCIDENT", "target1", 1)
    t2 = task_idempotency_key("acme", "RESOLVE_INCIDENT", "target1", 1)
    assert t1 == t2


def test_id_generators():
    eid = entity_id("service", "payments-api")
    assert eid == "ent_service_payments-api"

    mid = memory_id("semantic", "acme", "fact", "current version")
    assert mid.startswith("mem_semantic_acme_fact_")


def test_time_parsing():
    iso_str = utc_now_iso()
    dt = parse_iso(iso_str)
    assert dt is not None
    assert is_past("2020-01-01T00:00:00Z") is True
    assert is_past("2099-01-01T00:00:00Z") is False


def test_tenant_versioned_cache():
    cache = TenantVersionedCache(default_ttl_seconds=5.0)
    cache.set("acme", "key1", "val1")
    assert cache.get("acme", "key1") == "val1"
    assert cache.get("beta", "key1") is None

    # Invalidate tenant
    cache.invalidate_tenant("acme")
    assert cache.get("acme", "key1") is None
