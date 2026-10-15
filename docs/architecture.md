# OpsMemory Architecture & System Design

OpsMemory is an enterprise persistent-memory and multi-agent coordination system tailored for incident response and technical support workflows, built for **Track 2 (Agent Memory and Coordination)** of the **WeMakeDevs FalkorDB Hackathon (Graph Hacks: Context for AI Agents)**.

OpsMemory runs on **FalkorDB as its 100% native engine** for Graph Traversal, Full-Text Search, Dense Vector Similarity Search, Cross-Session Conversation Persistence, Multi-Agent Shared State Handoffs, and Atomic High-Concurrency Task Leases.

---

## 1. System Overview & Component Responsibilities

```
                      +---------------------------------------+
                      |            FastAPI Gateway            |
                      |  - X-Tenant-Key Auth & Tenant Context |
                      |  - REST Endpoints (/v1/chat, /ui)     |
                      |  - Inspection Endpoint (/v1/graph/ctx)|
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |       Deterministic Coordinator       |
                      |  - Persistent Conversation Graph      |
                      |  - Multi-Agent Handoff Dispatch       |
                      |  - Concurrency Limiter & Cache        |
                      +-------+-----------------------+-------+
                              |                       |
               +--------------+                       +---------------+
               |                                                      |
               v                                                      v
+-----------------------------+                        +-----------------------------+
|        Triage Agent         |                        |      Retrieval Service      |
|  - Salience & Entity Extr.  |                        |  - Query Intent Router      |
|  - Fuzzy Entity Resolution  |                        |  - Cypher Multi-Hop Graph   |
|  - Agent Handoff to Resolver|                        |  - FalkorDB Native Fulltext |
+--------------+--------------+                        |  - FalkorDB 64-dim Vector   |
               |                                       |  - Reciprocal Rank Fusion   |
               v                                       |  - Explainable Path Chains  |
+-----------------------------+                        +--------------+--------------+
|     FalkorDB Task Board     |                                       |
|  - Atomic Cypher Leases     |                                       v
|  - Mutual Exclusion Leases  |                        +-----------------------------+
|  - Resolver & Curator Agents|                        |         LLM Gateway         |
+--------------+--------------+                        |  - Google GenAI (Gemma)     |
               |                                       |  - Local Sovereign (Ollama) |
               +----------------------+----------------+  - Deterministic Mock       |
                                      |
                                      v
                      +---------------------------------------+
                      |        FalkorDB Native Engine         |
                      |  - Multi-Tenant Graph: tenant_<id>    |
                      |  - Range Indexes on Entities/Memories |
                      |  - RediSearch Native Full-Text Index  |
                      |  - Cosine Dense Vector Index (64-dim) |
                      |  - Multi-Agent Handoff Subgraph       |
                      +---------------------------------------+
```

### Component Breakdown
1. **FastAPI Gateway (`app/api/`)**:
   - Authenticates requests via `X-Tenant-Key`.
   - Derives the tenant-scoped graph identifier (`tenant_<tenant_id>`) server-side, preventing graph tampering or cross-tenant leaks.
   - Serves dark-themed web console, `/v1/chat`, `/v1/memories`, `/v1/tasks`, and `/v1/graph/context`.
2. **Deterministic Coordinator (`app/agents/coordinator.py`)**:
   - Persists `:Session` and `:Turn` nodes linked via `:HAS_TURN` and `:NEXT_TURN` in FalkorDB.
   - Orchestrates multi-agent handoffs between Triage, Resolver, and Curator agents.
   - Enforces per-tenant rate limits, asyncio semaphores, and single-flight query coalescing.
3. **Memory Lifecycle & Repository (`app/memory/repository.py`)**:
   - Manages episodic, semantic, and procedural memories directly in isolated tenant graphs.
   - Fuzzy entity resolution: resolves surface forms and aliases before node creation (`e.aliases`).
   - Temporal supersession: old facts transition to `superseded` status with `valid_to` timestamps and `:SUPERSEDES` graph edges.
   - Stores 64-dimensional semantic embeddings on `:Memory` nodes (`m.embedding = vecf32($embedding)`).
4. **Retrieval & RAG Engine (`app/retrieval/`)**:
   - **Semantic Vector Anchoring in FalkorDB**: Sub-millisecond start node discovery via FalkorDB native vector search on `:Entity` (`CALL db.idx.vector.queryNodes('Entity', 'embedding', ...)`) and graph alias matching, eliminating all static entity lists.
   - **Localized Subgraph Isolation & Cypher Traversal ($R_{\text{graph}}$)**: Bounded 1-to-3 hop bidirectional graph pattern matching over `-[r:DEPENDS_ON]-`, `[:ABOUT|MENTIONS]`, and `[:SUPERSEDES]` directly in FalkorDB.
   - **Native Fulltext Index ($R_{\text{fts}}$)**: FalkorDB RediSearch queries (`CALL db.idx.fulltext.queryNodes`) on titles, summaries, and subtypes.
   - **Native Vector Index ($R_{\text{vec}}$)**: Dense vector similarity (`CALL db.idx.vector.queryNodes`) using 64-dim cosine embeddings.
   - **Reciprocal Rank Fusion ($k=60$)**: Merges candidates across streams with confidence, graph proximity, intent matching, and status penalties.
   - **Explainable Reasoning Paths**: Extracts structured path chains (e.g. `["postgres-orders", "DEPENDS_ON", "payments-api", "DEPENDS_ON", "checkout-ui"]`).
5. **Task Board (`app/tasks/task_board.py`)**:
   - Atomic single-roundtrip Cypher task lease claiming in FalkorDB (`MATCH (t:Task) WHERE ... SET t.status = 'claimed' ... RETURN t`).
   - Mathematically guarantees mutual exclusion across concurrent workers with zero SQLite fallback.

---

## 2. Graph Schema & Node Specifications

Every tenant operates in an isolated FalkorDB graph namespace (`tenant_<tenant_id>`).

### Node Types
- **Entity**:
  - `id`: Tenant-scoped identifier (e.g. `ent_acme_service_payments-api`)
  - `kind`: `service` | `team` | `user` | `version` | `concept` | `error`
  - `name`: Clean display name (e.g. `payments-api`)
  - `aliases`: Array of normalized aliases (e.g. `["payments", "billing service"]`)
  - `description`: Textual documentation
  - `tenant_id`: Scoped tenant identifier
- **Memory**:
  - `id`: Stable deterministic memory ID (e.g. `mem_semantic_acme_fact_payments-api-current-version-is-v24`)
  - `memory_type`: `episodic` | `semantic` | `procedural`
  - `subtype`: `incident` | `decision` | `fact` | `preference` | `runbook` | `outcome`
  - `title`: Short title
  - `summary`: Core factual statement
  - `status`: `active` | `superseded` | `conflicted` | `expired` | `deleted`
  - `confidence`: Floating-point scalar (0.0 to 1.0)
  - `valid_from`: ISO timestamp (e.g. `2026-10-01T12:00:00Z`)
  - `valid_to`: Nullable ISO timestamp
  - `embedding`: 64-dimensional float vector (`vecf32`)
  - `idempotency_key`: SHA-256 hash preventing duplicate writes
- **Session & Turn**:
  - `Session`: `id`, `tenant_id`, `created_at`, `updated_at`
  - `Turn`: `id`, `session_id`, `role` (`user` | `assistant`), `content`, `created_at`
- **Agent**:
  - `id`: `agent_triage` | `agent_resolver` | `agent_curator`
  - `role`: Agent capability description
  - `tenant_id`: Scoped tenant identifier
- **Task**:
  - `id`: Stable task ID (e.g. `task_resolve-incident_inc101_1`)
  - `task_type`: `RESOLVE_INCIDENT` | `CURATE_MEMORY`
  - `status`: `pending` | `claimed` | `done` | `failed`
  - `lease_owner`: Worker identifier
  - `lease_expires`: ISO expiration timestamp

### Relationships
- `(:Session)-[:HAS_TURN]->(:Turn)`
- `(:Turn)-[:NEXT_TURN]->(:Turn)`
- `(:Memory)-[:DERIVED_FROM]->(:Turn)`
- `(:Memory)-[:MENTIONS]->(:Entity)`
- `(:Memory)-[:ABOUT]->(:Entity)`
- `(:Memory)-[:SUPERSEDES]->(:Memory)`
- `(:Entity)-[:DEPENDS_ON]->(:Entity)`
- `(:Agent)-[:HANDED_OFF_TO {task_id, reason, shared_state_json, timestamp}]->(:Agent)`
- `(:Agent)-[:ASSIGNED_TO]->(:Task)`
- `(:Task)-[:FOR]->(:Memory)`

---

## 3. FalkorDB Native Indexes & Exact Cypher Queries

### 1. Index Creation (scripts/init_schema.py & repository.py)
```cypher
-- Range Indexes for fast lookups
CREATE INDEX FOR (e:Entity) ON (e.id)
CREATE INDEX FOR (m:Memory) ON (m.id)
CREATE INDEX FOR (t:Task) ON (t.id)
CREATE INDEX FOR (s:Session) ON (s.id)
CREATE INDEX FOR (tu:Turn) ON (tu.id)
CREATE INDEX FOR (a:Agent) ON (a.id)

-- Native RediSearch Full-Text Index
CREATE FULLTEXT INDEX FOR (m:Memory) ON (m.title, m.summary, m.subtype)

-- Native Dense Vector Index (64-dimensional cosine)
CREATE VECTOR INDEX FOR (m:Memory) ON (m.embedding) OPTIONS {dimension: 64, similarityFunction: 'cosine'}
```

### 2. Hybrid Retrieval Queries
```cypher
-- Vector Similarity Search (R_vec)
CALL db.idx.vector.queryNodes('Memory', 'embedding', $k, vecf32($query_vec)) YIELD node, score
WHERE node.tenant_id = $tenant_id AND (node.status IS NULL OR node.status <> 'deleted')
RETURN node, score

-- Full-Text Keyword Search (R_fts)
CALL db.idx.fulltext.queryNodes('Memory', $fts_query) YIELD node, score
WHERE node.tenant_id = $tenant_id AND (node.status IS NULL OR node.status <> 'deleted')
RETURN node, score

-- Multi-Hop Graph Traversal & Explainable Path Chain (R_graph)
MATCH (e1:Entity {id: $eid, tenant_id: $tenant_id})-[r1:DEPENDS_ON]-(e2:Entity {tenant_id: $tenant_id})
OPTIONAL MATCH (e2)-[r2:DEPENDS_ON]-(e3:Entity {tenant_id: $tenant_id})
WHERE e3 IS NULL OR (e3 <> e1 AND e3 <> e2)
RETURN e1.name, type(r1), e2.name, type(r2), e3.name
```

### 3. Multi-Session Conversation Graph
```cypher
-- Record Session & Turn with Chained Order
MERGE (s:Session {id: $session_id, tenant_id: $tenant_id})
ON CREATE SET s.created_at = $now
SET s.updated_at = $now
CREATE (t:Turn {id: $turn_id, session_id: $session_id, role: $role, content: $content, created_at: $now})
MERGE (s)-[:HAS_TURN]->(t)

-- Link Sequential Turns
MATCH (prev:Turn {id: $last_turn_id}), (curr:Turn {id: $turn_id})
MERGE (prev)-[:NEXT_TURN]->(curr)

-- Provenance: Memory Derived from Turn
MATCH (m:Memory {id: $mem_id}), (t:Turn {id: $turn_id})
MERGE (m)-[:DERIVED_FROM]->(t)
```

### 4. Multi-Agent Shared State Handoffs & Atomic Task Claiming
```cypher
-- Record Agent Handoff Edge
MATCH (a1:Agent {id: $from_agent, tenant_id: $tenant_id})
MATCH (a2:Agent {id: $to_agent, tenant_id: $tenant_id})
CREATE (a1)-[:HANDED_OFF_TO {task_id: $task_id, reason: $reason, shared_state_json: $state, timestamp: $now}]->(a2)

-- Atomic Cypher Lease Claiming
MATCH (t:Task {id: $task_id, tenant_id: $tenant_id})
WHERE t.status = 'pending' OR (t.status = 'claimed' AND t.lease_expires < $now)
SET t.status = 'claimed', t.lease_owner = $worker_id, t.lease_expires = $lease_expires
RETURN t
```

---

## 4. Multi-Tenant Security Boundary

1. **Authentication Gate**: Every non-public API request requires the `X-Tenant-Key` header.
2. **Server-Side Scoping**: Client requests can never specify the graph name; `tenant_<tenant_id>` is derived strictly on the server.
3. **Graph-Level Data Isolation**: Each tenant's data lives in its own dedicated FalkorDB graph instance (`tenant_acme`, `tenant_beta`).
4. **Cache Partitioning**: Cache keys prefix tenant ID (`<tenant_id>:<query_hash>`). Any write to a tenant's graph invalidates only that tenant's cache partition.
5. **Prompt Injection Defense**: Retrieved memories are wrapped in `<untrusted_evidence>`. System prompts strictly instruct the LLM that evidence text cannot alter execution instructions.

---

## 5. Explainable Graph Paths & Inspection Endpoint

### Explainable Reasoning Paths (`reasoning_paths`)
Every response from `/v1/chat` includes structured `reasoning_paths: list[list[str]]` (e.g. `[["postgres-orders", "DEPENDS_ON", "payments-api", "DEPENDS_ON", "checkout-ui"]]`) and `agent_handoffs: list[dict]` detailing the exact graph traversal and coordination steps taken.

### Graph Context Inspection Endpoint (`GET /v1/graph/context`)
Authenticated via `X-Tenant-Key`, this endpoint returns:
- Active node counts grouped by label (`Entity`, `Memory`, `Task`, `Session`, `Turn`, `Agent`).
- Active edge counts grouped by relationship type (`DEPENDS_ON`, `MENTIONS`, `HAS_TURN`, `HANDED_OFF_TO`, `SUPERSEDES`).
- Recent conversation `:Session` turns.
- Multi-agent handoff history.
- Live FalkorDB indexes (`VECTOR`, `FULLTEXT`, `RANGE`) and operational statuses.
