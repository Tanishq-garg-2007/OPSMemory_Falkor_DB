"""Hold-out fixtures: a tenant ("gamma") with services, versions, owners and incidents that appear nowhere
in the acme/beta benchmark, its mock LLM special cases or the fusion/retrieval code.

Purpose: show whether OpsMemory generalises beyond the 88-question benchmark it was developed against.
Questions live in eval/dataset/holdout_questions.jsonl. Do not tune the code against these.
"""
from typing import Dict, Optional
from app.dependencies import TenantContext
from app.memory.repository import MemoryRepository, get_memory_repository
from app.memory.models import EntityModel, MemoryModel, SourceModel
from app.core.ids import entity_id, memory_id, source_id
from app.core.hashing import memory_idempotency_key
from app.core.time import utc_now_iso

HOLDOUT_TENANT = "gamma"

_SERVICES = [
    ("billing-gateway", "Gateway that authorises and captures customer charges"),
    ("ledger-db", "Primary double-entry ledger database"),
    ("notification-svc", "Sends email and push notifications from a message queue"),
    ("search-index", "Product search index cluster"),
    ("fraud-engine", "Real-time transaction risk scoring service"),
]
_EDGES = [  # (from, to): from DEPENDS_ON to
    ("notification-svc", "billing-gateway"),
    ("billing-gateway", "ledger-db"),
    ("billing-gateway", "fraud-engine"),
]

# (key, subtype, memory_type, title, summary, status, confidence, valid_from, valid_to, entities, supersedes_key)
_MEMORIES = [
    ("gw_old", "fact", "semantic", "billing-gateway version v3.0",
     "billing-gateway ran v3.0 until early October, then it was replaced by v3.1 and is no longer the live version.",
     "superseded", 0.9, "2026-09-20T00:00:00Z", "2026-10-05T09:00:00Z", ["billing-gateway"], None),
    ("gw_new", "fact", "semantic", "billing-gateway current version is v3.1",
     "billing-gateway current production version is v3.1, released to fix the notification backlog caused by v3.0.",
     "active", 0.85, "2026-10-05T09:00:00Z", None, ["billing-gateway"], "gw_old"),
    ("ledger_owner", "fact", "semantic", "ledger-db ownership",
     "ledger-db is owned and operated by Team Atlas.",
     "active", 0.95, "2026-06-01T00:00:00Z", None, ["ledger-db"], None),
    ("search_ver", "fact", "semantic", "search-index current version is v7.2",
     "search-index runs version v7.2 and is owned by Team Discovery.",
     "active", 0.9, "2026-08-15T00:00:00Z", None, ["search-index"], None),
    ("inc204", "incident", "episodic", "Incident inc-204: notification delays after billing-gateway upgrade",
     "Customers received notifications hours late on 2026-10-03 after billing-gateway moved to v3.0, because the notification queue backed up.",
     "active", 0.9, "2026-10-03T08:00:00Z", None, ["notification-svc", "billing-gateway"], None),
    ("dec204", "decision", "episodic", "Decision: cap notification consumers at 4 after inc-204",
     "After inc-204 the team decided to cap notification-svc consumer concurrency at 4 and to upgrade billing-gateway to v3.1.",
     "active", 0.9, "2026-10-05T10:00:00Z", None, ["notification-svc", "billing-gateway"], None),
    ("failover", "runbook", "procedural", "Failover procedure for ledger-db",
     "Step 1: pause writers. Step 2: promote the standby replica. Step 3: update the connection string in billing-gateway. Step 4: confirm replication lag is zero.",
     "active", 0.9, "2026-07-01T00:00:00Z", None, ["ledger-db", "billing-gateway"], None),
    ("freeze", "policy", "semantic", "Friday change freeze",
     "Production deployments are frozen every Friday from 16:00 UTC until Monday 06:00 UTC.",
     "active", 0.95, "2026-05-01T00:00:00Z", None, [], None),
    ("pref", "preference", "semantic", "Mateo preference detailed timelines",
     "User Mateo prefers detailed minute-by-minute timelines in incident reviews.",
     "active", 0.8, "2026-09-10T00:00:00Z", None, [], None),
]


def seed_holdout_fixtures(context: TenantContext, repo: Optional[MemoryRepository] = None) -> Dict[str, int]:
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
        id=source_id("conv_seed", "msg_seed_gamma"), source_type="seed", conversation_id="conv_seed",
        message_id="msg_seed_gamma", tenant_id=tenant, created_at=now,
        raw_text_ref="Gamma hold-out tenant seed documentation.",
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