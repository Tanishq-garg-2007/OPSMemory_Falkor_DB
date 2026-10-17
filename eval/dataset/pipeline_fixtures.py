"""Pipeline fixtures: a novel tenant family ("delta_001", "delta_002", ...) whose services, versions,
owners, incidents, runbooks and policies appear nowhere in the acme/beta benchmark or the gamma hold-out.

Purpose: exercise the ENTIRE pipeline (extraction -> storage/supersession -> retrieval) end to end,
including write-path assertions (memories created / superseded / tasks) that the answer-only benchmarks
cannot observe. Questions live in eval/dataset/pipeline_questions.jsonl.

Each test case gets its own isolated tenant (delta_001 .. delta_100) seeded with the same baseline below,
so cases never share state and remain deterministic. Do not tune the application code against these.
"""
from typing import Dict, Optional
from app.dependencies import TenantContext
from app.memory.repository import MemoryRepository, get_memory_repository
from app.memory.models import EntityModel, MemoryModel, SourceModel
from app.core.ids import entity_id, memory_id, source_id
from app.core.hashing import memory_idempotency_key
from app.core.time import utc_now_iso

PIPELINE_TENANT_PREFIX = "delta"


def pipeline_tenant(index: int) -> str:
    """Stable per-case tenant id, e.g. pipeline_tenant(7) -> 'delta_007'."""
    return f"{PIPELINE_TENANT_PREFIX}_{index:03d}"


_SERVICES = [
    ("catalog-svc", "Product catalog read and write service"),
    ("orders-db", "Primary order ledger database"),
    ("shipping-svc", "Shipment orchestration and carrier dispatch"),
    ("pricing-engine", "Dynamic pricing and discount computation"),
    ("returns-svc", "Customer returns and refunds workflow service"),
]
_EDGES = [  # (from, to): from DEPENDS_ON to
    ("shipping-svc", "catalog-svc"),
    ("catalog-svc", "orders-db"),
    ("catalog-svc", "pricing-engine"),
    ("returns-svc", "orders-db"),
]

# (key, subtype, memory_type, title, summary, status, confidence, valid_from, valid_to, entities, supersedes_key)
_MEMORIES = [
    ("cat_old", "fact", "semantic", "catalog-svc version v4.0",
     "catalog-svc ran v4.0 during September and is no longer the live version.",
     "superseded", 0.9, "2026-09-01T00:00:00Z", "2026-09-25T09:00:00Z", ["catalog-svc"], None),
    ("cat_new", "fact", "semantic", "catalog-svc current version is v4.1",
     "catalog-svc current production version is v4.1, released after the catalog caching fix.",
     "active", 0.85, "2026-09-25T09:00:00Z", None, ["catalog-svc"], "cat_old"),
    ("price_ver", "fact", "semantic", "pricing-engine current version is v2.2",
     "pricing-engine runs version v2.2 and computes promotional discounts.",
     "active", 0.9, "2026-08-10T00:00:00Z", None, ["pricing-engine"], None),
    ("ship_ver", "fact", "semantic", "shipping-svc current version is v1.9",
     "shipping-svc runs version v1.9 and orchestrates carrier dispatch.",
     "active", 0.9, "2026-08-12T00:00:00Z", None, ["shipping-svc"], None),
    ("orders_owner", "fact", "semantic", "orders-db ownership",
     "orders-db is owned and operated by Team Beacon.",
     "active", 0.95, "2026-06-01T00:00:00Z", None, ["orders-db"], None),
    ("returns_owner", "fact", "semantic", "returns-svc ownership",
     "returns-svc is owned and operated by Team Comet.",
     "active", 0.9, "2026-06-01T00:00:00Z", None, ["returns-svc"], None),
    ("inc770", "incident", "episodic", "Incident inc-770: shipping delays after catalog-svc upgrade",
     "Customers saw shipping delays on 2026-09-18 after catalog-svc moved to v4.0 while the shipping queue backed up.",
     "active", 0.9, "2026-09-18T08:00:00Z", None, ["shipping-svc", "catalog-svc"], None),
    ("dec770", "decision", "episodic", "Decision: raise shipping-svc retry budget after inc-770",
     "After inc-770 the team decided to raise shipping-svc carrier retry attempts to five.",
     "active", 0.9, "2026-09-19T10:00:00Z", None, ["shipping-svc"], None),
    ("runbook_orders", "runbook", "procedural", "Failover procedure for orders-db",
     "Step 1: pause catalog writers. Step 2: promote the standby replica. Step 3: repoint catalog-svc. Step 4: confirm replication lag is zero.",
     "active", 0.9, "2026-07-01T00:00:00Z", None, ["orders-db", "catalog-svc"], None),
    ("freeze", "policy", "semantic", "Month-end change freeze",
     "Production deployments are frozen from the 28th of each month until the 2nd of the next month.",
     "active", 0.95, "2026-05-01T00:00:00Z", None, [], None),
    ("pref_nadia", "preference", "semantic", "Nadia preference concise summaries",
     "User Nadia prefers concise summaries with direct bullet points in incident reviews.",
     "active", 0.8, "2026-09-10T00:00:00Z", None, [], None),
]


def seed_pipeline_fixtures(context: TenantContext, repo: Optional[MemoryRepository] = None) -> Dict[str, int]:
    r = repo or get_memory_repository()
    now = utc_now_iso()
    tenant = context.tenant_id

    for name, desc in _SERVICES:
        r.upsert_entity(context, EntityModel(
            id=entity_id("service", name, tenant_id=tenant), kind="service", name=name,
            aliases=[name.replace("-", " ")], description=desc, tenant_id=tenant,
            created_at=now, updated_at=now,
        ))
    for src_name, dst_name in _EDGES:
        r.add_relationship(context, entity_id("service", src_name, tenant_id=tenant),
                           entity_id("service", dst_name, tenant_id=tenant), "DEPENDS_ON")

    src = SourceModel(
        id=source_id("conv_seed", "msg_seed_delta"), source_type="seed", conversation_id="conv_seed",
        message_id="msg_seed_delta", tenant_id=tenant, created_at=now,
        raw_text_ref="Delta pipeline tenant seed documentation.",
    )
    r.save_source(context, src)

    ids: Dict[str, str] = {}
    for key, subtype, mtype, title, summary, status, conf, vfrom, vto, ents, sup in _MEMORIES:
        mid = memory_id(mtype, tenant, subtype, title)
        ids[key] = mid
        r.save_memory(context, MemoryModel(
            id=mid, tenant_id=tenant, memory_type=mtype, subtype=subtype, title=title, summary=summary,
            status=status, confidence=conf, valid_from=vfrom, valid_to=vto, observed_at=vfrom,
            created_at=vfrom, updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src.id, mtype, subtype, title, summary[:40]),
            entities=ents, source_id=src.id, supersedes_id=ids.get(sup) if sup else None,
        ))
    return {"entities": len(_SERVICES), "memories": len(_MEMORIES), "tasks": 0}
