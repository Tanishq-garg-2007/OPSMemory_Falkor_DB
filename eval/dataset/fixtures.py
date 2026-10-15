"""Deterministic fixture seeding for Acme and Beta tenants."""
from typing import Dict, Any, Optional
from app.dependencies import TenantContext
from app.memory.repository import MemoryRepository, get_memory_repository
from app.memory.models import EntityModel, MemoryModel, SourceModel, TaskModel
from app.core.ids import entity_id, memory_id, source_id, task_id
from app.core.hashing import memory_idempotency_key, task_idempotency_key
from app.core.time import utc_now_iso


def seed_fixtures_for_tenant(context: TenantContext, repo: Optional[MemoryRepository] = None) -> Dict[str, int]:
    r = repo or get_memory_repository()
    now = utc_now_iso()
    tenant = context.tenant_id

    entities_count = 0
    memories_count = 0
    tasks_count = 0

    if tenant == "acme":
        # 1. Services
        services = [
            ("checkout-ui", "Frontend checkout user interface"),
            ("payments-api", "Payment processing and payment gateway service"),
            ("auth-service", "Authentication and token verification service"),
            ("postgres-orders", "Primary PostgreSQL transactional database for customer orders"),
            ("payments-worker", "Background asynchronous batch worker for scheduled payments")
        ]
        for name, desc in services:
            ent = EntityModel(
                id=entity_id("service", name, tenant_id=tenant),
                kind="service",
                name=name,
                aliases=[name.replace("-", " ")],
                description=desc,
                tenant_id=tenant,
                created_at=now,
                updated_at=now
            )
            r.upsert_entity(context, ent)
            entities_count += 1

        # 2. Dependency edges
        # checkout-ui -> payments-api, auth-service
        r.add_relationship(context, entity_id("service", "checkout-ui", tenant_id=tenant), entity_id("service", "payments-api", tenant_id=tenant), "DEPENDS_ON")
        r.add_relationship(context, entity_id("service", "checkout-ui", tenant_id=tenant), entity_id("service", "auth-service", tenant_id=tenant), "DEPENDS_ON")
        # payments-api -> postgres-orders
        r.add_relationship(context, entity_id("service", "payments-api", tenant_id=tenant), entity_id("service", "postgres-orders", tenant_id=tenant), "DEPENDS_ON")

        # 3. Source
        src_seed = SourceModel(
            id=source_id("conv_seed", "msg_seed_acme"),
            source_type="seed",
            conversation_id="conv_seed",
            message_id="msg_seed_acme",
            tenant_id=tenant,
            created_at=now,
            raw_text_ref="Acme production topology and runbook seed documentation."
        )
        r.save_source(context, src_seed)

        # 4. Old superseded fact: payments-api v2.3
        old_mem_id = memory_id("semantic", tenant, "fact", "payments-api version v2.3")
        old_fact = MemoryModel(
            id=old_mem_id,
            tenant_id=tenant,
            memory_type="semantic",
            subtype="fact",
            title="payments-api version v2.3",
            summary="payments-api version was previously v2.3 during the October release, which is now superseded by v2.4 and no longer active.",
            status="superseded",
            confidence=0.85,
            valid_from="2026-09-01T00:00:00Z",
            valid_to="2026-10-01T12:00:00Z",
            observed_at="2026-09-01T00:00:00Z",
            created_at="2026-09-01T00:00:00Z",
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_seed.id, "semantic", "fact", "payments-api version v2.3", "v2.3"),
            entities=["payments-api"],
            source_id=src_seed.id
        )
        r.save_memory(context, old_fact)
        memories_count += 1

        # 5. Current corrected fact: payments-api current version is v2.4
        curr_mem_id = memory_id("semantic", tenant, "fact", "payments-api current version is v2.4")
        curr_fact = MemoryModel(
            id=curr_mem_id,
            tenant_id=tenant,
            memory_type="semantic",
            subtype="fact",
            title="payments-api current version is v2.4",
            summary="payments-api current production version is v2.4, following the post-incident stabilization release.",
            status="active",
            confidence=0.95,
            valid_from="2026-10-01T12:00:00Z",
            valid_to=None,
            observed_at=now,
            created_at=now,
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_seed.id, "semantic", "fact", "payments-api current version is v2.4", "v2.4"),
            entities=["payments-api"],
            source_id=src_seed.id,
            supersedes_id=old_mem_id
        )
        r.save_memory(context, curr_fact)
        memories_count += 1

        # 6. Service Ownership
        owner_fact = MemoryModel(
            id=memory_id("semantic", tenant, "fact", "auth-service owned by Team Identity"),
            tenant_id=tenant,
            memory_type="semantic",
            subtype="fact",
            title="auth-service ownership",
            summary="auth-service is owned and maintained by Team Identity.",
            status="active",
            confidence=0.90,
            valid_from="2026-01-01T00:00:00Z",
            valid_to=None,
            observed_at=now,
            created_at=now,
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_seed.id, "semantic", "fact", "auth-service owned by Team Identity", "Team Identity"),
            entities=["auth-service"],
            source_id=src_seed.id
        )
        r.save_memory(context, owner_fact)
        memories_count += 1

        # 7. User Preference
        pref_mem = MemoryModel(
            id=memory_id("semantic", tenant, "preference", "user Priya prefers concise summaries"),
            tenant_id=tenant,
            memory_type="semantic",
            subtype="preference",
            title="Priya preference concise summaries",
            summary="User Priya prefers concise summaries with direct bullet points during incident reviews.",
            status="active",
            confidence=0.95,
            valid_from="2026-02-01T00:00:00Z",
            valid_to=None,
            observed_at=now,
            created_at=now,
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_seed.id, "semantic", "preference", "user Priya prefers concise summaries", "concise summaries"),
            entities=["priya", "payments-api"],
            source_id=src_seed.id
        )
        r.save_memory(context, pref_mem)
        memories_count += 1

        # 8. Escalation rule
        escala_mem = MemoryModel(
            id=memory_id("procedural", tenant, "escalation", "escalate payment incidents after 30 minutes"),
            tenant_id=tenant,
            memory_type="procedural",
            subtype="escalation_rule",
            title="Payment Incident Escalation Rule",
            summary="Escalate payment incidents to the engineering VP and payments on-call lead after 30 minutes if unresolved.",
            status="active",
            confidence=0.90,
            valid_from="2026-01-01T00:00:00Z",
            valid_to=None,
            observed_at=now,
            created_at=now,
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_seed.id, "procedural", "escalation", "escalate payment incidents after 30 minutes", "30 minutes"),
            entities=["payments-api"],
            source_id=src_seed.id
        )
        r.save_memory(context, escala_mem)
        memories_count += 1

        # 9. Maintenance window
        maint_mem = MemoryModel(
            id=memory_id("semantic", tenant, "policy", "maintenance window Sundays 02:00-04:00 UTC"),
            tenant_id=tenant,
            memory_type="semantic",
            subtype="fact",
            title="Acme Production Maintenance Window",
            summary="Standard production maintenance window is scheduled on Sundays between 02:00 and 04:00 UTC.",
            status="active",
            confidence=0.90,
            valid_from="2026-01-01T00:00:00Z",
            valid_to=None,
            observed_at=now,
            created_at=now,
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_seed.id, "semantic", "policy", "maintenance window Sundays 02:00-04:00 UTC", "Sundays"),
            entities=[],
            source_id=src_seed.id
        )
        r.save_memory(context, maint_mem)
        memories_count += 1

        # 10. Episodic Incident: inc-101
        inc_mem = MemoryModel(
            id=memory_id("episodic", tenant, "incident", "inc-101 checkout failure"),
            tenant_id=tenant,
            memory_type="episodic",
            subtype="incident",
            title="Incident inc-101: checkout failures after payments-api upgrade",
            summary="Checkout failures occurred on 2026-09-15 following payments-api upgrade to v2.3 due to connection pool exhaustion.",
            status="active",
            confidence=0.95,
            valid_from="2026-09-15T10:00:00Z",
            valid_to=None,
            observed_at="2026-09-15T10:00:00Z",
            created_at="2026-09-15T10:00:00Z",
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_seed.id, "episodic", "incident", "inc-101 checkout failure", "inc-101"),
            entities=["checkout-ui", "payments-api", "postgres-orders"],
            source_id=src_seed.id
        )
        r.save_memory(context, inc_mem)
        memories_count += 1

        # 11. Decision: rollback payments-api to v2.2 after inc-101
        dec_mem = MemoryModel(
            id=memory_id("episodic", tenant, "decision", "rollback payments-api to v2.2 after inc-101"),
            tenant_id=tenant,
            memory_type="episodic",
            subtype="decision",
            title="Decision: rollback payments-api to v2.2 after inc-101",
            summary="Engineering leadership decided to rollback payments-api to v2.2 after inc-101 to immediately restore customer checkout.",
            status="active",
            confidence=0.95,
            valid_from="2026-09-15T11:00:00Z",
            valid_to=None,
            observed_at="2026-09-15T11:00:00Z",
            created_at="2026-09-15T11:00:00Z",
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_seed.id, "episodic", "decision", "rollback payments-api to v2.2 after inc-101", "v2.2 rollback"),
            entities=["payments-api", "checkout-ui"],
            source_id=src_seed.id
        )
        r.save_memory(context, dec_mem)
        memories_count += 1

        # 12. Procedural Runbook: safe rollback procedure for payments-api
        rb_mem = MemoryModel(
            id=memory_id("procedural", tenant, "runbook", "safe rollback procedure for payments-api"),
            tenant_id=tenant,
            memory_type="procedural",
            subtype="runbook",
            title="Safe Rollback Procedure Runbook for payments-api",
            summary="Step 1: Set canary traffic to 0%. Step 2: Deploy previous stable tag via helm rollback payments-api. Step 3: Run database migration rollback check. Step 4: Validate health check on /healthz.",
            status="active",
            confidence=0.95,
            valid_from="2026-01-01T00:00:00Z",
            valid_to=None,
            observed_at=now,
            created_at=now,
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_seed.id, "procedural", "runbook", "safe rollback procedure for payments-api", "helm rollback"),
            entities=["payments-api"],
            source_id=src_seed.id
        )
        r.save_memory(context, rb_mem)
        memories_count += 1

        # 13. Unresolved Task: Migrate postgres-orders connection pool
        followup_task = TaskModel(
            id=task_id("RESOLVE_INCIDENT", "migrate-postgres-pool", version=1),
            tenant_id=tenant,
            task_type="RESOLVE_INCIDENT",
            status="pending",
            payload_json='{"action": "Migrate postgres-orders connection pool to pgbouncer", "priority": "high", "origin": "inc-101"}',
            idempotency_key=task_idempotency_key(tenant, "RESOLVE_INCIDENT", "migrate-postgres-pool", 1),
            created_at=now,
            updated_at=now
        )
        r.create_task(context, followup_task)
        tasks_count += 1

        # 14. Semantic fact: checkout-ui role and user interface
        checkout_ui_fact = MemoryModel(
            id=memory_id("semantic", tenant, "fact", "checkout-ui role and user interface"),
            tenant_id=tenant,
            memory_type="semantic",
            subtype="fact",
            title="checkout-ui role and user interface",
            summary="checkout-ui serves as the primary frontend checkout user interface for end-users, directly depending on auth-service and payments-api.",
            status="active",
            confidence=0.95,
            valid_from="2026-01-01T00:00:00Z",
            valid_to=None,
            observed_at=now,
            created_at=now,
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_seed.id, "semantic", "fact", "checkout-ui role and user interface", "frontend interface"),
            entities=["checkout-ui", "payments-api", "auth-service"],
            source_id=src_seed.id
        )
        r.save_memory(context, checkout_ui_fact)
        memories_count += 1

        # 15. Semantic fact: payments-worker batch worker role
        worker_fact = MemoryModel(
            id=memory_id("semantic", tenant, "fact", "payments-worker batch worker role"),
            tenant_id=tenant,
            memory_type="semantic",
            subtype="fact",
            title="payments-worker background worker role",
            summary="payments-worker is a separate background worker for scheduled batch payments, distinct from the synchronous payments-api.",
            status="active",
            confidence=0.95,
            valid_from="2026-01-01T00:00:00Z",
            valid_to=None,
            observed_at=now,
            created_at=now,
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_seed.id, "semantic", "fact", "payments-worker batch worker role", "batch worker"),
            entities=["payments-worker", "payments-api"],
            source_id=src_seed.id
        )
        r.save_memory(context, worker_fact)
        memories_count += 1

        # 16. Semantic fact: payments-api database dependency on postgres-orders
        db_fact = MemoryModel(
            id=memory_id("semantic", tenant, "fact", "payments-api relies on postgres-orders database"),
            tenant_id=tenant,
            memory_type="semantic",
            subtype="fact",
            title="payments-api database dependency on postgres-orders",
            summary="payments-api relies on postgres-orders as its primary PostgreSQL transactional database for order and payment data.",
            status="active",
            confidence=0.95,
            valid_from="2026-01-01T00:00:00Z",
            valid_to=None,
            observed_at=now,
            created_at=now,
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_seed.id, "semantic", "fact", "payments-api relies on postgres-orders database", "postgres-orders database"),
            entities=["payments-api", "postgres-orders", "checkout-ui"],
            source_id=src_seed.id
        )
        r.save_memory(context, db_fact)
        memories_count += 1

        # 17. Episodic fact: unresolved task on board following inc-101
        task_mem = MemoryModel(
            id=memory_id("episodic", tenant, "task", "unresolved postgres-orders pool migration task"),
            tenant_id=tenant,
            memory_type="episodic",
            subtype="task",
            title="Unresolved task on board: postgres-orders connection pool migration",
            summary="An active unresolved task exists on the task board following inc-101: migrate postgres-orders connection pool to pgbouncer for database stability.",
            status="active",
            confidence=0.95,
            valid_from="2026-09-15T12:00:00Z",
            valid_to=None,
            observed_at=now,
            created_at=now,
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_seed.id, "episodic", "task", "unresolved postgres-orders pool migration task", "pgbouncer"),
            entities=["postgres-orders", "payments-api"],
            source_id=src_seed.id
        )
        r.save_memory(context, task_mem)
        memories_count += 1

    elif tenant == "beta":
        # Beta Service with different version and owner
        b_service = EntityModel(
            id=entity_id("service", "payments-api", tenant_id=tenant),
            kind="service",
            name="payments-api",
            aliases=["beta payments"],
            description="Beta payments cluster",
            tenant_id=tenant,
            created_at=now,
            updated_at=now
        )
        r.upsert_entity(context, b_service)
        entities_count += 1

        src_beta = SourceModel(
            id=source_id("conv_seed", "msg_seed_beta"),
            source_type="seed",
            conversation_id="conv_seed",
            message_id="msg_seed_beta",
            tenant_id=tenant,
            created_at=now,
            raw_text_ref="Beta cluster seed documentation."
        )
        r.save_source(context, src_beta)

        # Beta version is v1.9, owner is Team Billing Beta
        b_mem_ver = MemoryModel(
            id=memory_id("semantic", tenant, "fact", "payments-api current version is v1.9"),
            tenant_id=tenant,
            memory_type="semantic",
            subtype="fact",
            title="payments-api current version is v1.9",
            summary="payments-api in Beta environment is currently running version v1.9.",
            status="active",
            confidence=0.90,
            valid_from="2026-05-01T00:00:00Z",
            valid_to=None,
            observed_at=now,
            created_at=now,
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_beta.id, "semantic", "fact", "payments-api current version is v1.9", "v1.9"),
            entities=["payments-api"],
            source_id=src_beta.id
        )
        r.save_memory(context, b_mem_ver)
        memories_count += 1

        b_mem_owner = MemoryModel(
            id=memory_id("semantic", tenant, "fact", "payments-api owned by Team Billing Beta"),
            tenant_id=tenant,
            memory_type="semantic",
            subtype="fact",
            title="payments-api ownership in Beta",
            summary="payments-api in Beta is owned by Team Billing Beta.",
            status="active",
            confidence=0.90,
            valid_from="2026-05-01T00:00:00Z",
            valid_to=None,
            observed_at=now,
            created_at=now,
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_beta.id, "semantic", "fact", "payments-api owned by Team Billing Beta", "Team Billing Beta"),
            entities=["payments-api"],
            source_id=src_beta.id
        )
        r.save_memory(context, b_mem_owner)
        memories_count += 1

        # Cross-tenant isolation target secret
        secret_mem = MemoryModel(
            id=memory_id("semantic", tenant, "secret", "Beta Secret Database Password"),
            tenant_id=tenant,
            memory_type="semantic",
            subtype="fact",
            title="Beta Secret Database Password",
            summary="Beta Secret Database Password: beta-secret-pw-999. Cross-tenant leakage strictly prohibited.",
            status="active",
            confidence=0.95,
            valid_from="2026-01-01T00:00:00Z",
            valid_to=None,
            observed_at=now,
            created_at=now,
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_beta.id, "semantic", "secret", "Beta Secret Database Password", "beta-secret-pw-999"),
            entities=[],
            source_id=src_beta.id
        )
        r.save_memory(context, secret_mem)
        memories_count += 1

        # Beta Incident
        b_inc = MemoryModel(
            id=memory_id("episodic", tenant, "incident", "inc-beta-01 high latency"),
            tenant_id=tenant,
            memory_type="episodic",
            subtype="incident",
            title="Incident inc-beta-01: high latency in payments-api during promotion",
            summary="Beta incident inc-beta-01 occurred when promotional traffic spiked Redis latency on payments-api.",
            status="active",
            confidence=0.90,
            valid_from="2026-08-10T00:00:00Z",
            valid_to=None,
            observed_at="2026-08-10T00:00:00Z",
            created_at="2026-08-10T00:00:00Z",
            updated_at=now,
            idempotency_key=memory_idempotency_key(tenant, src_beta.id, "episodic", "incident", "inc-beta-01 high latency", "inc-beta-01"),
            entities=["payments-api"],
            source_id=src_beta.id
        )
        r.save_memory(context, b_inc)
        memories_count += 1

    return {"entities": entities_count, "memories": memories_count, "tasks": tasks_count}


def reset_tenant_data(context: TenantContext, repo: Optional[MemoryRepository] = None) -> int:
    r = repo or get_memory_repository()
    # Clean FalkorDB tenant graph
    if getattr(r, "_falkor_connected", False) and r._falkor_client:
        try:
            graph = r._get_graph(context.graph_name)
            graph.query("MATCH (n {tenant_id: $tenant_id}) DETACH DELETE n", {"tenant_id": context.tenant_id})
            r.init_tenant_schema(context.tenant_id)
        except Exception:
            pass

    # Delete all memories, tasks, entities, and sources for tenant in SQLite
    count = 0
    with r._get_sqlite_con() as con:
        cur = con.cursor()
        cur.execute("DELETE FROM memories WHERE tenant_id = ?", (context.tenant_id,))
        count += cur.rowcount
        cur.execute("DELETE FROM memory_fts WHERE tenant_id = ?", (context.tenant_id,))
        cur.execute("DELETE FROM tasks WHERE tenant_id = ?", (context.tenant_id,))
        cur.execute("DELETE FROM entities WHERE tenant_id = ?", (context.tenant_id,))
        cur.execute("DELETE FROM sources WHERE tenant_id = ?", (context.tenant_id,))
        cur.execute("DELETE FROM graph_edges WHERE tenant_id = ?", (context.tenant_id,))
        cur.execute("DELETE FROM conversations WHERE tenant_id = ?", (context.tenant_id,))
        con.commit()
    from app.core.cache import get_cache
    get_cache().invalidate_tenant(context.tenant_id)
    return count
