"""Persistence repository with FalkorDB graph and SQLite FTS5 support."""
import json
import sqlite3
import os
from typing import Optional, List, Dict, Any, Tuple
from app.config import Settings, get_settings
from app.dependencies import TenantContext
from app.errors import TenantIsolationError, ResourceNotFoundError, ConflictError, TaskClaimError
from app.core.time import utc_now_iso, is_past
from app.core.cache import get_cache
from app.core.logging import get_logger
from app.memory.models import (
    EntityModel, MemoryModel, SourceModel, TaskModel, ConversationModel
)

logger = get_logger("repository")


class MemoryRepository:
    """Repository handling both FalkorDB graph and SQLite storage + FTS."""
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.db_path = self.settings.SQLITE_DB_PATH
        self._falkor_client = None
        self._falkor_connected = False
        self._init_sqlite()
        self._try_init_falkordb()

    def _get_sqlite_con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=10.0)
        con.row_factory = sqlite3.Row
        return con

    def _init_sqlite(self) -> None:
        """Initialize tables and FTS5 index in SQLite."""
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            # Tenants control table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    tenant_id TEXT PRIMARY KEY,
                    api_key_hash TEXT NOT NULL,
                    graph_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # Derived SQLite FTS5 table
            cur.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    tenant_id UNINDEXED,
                    memory_id UNINDEXED,
                    title,
                    summary,
                    entities
                )
            """)

            # Fallback & Durability tables
            cur.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    aliases_json TEXT,
                    description TEXT,
                    version INT DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_tenant ON entities(tenant_id)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    subtype TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    content_json TEXT,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    observed_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INT DEFAULT 1,
                    created_by TEXT,
                    extraction_method TEXT,
                    idempotency_key TEXT UNIQUE,
                    entities_json TEXT,
                    source_id TEXT,
                    superseded_by TEXT,
                    supersedes_id TEXT
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_memories_tenant ON memories(tenant_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_memories_idemp ON memories(idempotency_key)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    conversation_id TEXT,
                    message_id TEXT,
                    created_at TEXT NOT NULL,
                    raw_text_ref TEXT
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_tenant ON sources(tenant_id)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    idempotency_key TEXT UNIQUE,
                    lease_owner TEXT,
                    lease_expires TEXT,
                    attempts INT DEFAULT 0,
                    version INT DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_tenant ON tasks(tenant_id)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    title TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_tenant ON conversations(tenant_id)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS graph_edges (
                    from_id TEXT NOT NULL,
                    to_id TEXT NOT NULL,
                    rel_type TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    props_json TEXT,
                    PRIMARY KEY (from_id, to_id, rel_type, tenant_id)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_tenant ON graph_edges(tenant_id)")
            con.commit()

    def _try_init_falkordb(self) -> None:
        """Attempt to connect to FalkorDB."""
        try:
            from falkordb import FalkorDB
            client = FalkorDB(
                host=self.settings.FALKORDB_HOST,
                port=self.settings.FALKORDB_PORT,
                password=self.settings.FALKORDB_PASSWORD or None,
            )
            # Lightweight ping
            client.connection.ping()
            self._falkor_client = client
            self._falkor_connected = True
            logger.info("FalkorDB connection established successfully.")
        except Exception as e:
            self._falkor_connected = False
            self._falkor_client = None
            logger.warning(f"FalkorDB unavailable on {self.settings.FALKORDB_HOST}:{self.settings.FALKORDB_PORT} ({e}). Using embedded durable persistence.")

    def check_health(self) -> Dict[str, Any]:
        """Check persistence layer health."""
        sqlite_ok = False
        try:
            with self._get_sqlite_con() as con:
                con.execute("SELECT 1").fetchone()
            sqlite_ok = True
        except Exception:
            pass

        # FalkorDB check
        falkor_ok = False
        if self._falkor_client:
            try:
                self._falkor_client.connection.ping()
                falkor_ok = True
            except Exception:
                falkor_ok = False

        return {
            "ok": sqlite_ok,
            "sqlite": sqlite_ok,
            "falkordb_connected": falkor_ok,
            "mode": "falkordb+sqlite" if falkor_ok else "sqlite_standalone"
        }

    # ==========================
    # Entity Operations
    # ==========================
    def upsert_entity(self, context: TenantContext, entity: EntityModel) -> EntityModel:
        context.assert_same_tenant(entity.tenant_id)
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO entities (id, tenant_id, kind, name, aliases_json, description, version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    aliases_json=excluded.aliases_json,
                    description=excluded.description,
                    version=entities.version + 1,
                    updated_at=excluded.updated_at
            """, (
                entity.id, entity.tenant_id, entity.kind, entity.name,
                json.dumps(entity.aliases), entity.description,
                entity.version, entity.created_at, entity.updated_at
            ))
            con.commit()

        # FalkorDB sync if connected
        if self._falkor_connected and self._falkor_client:
            try:
                graph = self._falkor_client.select_graph(context.graph_name)
                cypher = """
                MERGE (e:Entity {id: $id, tenant_id: $tenant_id})
                SET e.kind = $kind, e.name = $name, e.description = $desc,
                    e.version = e.version + 1, e.updated_at = $now
                RETURN e
                """
                graph.query(cypher, {
                    "id": entity.id, "tenant_id": entity.tenant_id, "kind": entity.kind,
                    "name": entity.name, "desc": entity.description or "", "now": utc_now_iso()
                })
            except Exception as e:
                logger.warning(f"FalkorDB entity sync error: {e}")

        get_cache().invalidate_tenant(context.tenant_id)
        return self.get_entity(context, entity.id)

    def get_entity(self, context: TenantContext, entity_id: str) -> Optional[EntityModel]:
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM entities WHERE id = ? AND tenant_id = ?", (entity_id, context.tenant_id))
            row = cur.fetchone()
            if not row:
                return None
            return EntityModel(
                id=row["id"],
                kind=row["kind"],
                name=row["name"],
                aliases=json.loads(row["aliases_json"] or "[]"),
                description=row["description"],
                tenant_id=row["tenant_id"],
                version=row["version"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )

    def list_entities(self, context: TenantContext, kind: Optional[str] = None) -> List[EntityModel]:
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            if kind:
                cur.execute("SELECT * FROM entities WHERE tenant_id = ? AND kind = ?", (context.tenant_id, kind))
            else:
                cur.execute("SELECT * FROM entities WHERE tenant_id = ?", (context.tenant_id,))
            rows = cur.fetchall()
            return [
                EntityModel(
                    id=r["id"],
                    kind=r["kind"],
                    name=r["name"],
                    aliases=json.loads(r["aliases_json"] or "[]"),
                    description=r["description"],
                    tenant_id=r["tenant_id"],
                    version=r["version"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"]
                ) for r in rows
            ]

    # ==========================
    # Memory Operations
    # ==========================
    def save_memory(self, context: TenantContext, memory: MemoryModel) -> MemoryModel:
        context.assert_same_tenant(memory.tenant_id)

        # Idempotency check: if memory with same idempotency_key exists for tenant, return it
        existing = self.get_memory_by_idempotency_key(context, memory.idempotency_key)
        if existing:
            return existing

        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO memories (
                    id, tenant_id, memory_type, subtype, title, summary, content_json,
                    status, confidence, valid_from, valid_to, observed_at, created_at,
                    updated_at, version, created_by, extraction_method, idempotency_key,
                    entities_json, source_id, superseded_by, supersedes_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    summary = excluded.summary,
                    content_json = excluded.content_json,
                    status = excluded.status,
                    confidence = excluded.confidence,
                    valid_to = excluded.valid_to,
                    updated_at = excluded.updated_at,
                    version = memories.version + 1,
                    superseded_by = excluded.superseded_by,
                    supersedes_id = excluded.supersedes_id
            """, (
                memory.id, memory.tenant_id, memory.memory_type, memory.subtype,
                memory.title, memory.summary, memory.content_json, memory.status,
                memory.confidence, memory.valid_from, memory.valid_to, memory.observed_at,
                memory.created_at, memory.updated_at, memory.version, memory.created_by,
                memory.extraction_method, memory.idempotency_key, json.dumps(memory.entities),
                memory.source_id, memory.superseded_by, memory.supersedes_id
            ))
            # Sync to FTS5 (clean old entry first to prevent duplicate FTS rows)
            cur.execute("DELETE FROM memory_fts WHERE memory_id = ? AND tenant_id = ?", (memory.id, memory.tenant_id))
            cur.execute("""
                INSERT INTO memory_fts (tenant_id, memory_id, title, summary, entities)
                VALUES (?, ?, ?, ?, ?)
            """, (
                memory.tenant_id, memory.id, memory.title, memory.summary, " ".join(memory.entities)
            ))
            con.commit()

        # Connect graph relationships in SQLite
        for ent_name in memory.entities:
            from app.core.ids import entity_id
            ent_slug = entity_id("service", ent_name, tenant_id=context.tenant_id)
            self.add_relationship(context, memory.id, ent_slug, "MENTIONS")
            self.add_relationship(context, memory.id, ent_slug, "ABOUT")

        if memory.source_id:
            self.add_relationship(context, memory.id, memory.source_id, "DERIVED_FROM")

        if memory.supersedes_id:
            self.add_relationship(context, memory.id, memory.supersedes_id, "SUPERSEDES")

        # FalkorDB sync if available
        if self._falkor_connected and self._falkor_client:
            try:
                graph = self._falkor_client.select_graph(context.graph_name)
                cypher = """
                MERGE (m:Memory {id: $id, tenant_id: $tenant_id})
                SET m.memory_type = $mtype, m.subtype = $subtype, m.title = $title,
                    m.summary = $summary, m.status = $status, m.confidence = $conf,
                    m.valid_from = $valid_from, m.valid_to = $valid_to,
                    m.version = $ver, m.updated_at = $now, m.idempotency_key = $idemp
                RETURN m
                """
                graph.query(cypher, {
                    "id": memory.id, "tenant_id": memory.tenant_id, "mtype": memory.memory_type,
                    "subtype": memory.subtype, "title": memory.title, "summary": memory.summary,
                    "status": memory.status, "conf": memory.confidence, "valid_from": memory.valid_from,
                    "valid_to": memory.valid_to or "", "ver": memory.version, "now": memory.updated_at,
                    "idemp": memory.idempotency_key
                })
            except Exception as e:
                logger.warning(f"FalkorDB memory sync error: {e}")

        get_cache().invalidate_tenant(context.tenant_id)
        return memory

    def get_memory(self, context: TenantContext, memory_id: str) -> Optional[MemoryModel]:
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM memories WHERE id = ? AND tenant_id = ?", (memory_id, context.tenant_id))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_memory(row)

    def get_memory_by_idempotency_key(self, context: TenantContext, idempotency_key: str) -> Optional[MemoryModel]:
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM memories WHERE idempotency_key = ? AND tenant_id = ?", (idempotency_key, context.tenant_id))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_memory(row)

    def update_memory_status(
        self,
        context: TenantContext,
        memory_id: str,
        new_status: str,
        valid_to: Optional[str] = None,
        expected_version: Optional[int] = None,
        superseded_by: Optional[str] = None
    ) -> Optional[MemoryModel]:
        """Versioned compare-and-set memory update."""
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            now = utc_now_iso()
            if expected_version is not None:
                cur.execute("""
                    UPDATE memories
                    SET status = ?, valid_to = COALESCE(?, valid_to), superseded_by = COALESCE(?, superseded_by),
                        updated_at = ?, version = version + 1
                    WHERE id = ? AND tenant_id = ? AND version = ?
                """, (new_status, valid_to, superseded_by, now, memory_id, context.tenant_id, expected_version))
                if cur.rowcount == 0:
                    # Version mismatch or not found
                    cur.execute("SELECT version FROM memories WHERE id = ? AND tenant_id = ?", (memory_id, context.tenant_id))
                    r = cur.fetchone()
                    if r:
                        raise ConflictError(f"Memory {memory_id} version mismatch (current: {r['version']}, expected: {expected_version})")
                    return None
            else:
                cur.execute("""
                    UPDATE memories
                    SET status = ?, valid_to = COALESCE(?, valid_to), superseded_by = COALESCE(?, superseded_by),
                        updated_at = ?, version = version + 1
                    WHERE id = ? AND tenant_id = ?
                """, (new_status, valid_to, superseded_by, now, memory_id, context.tenant_id))

            con.commit()

        get_cache().invalidate_tenant(context.tenant_id)
        return self.get_memory(context, memory_id)

    def delete_memory(self, context: TenantContext, memory_id: str, hard_delete: bool = False) -> bool:
        """Soft or hard delete memory and sync FTS index."""
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            if hard_delete:
                cur.execute("DELETE FROM memories WHERE id = ? AND tenant_id = ?", (memory_id, context.tenant_id))
                cur.execute("DELETE FROM memory_fts WHERE memory_id = ? AND tenant_id = ?", (memory_id, context.tenant_id))
                cur.execute("DELETE FROM graph_edges WHERE (from_id = ? OR to_id = ?) AND tenant_id = ?", (memory_id, memory_id, context.tenant_id))
            else:
                cur.execute("""
                    UPDATE memories SET status = 'deleted', updated_at = ?
                    WHERE id = ? AND tenant_id = ?
                """, (utc_now_iso(), memory_id, context.tenant_id))
                # Remove from FTS to prevent retrieval
                cur.execute("DELETE FROM memory_fts WHERE memory_id = ? AND tenant_id = ?", (memory_id, context.tenant_id))
            con.commit()

        get_cache().invalidate_tenant(context.tenant_id)
        return True

    def list_memories(
        self,
        context: TenantContext,
        status: Optional[str] = None,
        memory_type: Optional[str] = None
    ) -> List[MemoryModel]:
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            query = "SELECT * FROM memories WHERE tenant_id = ?"
            params: List[Any] = [context.tenant_id]
            if status:
                query += " AND status = ?"
                params.append(status)
            if memory_type:
                query += " AND memory_type = ?"
                params.append(memory_type)
            query += " ORDER BY created_at DESC"
            cur.execute(query, params)
            return [self._row_to_memory(r) for r in cur.fetchall()]

    # ==========================
    # Relationship Operations
    # ==========================
    def add_relationship(
        self,
        context: TenantContext,
        from_id: str,
        to_id: str,
        rel_type: str,
        props: Optional[Dict[str, Any]] = None
    ) -> None:
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO graph_edges (from_id, to_id, rel_type, tenant_id, props_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(from_id, to_id, rel_type, tenant_id) DO UPDATE SET
                    props_json = excluded.props_json
            """, (from_id, to_id, rel_type, context.tenant_id, json.dumps(props or {})))
            con.commit()

        # FalkorDB sync if available
        if self._falkor_connected and self._falkor_client:
            try:
                graph = self._falkor_client.select_graph(context.graph_name)
                cypher = f"""
                MATCH (a {{id: $from_id, tenant_id: $tenant_id}}), (b {{id: $to_id, tenant_id: $tenant_id}})
                MERGE (a)-[r:{rel_type}]->(b)
                RETURN r
                """
                graph.query(cypher, {"from_id": from_id, "to_id": to_id, "tenant_id": context.tenant_id})
            except Exception as e:
                logger.warning(f"FalkorDB relationship sync error: {e}")

    def get_related_entities(self, context: TenantContext, memory_id: str) -> List[EntityModel]:
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT e.* FROM entities e
                JOIN graph_edges g ON e.id = g.to_id
                WHERE g.from_id = ? AND g.tenant_id = ?
            """, (memory_id, context.tenant_id))
            return [
                EntityModel(
                    id=r["id"], kind=r["kind"], name=r["name"],
                    aliases=json.loads(r["aliases_json"] or "[]"),
                    description=r["description"], tenant_id=r["tenant_id"],
                    version=r["version"], created_at=r["created_at"], updated_at=r["updated_at"]
                ) for r in cur.fetchall()
            ]

    def get_entity_dependencies(self, context: TenantContext, entity_id: str, hops: int = 2) -> List[EntityModel]:
        """Traverse DEPENDS_ON relationships up to hops."""
        visited = set()
        queue = [(entity_id, 0)]
        results = []

        with self._get_sqlite_con() as con:
            cur = con.cursor()
            while queue:
                curr_id, current_hop = queue.pop(0)
                if current_hop >= hops:
                    continue
                cur.execute("""
                    SELECT e.* FROM entities e
                    JOIN graph_edges g ON (e.id = g.to_id AND g.from_id = ?) OR (e.id = g.from_id AND g.to_id = ?)
                    WHERE g.rel_type = 'DEPENDS_ON' AND g.tenant_id = ?
                """, (curr_id, curr_id, context.tenant_id))
                for row in cur.fetchall():
                    target_id = row["id"]
                    if target_id not in visited:
                        visited.add(target_id)
                        queue.append((target_id, current_hop + 1))
                        results.append(EntityModel(
                            id=row["id"], kind=row["kind"], name=row["name"],
                            aliases=json.loads(row["aliases_json"] or "[]"),
                            description=row["description"], tenant_id=row["tenant_id"],
                            version=row["version"], created_at=row["created_at"], updated_at=row["updated_at"]
                        ))
        return results

    # ==========================
    # Task Board Operations (Lease-based)
    # ==========================
    def create_task(self, context: TenantContext, task: TaskModel) -> TaskModel:
        context.assert_same_tenant(task.tenant_id)
        # Idempotency check
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM tasks WHERE idempotency_key = ? AND tenant_id = ?", (task.idempotency_key, context.tenant_id))
            row = cur.fetchone()
            if row:
                return self._row_to_task(row)

            cur.execute("""
                INSERT INTO tasks (
                    id, tenant_id, task_type, status, payload_json, result_json,
                    idempotency_key, lease_owner, lease_expires, attempts, version,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id, task.tenant_id, task.task_type, task.status, task.payload_json,
                task.result_json, task.idempotency_key, task.lease_owner, task.lease_expires,
                task.attempts, task.version, task.created_at, task.updated_at
            ))
            con.commit()
        return task

    def get_task(self, context: TenantContext, task_id: str) -> Optional[TaskModel]:
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM tasks WHERE id = ? AND tenant_id = ?", (task_id, context.tenant_id))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_task(row)

    def list_tasks(self, context: TenantContext, status: Optional[str] = None) -> List[TaskModel]:
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            if status:
                cur.execute("SELECT * FROM tasks WHERE tenant_id = ? AND status = ? ORDER BY created_at DESC", (context.tenant_id, status))
            else:
                cur.execute("SELECT * FROM tasks WHERE tenant_id = ? ORDER BY created_at DESC", (context.tenant_id,))
            return [self._row_to_task(r) for r in cur.fetchall()]

    def claim_task(
        self,
        context: TenantContext,
        task_id: str,
        worker_id: str,
        lease_seconds: int = 30
    ) -> Optional[TaskModel]:
        """
        Atomic lease-based task claim.
        Valid claim condition:
          status = 'pending' AND (lease_owner IS NULL OR lease_expires < now)
        """
        from datetime import timedelta
        from app.core.time import utc_now
        lease_until = (utc_now() + timedelta(seconds=lease_seconds)).isoformat()
        now = utc_now_iso()

        with self._get_sqlite_con() as con:
            cur = con.cursor()
            # We select first to verify tenant isolation and pending state
            cur.execute("SELECT * FROM tasks WHERE id = ? AND tenant_id = ?", (task_id, context.tenant_id))
            row = cur.fetchone()
            if not row:
                return None

            # Check if pending or expired lease
            is_claimable = (row["status"] == "pending") or (
                row["status"] == "claimed" and row["lease_expires"] and is_past(row["lease_expires"])
            )
            if not is_claimable:
                return None

            cur.execute("""
                UPDATE tasks
                SET status = 'claimed',
                    lease_owner = ?,
                    lease_expires = ?,
                    attempts = attempts + 1,
                    version = version + 1,
                    updated_at = ?
                WHERE id = ? AND tenant_id = ? AND version = ?
            """, (worker_id, lease_until, now, task_id, context.tenant_id, row["version"]))

            if cur.rowcount == 0:
                # Concurrent claim lost
                return None
            con.commit()

        return self.get_task(context, task_id)

    def complete_task(
        self,
        context: TenantContext,
        task_id: str,
        worker_id: str,
        result_json: str
    ) -> Optional[TaskModel]:
        now = utc_now_iso()
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("""
                UPDATE tasks
                SET status = 'done',
                    result_json = ?,
                    lease_owner = NULL,
                    lease_expires = NULL,
                    version = version + 1,
                    updated_at = ?
                WHERE id = ? AND tenant_id = ? AND lease_owner = ?
            """, (result_json, now, task_id, context.tenant_id, worker_id))
            con.commit()
        return self.get_task(context, task_id)

    def fail_task(
        self,
        context: TenantContext,
        task_id: str,
        worker_id: str,
        reason: str
    ) -> Optional[TaskModel]:
        now = utc_now_iso()
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("""
                UPDATE tasks
                SET status = 'failed',
                    result_json = ?,
                    lease_owner = NULL,
                    lease_expires = NULL,
                    version = version + 1,
                    updated_at = ?
                WHERE id = ? AND tenant_id = ?
            """, (json.dumps({"error": reason}), now, task_id, context.tenant_id))
            con.commit()
        return self.get_task(context, task_id)

    def recover_expired_leases(self, context: TenantContext) -> int:
        """Reset tasks with expired leases back to pending if attempts < max_attempts (5)."""
        now = utc_now_iso()
        recovered = 0
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT id, attempts, lease_expires FROM tasks
                WHERE tenant_id = ? AND status = 'claimed'
            """, (context.tenant_id,))
            for r in cur.fetchall():
                if r["lease_expires"] and is_past(r["lease_expires"]):
                    if r["attempts"] >= 5:
                        cur.execute("""
                            UPDATE tasks SET status = 'failed', result_json = ?, updated_at = ?
                            WHERE id = ? AND tenant_id = ?
                        """, (json.dumps({"error": "Max lease retry attempts exceeded"}), now, r["id"], context.tenant_id))
                    else:
                        cur.execute("""
                            UPDATE tasks SET status = 'pending', lease_owner = NULL, lease_expires = NULL, updated_at = ?
                            WHERE id = ? AND tenant_id = ?
                        """, (now, r["id"], context.tenant_id))
                    recovered += 1
            con.commit()
        return recovered

    # ==========================
    # Conversation & Source
    # ==========================
    def save_source(self, context: TenantContext, source: SourceModel) -> SourceModel:
        context.assert_same_tenant(source.tenant_id)
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO sources (id, tenant_id, source_type, conversation_id, message_id, created_at, raw_text_ref)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET raw_text_ref = excluded.raw_text_ref
            """, (
                source.id, source.tenant_id, source.source_type, source.conversation_id,
                source.message_id, source.created_at, source.raw_text_ref
            ))
            con.commit()
        return source

    def save_conversation(self, context: TenantContext, conv: ConversationModel) -> ConversationModel:
        context.assert_same_tenant(conv.tenant_id)
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO conversations (id, tenant_id, title, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = COALESCE(excluded.title, conversations.title),
                    status = excluded.status,
                    updated_at = excluded.updated_at
            """, (conv.id, conv.tenant_id, conv.title, conv.status, conv.created_at, conv.updated_at))
            con.commit()
        return conv

    def get_conversation(self, context: TenantContext, conv_id: str) -> Optional[ConversationModel]:
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM conversations WHERE id = ? AND tenant_id = ?", (conv_id, context.tenant_id))
            row = cur.fetchone()
            if not row:
                return None
            return ConversationModel(
                id=row["id"], tenant_id=row["tenant_id"], title=row["title"],
                status=row["status"], created_at=row["created_at"], updated_at=row["updated_at"]
            )

    # ==========================
    # FTS Retrieval & Rebuild
    # ==========================
    def search_fts(self, context: TenantContext, query: str, limit: int = 20) -> List[Tuple[MemoryModel, float]]:
        """Search derived SQLite FTS5 index filtered by tenant."""
        results = []
        # Sanitize query for FTS5 (avoid syntax errors on special characters)
        clean_terms = "".join(c if c.isalnum() or c.isspace() else " " for c in query).strip()
        if not clean_terms:
            return []

        stop_words = {
            "what", "is", "the", "of", "to", "in", "for", "on", "a", "an", "and", "or",
            "how", "do", "does", "did", "can", "could", "would", "should", "at", "by",
            "from", "with", "about", "are", "was", "were", "be", "been", "being", "it",
            "this", "that", "there", "their", "my", "your", "our", "me", "tell", "give", "show"
        }
        filtered_terms = [t for t in clean_terms.split() if len(t) > 1 and t.lower() not in stop_words]
        if not filtered_terms:
            filtered_terms = [t for t in clean_terms.split() if len(t) > 1]
        if not filtered_terms:
            return []

        match_expression = " OR ".join(f'"{term}"*' for term in filtered_terms)

        with self._get_sqlite_con() as con:
            cur = con.cursor()
            try:
                cur.execute("""
                    SELECT memory_id, bm25(memory_fts) as rank
                    FROM memory_fts
                    WHERE tenant_id = ? AND memory_fts MATCH ?
                    ORDER BY rank ASC
                    LIMIT ?
                """, (context.tenant_id, match_expression, limit))
                rows = cur.fetchall()
            except sqlite3.OperationalError:
                # Fallback to LIKE if syntax issue
                cur.execute("""
                    SELECT id as memory_id, 1.0 as rank
                    FROM memories
                    WHERE tenant_id = ? AND (title LIKE ? OR summary LIKE ?)
                    LIMIT ?
                """, (context.tenant_id, f"%{clean_terms}%", f"%{clean_terms}%", limit))
                rows = cur.fetchall()

            for r in rows:
                mem = self.get_memory(context, r["memory_id"])
                if mem and mem.status != "deleted":
                    # In FTS5, lower BM25 score means better match; invert for standard scoring
                    score = 1.0 / (1.0 + abs(float(r["rank"])))
                    results.append((mem, score))
        return results

    def rebuild_fts(self) -> int:
        """Rebuild derived SQLite FTS table from all active memories."""
        count = 0
        with self._get_sqlite_con() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM memory_fts")
            cur.execute("SELECT tenant_id, id, title, summary, entities_json FROM memories WHERE status != 'deleted'")
            rows = cur.fetchall()
            for r in rows:
                entities = " ".join(json.loads(r["entities_json"] or "[]"))
                cur.execute("""
                    INSERT INTO memory_fts (tenant_id, memory_id, title, summary, entities)
                    VALUES (?, ?, ?, ?, ?)
                """, (r["tenant_id"], r["id"], r["title"], r["summary"], entities))
                count += 1
            con.commit()
        return count

    def _row_to_memory(self, row: sqlite3.Row) -> MemoryModel:
        return MemoryModel(
            id=row["id"],
            tenant_id=row["tenant_id"],
            memory_type=row["memory_type"],
            subtype=row["subtype"],
            title=row["title"],
            summary=row["summary"],
            content_json=row["content_json"],
            status=row["status"],
            confidence=row["confidence"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            observed_at=row["observed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=row["version"],
            created_by=row["created_by"],
            extraction_method=row["extraction_method"],
            idempotency_key=row["idempotency_key"],
            entities=json.loads(row["entities_json"] or "[]"),
            source_id=row["source_id"],
            superseded_by=row["superseded_by"],
            supersedes_id=row["supersedes_id"]
        )

    def _row_to_task(self, row: sqlite3.Row) -> TaskModel:
        return TaskModel(
            id=row["id"],
            tenant_id=row["tenant_id"],
            task_type=row["task_type"],
            status=row["status"],
            payload_json=row["payload_json"],
            result_json=row["result_json"],
            idempotency_key=row["idempotency_key"],
            lease_owner=row["lease_owner"],
            lease_expires=row["lease_expires"],
            attempts=row["attempts"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )


_repo: Optional[MemoryRepository] = None


def get_memory_repository() -> MemoryRepository:
    global _repo
    if _repo is None:
        _repo = MemoryRepository()
    return _repo
