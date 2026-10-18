# OpsMemory

> **Persistent memory and multi-agent coordination for incident response and technical-support workflows.**
> Built for **Track 2 (Agent Memory and Coordination)** of the **WeMakeDevs FalkorDB Hackathon (Graph Hacks: Context for AI Agents)**.

OpsMemory lets engineering and operations teams remember past incidents, decisions, service dependencies, versions, user preferences and runbooks across sessions. Specialised agents (triage, resolver, curator) coordinate through a shared, lease-based state graph that lives entirely in **FalkorDB**.

- **Demo video:** _add link here before submitting_ (shot list in [docs/demo_script.md](docs/demo_script.md))
- **Live deployment:** [https://opsmemory-9uet.onrender.com](https://opsmemory-9uet.onrender.com) (Web Console at [`/ui/`](https://opsmemory-9uet.onrender.com/ui/))
- **AI assistance:** see [AI disclosure](#ai-disclosure)

---

## What it does

- **FalkorDB is the only datastore.** Entities, memories, tasks, sources, conversations, turns and agent handoffs are nodes and edges in a per-tenant graph (`tenant_<id>`). There is no SQLite or any secondary copy. If FalkorDB is unreachable the API answers `503` instead of degrading silently.
- **Temporal memory.** A newer fact supersedes an older one (`valid_to` is set and a `:SUPERSEDES` edge is written). Superseded facts stay queryable for "what was it before?" questions.
- **Hybrid retrieval.** FalkorDB vector search, full-text search and directed Cypher traversal are fused with Reciprocal Rank Fusion (k = 60), packed within a token budget and answered with citations.
- **Grounded abstention.** If nothing the system remembers relates to a question, it abstains instead of improvising (`app/retrieval/grounding.py`); the answer prompt also tells the LLM to abstain when evidence is insufficient.
- **Explainable paths.** `reasoning_paths` returns dependency chains in their real direction, e.g. `checkout-ui DEPENDS_ON payments-api DEPENDS_ON postgres-orders`.
- **Multi-agent handoffs and atomic task leases.** Handoffs are `(:Agent)-[:HANDED_OFF_TO]->(:Agent)` edges. Tasks are claimed with a single Cypher `MATCH ... SET` so two workers cannot claim the same task.
- **Tenant isolation.** Hashed API keys in a control graph, a server-side graph name per tenant, strict tenant-id format (`[a-z0-9_]`, 1-48 chars) and a separate admin key.

## Architecture

```
User ---> FastAPI ---> Coordinator ---> Hybrid retrieval + RAG
              |            |                  |
        X-Tenant-Key   Triage agent      FalkorDB vector search
              |            |             FalkorDB full-text search
        Tenant context  Task board       Directed Cypher traversal
                       (Cypher leases)   Reciprocal Rank Fusion
                           |             Grounding gate
                      Resolver agent     Evidence packing -> answer + citations
                           |
                      Curator agent
                           |
                  FalkorDB (graph per tenant)
```

Full design: [docs/architecture.md](docs/architecture.md).

## Graph data model

Nodes (all carry `tenant_id`):

| Label | Purpose |
|---|---|
| `:Entity` | Service, team, user, version, concept (`kind`, `name`, `aliases`, `embedding`) |
| `:Memory` | Episodic / semantic / procedural memory (`status`, `confidence`, `valid_from`, `valid_to`, `embedding`) |
| `:Source`, `:Conversation` | Provenance of a memory |
| `:Session`, `:Turn` | Cross-session conversation history |
| `:Task`, `:Agent` | Coordination board and the three agents |

Relationships:

```
(:Entity)-[:DEPENDS_ON]->(:Entity)          direction is meaningful: A depends on B
(:Memory)-[:ABOUT|MENTIONS]->(:Entity)
(:Memory)-[:SUPERSEDES]->(:Memory)          newer fact replaces older fact
(:Memory)-[:DERIVED_FROM]->(:Source|:Turn)
(:Session)-[:HAS_TURN]->(:Turn)-[:NEXT_TURN]->(:Turn)
(:Agent)-[:HANDED_OFF_TO {task_id, reason, shared_state_json, timestamp}]->(:Agent)
(:Task)-[:FOR]->(:Memory)    (:Agent)-[:ASSIGNED_TO]->(:Task)
```

Tenants are registered in a control graph, `opsmemory_control` (`(:Tenant {tenant_id, graph_name, api_key_hash})`); raw API keys are never stored.

## Cypher Queries and Graph Algorithms

OpsMemory relies on native FalkorDB Cypher queries and graph traversal algorithms to power persistent memory, multi-hop reasoning, and agent coordination:

### 1. Graph Algorithms

- **Directed Multi-Hop Dependency Traversal (Forward Reachability)**:
  Traverses directed `(:Entity)-[:DEPENDS_ON]->(:Entity)` edges up to 3 hops deep to construct explainable `reasoning_paths` (e.g., `checkout-ui -> payments-api -> postgres-orders`).
- **Blast-Radius Impact Analysis (Reverse Reachability)**:
  Traverses reverse incoming dependency edges (`(dependent)-[:DEPENDS_ON]->(failed_service)`) to calculate indirect outages and downstream affected user interfaces.
- **Temporal Supersession Chain Traversal (DAG Resolution)**:
  Traverses `(:Memory)-[:SUPERSEDES]->(:Memory)` directed acyclic graphs to distinguish current production facts from historical/outdated context, resolving temporal queries like *"What was the version before v2.4?"*.
- **Multi-Modal Reciprocal Rank Fusion (RRF Algorithm, $k=60$)**:
  Fuses candidate rankings from three independent retrieval engines inside FalkorDB:
  $$\text{RRF Score}(d) = \sum_{m \in \{\text{vector}, \text{fts}, \text{graph}\}} \frac{w_m}{k + \text{rank}_m(d)}$$
  Augmented with confidence multipliers, recency decay, and status penalties.
- **Distributed Mutual Exclusion (Atomic Lease Claim Algorithm)**:
  Ensures exactly-once task execution across distributed agents using atomic single-roundtrip Cypher conditional writes with lease expiration timeouts.

### 2. Core Cypher Queries

```cypher
-- Indexes (per tenant graph)
CREATE FULLTEXT INDEX FOR (m:Memory) ON (m.title, m.summary, m.subtype)
CREATE VECTOR INDEX FOR (m:Memory) ON (m.embedding) OPTIONS {dimension: 64, similarityFunction: 'cosine'}

-- 1. Forward Dependency Traversal (What does X depend on?)
MATCH (e1:Entity {tenant_id: $tenant_id}) WHERE e1.id = $eid OR toLower(e1.name) = toLower($ent_name)
MATCH (e1)-[:DEPENDS_ON]->(e2:Entity {tenant_id: $tenant_id})
OPTIONAL MATCH (e2)-[:DEPENDS_ON]->(e3:Entity {tenant_id: $tenant_id}) WHERE e3 <> e1
RETURN e1.name, e2.name, e3.name

-- 2. Blast Radius Analysis (What downstream services break if X fails?)
MATCH (e1:Entity {tenant_id: $tenant_id}) WHERE e1.id = $eid OR toLower(e1.name) = toLower($ent_name)
MATCH (e2:Entity {tenant_id: $tenant_id})-[:DEPENDS_ON]->(e1)
OPTIONAL MATCH (e3:Entity {tenant_id: $tenant_id})-[:DEPENDS_ON]->(e2) WHERE e3 <> e1
RETURN e3.name, e2.name, e1.name

-- 3. Hybrid Retrieval: Native Vector Similarity Search
CALL db.idx.vector.queryNodes('Memory', 'embedding', $k, vecf32($query_vec)) YIELD node, score
RETURN node, score

-- 4. Hybrid Retrieval: RediSearch Full-Text Search
CALL db.idx.fulltext.queryNodes('Memory', $fts_query) YIELD node, score
RETURN node, score

-- 5. Atomic Task Claim (Mutual Exclusion with Lease)
MATCH (t:Task {id: $task_id, tenant_id: $tenant_id})
WHERE t.status = 'pending' OR (t.status = 'claimed' AND t.lease_expires < $now)
SET t.status = 'claimed', t.lease_owner = $worker_id, t.lease_expires = $lease_expires
RETURN t

-- 6. Temporal Supersession Edge Creation
MATCH (m_new:Memory {id: $new_id, tenant_id: $tid}), (m_old:Memory {id: $old_id, tenant_id: $tid})
SET m_old.status = 'superseded', m_old.valid_to = $now, m_old.superseded_by = m_new.id
CREATE (m_new)-[:SUPERSEDES]->(m_old)
```

## Setup

Requirements: Python 3.11+, Docker (for FalkorDB).

```bash
git clone https://github.com/Tanishq-garg-2007/OPSMemory.git && cd OPSMemory
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"

cp .env.example .env                 # then edit .env:
#   ADMIN_API_KEY=<long random string>   (admin endpoints stay disabled until this is set)
#   LLM_PROVIDER=mock                    (offline demo) or google_genai with GOOGLE_API_KEY=...

docker compose up -d falkordb        # FalkorDB on localhost:6379
python scripts/init_schema.py        # registers demo tenants (hashed keys) + creates indexes
python scripts/seed.py               # loads fixtures for acme and beta (gamma = hold-out set)
python -m uvicorn app.main:app --port 8000
```

Open `http://localhost:8000/ui/` for the web console.

Everything in one container set instead: `docker compose up -d --build`, then `docker compose exec app python scripts/init_schema.py`.

### Authentication

| Use | Header | Value |
|---|---|---|
| Tenant API (`/v1/chat`, `/v1/memories`, `/v1/tasks`, `/v1/graph/context`, ...) | `X-Tenant-Key` | Key registered by `scripts/init_schema.py`. Demo keys: `key_acme_secret`, `key_beta_secret`, `key_gamma_secret` (override with `OPSMEMORY_KEY_ACME`, `..._BETA`, `..._GAMMA`). **Demo keys only; change them for any real deployment.** |
| Admin API (`/v1/admin/seed`, `/v1/admin/reset`) | `X-Admin-Key` | Value of `ADMIN_API_KEY` |

```bash
curl -X POST http://localhost:8000/v1/chat -H "X-Tenant-Key: key_acme_secret" -H "Content-Type: application/json" \
     -d '{"message": "What is the current version of payments-api?"}'
curl -X POST "http://localhost:8000/v1/admin/reset?tenant_id=acme" -H "X-Admin-Key: $ADMIN_API_KEY"
```

## Tests

```bash
python -m pytest -q          # needs FalkorDB running; unit tests that need no database run regardless
python scripts/smoke.py      # end-to-end HTTP smoke test (set ADMIN_API_KEY first)
python scripts/benchmark_concurrency.py --requests 20 --concurrency 5
```

The number of tests changes as the suite grows; run the command rather than trusting a number written here.

## Benchmark, and what it does and does not show

```bash
python -m eval.run --suite all                     # 88 bundled questions, tenants acme + beta
python -m eval.run --dataset holdout               # 30 unseen questions, unseen tenant gamma
python -m eval.run --suite all --real-llm          # same 88 questions with a real LLM (needs GOOGLE_API_KEY)
python -m eval.run --dataset holdout --real-llm
```

Reports are written to `reports/` (`benchmark_*` and `holdout_*`, as JSON, CSV and Markdown).

**Read the numbers honestly.** The 88 bundled questions, their fixtures and the offline mock LLM were developed together, so a perfect score on them (88/88 on the last recorded run, mock LLM) shows the pipeline works end to end, **not** that it generalises. The mock LLM has a short list of abstain markers (`MOCK_ONLY_ABSTAIN_MARKERS` in `app/llm/mock.py`) that stand in for an LLM's judgement; the product's own abstention is the generic grounding gate plus the answer prompt. For evidence of generalisation use the hold-out run (a new tenant with new services, versions, owners and incidents, none of which appear in the code) and the `--real-llm` runs.

| Run | Result |
|---|---|
| Bundled benchmark, mock LLM | 88/88 on the last recorded run |
| Hold-out (`gamma`), mock LLM | _run and fill in_ |
| Bundled benchmark, real LLM | _run and fill in_ |
| Hold-out, real LLM | _run and fill in_ |

Methodology: [docs/evaluation.md](docs/evaluation.md).

## API

| Method | Path | Description | Auth |
|---|---|---|---|
| `GET` | `/healthz` | System and FalkorDB health | none |
| `POST` | `/v1/chat` | Question answering, memory capture, reasoning paths | `X-Tenant-Key` |
| `GET` | `/v1/graph/context` | Live graph inspection: node/edge counts, turns, handoffs, indexes | `X-Tenant-Key` |
| `GET` | `/v1/conversations/{id}` | Conversation history | `X-Tenant-Key` |
| `GET` / `DELETE` | `/v1/memories/{id}` | Inspect or delete a memory (404 if unknown) | `X-Tenant-Key` |
| `GET` | `/v1/tasks` | Task board | `X-Tenant-Key` |
| `POST` | `/v1/admin/seed`, `/v1/admin/reset` | Seed fixtures / wipe a tenant | `X-Admin-Key` |
| `GET` | `/ui/` | Web console | none |

## Known limitations

- Entity and intent detection use rules plus the LLM; keyword matching is word-boundary based but English-only.
- The offline mock LLM is a test double, not a product feature.
- The 64-dimension encoder is a lightweight hashing n-gram encoder, not a learned embedding model.
- Progress on the audit of rules, logical flaws and hard-coded values is tracked in [docs/audit_progress.md](docs/audit_progress.md).

## AI disclosure

This project was built with AI coding assistance, which the hackathon rules ask teams to disclose.

- **Initial implementation:** developed with AI coding assistant(s): _author to list the tool names and what they were used for_.
- **Audit remediation (15 Oct 2026):** fixes for the audit findings (supersession, update capture, path direction, admin and tenant auth, FalkorDB-only storage, incident detection, ID collisions, grounding gate, name resolution, hold-out benchmark, documentation) were drafted with Claude (Anthropic) and then reviewed, applied and tested by the author.
- The author is responsible for the submitted code and can explain it.

## Documentation

- [Architecture and schema](docs/architecture.md)
- [Evaluation methodology](docs/evaluation.md)
- [Demo walkthrough and video shot list](docs/demo_script.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Audit remediation progress](docs/audit_progress.md)