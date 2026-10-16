"""Persistence repository: FalkorDB is the single source of truth.

Every entity, memory, task, source, conversation, session turn and relationship
lives in the tenant's FalkorDB graph. There is no SQLite (or any other) copy.
If FalkorDB is unreachable, operations raise ``DatabaseUnavailableError`` (HTTP 503)
instead of silently degrading to a different store.
"""
import json
import re
import threading
from typing import Optional, List, Dict, Any, Tuple, Set

from redis.exceptions import (
    ConnectionError as RedisConnectionError,
    ResponseError as RedisResponseError,
    TimeoutError as RedisTimeoutError,
)

from app.config import Settings, get_settings
from app.dependencies import TenantContext
from app.errors import ConflictError, DatabaseUnavailableError, ValidationError
from app.core.time import utc_now_iso
from app.core.cache import get_cache
from app.core.logging import get_logger
from app.memory.models import (
    EntityModel, MemoryModel, SourceModel, TaskModel, ConversationModel
)

logger = get_logger("repository")

# Cypher relationship types cannot be parameterised, so they are validated instead.
_REL_TYPE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

# Deterministic id prefixes (see app/core/ids.py) -> node label. Lets edge creation use
# the (label, id) index instead of scanning every node.
_LABEL_BY_PREFIX = (
    ("ent_", "Entity"),
    ("mem_", "Memory"),
    ("src_", "Source"),
    ("task_", "Task"),
    ("conv_", "Conversation"),
)

_INDEXED_LABELS = ["Entity", "Memory", "Task", "Source", "Conversation", "Session", "Turn", "Agent"]
_CONNECTION_ERRORS = (RedisConnectionError, RedisTimeoutError, ConnectionError, TimeoutError, OSError)


def _props(node: Any) -> Dict[str, Any]:
    if isinstance(node, dict):
        return node
    return getattr(node, "properties", None) or {}


def _label_for_id(node_id: str) -> str:
    for prefix, label in _LABEL_BY_PREFIX:
        if node_id.startswith(prefix):
            return f":{label}"
    return ""


class MemoryRepository:
    """FalkorDB-backed repository (graph + native full-text + native vector indexes)."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._falkor_client = None
        self._schema_ready: Set[str] = set()
        self._lock = threading.RLock()
        try:
            self._connect()
        except Exception as e:
            self._falkor_client = None
            logger.warning(
                f"FalkorDB unavailable on {self.settings.FALKORDB_HOST}:{self.settings.FALKORDB_PORT} ({e}). "
                "Requests will fail with 503 until it is reachable."
            )

    # ==========================
    # Connection management
    # ==========================
    @property
    def _falkor_connected(self) -> bool:
        return self._falkor_client is not None

    def _connect(self) -> None:
        from falkordb import FalkorDB
        timeout = self.settings.FALKORDB_TIMEOUT_SECONDS
        client = FalkorDB(
            host=self.settings.FALKORDB_HOST,
            port=self.settings.FALKORDB_PORT,
            password=self.settings.FALKORDB_PASSWORD or None,
            socket_connect_timeout=timeout,
            socket_timeout=max(timeout * 3, 10.0),
        )
        client.connection.ping()
        self._falkor_client = client
        logger.info("FalkorDB connection established successfully.")

    def _client(self):
        client = self._falkor_client
        if client is not None:
            return client
        with self._lock:
            if self._falkor_client is None:
                try:
                    self._connect()
                except Exception as e:
                    raise DatabaseUnavailableError(
                        f"FalkorDB is unreachable at {self.settings.FALKORDB_HOST}:{self.settings.FALKORDB_PORT}"
                    ) from e
            return self._falkor_client

    def _mark_down(self) -> None:
        with self._lock:
            self._falkor_client = None
            self._schema_ready.clear()

    def _graph(self, context: TenantContext):
        client = self._client()
        self._ensure_schema(context.graph_name, context.tenant_id)
        return client.select_graph(context.graph_name)

    def _get_graph(self, graph_name: str):
        """Raw graph handle (no schema bootstrap). Prefer ``graph_for``/``run_query``."""
        return self._client().select_graph(graph_name)

    def _exec(self, graph, cypher: str, params: Optional[Dict[str, Any]] = None):
        try:
            return graph.query(cypher, params or {})
        except _CONNECTION_ERRORS as e:
            self._mark_down()
            raise DatabaseUnavailableError("FalkorDB connection lost while executing a query") from e

    def run_query(self, context: TenantContext, cypher: str, params: Optional[Dict[str, Any]] = None):
        """Execute a parameterised Cypher query in the tenant's graph."""
        return self._exec(self._graph(context), cypher, params)

    def graph_for(self, context: TenantContext):
        """Tenant graph handle (schema bootstrapped). Connection errors surface as 503 on use."""
        return self._graph(context)

    # ==========================
    # Schema
    # ==========================
    def _ensure_schema(self, graph_name: str, tenant_id: str) -> None:
        if graph_name in self._schema_ready:
            return
        with self._lock:
            if graph_name in self._schema_ready:
                return
            self._init_graph(graph_name, tenant_id)
            self._schema_ready.add(graph_name)

    def init_tenant_schema(self, tenant_id: str) -> None:
        """Idempotently create indexes and default agents for a tenant graph."""
        graph_name = self.settings.tenant_graph_name(tenant_id)
        self._client()
        with self._lock:
            self._init_graph(graph_name, tenant_id)
            self._schema_ready.add(graph_name)

    def _init_graph(self, graph_name: str, tenant_id: str) -> None:
        graph = self._client().select_graph(graph_name)

        def ddl(stmt: str) -> None:
            try:
                self._exec(graph, stmt)
            except RedisResponseError as e:
                if "already" not in str(e).lower():
                    logger.warning(f"Index statement failed ({stmt}): {e}")

        for lbl in _INDEXED_LABELS:
            ddl(f"CREATE INDEX FOR (n:{lbl}) ON (n.id)")
        ddl("CREATE FULLTEXT INDEX FOR (m:Memory) ON (m.title, m.summary, m.subtype)")
        ddl("CREATE VECTOR INDEX FOR (m:Memory) ON (m.embedding) OPTIONS {dimension: 64, similarityFunction: 'cosine'}")
        ddl("CREATE VECTOR INDEX FOR (e:Entity) ON (e.embedding) OPTIONS {dimension: 64, similarityFunction: 'cosine'}")
        self._seed_agents(graph, tenant_id)

    def _seed_agents(self, graph, tenant_id: str) -> None:
        self._exec(graph, """
            MERGE (:Agent {id: 'agent_triage', tenant_id: $tenant_id, role: 'triage'})
            MERGE (:Agent {id: 'agent_resolver', tenant_id: $tenant_id, role: 'resolver'})
            MERGE (:Agent {id: 'agent_curator', tenant_id: $tenant_id, role: 'curator'})
        """, {"tenant_id": tenant_id})

    def check_health(self) -> Dict[str, Any]:
        """Check persistence layer health (FalkorDB is the only store)."""
        falkor_ok = False
        try:
            client = self._client()
            client.connection.ping()
            falkor_ok = True
        except Exception:
            self._mark_down()
        return {
            "ok": falkor_ok,
            "falkordb_connected": falkor_ok,
            "mode": "falkordb_native" if falkor_ok else "falkordb_unavailable",
        }

    # ==========================
    # Tenant registry (control graph)
    # ==========================
    CONTROL_GRAPH = "opsmemory_control"

    def _control_graph(self):
        graph = self._client().select_graph(self.CONTROL_GRAPH)
        if self.CONTROL_GRAPH not in self._schema_ready:
            try:
                graph.query("CREATE INDEX FOR (t:Tenant) ON (t.api_key_hash)")
            except RedisResponseError:
                pass  # index already exists
            self._schema_ready.add(self.CONTROL_GRAPH)
        return graph

    def register_tenant(self, tenant_id: str, api_key: str) -> None:
        """Create or update a tenant. Only the SHA-256 hash of its API key is stored."""
        from app.core.hashing import hash_api_key
        graph_name = self.settings.tenant_graph_name(tenant_id)  # validates tenant_id
        self._exec(
            self._control_graph(),
            """
            MERGE (t:Tenant {tenant_id: $tid})
            SET t.api_key_hash = $h, t.graph_name = $g,
                t.created_at = coalesce(t.created_at, $now)
            """,
            {"tid": tenant_id, "h": hash_api_key(api_key), "g": graph_name, "now": utc_now_iso()},
        )

    def find_tenant_by_api_key(self, api_key: str) -> Optional[Dict[str, str]]:
        """Return {'tenant_id', 'graph_name'} for a registered API key, else None."""
        from app.core.hashing import hash_api_key
        res = self._exec(
            self._control_graph(),
            "MATCH (t:Tenant {api_key_hash: $h}) RETURN t.tenant_id, t.graph_name LIMIT 1",
            {"h": hash_api_key(api_key)},
        )
        rows = res.result_set
        return {"tenant_id": rows[0][0], "graph_name": rows[0][1]} if rows else None

    def delete_all_tenant_data(self, context: TenantContext) -> int:
        """Delete every node/edge of a tenant (admin reset, tests). Returns nodes deleted."""
        graph = self._graph(context)
        res = self._exec(graph, "MATCH (n {tenant_id: $tid}) DETACH DELETE n", {"tid": context.tenant_id})
        self._seed_agents(graph, context.tenant_id)
        get_cache().invalidate_tenant(context.tenant_id)
        return int(getattr(res, "nodes_deleted", 0) or 0)

    # ==========================
    # Node -> model converters
    # ==========================
    def _node_to_task(self, node: Any) -> TaskModel:
        props = _props(node)
        return TaskModel(
            id=props.get("id", ""),
            tenant_id=props.get("tenant_id", ""),
            task_type=props.get("task_type", ""),
            status=props.get("status", "pending"),
            payload_json=props.get("payload_json", "{}"),
            result_json=props.get("result_json") or None,
            idempotency_key=props.get("idempotency_key", props.get("id", "")),
            lease_owner=props.get("lease_owner") or None,
            lease_expires=props.get("lease_expires") or None,
            attempts=int(props.get("attempts", 0) or 0),
            version=int(props.get("version", 1) or 1),
            created_at=props.get("created_at", utc_now_iso()),
            updated_at=props.get("updated_at", utc_now_iso()),
        )

    def _node_to_memory(self, node: Any) -> MemoryModel:
        props = _props(node)
        entities: List[str] = []
        if props.get("entities_json"):
            try:
                entities = json.loads(props["entities_json"])
            except Exception:
                entities = []
        elif isinstance(props.get("entities"), list):
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
            version=int(props.get("version", 1) or 1),
            created_by=props.get("created_by") or "system",
            extraction_method=ext_method,
            idempotency_key=props.get("idempotency_key", props.get("id", "")),
            entities=entities,
            source_id=props.get("source_id") or None,
            superseded_by=props.get("superseded_by") or None,
            supersedes_id=props.get("supersedes_id") or None,
        )

    def _node_to_entity(self, node: Any) -> EntityModel:
        props = _props(node)
        aliases: List[str] = []
        if isinstance(props.get("aliases"), list):
            aliases = props["aliases"]
        elif props.get("aliases_json"):
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
            version=int(props.get("version", 1) or 1),
            created_at=props.get("created_at", utc_now_iso()),
            updated_at=props.get("updated_at", utc_now_iso()),
        )

    # ==========================
    # Entity Operations
    # ==========================
    def upsert_entity(self, context: TenantContext, entity: EntityModel) -> EntityModel:
        context.assert_same_tenant(entity.tenant_id)
        from app.retrieval.vector_encoder import encode_vector

        embedding = encode_vector(f"{entity.name} {' '.join(entity.aliases)} {entity.description or ''}")
        now = utc_now_iso()
        res = self.run_query(context, """
            MERGE (e:Entity {id: $id, tenant_id: $tid})
            ON CREATE SET e.created_at = $created_at, e.version = $version
            ON MATCH SET e.version = coalesce(e.version, 1) + 1
            SET e.kind = $kind, e.name = $name, e.description = $desc,
                e.aliases = $aliases, e.aliases_json = $aliases_json,
                e.embedding = vecf32($embedding), e.updated_at = $now
            RETURN e
        """, {
            "id": entity.id, "tid": entity.tenant_id, "created_at": entity.created_at,
            "version": entity.version, "kind": entity.kind, "name": entity.name,
            "desc": entity.description or "", "aliases": list(entity.aliases),
            "aliases_json": json.dumps(entity.aliases), "embedding": embedding, "now": now,
        })
        get_cache().invalidate_tenant(context.tenant_id)
        return self._node_to_entity(res.result_set[0][0])

    save_entity = upsert_entity

    def find_anchor_entities(
        self,
        context: TenantContext,
        query: str,
        limit: int = 5
    ) -> List[EntityModel]:
        """Find starting graph anchors.

        Step 1 scans the tenant's entities in Python for name / alias / base-name matches (a full
        scan of this tenant's :Entity nodes, fine at tenant scale). Step 2 adds approximate
        nearest neighbours from the FalkorDB vector index.
        """
        from app.retrieval.vector_encoder import encode_vector

        anchors: List[EntityModel] = []
        seen_names: Set[str] = set()
        q_lower = query.lower()

        # 1. Exact / alias name matching over the tenant's entities
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

        # 2. FalkorDB ANN vector search on :Entity (strict similarity >= 0.35)
        try:
            res = self.run_query(context, """
                CALL db.idx.vector.queryNodes('Entity', 'embedding', $k, vecf32($vec)) YIELD node, score
                WHERE node.tenant_id = $tenant_id
                RETURN node, score
                ORDER BY score ASC
                LIMIT $limit
            """, {
                "k": limit * 3,
                "vec": encode_vector(query),
                "tenant_id": context.tenant_id,
                "limit": limit,
            })
            for row in res.result_set:
                ent = self._node_to_entity(row[0])
                dist = float(row[1]) if row[1] is not None else 1.0
                sim = max(0.0, 1.0 - dist)
                if sim >= 0.35 and ent.name not in seen_names:
                    seen_names.add(ent.name)
                    anchors.append(ent)
        except RedisResponseError as e:
            logger.debug(f"Entity vector index query: {e}")

        return anchors[:limit]

    def get_entity(self, context: TenantContext, entity_id: str) -> Optional[EntityModel]:
        res = self.run_query(
            context,
            "MATCH (e:Entity {id: $id, tenant_id: $tid}) RETURN e",
            {"id": entity_id, "tid": context.tenant_id},
        )
        return self._node_to_entity(res.result_set[0][0]) if res.result_set else None

    def list_entities(self, context: TenantContext, kind: Optional[str] = None) -> List[EntityModel]:
        if kind:
            res = self.run_query(
                context,
                "MATCH (e:Entity {tenant_id: $tid, kind: $kind}) RETURN e",
                {"tid": context.tenant_id, "kind": kind},
            )
        else:
            res = self.run_query(context, "MATCH (e:Entity {tenant_id: $tid}) RETURN e", {"tid": context.tenant_id})
        return [self._node_to_entity(row[0]) for row in res.result_set]

    # ==========================
    # Memory Operations
    # ==========================
    def save_memory(self, context: TenantContext, memory: MemoryModel) -> MemoryModel:
        context.assert_same_tenant(memory.tenant_id)

        # Idempotency: a memory with the same idempotency_key is returned unchanged.
        existing = self.get_memory_by_idempotency_key(context, memory.idempotency_key)
        if existing:
            return existing

        from app.core.ids import entity_id
        from app.retrieval.vector_encoder import encode_vector

        embedding = encode_vector(
            f"{memory.title} {memory.summary} {memory.subtype} {' '.join(memory.entities)}"
        )
        params = {
            "id": memory.id, "tid": memory.tenant_id, "mtype": memory.memory_type,
            "subtype": memory.subtype, "title": memory.title, "summary": memory.summary,
            "status": memory.status, "conf": memory.confidence, "valid_from": memory.valid_from,
            "valid_to": memory.valid_to or "", "observed_at": memory.observed_at,
            "created_at": memory.created_at, "ver": memory.version, "now": memory.updated_at,
            "idemp": memory.idempotency_key, "entities_json": json.dumps(memory.entities),
            "content_json": memory.content_json or "", "source_id": memory.source_id or "",
            "created_by": memory.created_by, "ext_method": memory.extraction_method,
            "superseded_by": memory.superseded_by or "", "supersedes_id": memory.supersedes_id or "",
            "embedding": embedding,
        }
        res = self.run_query(context, """
            MERGE (m:Memory {id: $id, tenant_id: $tid})
            ON CREATE SET m.memory_type = $mtype, m.subtype = $subtype, m.title = $title,
                m.valid_from = $valid_from, m.observed_at = $observed_at, m.created_at = $created_at,
                m.version = $ver, m.idempotency_key = $idemp, m.entities_json = $entities_json,
                m.source_id = $source_id, m.created_by = $created_by, m.extraction_method = $ext_method
            ON MATCH SET m.version = coalesce(m.version, 1) + 1
            SET m.summary = $summary, m.content_json = $content_json, m.status = $status,
                m.confidence = $conf, m.valid_to = $valid_to, m.updated_at = $now,
                m.superseded_by = $superseded_by, m.supersedes_id = $supersedes_id,
                m.embedding = vecf32($embedding)
            RETURN m
        """, params)
        saved = self._node_to_memory(res.result_set[0][0])

        # Relationships (edges are only created when both endpoints exist)
        if memory.entities:
            eids = [entity_id("service", n, tenant_id=context.tenant_id) for n in memory.entities]
            self.run_query(context, """
                MATCH (m:Memory {id: $mid, tenant_id: $tid})
                UNWIND $eids AS eid
                MATCH (e:Entity {id: eid, tenant_id: $tid})
                MERGE (m)-[:MENTIONS]->(e)
                MERGE (m)-[:ABOUT]->(e)
            """, {"mid": memory.id, "tid": context.tenant_id, "eids": eids})
        if memory.source_id:
            self.run_query(context, """
                MATCH (m:Memory {id: $mid, tenant_id: $tid}), (s:Source {id: $sid, tenant_id: $tid})
                MERGE (m)-[:DERIVED_FROM]->(s)
            """, {"mid": memory.id, "sid": memory.source_id, "tid": context.tenant_id})
        if memory.supersedes_id:
            self.run_query(context, """
                MATCH (m:Memory {id: $mid, tenant_id: $tid}), (old:Memory {id: $oid, tenant_id: $tid})
                MERGE (m)-[:SUPERSEDES]->(old)
            """, {"mid": memory.id, "oid": memory.supersedes_id, "tid": context.tenant_id})

        get_cache().invalidate_tenant(context.tenant_id)
        return saved

    def get_memory(self, context: TenantContext, memory_id: str) -> Optional[MemoryModel]:
        res = self.run_query(
            context,
            "MATCH (m:Memory {id: $id, tenant_id: $tid}) RETURN m",
            {"id": memory_id, "tid": context.tenant_id},
        )
        return self._node_to_memory(res.result_set[0][0]) if res.result_set else None

    def get_memory_by_idempotency_key(self, context: TenantContext, idempotency_key: str) -> Optional[MemoryModel]:
        res = self.run_query(
            context,
            "MATCH (m:Memory {idempotency_key: $key, tenant_id: $tid}) RETURN m LIMIT 1",
            {"key": idempotency_key, "tid": context.tenant_id},
        )
        return self._node_to_memory(res.result_set[0][0]) if res.result_set else None

    def update_memory_status(
        self,
        context: TenantContext,
        memory_id: str,
        new_status: str,
        valid_to: Optional[str] = None,
        expected_version: Optional[int] = None,
        superseded_by: Optional[str] = None
    ) -> Optional[MemoryModel]:
        """Versioned compare-and-set memory update (atomic single Cypher statement)."""
        version_guard = "AND m.version = $expected" if expected_version is not None else ""
        res = self.run_query(context, f"""
            MATCH (m:Memory {{id: $id, tenant_id: $tid}})
            WHERE true {version_guard}
            SET m.status = $status,
                m.valid_to = CASE WHEN $valid_to = '' THEN m.valid_to ELSE $valid_to END,
                m.superseded_by = CASE WHEN $superseded_by = '' THEN m.superseded_by ELSE $superseded_by END,
                m.version = coalesce(m.version, 1) + 1,
                m.updated_at = $now
            RETURN m
        """, {
            "id": memory_id, "tid": context.tenant_id, "status": new_status,
            "valid_to": valid_to or "", "superseded_by": superseded_by or "",
            "now": utc_now_iso(), "expected": expected_version,
        })
        if not res.result_set:
            current = self.get_memory(context, memory_id)
            if current and expected_version is not None:
                raise ConflictError(
                    f"Memory {memory_id} version mismatch (current: {current.version}, expected: {expected_version})"
                )
            return None
        get_cache().invalidate_tenant(context.tenant_id)
        return self._node_to_memory(res.result_set[0][0])

    def delete_memory(self, context: TenantContext, memory_id: str, hard_delete: bool = False) -> bool:
        """Soft delete (status='deleted', excluded from retrieval) or hard delete (DETACH DELETE).

        Returns False when the memory does not exist for this tenant.
        """
        params = {"id": memory_id, "tid": context.tenant_id, "now": utc_now_iso()}
        if hard_delete:
            res = self.run_query(
                context,
                "MATCH (m:Memory {id: $id, tenant_id: $tid}) DETACH DELETE m",
                params,
            )
            found = int(getattr(res, "nodes_deleted", 0) or 0) > 0
        else:
            res = self.run_query(context, """
                MATCH (m:Memory {id: $id, tenant_id: $tid})
                SET m.status = 'deleted', m.updated_at = $now
                RETURN count(m)
            """, params)
            found = bool(res.result_set and res.result_set[0][0])
        get_cache().invalidate_tenant(context.tenant_id)
        return found

    def list_memories(
        self,
        context: TenantContext,
        status: Optional[str] = None,
        memory_type: Optional[str] = None
    ) -> List[MemoryModel]:
        conditions = []
        params: Dict[str, Any] = {"tid": context.tenant_id}
        if status:
            conditions.append("m.status = $status")
            params["status"] = status
        if memory_type:
            conditions.append("m.memory_type = $mtype")
            params["mtype"] = memory_type
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        res = self.run_query(context, f"""
            MATCH (m:Memory {{tenant_id: $tid}})
            {where}
            RETURN m
            ORDER BY m.created_at DESC
        """, params)
        return [self._node_to_memory(row[0]) for row in res.result_set]

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
        if not _REL_TYPE_RE.match(rel_type):
            raise ValidationError(f"Invalid relationship type '{rel_type}'")
        self.run_query(context, f"""
            MATCH (a{_label_for_id(from_id)} {{id: $from_id, tenant_id: $tid}}),
                  (b{_label_for_id(to_id)} {{id: $to_id, tenant_id: $tid}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r.props_json = $props_json
        """, {
            "from_id": from_id, "to_id": to_id, "tid": context.tenant_id,
            "props_json": json.dumps(props or {}),
        })
        get_cache().invalidate_tenant(context.tenant_id)

    def get_related_entities(self, context: TenantContext, memory_id: str) -> List[EntityModel]:
        res = self.run_query(context, """
            MATCH (m:Memory {id: $mid, tenant_id: $tid})-[]->(e:Entity {tenant_id: $tid})
            RETURN DISTINCT e
        """, {"mid": memory_id, "tid": context.tenant_id})
        return [self._node_to_entity(row[0]) for row in res.result_set]

    def get_entity_dependencies(self, context: TenantContext, entity_id: str, hops: int = 2) -> List[EntityModel]:
        """Traverse DEPENDS_ON relationships up to ``hops`` directly in FalkorDB."""
        hops = max(1, min(int(hops), 5))
        res = self.run_query(context, f"""
            MATCH (e:Entity {{id: $eid, tenant_id: $tid}})-[:DEPENDS_ON*1..{hops}]-(dep:Entity {{tenant_id: $tid}})
            RETURN DISTINCT dep
        """, {"eid": entity_id, "tid": context.tenant_id})
        return [self._node_to_entity(row[0]) for row in res.result_set]

    # ==========================
    # Task Board Operations (Lease-based)
    # ==========================
    def create_task(self, context: TenantContext, task: TaskModel) -> TaskModel:
        """Idempotent task creation: one atomic MERGE keyed on the idempotency key."""
        context.assert_same_tenant(task.tenant_id)
        res = self.run_query(context, """
            MERGE (t:Task {idempotency_key: $idemp, tenant_id: $tid})
            ON CREATE SET t.id = $id, t.task_type = $task_type, t.status = $status,
                t.payload_json = $payload_json, t.result_json = $result_json,
                t.lease_owner = $lease_owner, t.lease_expires = $lease_expires,
                t.attempts = $attempts, t.version = $ver,
                t.created_at = $created_at, t.updated_at = $updated_at
            RETURN t
        """, {
            "id": task.id, "tid": task.tenant_id, "task_type": task.task_type,
            "status": task.status, "payload_json": task.payload_json,
            "result_json": task.result_json or "", "idemp": task.idempotency_key,
            "lease_owner": task.lease_owner or "", "lease_expires": task.lease_expires or "",
            "attempts": task.attempts, "ver": task.version,
            "created_at": task.created_at, "updated_at": task.updated_at,
        })
        return self._node_to_task(res.result_set[0][0])

    def get_task(self, context: TenantContext, task_id: str) -> Optional[TaskModel]:
        res = self.run_query(
            context,
            "MATCH (t:Task {id: $id, tenant_id: $tid}) RETURN t",
            {"id": task_id, "tid": context.tenant_id},
        )
        return self._node_to_task(res.result_set[0][0]) if res.result_set else None

    def list_tasks(self, context: TenantContext, status: Optional[str] = None) -> List[TaskModel]:
        params: Dict[str, Any] = {"tid": context.tenant_id}
        where = ""
        if status:
            where = "WHERE t.status = $status"
            params["status"] = status
        res = self.run_query(context, f"""
            MATCH (t:Task {{tenant_id: $tid}})
            {where}
            RETURN t
            ORDER BY t.created_at DESC
        """, params)
        return [self._node_to_task(row[0]) for row in res.result_set]

    def claim_task(
        self,
        context: TenantContext,
        task_id: str,
        worker_id: str,
        lease_seconds: int = 30
    ) -> Optional[TaskModel]:
        """Atomic lease-based claim in a single Cypher statement (FalkorDB serialises writes)."""
        from datetime import timedelta
        from app.core.time import utc_now
        lease_until = (utc_now() + timedelta(seconds=lease_seconds)).isoformat()
        res = self.run_query(context, """
            MATCH (t:Task {id: $task_id, tenant_id: $tid})
            WHERE t.status = 'pending' OR (t.status = 'claimed' AND t.lease_expires < $now)
            SET t.status = 'claimed', t.lease_owner = $worker_id, t.lease_expires = $lease_expires,
                t.attempts = coalesce(t.attempts, 0) + 1, t.version = coalesce(t.version, 1) + 1,
                t.updated_at = $now
            RETURN t
        """, {
            "task_id": task_id, "tid": context.tenant_id, "worker_id": worker_id,
            "lease_expires": lease_until, "now": utc_now_iso(),
        })
        return self._node_to_task(res.result_set[0][0]) if res.result_set else None

    def complete_task(
        self,
        context: TenantContext,
        task_id: str,
        worker_id: str,
        result_json: str
    ) -> Optional[TaskModel]:
        self.run_query(context, """
            MATCH (t:Task {id: $task_id, tenant_id: $tid})
            WHERE t.lease_owner = $worker_id
            SET t.status = 'done', t.result_json = $result_json,
                t.lease_owner = '', t.lease_expires = '',
                t.version = coalesce(t.version, 1) + 1, t.updated_at = $now
        """, {
            "task_id": task_id, "tid": context.tenant_id, "worker_id": worker_id,
            "result_json": result_json, "now": utc_now_iso(),
        })
        return self.get_task(context, task_id)

    def fail_task(
        self,
        context: TenantContext,
        task_id: str,
        worker_id: str,
        reason: str
    ) -> Optional[TaskModel]:
        self.run_query(context, """
            MATCH (t:Task {id: $task_id, tenant_id: $tid})
            SET t.status = 'failed', t.result_json = $result_json,
                t.lease_owner = '', t.lease_expires = '',
                t.version = coalesce(t.version, 1) + 1, t.updated_at = $now
        """, {
            "task_id": task_id, "tid": context.tenant_id,
            "result_json": json.dumps({"error": reason}), "now": utc_now_iso(),
        })
        return self.get_task(context, task_id)

    def recover_expired_leases(self, context: TenantContext) -> int:
        """Reset expired leases to pending, or fail the task once attempts >= 5. One atomic statement."""
        res = self.run_query(context, """
            MATCH (t:Task {tenant_id: $tid, status: 'claimed'})
            WHERE t.lease_expires <> '' AND t.lease_expires < $now
            SET t.result_json = CASE WHEN t.attempts >= 5 THEN $err ELSE t.result_json END,
                t.status = CASE WHEN t.attempts >= 5 THEN 'failed' ELSE 'pending' END,
                t.lease_owner = '', t.lease_expires = '', t.updated_at = $now
            RETURN count(t)
        """, {
            "tid": context.tenant_id, "now": utc_now_iso(),
            "err": json.dumps({"error": "Max lease retry attempts exceeded"}),
        })
        return int(res.result_set[0][0]) if res.result_set else 0

    # ==========================
    # Conversation & Source
    # ==========================
    def save_source(self, context: TenantContext, source: SourceModel) -> SourceModel:
        context.assert_same_tenant(source.tenant_id)
        self.run_query(context, """
            MERGE (s:Source {id: $id, tenant_id: $tid})
            ON CREATE SET s.source_type = $stype, s.conversation_id = $conv_id,
                s.message_id = $msg_id, s.created_at = $created_at
            SET s.raw_text_ref = $raw
        """, {
            "id": source.id, "tid": source.tenant_id, "stype": source.source_type,
            "conv_id": source.conversation_id or "", "msg_id": source.message_id or "",
            "created_at": source.created_at, "raw": source.raw_text_ref or "",
        })
        return source

    def save_conversation(self, context: TenantContext, conv: ConversationModel) -> ConversationModel:
        context.assert_same_tenant(conv.tenant_id)
        self.run_query(context, """
            MERGE (c:Conversation {id: $id, tenant_id: $tid})
            ON CREATE SET c.created_at = $created_at
            SET c.title = CASE WHEN $title = '' THEN coalesce(c.title, '') ELSE $title END,
                c.status = $status, c.updated_at = $updated_at
        """, {
            "id": conv.id, "tid": conv.tenant_id, "title": conv.title or "",
            "status": conv.status, "created_at": conv.created_at, "updated_at": conv.updated_at,
        })
        return conv

    def get_conversation(self, context: TenantContext, conv_id: str) -> Optional[ConversationModel]:
        res = self.run_query(
            context,
            "MATCH (c:Conversation {id: $id, tenant_id: $tid}) RETURN c",
            {"id": conv_id, "tid": context.tenant_id},
        )
        if not res.result_set:
            return None
        props = _props(res.result_set[0][0])
        return ConversationModel(
            id=props.get("id", ""),
            tenant_id=props.get("tenant_id", ""),
            title=props.get("title") or None,
            status=props.get("status", "active"),
            created_at=props.get("created_at", utc_now_iso()),
            updated_at=props.get("updated_at", utc_now_iso()),
        )

    def list_conversations(
        self,
        context: TenantContext,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Return conversation summaries for the tenant, newest first.

        Each row contains: id, created_at, preview (first user turn truncated to 80 chars),
        and turn_count.  Tenant isolation is enforced by scoping all queries to context.tenant_id.
        """
        # Fetch Conversation nodes ordered by created_at DESC
        res = self.run_query(context, """
            MATCH (c:Conversation {tenant_id: $tid})
            RETURN c.id, c.created_at
            ORDER BY c.created_at DESC
            SKIP $offset
            LIMIT $limit
        """, {"tid": context.tenant_id, "limit": limit, "offset": offset})

        summaries: List[Dict[str, Any]] = []
        for row in res.result_set:
            conv_id = row[0]
            created_at = row[1] or ""

            # First user turn (preview)
            turn_res = self.run_query(context, """
                MATCH (s:Session {id: $sid, tenant_id: $tid})-[:HAS_TURN]->(t:Turn {role: 'user'})
                RETURN t.content
                ORDER BY t.created_at ASC
                LIMIT 1
            """, {"sid": conv_id, "tid": context.tenant_id})
            preview = ""
            if turn_res.result_set:
                raw = turn_res.result_set[0][0] or ""
                preview = raw[:80] + ("…" if len(raw) > 80 else "")

            # Turn count
            count_res = self.run_query(context, """
                MATCH (s:Session {id: $sid, tenant_id: $tid})-[:HAS_TURN]->(t:Turn)
                RETURN count(t)
            """, {"sid": conv_id, "tid": context.tenant_id})
            turn_count = int(count_res.result_set[0][0]) if count_res.result_set else 0

            summaries.append({
                "id": conv_id,
                "created_at": created_at,
                "preview": preview,
                "turn_count": turn_count,
            })
        return summaries

    def get_conversation_turns(
        self,
        context: TenantContext,
        conversation_id: str,
    ) -> List[Dict[str, Any]]:
        """Return all turns for a conversation/session in chronological order.

        Scoped strictly to context.tenant_id to prevent cross-tenant leakage.
        """
        res = self.run_query(context, """
            MATCH (s:Session {id: $sid, tenant_id: $tid})-[:HAS_TURN]->(t:Turn)
            RETURN t.id, t.role, t.content, t.created_at
            ORDER BY t.created_at ASC
        """, {"sid": conversation_id, "tid": context.tenant_id})
        return [
            {
                "id": row[0],
                "role": row[1],
                "content": row[2],
                "created_at": row[3],
            }
            for row in res.result_set
        ]

    def record_session_turn(
        self,
        context: TenantContext,
        session_id: str,
        turn_id: str,
        role: str,
        content: str,
        memory_ids: Optional[List[str]] = None
    ) -> None:
        """Persist :Session and :Turn nodes with :HAS_TURN, :NEXT_TURN and :DERIVED_FROM edges."""
        tid = context.tenant_id
        now = utc_now_iso()

        # 1. Find previous turn in session to chain NEXT_TURN
        prev = self.run_query(context, """
            MATCH (s:Session {id: $session_id, tenant_id: $tid})-[:HAS_TURN]->(t:Turn)
            WHERE NOT (t)-[:NEXT_TURN]->()
            RETURN t.id
            ORDER BY t.created_at DESC
            LIMIT 1
        """, {"session_id": session_id, "tid": tid})
        prev_turn_id = prev.result_set[0][0] if prev.result_set else None

        # 2. Merge session, create turn, link HAS_TURN
        self.run_query(context, """
            MERGE (s:Session {id: $session_id, tenant_id: $tid})
            ON CREATE SET s.created_at = $now
            SET s.updated_at = $now
            CREATE (t:Turn {id: $turn_id, tenant_id: $tid, session_id: $session_id,
                            role: $role, content: $content, created_at: $now})
            MERGE (s)-[:HAS_TURN]->(t)
        """, {
            "session_id": session_id, "tid": tid, "turn_id": turn_id,
            "role": role, "content": content, "now": now,
        })

        # 3. Chain :NEXT_TURN
        if prev_turn_id and prev_turn_id != turn_id:
            self.run_query(context, """
                MATCH (p:Turn {id: $prev_id, tenant_id: $tid, session_id: $session_id}),
                      (c:Turn {id: $curr_id, tenant_id: $tid, session_id: $session_id})
                MERGE (p)-[:NEXT_TURN]->(c)
            """, {"prev_id": prev_turn_id, "curr_id": turn_id, "session_id": session_id, "tid": tid})

        # 4. Link extracted memories via (:Memory)-[:DERIVED_FROM]->(:Turn)
        if memory_ids:
            self.run_query(context, """
                UNWIND $mids AS mid
                MATCH (m:Memory {id: mid, tenant_id: $tid}), (t:Turn {id: $turn_id, tenant_id: $tid})
                MERGE (m)-[:DERIVED_FROM]->(t)
            """, {"mids": list(memory_ids), "tid": tid, "turn_id": turn_id})

    def record_agent_handoff(
        self,
        context: TenantContext,
        from_agent: str,
        to_agent: str,
        task_id: str,
        reason: str,
        shared_state: Optional[Dict[str, Any]] = None,
        memory_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> None:
        """Persist an explicit multi-agent handoff edge."""
        tid = context.tenant_id
        self.run_query(context, """
            MERGE (:Agent {id: $from_id, tenant_id: $tid})
            MERGE (:Agent {id: $to_id, tenant_id: $tid})
        """, {"from_id": from_agent, "to_id": to_agent, "tid": tid})

        self.run_query(context, """
            MATCH (a1:Agent {id: $from_id, tenant_id: $tid}), (a2:Agent {id: $to_id, tenant_id: $tid})
            CREATE (a1)-[h:HANDED_OFF_TO {task_id: $task_id, reason: $reason,
                                          turn_id: $turn_id, conversation_id: $conv_id,
                                          shared_state_json: $state, timestamp: $now}]->(a2)
        """, {
            "from_id": from_agent, "to_id": to_agent, "task_id": task_id, "reason": reason,
            "turn_id": turn_id or "", "conv_id": conversation_id or "",
            "state": json.dumps(shared_state or {}), "now": utc_now_iso(), "tid": tid,
        })

        if task_id:
            self.run_query(context, """
                MATCH (a:Agent {id: $agent_id, tenant_id: $tid}), (t:Task {id: $task_id, tenant_id: $tid})
                MERGE (a)-[:ASSIGNED_TO]->(t)
            """, {"agent_id": to_agent, "task_id": task_id, "tid": tid})

        if task_id and memory_id:
            self.run_query(context, """
                MATCH (t:Task {id: $task_id, tenant_id: $tid}), (m:Memory {id: $mem_id, tenant_id: $tid})
                MERGE (t)-[:FOR]->(m)
            """, {"task_id": task_id, "mem_id": memory_id, "tid": tid})

    # ==========================
    # Retrieval (native FalkorDB indexes)
    # ==========================
    def search_fts(self, context: TenantContext, query: str, limit: int = 20) -> List[Tuple[MemoryModel, float]]:
        """Native FalkorDB full-text search, filtered by tenant and excluding deleted memories."""
        clean_terms = "".join(c if c.isalnum() or c.isspace() else " " for c in query).strip()
        if not clean_terms:
            return []

        stop_words = {
            "what", "is", "the", "of", "to", "in", "for", "on", "a", "an", "and", "or",
            "how", "do", "does", "did", "can", "could", "would", "should", "at", "by",
            "from", "with", "about", "are", "was", "were", "be", "been", "being", "it",
            "this", "that", "there", "their", "my", "your", "our", "me", "tell", "give", "show"
        }
        terms = [t for t in clean_terms.split() if len(t) > 1 and t.lower() not in stop_words]
        if not terms:
            terms = [t for t in clean_terms.split() if len(t) > 1]
        if not terms:
            return []

        results: List[Tuple[MemoryModel, float]] = []
        try:
            res = self.run_query(context, """
                CALL db.idx.fulltext.queryNodes('Memory', $fts_query) YIELD node, score
                WHERE node.tenant_id = $tid AND (node.status IS NULL OR node.status <> 'deleted')
                RETURN node, score
                LIMIT $limit
            """, {"fts_query": " | ".join(terms), "tid": context.tenant_id, "limit": limit})
        except RedisResponseError as e:
            # A malformed full-text expression must not take the request down.
            logger.warning(f"FalkorDB fulltext query error: {e}")
            return results
        for row in res.result_set:
            raw_score = float(row[1]) if row[1] is not None else 1.0
            results.append((self._node_to_memory(row[0]), max(0.01, min(1.0, raw_score / 2.0))))
        return results

    def search_vector(
        self,
        context: TenantContext,
        query: str,
        limit: int = 10
    ) -> List[Tuple[MemoryModel, float]]:
        """Native FalkorDB vector similarity search using deterministic 64-dim embeddings."""
        from app.retrieval.vector_encoder import encode_vector

        results: List[Tuple[MemoryModel, float]] = []
        try:
            # FalkorDB cosine distance: 0 is identical, so similarity = 1.0 - score
            res = self.run_query(context, """
                CALL db.idx.vector.queryNodes('Memory', 'embedding', $k, vecf32($vec)) YIELD node, score
                WHERE node.tenant_id = $tid AND (node.status IS NULL OR node.status <> 'deleted')
                RETURN node, score
            """, {"k": limit * 2, "vec": encode_vector(query), "tid": context.tenant_id})
        except RedisResponseError as e:
            logger.warning(f"FalkorDB vector query error: {e}")
            return results
        for row in res.result_set:
            dist = float(row[1]) if row[1] is not None else 1.0
            sim = max(0.01, min(1.0, 1.0 - dist))
            if sim < 0.28:
                continue
            results.append((self._node_to_memory(row[0]), sim))
            if len(results) >= limit:
                break
        return results

    # ==========================
    # Graph inspection
    # ==========================
    def get_recent_handoffs(
        self,
        context: TenantContext,
        conversation_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        conv_filter = "AND h.conversation_id = $conv_id" if conversation_id else ""
        res = self.run_query(context, f"""
            MATCH (a1:Agent)-[h:HANDED_OFF_TO]->(a2:Agent)
            WHERE a1.tenant_id = $tid {conv_filter}
            RETURN a1.id, a2.id, h.task_id, h.reason, h.shared_state_json, h.timestamp, h.turn_id, h.conversation_id
            ORDER BY h.timestamp DESC
            LIMIT $limit
        """, {"tid": context.tenant_id, "conv_id": conversation_id or "", "limit": limit})
        handoffs: List[Dict[str, Any]] = []
        for row in res.result_set:
            try:
                state = json.loads(row[4]) if row[4] else {}
            except Exception:
                state = {}
            handoffs.append({
                "from_agent": row[0], "to_agent": row[1], "task_id": row[2],
                "reason": row[3], "shared_state": state, "timestamp": row[5],
                "turn_id": row[6] or None, "conversation_id": row[7] or None,
            })
        return handoffs

    def get_graph_context(self, context: TenantContext) -> Dict[str, Any]:
        """Inspect live graph state: node/edge counts, turns, handoffs and indexes."""
        tid = context.tenant_id
        data: Dict[str, Any] = {
            "tenant_id": tid,
            "graph_name": context.graph_name,
            "falkordb_connected": True,
            "node_counts": {},
            "edge_counts": {},
            "recent_turns": [],
            "agent_handoffs": [],
            "handoff_count": 0,
            "indexes": [],
        }
        for row in self.run_query(
            context, "MATCH (n) WHERE n.tenant_id = $tid RETURN labels(n), count(n)", {"tid": tid}
        ).result_set:
            lbls, cnt = row[0], row[1]
            data["node_counts"][lbls[0] if isinstance(lbls, list) and lbls else str(lbls)] = cnt

        for row in self.run_query(
            context, "MATCH (n1)-[r]->(n2) WHERE n1.tenant_id = $tid RETURN type(r), count(r)", {"tid": tid}
        ).result_set:
            data["edge_counts"][row[0]] = row[1]

        for row in self.run_query(context, """
            MATCH (s:Session {tenant_id: $tid})-[:HAS_TURN]->(t:Turn)
            RETURN s.id, t.id, t.role, t.content, t.created_at
            ORDER BY t.created_at DESC
            LIMIT 10
        """, {"tid": tid}).result_set:
            data["recent_turns"].append({
                "session_id": row[0], "turn_id": row[1], "role": row[2],
                "content": row[3], "created_at": row[4],
            })

        data["agent_handoffs"] = self.get_recent_handoffs(context, limit=10)
        handoff_count_res = self.run_query(
            context,
            "MATCH (a1:Agent {tenant_id: $tid})-[h:HANDED_OFF_TO]->(a2:Agent {tenant_id: $tid}) RETURN count(h)",
            {"tid": tid}
        )
        handoff_count = int(handoff_count_res.result_set[0][0]) if handoff_count_res.result_set else 0
        data["handoff_count"] = handoff_count
        data["edge_counts"]["HANDED_OFF_TO"] = handoff_count

        for row in self.run_query(context, "CALL db.indexes()").result_set:
            data["indexes"].append({
                "label": row[0],
                "properties": row[1],
                "types": dict(row[2]) if hasattr(row[2], "items") else row[2],
                "status": row[7] if len(row) > 7 else "UNKNOWN",
            })
        return data

    def get_entity_timeline(
        self,
        context: TenantContext,
        entity_id: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """Return chronological memory timeline for an entity linked via ABOUT.

        Returns None if the entity does not exist for the tenant.
        """
        tid = context.tenant_id
        ent_res = self.run_query(context, """
            MATCH (e:Entity {tenant_id: $tid})
            WHERE e.id = $eid OR toLower(e.name) = toLower($eid)
            RETURN e LIMIT 1
        """, {"tid": tid, "eid": entity_id})
        if not ent_res.result_set:
            return None

        mem_res = self.run_query(context, """
            MATCH (m:Memory {tenant_id: $tid})-[:ABOUT]->(e:Entity {tenant_id: $tid})
            WHERE e.id = $eid OR toLower(e.name) = toLower($eid)
            OPTIONAL MATCH (m)-[:SUPERSEDES]->(old:Memory)
            OPTIONAL MATCH (new:Memory)-[:SUPERSEDES]->(m)
            RETURN m, old.id, new.id
            ORDER BY m.valid_from ASC, m.created_at ASC
        """, {"tid": tid, "eid": entity_id})

        timeline = []
        seen = set()
        for row in mem_res.result_set:
            mem = self._node_to_memory(row[0])
            if mem.id in seen:
                continue
            seen.add(mem.id)
            old_id = row[1]
            new_id = row[2]
            timeline.append({
                "id": mem.id,
                "title": mem.title,
                "summary": mem.summary,
                "valid_from": mem.valid_from,
                "valid_to": mem.valid_to,
                "status": mem.status,
                "supersedes": mem.supersedes_id or (old_id if old_id else None),
                "superseded_by": mem.superseded_by or (new_id if new_id else None),
            })
        return timeline


_repo: Optional[MemoryRepository] = None


def get_memory_repository() -> MemoryRepository:
    global _repo
    if _repo is None:
        _repo = MemoryRepository()
    return _repo