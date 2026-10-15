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

    def _get_graph(self, graph_name: str):
        if not self._falkor_connected or not self._falkor_client:
            self._try_init_falkordb()
        if not self._falkor_connected or not self._falkor_client:
            raise RuntimeError("FalkorDB connection required. Graph engine is not available.")
        return self._falkor_client.select_graph(graph_name)

    def init_tenant_schema(self, tenant_id: str) -> None:
        """Idempotently initialize FalkorDB indexes for tenant graph."""
        if not self._falkor_connected or not self._falkor_client:
            self._try_init_falkordb()
        if not self._falkor_connected or not self._falkor_client:
            return
        graph_name = self.settings.tenant_graph_name(tenant_id)
        graph = self._get_graph(graph_name)
        # 1. Range indexes
        for lbl in ["Entity", "Memory", "Task", "Session", "Turn", "Agent"]:
            try:
                graph.query(f"CREATE INDEX FOR (n:{lbl}) ON (n.id)")
            except Exception:
                pass
        # 2. Full-text index on Memory
        try:
            graph.query("CREATE FULLTEXT INDEX FOR (m:Memory) ON (m.title, m.summary, m.subtype)")
        except Exception:
            pass
        # 3. Vector index on Memory
        try:
            graph.query("CREATE VECTOR INDEX FOR (m:Memory) ON (m.embedding) OPTIONS {dimension: 64, similarityFunction: 'cosine'}")
        except Exception:
            pass
        # 3b. Vector index on Entity
        try:
            graph.query("CREATE VECTOR INDEX FOR (e:Entity) ON (e.embedding) OPTIONS {dimension: 64, similarityFunction: 'cosine'}")
        except Exception:
            pass
        # 4. Ensure default Agent nodes exist
        try:
            graph.query("""
            MERGE (:Agent {id: 'agent_triage', tenant_id: $tenant_id, role: 'triage'})
            MERGE (:Agent {id: 'agent_resolver', tenant_id: $tenant_id, role: 'resolver'})
            MERGE (:Agent {id: 'agent_curator', tenant_id: $tenant_id, role: 'curator'})
            """, {"tenant_id": tenant_id})
        except Exception:
            pass

    def _node_to_task(self, node: Any) -> TaskModel:
        props = getattr(node, "properties", node) if not isinstance(node, dict) else node
        return TaskModel(
            id=props.get("id", ""),
            tenant_id=props.get("tenant_id", ""),
            task_type=props.get("task_type", ""),
            status=props.get("status", "pending"),
            payload_json=props.get("payload_json", "{}"),
            result_json=props.get("result_json") or None,
            idempotency_key=props.get("idempotency_key"),
            lease_owner=props.get("lease_owner") or None,
            lease_expires=props.get("lease_expires") or None,
            attempts=int(props.get("attempts", 0)),
            version=int(props.get("version", 1)),
            created_at=props.get("created_at", utc_now_iso()),
            updated_at=props.get("updated_at", utc_now_iso())
        )

    def _node_to_memory(self, node: Any) -> MemoryModel:
        props = getattr(node, "properties", node) if not isinstance(node, dict) else node
        entities = []
        if "entities_json" in props and props["entities_json"]:
            try:
                entities = json.loads(props["entities_json"])
            except Exception:
                entities = []
        elif "entities" in props and isinstance(props["entities"], list):
            entities = props["entities"]

        ext_method = props.get("extraction_method")
        if ext_method not in ("user_explicit", "deterministic", "llm"):
            ext_method = "deterministic"

        return MemoryModel(
            id=props.get("id", ""),
            tenant_id=props.get("tenant_id", ""),
            memory_type=props.get("memory_type", "episodic"),
            subtype=props.get("subtype", "general"),
            title=props.get("title", ""),
            summary=props.get("summary", ""),
            content_json=props.get("content_json") or None,
            status=props.get("status", "active"),
            confidence=float(props.get("confidence", 1.0)),
            valid_from=props.get("valid_from", utc_now_iso()),
            valid_to=props.get("valid_to") or None,
            observed_at=props.get("observed_at", utc_now_iso()),
            created_at=props.get("created_at", utc_now_iso()),
            updated_at=props.get("updated_at", utc_now_iso()),
            version=int(props.get("version", 1)),
            created_by=props.get("created_by") or "system",
            extraction_method=ext_method,
            idempotency_key=props.get("idempotency_key", props.get("id", "")),
            entities=entities,
            source_id=props.get("source_id") or None,
            superseded_by=props.get("superseded_by") or None,
            supersedes_id=props.get("supersedes_id") or None
        )

    def _node_to_entity(self, node: Any) -> EntityModel:
        props = getattr(node, "properties", node) if not isinstance(node, dict) else node
        aliases = []
        if "aliases_json" in props and props["aliases_json"]:
            try:
                aliases = json.loads(props["aliases_json"])
            except Exception:
                aliases = []
        elif "aliases" in props and isinstance(props["aliases"], list):
            aliases = props["aliases"]

        return EntityModel(
            id=props.get("id", ""),
            tenant_id=props.get("tenant_id", ""),
            kind=props.get("kind", "service"),
            name=props.get("name", ""),
            aliases=aliases,
            description=props.get("description", ""),
            version=int(props.get("version", 1)),
            created_at=props.get("created_at", utc_now_iso()),
            updated_at=props.get("updated_at", utc_now_iso())
        )

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
            "ok": falkor_ok,
            "sqlite": sqlite_ok,
            "falkordb_connected": falkor_ok,
            "mode": "falkordb_native" if falkor_ok else "falkordb_unavailable"
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
                from app.retrieval.vector_encoder import encode_vector
                embedding_text = f"{entity.name} {' '.join(entity.aliases)} {entity.description or ''}"
                ent_vec = encode_vector(embedding_text)
                graph = self._falkor_client.select_graph(context.graph_name)
                cypher = """
                MERGE (e:Entity {id: $id, tenant_id: $tenant_id})
                SET e.kind = $kind, e.name = $name, e.description = $desc,
                    e.aliases = $aliases, e.aliases_json = $aliases_json,
                    e.embedding = vecf32($embedding),
                    e.version = e.version + 1, e.updated_at = $now
                RETURN e
                """
                graph.query(cypher, {
                    "id": entity.id, "tenant_id": entity.tenant_id, "kind": entity.kind,
                    "name": entity.name, "desc": entity.description or "",
                    "aliases": entity.aliases, "aliases_json": json.dumps(entity.aliases),
                    "embedding": ent_vec, "now": utc_now_iso()
                })
            except Exception as e:
                logger.warning(f"FalkorDB entity sync error: {e}")

        get_cache().invalidate_tenant(context.tenant_id)
        return self.get_entity(context, entity.id)

    save_entity = upsert_entity

    def _node_to_entity(self, node: Any) -> EntityModel:
        props = getattr(node, "properties", node) if not isinstance(node, dict) else node
        aliases = []
        if "aliases" in props and isinstance(props["aliases"], list):
            aliases = props["aliases"]
        elif "aliases_json" in props and props["aliases_json"]:
            try:
                aliases = json.loads(props["aliases_json"])
            except Exception:
                aliases = []
        return EntityModel(
            id=props.get("id", ""),
            tenant_id=props.get("tenant_id", ""),
            kind=props.get("kind", "service"),
            name=props.get("name", ""),
            aliases=aliases,
            description=props.get("description") or props.get("desc") or None,
            version=int(props.get("version", 1)),
            created_at=props.get("created_at", utc_now_iso()),
            updated_at=props.get("updated_at", utc_now_iso())
        )

    def find_anchor_entities(
        self,
        context: TenantContext,
        query: str,
        limit: int = 5
    ) -> List[EntityModel]:
        """Find starting graph anchor entities dynamically via vector similarity and alias matching in FalkorDB."""
        anchors: List[EntityModel] = []
        seen_names: Set[str] = set()
        q_lower = query.lower()

        if self._falkor_connected and self._falkor_client:
            try:
                graph = self._get_graph(context.graph_name)
                from app.retrieval.vector_encoder import encode_vector
                q_vec = encode_vector(query)

                # 1. FalkorDB ANN Vector Search on :Entity
                # 1. FalkorDB Exact & Alias Name Matching in Graph
                cypher_all = """
                MATCH (e:Entity {tenant_id: $tenant_id})
                RETURN e
                """
                res_all = graph.query(cypher_all, {"tenant_id": context.tenant_id})
                for row in res_all.result_set:
                    ent = self._node_to_entity(row[0])
                    if ent.name in seen_names:
                        continue
                    ent_norm = ent.name.lower()
                    base = ent_norm.split("-")[0]
                    aliases_norm = [a.lower() for a in ent.aliases]
                    if (ent_norm in q_lower or 
                        ent_norm.replace("-", " ") in q_lower or 
                        (len(base) >= 4 and f" {base} " in f" {q_lower} ") or
                        any(a in q_lower for a in aliases_norm)):
                        seen_names.add(ent.name)
                        anchors.append(ent)

                # 2. FalkorDB ANN Vector Search on :Entity (strict sim >= 0.35)
                try:
                    cypher = """
                    CALL db.idx.vector.queryNodes('Entity', 'embedding', $k, vecf32($vec)) YIELD node, score
                    WHERE node.tenant_id = $tenant_id
                    RETURN node, score
                    ORDER BY score ASC
                    LIMIT $limit
                    """
                    res = graph.query(cypher, {
                        "k": limit * 3,
                        "vec": q_vec,
                        "tenant_id": context.tenant_id,
                        "limit": limit
                    })
                    for row in res.result_set:
                        ent = self._node_to_entity(row[0])
                        dist = float(row[1]) if row[1] is not None else 1.0
                        sim = max(0.0, 1.0 - dist)
                        if sim >= 0.35 and ent.name not in seen_names:
                            seen_names.add(ent.name)
                            anchors.append(ent)
                except Exception as e:
                    logger.debug(f"Entity vector index query: {e}")
            except Exception as e:
                logger.warning(f"FalkorDB anchor search error: {e}")

        # Fallback to local list_entities if graph is empty or disconnected
        if not anchors:
            for ent in self.list_entities(context):
                if ent.name in seen_names:
                    continue
                ent_norm = ent.name.lower()
                base = ent_norm.split("-")[0]
                aliases_norm = [a.lower() for a in ent.aliases]
                if (ent_norm in q_lower or 
                    ent_norm.replace("-", " ") in q_lower or 
                    (len(base) >= 4 and f" {base} " in f" {q_lower} ") or
                    any(a in q_lower for a in aliases_norm)):
                    seen_names.add(ent.name)
                    anchors.append(ent)

        return anchors[:limit]

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
                graph = self._get_graph(context.graph_name)
                from app.retrieval.vector_encoder import encode_vector
                text_for_vec = f"{memory.title} {memory.summary} {memory.subtype} {' '.join(memory.entities)}"
                embedding = encode_vector(text_for_vec)

                cypher = """
                MERGE (m:Memory {id: $id, tenant_id: $tenant_id})
                SET m.memory_type = $mtype, m.subtype = $subtype, m.title = $title,
                    m.summary = $summary, m.status = $status, m.confidence = $conf,
                    m.valid_from = $valid_from, m.valid_to = $valid_to,
                    m.observed_at = $observed_at, m.created_at = $created_at,
                    m.version = $ver, m.updated_at = $now, m.idempotency_key = $idemp,
                    m.entities_json = $entities_json, m.content_json = $content_json,
                    m.source_id = $source_id, m.superseded_by = $superseded_by,
                    m.supersedes_id = $supersedes_id,
                    m.embedding = vecf32($embedding)
                RETURN m
                """
                graph.query(cypher, {
                    "id": memory.id, "tenant_id": memory.tenant_id, "mtype": memory.memory_type,
                    "subtype": memory.subtype, "title": memory.title, "summary": memory.summary,
                    "status": memory.status, "conf": memory.confidence, "valid_from": memory.valid_from,
                    "valid_to": memory.valid_to or "", "observed_at": memory.observed_at,
                    "created_at": memory.created_at, "ver": memory.version, "now": memory.updated_at,
                    "idemp": memory.idempotency_key, "entities_json": json.dumps(memory.entities),
                    "content_json": memory.content_json or "", "source_id": memory.source_id or "",
                    "superseded_by": memory.superseded_by or "", "supersedes_id": memory.supersedes_id or "",
                    "embedding": embedding
                })

                # Connect relationships in FalkorDB
                from app.core.ids import entity_id
                for ent_name in memory.entities:
                    ent_slug = entity_id("service", ent_name, tenant_id=context.tenant_id)
                    edge_cypher = """
                    MATCH (m:Memory {id: $mid, tenant_id: $tid}), (e:Entity {id: $eid, tenant_id: $tid})
                    MERGE (m)-[:MENTIONS]->(e)
                    MERGE (m)-[:ABOUT]->(e)
                    """
                    graph.query(edge_cypher, {"mid": memory.id, "eid": ent_slug, "tid": context.tenant_id})

                if memory.source_id:
                    graph.query("""
                    MATCH (m:Memory {id: $mid, tenant_id: $tid}), (s:Source {id: $sid, tenant_id: $tid})
                    MERGE (m)-[:DERIVED_FROM]->(s)
                    """, {"mid": memory.id, "sid": memory.source_id, "tid": context.tenant_id})

                if memory.supersedes_id:
                    graph.query("""
                    MATCH (m:Memory {id: $mid, tenant_id: $tid}), (old:Memory {id: $oid, tenant_id: $tid})
                    MERGE (m)-[:SUPERSEDES]->(old)
                    """, {"mid": memory.id, "oid": memory.supersedes_id, "tid": context.tenant_id})
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

        if self._falkor_connected and self._falkor_client:
            try:
                graph = self._get_graph(context.graph_name)
                graph.query("""
                MATCH (m:Memory {id: $id, tenant_id: $tid})
                SET m.status = $status, m.valid_to = COALESCE($valid_to, m.valid_to),
                    m.superseded_by = COALESCE($superseded_by, m.superseded_by),
                    m.version = m.version + 1, m.updated_at = $now
                """, {"id": memory_id, "tid": context.tenant_id, "status": new_status, "valid_to": valid_to or "", "superseded_by": superseded_by or "", "now": now})
            except Exception as e:
                logger.warning(f"FalkorDB update_memory_status error: {e}")

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

        if self._falkor_connected and self._falkor_client:
            try:
                graph = self._get_graph(context.graph_name)
                if hard_delete:
                    graph.query("MATCH (m:Memory {id: $id, tenant_id: $tid}) DETACH DELETE m", {"id": memory_id, "tid": context.tenant_id})
                else:
                    graph.query("MATCH (m:Memory {id: $id, tenant_id: $tid}) SET m.status = 'deleted', m.updated_at = $now", {"id": memory_id, "tid": context.tenant_id, "now": utc_now_iso()})
            except Exception as e:
                logger.warning(f"FalkorDB delete_memory error: {e}")

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
        """Traverse DEPENDS_ON relationships up to hops directly in FalkorDB."""
        results = []
        visited = set()
        if self._falkor_connected and self._falkor_client:
            try:
                graph = self._get_graph(context.graph_name)
                cypher = """
                MATCH (e:Entity {id: $eid, tenant_id: $tenant_id})-[:DEPENDS_ON*1..2]-(dep:Entity {tenant_id: $tenant_id})
                RETURN DISTINCT dep
                """
                res = graph.query(cypher, {"eid": entity_id, "tenant_id": context.tenant_id})
                for row in res.result_set:
                    ent = self._node_to_entity(row[0])
                    if ent.id not in visited:
                        visited.add(ent.id)
                        results.append(ent)
                if results:
                    return results
            except Exception as e:
                logger.warning(f"FalkorDB get_entity_dependencies error: {e}")

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

        # FalkorDB sync
        if self._falkor_connected and self._falkor_client:
            try:
                graph = self._get_graph(context.graph_name)
                cypher = """
                MERGE (t:Task {id: $id, tenant_id: $tenant_id})
                SET t.task_type = $task_type, t.status = $status, t.payload_json = $payload_json,
                    t.result_json = $result_json, t.idempotency_key = $idemp,
                    t.lease_owner = $lease_owner, t.lease_expires = $lease_expires,
                    t.attempts = $attempts, t.version = $ver,
                    t.created_at = $created_at, t.updated_at = $updated_at
                RETURN t
                """
                graph.query(cypher, {
                    "id": task.id, "tenant_id": task.tenant_id, "task_type": task.task_type,
                    "status": task.status, "payload_json": task.payload_json,
                    "result_json": task.result_json or "", "idemp": task.idempotency_key,
                    "lease_owner": task.lease_owner or "", "lease_expires": task.lease_expires or "",
                    "attempts": task.attempts, "ver": task.version,
                    "created_at": task.created_at, "updated_at": task.updated_at
                })
            except Exception as e:
                logger.warning(f"FalkorDB create_task error: {e}")

        return task

    def get_task(self, context: TenantContext, task_id: str) -> Optional[TaskModel]:
        if self._falkor_connected and self._falkor_client:
            try:
                graph = self._get_graph(context.graph_name)
                res = graph.query("MATCH (t:Task {id: $id, tenant_id: $tenant_id}) RETURN t", {"id": task_id, "tenant_id": context.tenant_id})
                if res.result_set:
                    return self._node_to_task(res.result_set[0][0])
            except Exception:
                pass
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
        """Atomic Cypher lease-based task claiming in FalkorDB."""
        from datetime import timedelta
        from app.core.time import utc_now
        lease_until = (utc_now() + timedelta(seconds=lease_seconds)).isoformat()
        now = utc_now_iso()

        # 1. FalkorDB atomic single-roundtrip Cypher query
        if self._falkor_connected and self._falkor_client:
            try:
                graph = self._get_graph(context.graph_name)
                cypher = """
                MATCH (t:Task {id: $task_id, tenant_id: $tenant_id})
                WHERE t.status = 'pending' OR (t.status = 'claimed' AND t.lease_expires < $now)
                SET t.status = 'claimed', t.lease_owner = $worker_id, t.lease_expires = $lease_expires,
                    t.attempts = coalesce(t.attempts, 0) + 1, t.version = coalesce(t.version, 1) + 1,
                    t.updated_at = $now
                RETURN t
                """
                res = graph.query(cypher, {
                    "task_id": task_id,
                    "tenant_id": context.tenant_id,
                    "worker_id": worker_id,
                    "lease_expires": lease_until,
                    "now": now
                })
                if res.result_set:
                    claimed_task = self._node_to_task(res.result_set[0][0])
                    # Update local DB if present
                    with self._get_sqlite_con() as con:
                        con.execute("""
                            UPDATE tasks SET status = 'claimed', lease_owner = ?, lease_expires = ?, attempts = attempts + 1, updated_at = ?
                            WHERE id = ? AND tenant_id = ?
                        """, (worker_id, lease_until, now, task_id, context.tenant_id))
                        con.commit()
                    return claimed_task
                else:
                    return None
            except Exception as e:
                logger.warning(f"FalkorDB atomic claim error: {e}")
                return None

        return None

    def complete_task(
        self,
        context: TenantContext,
        task_id: str,
        worker_id: str,
        result_json: str
    ) -> Optional[TaskModel]:
        now = utc_now_iso()
        if self._falkor_connected and self._falkor_client:
            try:
                graph = self._get_graph(context.graph_name)
                cypher = """
                MATCH (t:Task {id: $task_id, tenant_id: $tenant_id})
                WHERE t.lease_owner = $worker_id
                SET t.status = 'done', t.result_json = $result_json,
                    t.lease_owner = '', t.lease_expires = '',
                    t.version = t.version + 1, t.updated_at = $now
                RETURN t
                """
                graph.query(cypher, {
                    "task_id": task_id, "tenant_id": context.tenant_id,
                    "worker_id": worker_id, "result_json": result_json, "now": now
                })
            except Exception as e:
                logger.warning(f"FalkorDB complete_task error: {e}")

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
        if self._falkor_connected and self._falkor_client:
            try:
                graph = self._get_graph(context.graph_name)
                cypher = """
                MATCH (t:Task {id: $task_id, tenant_id: $tenant_id})
                SET t.status = 'failed', t.result_json = $result_json,
                    t.lease_owner = '', t.lease_expires = '',
                    t.version = t.version + 1, t.updated_at = $now
                RETURN t
                """
                graph.query(cypher, {
                    "task_id": task_id, "tenant_id": context.tenant_id,
                    "result_json": json.dumps({"error": reason}), "now": now
                })
            except Exception as e:
                logger.warning(f"FalkorDB fail_task error: {e}")

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

    def record_session_turn(
        self,
        context: TenantContext,
        session_id: str,
        turn_id: str,
        role: str,
        content: str,
        memory_ids: Optional[List[str]] = None
    ) -> None:
        """Persist :Session and :Turn nodes with :HAS_TURN, :NEXT_TURN, and :DERIVED_FROM in FalkorDB."""
        if not self._falkor_connected or not self._falkor_client:
            return
        try:
            graph = self._get_graph(context.graph_name)
            now = utc_now_iso()

            # 1. Find previous turn in session to chain NEXT_TURN
            prev_turn_res = graph.query("""
                MATCH (s:Session {id: $session_id, tenant_id: $tenant_id})-[:HAS_TURN]->(t:Turn)
                WHERE NOT (t)-[:NEXT_TURN]->()
                RETURN t.id
                ORDER BY t.created_at DESC
                LIMIT 1
            """, {"session_id": session_id, "tenant_id": context.tenant_id})
            prev_turn_id = prev_turn_res.result_set[0][0] if prev_turn_res.result_set else None

            # 2. Merge session, create turn, merge HAS_TURN
            cypher = """
            MERGE (s:Session {id: $session_id, tenant_id: $tenant_id})
            ON CREATE SET s.created_at = $now
            SET s.updated_at = $now
            CREATE (t:Turn {id: $turn_id, session_id: $session_id, role: $role, content: $content, created_at: $now})
            MERGE (s)-[:HAS_TURN]->(t)
            """
            graph.query(cypher, {
                "session_id": session_id,
                "tenant_id": context.tenant_id,
                "turn_id": turn_id,
                "role": role,
                "content": content,
                "now": now
            })

            # 3. Chain :NEXT_TURN edge
            if prev_turn_id and prev_turn_id != turn_id:
                graph.query("""
                MATCH (t_prev:Turn {id: $prev_id, session_id: $session_id}), (t_curr:Turn {id: $curr_id, session_id: $session_id})
                MERGE (t_prev)-[:NEXT_TURN]->(t_curr)
                """, {"prev_id": prev_turn_id, "curr_id": turn_id, "session_id": session_id})

            # 4. Link extracted memories via (:Memory)-[:DERIVED_FROM]->(:Turn)
            if memory_ids:
                for mid in memory_ids:
                    graph.query("""
                    MATCH (m:Memory {id: $mid, tenant_id: $tenant_id}), (t:Turn {id: $turn_id})
                    MERGE (m)-[:DERIVED_FROM]->(t)
                    """, {"mid": mid, "tenant_id": context.tenant_id, "turn_id": turn_id})
        except Exception as e:
            logger.warning(f"FalkorDB record_session_turn error: {e}")

    def record_agent_handoff(
        self,
        context: TenantContext,
        from_agent: str,
        to_agent: str,
        task_id: str,
        reason: str,
        shared_state: Optional[Dict[str, Any]] = None,
        memory_id: Optional[str] = None
    ) -> None:
        """Persist explicit multi-agent handoff edge in FalkorDB."""
        if not self._falkor_connected or not self._falkor_client:
            return
        try:
            graph = self._get_graph(context.graph_name)
            now = utc_now_iso()
            state_json = json.dumps(shared_state or {})

            # 1. Ensure agents exist
            graph.query("""
            MERGE (:Agent {id: $from_id, tenant_id: $tenant_id})
            MERGE (:Agent {id: $to_id, tenant_id: $tenant_id})
            """, {"from_id": from_agent, "to_id": to_agent, "tenant_id": context.tenant_id})

            # 2. Record HANDED_OFF_TO edge
            handoff_cypher = """
            MATCH (a1:Agent {id: $from_id, tenant_id: $tenant_id}), (a2:Agent {id: $to_id, tenant_id: $tenant_id})
            CREATE (a1)-[h:HANDED_OFF_TO {task_id: $task_id, reason: $reason, shared_state_json: $state, timestamp: $now}]->(a2)
            RETURN h
            """
            graph.query(handoff_cypher, {
                "from_id": from_agent,
                "to_id": to_agent,
                "task_id": task_id,
                "reason": reason,
                "state": state_json,
                "now": now,
                "tenant_id": context.tenant_id
            })

            # 3. Link ASSIGNED_TO and FOR if task_id / memory_id present
            if task_id:
                graph.query("""
                MATCH (a:Agent {id: $agent_id, tenant_id: $tenant_id}), (t:Task {id: $task_id, tenant_id: $tenant_id})
                MERGE (a)-[:ASSIGNED_TO]->(t)
                """, {"agent_id": to_agent, "task_id": task_id, "tenant_id": context.tenant_id})

            if task_id and memory_id:
                graph.query("""
                MATCH (t:Task {id: $task_id, tenant_id: $tenant_id}), (m:Memory {id: $mem_id, tenant_id: $tenant_id})
                MERGE (t)-[:FOR]->(m)
                """, {"task_id": task_id, "mem_id": memory_id, "tenant_id": context.tenant_id})
        except Exception as e:
            logger.warning(f"FalkorDB agent handoff error: {e}")

    # ==========================
    # FTS Retrieval & Rebuild
    # ==========================
    def search_fts(self, context: TenantContext, query: str, limit: int = 20) -> List[Tuple[MemoryModel, float]]:
        """Search native FalkorDB fulltext index filtered by tenant."""
        results = []
        # Sanitize query for RediSearch (avoid syntax errors on special characters)
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

        # 1. FalkorDB Native RediSearch fulltext index query
        if self._falkor_connected and self._falkor_client:
            try:
                graph = self._get_graph(context.graph_name)
                fts_query = " | ".join(filtered_terms)
                cypher = """
                CALL db.idx.fulltext.queryNodes('Memory', $fts_query) YIELD node, score
                WHERE node.tenant_id = $tenant_id AND (node.status IS NULL OR node.status <> 'deleted')
                RETURN node, score
                LIMIT $limit
                """
                res = graph.query(cypher, {
                    "fts_query": fts_query,
                    "tenant_id": context.tenant_id,
                    "limit": limit
                })
                for row in res.result_set:
                    mem = self._node_to_memory(row[0])
                    raw_score = float(row[1]) if row[1] is not None else 1.0
                    norm_score = max(0.01, min(1.0, raw_score / 2.0))
                    results.append((mem, norm_score))
                return results
            except Exception as e:
                logger.warning(f"FalkorDB fulltext query error: {e}")

        return results

    def search_vector(
        self,
        context: TenantContext,
        query: str,
        limit: int = 10
    ) -> List[Tuple[MemoryModel, float]]:
        """Native FalkorDB vector similarity search using deterministic 64-dim embeddings."""
        from app.retrieval.vector_encoder import encode_vector
        query_vec = encode_vector(query)
        results: List[Tuple[MemoryModel, float]] = []

        if self._falkor_connected and self._falkor_client:
            try:
                graph = self._get_graph(context.graph_name)
                # FalkorDB cosine distance score: 0 is identical, so similarity is 1.0 - score
                cypher = """
                CALL db.idx.vector.queryNodes('Memory', 'embedding', $k, vecf32($vec)) YIELD node, score
                WHERE node.tenant_id = $tenant_id AND (node.status IS NULL OR node.status <> 'deleted')
                RETURN node, score
                """
                res = graph.query(cypher, {
                    "k": limit * 2,
                    "vec": query_vec,
                    "tenant_id": context.tenant_id
                })
                for row in res.result_set:
                    mem = self._node_to_memory(row[0])
                    dist = float(row[1]) if row[1] is not None else 1.0
                    sim = max(0.01, min(1.0, 1.0 - dist))
                    if sim < 0.28:
                        continue
                    results.append((mem, sim))
                    if len(results) >= limit:
                        break
                return results
            except Exception as e:
                logger.warning(f"FalkorDB vector query error: {e}")

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

    def get_recent_handoffs(self, context: TenantContext, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent agent handoffs from FalkorDB."""
        handoffs: List[Dict[str, Any]] = []
        if self._falkor_connected and self._falkor_client:
            try:
                graph = self._get_graph(context.graph_name)
                cypher = """
                MATCH (a1:Agent)-[h:HANDED_OFF_TO]->(a2:Agent)
                WHERE a1.tenant_id = $tenant_id
                RETURN a1.id, a2.id, h.task_id, h.reason, h.shared_state_json, h.timestamp
                ORDER BY h.timestamp DESC
                LIMIT $limit
                """
                res = graph.query(cypher, {"tenant_id": context.tenant_id, "limit": limit})
                for row in res.result_set:
                    try:
                        state = json.loads(row[4]) if row[4] else {}
                    except Exception:
                        state = {}
                    handoffs.append({
                        "from_agent": row[0],
                        "to_agent": row[1],
                        "task_id": row[2],
                        "reason": row[3],
                        "shared_state": state,
                        "timestamp": row[5]
                    })
            except Exception as e:
                logger.warning(f"Error fetching handoffs from FalkorDB: {e}")
        return handoffs

    def get_graph_context(self, context: TenantContext) -> Dict[str, Any]:
        """Inspect live FalkorDB graph state: active nodes, edges, turns, handoffs, and indexes."""
        context_data: Dict[str, Any] = {
            "tenant_id": context.tenant_id,
            "graph_name": context.graph_name,
            "falkordb_connected": self._falkor_connected,
            "node_counts": {},
            "edge_counts": {},
            "recent_turns": [],
            "agent_handoffs": [],
            "indexes": []
        }
        if not (self._falkor_connected and self._falkor_client):
            return context_data

        try:
            graph = self._get_graph(context.graph_name)
            # 1. Node counts by label
            lbl_res = graph.query("MATCH (n) WHERE n.tenant_id = $tenant_id RETURN labels(n), count(n)", {"tenant_id": context.tenant_id})
            for row in lbl_res.result_set:
                lbls, cnt = row[0], row[1]
                lbl_name = lbls[0] if isinstance(lbls, list) and lbls else str(lbls)
                context_data["node_counts"][lbl_name] = cnt

            # 2. Edge counts by relationship type
            edge_res = graph.query("MATCH (n1)-[r]->(n2) WHERE n1.tenant_id = $tenant_id RETURN type(r), count(r)", {"tenant_id": context.tenant_id})
            for row in edge_res.result_set:
                context_data["edge_counts"][row[0]] = row[1]

            # 3. Recent turns
            turn_res = graph.query("""
            MATCH (s:Session {tenant_id: $tenant_id})-[:HAS_TURN]->(t:Turn)
            RETURN s.id, t.id, t.role, t.content, t.created_at
            ORDER BY t.created_at DESC
            LIMIT 10
            """, {"tenant_id": context.tenant_id})
            for row in turn_res.result_set:
                context_data["recent_turns"].append({
                    "session_id": row[0],
                    "turn_id": row[1],
                    "role": row[2],
                    "content": row[3],
                    "created_at": row[4]
                })

            # 4. Agent handoffs
            context_data["agent_handoffs"] = self.get_recent_handoffs(context, limit=10)

            # 5. Indexes
            idx_res = graph.query("CALL db.indexes()")
            for row in idx_res.result_set:
                context_data["indexes"].append({
                    "label": row[0],
                    "properties": row[1],
                    "types": dict(row[2]) if hasattr(row[2], "items") else row[2],
                    "status": row[7] if len(row) > 7 else "UNKNOWN"
                })
        except Exception as e:
            logger.warning(f"Error fetching graph context from FalkorDB: {e}")
            context_data["error"] = str(e)

        return context_data


_repo: Optional[MemoryRepository] = None


def get_memory_repository() -> MemoryRepository:
    global _repo
    if _repo is None:
        _repo = MemoryRepository()
    return _repo
