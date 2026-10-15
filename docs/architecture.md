# OpsMemory Architecture & System Design

OpsMemory is an enterprise persistent-memory and multi-agent coordination system tailored for incident response and technical support workflows. It enables cross-session knowledge retention, temporal fact supersession, evidence-grounded reasoning, and coordinated multi-worker incident resolution across isolated organizational tenants.

---

## 1. System Overview & Component Responsibilities

```
                      +---------------------------------------+
                      |            FastAPI Gateway            |
                      |  - X-Tenant-Key Auth & Tenant Context |
                      |  - API Endpoints (/v1/chat, /ui)      |
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |       Deterministic Coordinator       |
                      |  - Conversation Session Manager       |
                      |  - Triage Dispatch & Worker Routing   |
                      |  - Concurrency Limiter & Cache        |
                      +-------+-----------------------+-------+
                              |                       |
               +--------------+                       +---------------+
               |                                                      |
               v                                                      v
+-----------------------------+                        +-----------------------------+
|        Triage Agent         |                        |      Retrieval Service      |
|  - Salience & Entity Extr.  |                        |  - Query Intent Router      |
|  - Provenance (Sources)     |                        |  - Graph Searcher (1-2 hop) |
|  - Incident Task Dispatch   |                        |  - SQLite FTS5 Keyword Rerank|
+--------------+--------------+                        |  - Reciprocal Rank Fusion   |
               |                                       |  - Evidence Bounded Packing |
               v                                       |  - Grounded RAG Engine      |
+-----------------------------+                        +--------------+--------------+
|     Task Board & Leases     |                                       |
|  - Atomic Lease Claiming    |                                       v
|  - Idempotency & Retries    |                        +-----------------------------+
|  - Resolver & Curator Agents|                        |         LLM Gateway         |
+--------------+--------------+                        |  - Google GenAI (Gemma 31B) |
               |                                       |  - Deterministic Mock       |
               +----------------------+----------------+  - Prompt Injection Defense |
                                      |
                                      v
                      +---------------------------------------+
                      |       Dual-Tier Persistence Layer     |
                      |  - FalkorDB: Tenant Graph Cypher Store|
                      |  - SQLite: Metadata & FTS5 Index      |
                      |  - Transparent Graceful Fallback      |
                      +---------------------------------------+
```

### Component Breakdown
1. **FastAPI Gateway (`app/api/`)**:
   - Authenticates requests via `X-Tenant-Key`.
   - Derives the tenant-scoped graph identifier (`tenant_<tenant_id>`) server-side, preventing client graph tampering.
   - Serves modern dark-themed web console and REST endpoints.
2. **Deterministic Coordinator (`app/agents/coordinator.py`)**:
   - Manages cross-session conversations and conversation state.
   - Determines salience, orchestrating triage extraction, incident task scheduling, and retrieval RAG.
   - Enforces per-tenant rate limits, asyncio semaphores, and single-flight query coalescing.
3. **Memory Lifecycle & Repository (`app/memory/`)**:
   - Manages episodic, semantic, and procedural memories.
   - Normalizes entities into tenant-scoped identifiers (`ent_<tenant>_<kind>_<slug>`).
   - Handles temporal supersession: old facts transition to `superseded` status with `valid_to` timestamps and `:SUPERSEDES` graph edges without silent overwriting.
   - Maintains derived SQLite FTS5 virtual table for lightning-fast lexical search.
4. **Retrieval & RAG Engine (`app/retrieval/`)**:
   - Classifies query intent: procedural runbook queries, historical queries, current facts, and incident reviews.
   - Queries FalkorDB graph adjacency (1-2 hops bidirectional `DEPENDS_ON` and `MENTIONS`).
   - Queries SQLite FTS5 with BM25 ranking.
   - Combines candidates via Reciprocal Rank Fusion ($k=60$) with confidence, graph proximity, procedural matching, and temporal supersession adjustments.
   - Packs top evidence within token budget, enclosing in `<untrusted_evidence>` isolation tags to thwart prompt injection.
   - Enforces grounded answering with memory ID citations or explicit abstention when evidence is insufficient.
5. **Task Board (`app/tasks/task_board.py`)**:
   - Backed by persistent storage with atomic lease-based claims (`lease_owner`, `lease_expires`).
   - Prevents duplicate work across distributed workers and provides automatic lease expiration recovery.

---

## 2. Graph Schema & Node Specifications

Every tenant operates in an isolated graph namespace (`tenant_<tenant_id>`).

### Node Types
- **Entity**:
  - `id`: Tenant-scoped identifier (e.g. `ent_acme_service_payments-api`)
  - `kind`: `service` | `team` | `user` | `version` | `concept` | `error`
  - `name`: Clean display name (e.g. `payments-api`)
  - `aliases`: Array of normalized aliases (e.g. `["payments", "billing service"]`)
  - `description`: Textual documentation
  - `tenant_id`: Scoped tenant identifier
  - `version`: Integer revision counter
- **Memory**:
  - `id`: Stable deterministic memory ID (e.g. `mem_semantic_acme_fact_payments-api-version-v24`)
  - `memory_type`: `episodic` | `semantic` | `procedural`
  - `subtype`: `incident` | `decision` | `fact` | `preference` | `runbook` | `outcome`
  - `title`: Short title
  - `summary`: Core factual statement
  - `status`: `active` | `superseded` | `conflicted` | `expired` | `deleted`
  - `confidence`: Floating-point scalar (0.0 to 1.0)
  - `valid_from`: ISO timestamp (e.g. `2026-10-01T12:00:00Z`)
  - `valid_to`: Nullable ISO timestamp
  - `observed_at`: Observation timestamp
  - `extraction_method`: `user_explicit` | `deterministic` | `llm`
  - `idempotency_key`: SHA-256 hash preventing duplicate writes
- **Source**:
  - `id`: Provenance ID (e.g. `src_conv42_msg17`)
  - `source_type`: `conversation` | `user_correction` | `agent_inference` | `seed` | `admin`
  - `raw_text_ref`: Original input snapshot
- **Task**:
  - `id`: Stable task ID (e.g. `task_resolve_incident_inc101_1`)
  - `task_type`: `RESOLVE_INCIDENT` | `CURATE_MEMORY`
  - `status`: `pending` | `claimed` | `done` | `failed`
  - `lease_owner`: Worker identifier
  - `lease_expires`: ISO expiration timestamp
  - `payload_json`, `result_json`: Structured context and resolution output

### Relationships
- `(:Memory)-[:MENTIONS]->(:Entity)`
- `(:Memory)-[:ABOUT]->(:Entity)`
- `(:Memory)-[:DERIVED_FROM]->(:Source)`
- `(:Memory)-[:SUPERSEDES]->(:Memory)`
- `(:Memory)-[:CONTRADICTS]->(:Memory)`
- `(:Memory)-[:RELATED_TO]->(:Memory)`
- `(:Task)-[:FOR]->(:Memory)`
- `(:Entity)-[:DEPENDS_ON]->(:Entity)`

---

## 3. Retrieval & Fusion Pipeline

### Mathematical Fusion Formulation
Given candidate sets from Graph Traversal ($R_{\text{graph}}$), SQLite FTS5 ($R_{\text{fts}}$), and optional Vector Search ($R_{\text{vec}}$), each candidate $m$ receives a base RRF score:

$$RRF(m) = \sum_{c \in \{graph, fts, vec\}} \frac{\mathbb{I}(m \in c)}{60 + \text{rank}_c(m)}$$

The final ranking score incorporates confidence, temporal validity, and domain relevance:

$$\text{FinalScore}(m) = RRF(m) + 0.20 \cdot \text{conf}(m) + 0.15 \cdot \text{recency}(m) + 0.20 \cdot \text{prox}(m) + 0.15 \cdot \text{intent}(m) + 0.25 \cdot \text{distinct}(m) - 0.30 \cdot \text{penalty}(m)$$

Where:
- $\text{penalty}(m) = 0.0$ for `active` memories (or `superseded` memories during historical queries or explicit direct targets).
- $\text{penalty}(m) = 0.30$ for `superseded` memories during standard current-state queries.
- $\text{penalty}(m) = 0.50$ for `conflicted` memories.
- $\text{penalty}(m) = 0.70$ for `expired` memories.
- Excluded entirely if `status == "deleted"`.

---

## 4. Multi-Tenant Security Boundary

1. **Authentication Gate**: Every non-public API request requires the `X-Tenant-Key` header.
2. **Server-Side Scoping**: Client requests can never specify the graph name; the graph name `tenant_<tenant_id>` is derived strictly on the server.
3. **Repository Enforcements**: All database operations (`SELECT`, `INSERT`, `UPDATE`, `FTS`) enforce `WHERE tenant_id = ?`.
4. **Cache Partitioning**: Cache keys prefix the tenant ID (`<tenant_id>:<query_hash>`). Any write to a tenant's graph invalidates only that tenant's cache partition.
5. **Prompt Injection Defense**: Retrieved memories are treated as untrusted data and wrapped in `<untrusted_evidence>`. System prompts strictly instruct the LLM that evidence text cannot alter execution instructions.
