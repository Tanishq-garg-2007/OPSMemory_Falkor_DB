# OpsMemory

> **Persistent-memory and multi-agent coordination system for incident response and technical support workflows.**

OpsMemory allows engineering and operations teams to remember past incidents, architectural decisions, service dependencies, versions, user preferences, and runbooks across sessions. Multiple specialized agents coordinate through a shared, lease-based persistent state graph.

---

## Key Highlights

- **Episodic, Semantic, & Procedural Memory**: Retains incident timelines, service topologies, and runbooks across sessions.
- **Evidence-Linked Temporal Graph**: Outdated facts are cleanly superseded with `valid_to` timestamps and `:SUPERSEDES` relationships rather than silently overwritten.
- **Strict Multi-Tenant Isolation**: Cryptographic tenant boundaries with server-derived graph scoping (`tenant_<tenant_id>`) preventing cross-tenant leakage.
- **Atomic Lease-Based Coordination**: Distributed task board with leases preventing duplicate work or split-brain worker collisions.
- **Dual-Tier Resilient Persistence**: Primary FalkorDB Cypher graph with an automatic, zero-crash embedded SQLite + FTS5 durable fallback.
- **Query-Adaptive Retrieval**: Multi-hop graph traversal combined with SQLite FTS5 BM25 search via Reciprocal Rank Fusion ($k=60$) and grounded abstention.
- **Zero-Monetary Cost**: Runs 100% locally with open-source tools and zero paid dependencies. Ready for Google Gemma 4 31B via Google GenAI SDK.
- **100% Benchmark Accuracy**: 88/88 test cases passing across Easy, Medium, Hard, and Adversarial test suites with 23.6ms p50 latency.

---

## Architecture Overview

```
User Query ---> FastAPI Gateway ---> Deterministic Coordinator ---> Retrieval & RAG
                       |                        |                          |
               Auth: X-Tenant-Key         Triage Agent            Graph Traversal (1-2 hop)
                       |                        |                 SQLite FTS5 BM25 Rerank
               Tenant Context Scope       Task Board              Reciprocal Rank Fusion
                                          (Atomic Leases)         Token-Bounded Packing
                                                |                 Grounded Answer & Citations
                                          Resolver Agent
                                                |
                              FalkorDB / SQLite Dual Persistence
```

See [docs/architecture.md](docs/architecture.md) for full design documentation.

---

## Quickstart

### 1. Requirements
- Python 3.11+ (Python 3.13 tested)
- Optional: Docker / Docker Compose for local FalkorDB

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

### 3. Configure Environment
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Default `.env` settings:
```ini
LLM_PROVIDER=google_genai
LLM_MODEL_ID=gemma-4-31b-it
GOOGLE_API_KEY=
REAL_LLM=0
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
SQLITE_DB_PATH=opsmemory.db
```

### 4. Initialize Database & Seed Fixtures
```bash
# Optional: start FalkorDB container
docker compose up -d falkordb

# Initialize schema and seed Acme & Beta tenants
python scripts/init_schema.py
python scripts/seed.py
```

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
*Current result: **31 passed in 6.41s** (100% pass rate).*

### End-to-End HTTP Smoke Test
```bash
python scripts/smoke.py
```
*Verifies `/healthz`, admin seeding, chat with citations, memories API, task board, cross-tenant isolation, and static UI.*

### Concurrency Stress Test
```bash
python scripts/benchmark_concurrency.py --requests 20 --concurrency 5
```
*Validates atomic lease contention races (exactly 1 winner), request coalescing, and zero duplicate memories under concurrent load.*

### LLM Connectivity Check
```bash
python scripts/check_llm.py
```

---

## Mandatory Benchmark Suite

OpsMemory includes a 88-question ground-truth evaluation suite across 4 difficulty tiers:

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
- **Easy**: 22/22 (100.0%) [p50: 23.6ms, p95: 33.3ms]
- **Medium**: 22/22 (100.0%) [p50: 22.9ms, p95: 41.4ms]
- **Hard**: 22/22 (100.0%) [p50: 35.6ms, p95: 205.3ms]
- **Edge / Adversarial**: 22/22 (100.0%) [p50: 19.0ms, p95: 40.1ms]
- **p50 Latency**: 23.6 ms
- **p95 Latency**: 92.2 ms

Reports are generated automatically in `reports/benchmark_<timestamp>.{json,csv,md}`. See [docs/evaluation.md](docs/evaluation.md) for full benchmark methodology.

---

## API Endpoints

| Method | Path | Description | Headers |
|---|---|---|---|
| `GET` | `/healthz` | System and DB health status | None |
| `POST` | `/v1/chat` | Main RAG & memory inquiry endpoint | `X-Tenant-Key` |
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
2. Cross-session multi-hop dependency analysis.
3. Procedural runbook recall.
4. Tenant isolation verification.
5. Persistent restart resilience.

---

## Documentation Index

- [Architecture Design & Schema](docs/architecture.md)
- [Evaluation & Benchmark Methodology](docs/evaluation.md)
- [Interactive Demo Walkthrough](docs/demo_script.md)
- [Troubleshooting Guide](docs/troubleshooting.md)
