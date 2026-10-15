# OpsMemory

> **Persistent-memory and multi-agent coordination system for incident response and technical support workflows.**  
> Built for **Track 2 (Agent Memory and Coordination)** of the **WeMakeDevs FalkorDB Hackathon (Graph Hacks: Context for AI Agents)**.

OpsMemory allows engineering and operations teams to remember past incidents, architectural decisions, service dependencies, versions, user preferences, and runbooks across sessions. Multiple specialized agents coordinate through a shared, lease-based persistent state graph running natively in **FalkorDB**.

---

## Key Highlights

- **100% Native FalkorDB Engine**: Primary multi-tenant graph, RediSearch full-text, and dense vector similarity search engine running entirely on FalkorDB with zero dead SQL/SQLite fallbacks.
- **Dynamic Semantic Vector Anchoring**: Sub-millisecond graph entry point discovery via FalkorDB ANN vector search on `:Entity` and live graph alias matching, eliminating static entity lists.
- **Localized Subgraph Isolation & Cypher Traversal**: Bounded 1-to-3 hop Cypher traversal extracting verified reasoning path chains.
- **Episodic, Semantic, & Procedural Memory**: Retains incident timelines, service topologies, and runbooks across sessions.
- **Evidence-Linked Temporal Graph**: Outdated facts are cleanly superseded with `valid_to` timestamps and `:SUPERSEDES` relationships rather than silently overwritten.
- **Persistent Cross-Session Conversation Graph**: Persists conversation turns as `:Session` and `:Turn` nodes chained via `:NEXT_TURN` with memory provenance edges (`:DERIVED_FROM`).
- **Graph-Mediated Multi-Agent Handoffs**: Direct Cypher edge handoffs (`(:Agent)-[:HANDED_OFF_TO]->(:Agent)`) transferring state between Triage, Resolver, and Curator agents.
- **Atomic Cypher Task Leases**: Single-roundtrip atomic Cypher task claiming (`MATCH (t:Task) WHERE ... SET t.status = 'claimed' RETURN t`) mathematically guaranteeing zero double-claims under high concurrency.
- **Native Hybrid RRF Retrieval**: Seamlessly fuses FalkorDB Dense Vector Search (`db.idx.vector.queryNodes`), Full-Text Search (`db.idx.fulltext.queryNodes`), and Multi-Hop Cypher Traversal via Reciprocal Rank Fusion ($k=60$).
- **Explainable Graph Paths**: Outputs readable dependency chains (e.g. `["postgres-orders", "DEPENDS_ON", "payments-api", "DEPENDS_ON", "checkout-ui"]`) in `reasoning_paths`.
- **Live Graph Context Inspection**: Dedicated `GET /v1/graph/context` endpoint allowing judges and UI consoles to inspect active nodes, edges, turns, handoffs, and indexes.
- **Rigorous Ground-Truth Benchmark**: 88/88 test cases passing at **100.0% accuracy** across Easy, Medium, Hard, and Adversarial test suites.

---

## Architecture Overview

```
User Query ---> FastAPI Gateway ---> Deterministic Coordinator ---> Hybrid Retrieval & RAG
                       |                        |                          |
               Auth: X-Tenant-Key         Triage Agent            FalkorDB Vector Search
                       |                        |                 FalkorDB Full-Text Search
               Tenant Context Scope       Task Board              Cypher Multi-Hop Graph
                                          (Atomic Cypher Leases)  Reciprocal Rank Fusion
                                                |                 Explainable Paths
                                          Resolver Agent          Token-Bounded Packing
                                                |                 Grounded Answer & Citations
                                          Curator Agent
                                                |
                                    FalkorDB Native Engine
```

See [docs/architecture.md](docs/architecture.md) for full design documentation.

---

## Quickstart

### 1. Requirements
- Python 3.11+ (Python 3.13 tested)
- Docker / Docker Compose for local FalkorDB

### 2. Environment Setup
```bash
# Clone and enter workspace
cd OPSMemory

# Create virtual environment and activate
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -e .
```

### 3. Start FalkorDB
```bash
docker compose up -d falkordb
```
Verify FalkorDB is listening on `localhost:6379`:
```bash
python -c "import socket; s=socket.create_connection(('localhost', 6379), timeout=3); print('FALKORDB_PORT_OK'); s.close()"
```

### 4. Initialize Schema & Seed Fixtures
```bash
python scripts/init_schema.py
python scripts/seed.py
```
This idempotently creates the following FalkorDB indexes in `tenant_acme` and `tenant_beta`:
- Range Indexes on `(:Entity {id})`, `(:Memory {id})`, `(:Task {id})`, `(:Session {id})`, `(:Turn {id})`, `(:Agent {id})`.
- Full-Text Index on `:Memory(title, summary, subtype)`.
- Dense Vector Index on `:Memory(embedding)` with 64 dimensions and cosine similarity.

### 5. Start the Application
```bash
python -m uvicorn app.main:app --port 8000
```
Open **`http://localhost:8000/ui/`** in your browser to access the interactive web console.

---

## Terminal Verification & Testing

All verification in OpsMemory is terminal-driven without requiring manual clicking.

### Unit & Integration Tests (pytest)
```bash
python -m pytest -q
```
*Result: **31 passed** (100% pass rate).*

### End-to-End HTTP Smoke Test
```bash
python scripts/smoke.py
```
*Verifies `/healthz`, admin seeding, chat with citations, memories API, task board, cross-tenant isolation, and static UI.*

### Concurrency Stress Test
```bash
python scripts/benchmark_concurrency.py --requests 20 --concurrency 5
```
*Validates atomic Cypher lease contention races (exactly 1 winner), request coalescing, and zero duplicate memories under concurrent load.*

### Judge Graph Inspection Endpoint
```bash
curl -H "X-Tenant-Key: test_acme_key" http://localhost:8000/v1/graph/context
```
*Returns active node counts, edge counts, recent conversation turns, agent handoffs, and FalkorDB index statuses.*

---

## Mandatory Benchmark Suite

OpsMemory includes an 88-question ground-truth evaluation suite across 4 difficulty tiers:

```bash
# Run all 88 test cases
python -m eval.run --suite all

# Run specific difficulty suites
python -m eval.run --suite easy
python -m eval.run --suite medium
python -m eval.run --suite hard
python -m eval.run --suite edge
```

### Benchmark Results
- **Overall Accuracy**: **100.0% (88/88 passed)**
- **Easy**: 22/22 (100.0%) [p50: 30.5ms, p95: 36.4ms]
- **Medium**: 22/22 (100.0%) [p50: 30.8ms, p95: 37.2ms]
- **Hard**: 22/22 (100.0%) [p50: 35.4ms, p95: 210.1ms]
- **Edge / Adversarial**: 22/22 (100.0%) [p50: 28.0ms, p95: 34.3ms]
- **p50 Latency**: 30.8 ms
- **p95 Latency**: 75.3 ms

Reports are generated automatically in `reports/benchmark_<timestamp>.{json,csv,md}`. See [docs/evaluation.md](docs/evaluation.md) for full benchmark methodology.

---

## API Endpoints

| Method | Path | Description | Headers |
|---|---|---|---|
| `GET` | `/healthz` | System and FalkorDB health status | None |
| `POST` | `/v1/chat` | Main RAG, memory inquiry & explainable reasoning paths | `X-Tenant-Key` |
| `GET` | `/v1/graph/context` | Live FalkorDB graph state inspection for judges & UI | `X-Tenant-Key` |
| `GET` | `/v1/conversations/{id}`| Retrieve conversation history | `X-Tenant-Key` |
| `GET` | `/v1/memories/{id}` | Inspect memory by ID | `X-Tenant-Key` |
| `GET` | `/v1/tasks` | List coordination tasks on task board | `X-Tenant-Key` |
| `POST` | `/v1/admin/seed` | Seed deterministic test fixtures | `X-Tenant-Key` |
| `POST` | `/v1/admin/reset` | Wipe tenant memory records | `X-Tenant-Key` |
| `GET` | `/ui/` | Interactive web console UI | None |

---

## Interactive Demo

See [docs/demo_script.md](docs/demo_script.md) for step-by-step terminal and UI instructions covering:
1. Fact recall & temporal supersession.
2. Cross-session multi-hop dependency analysis with explainable graph paths.
3. Graph-mediated multi-agent handoffs & atomic Cypher task leases.
4. Tenant isolation verification.
5. Persistent restart resilience in FalkorDB.

---

## Documentation Index

- [Architecture Design & Schema](docs/architecture.md)
- [Evaluation & Benchmark Methodology](docs/evaluation.md)
- [Interactive Demo Walkthrough](docs/demo_script.md)
- [Troubleshooting Guide](docs/troubleshooting.md)
