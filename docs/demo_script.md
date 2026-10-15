# OpsMemory Interactive Demo Script

This script walks through an end-to-end demonstration of OpsMemory's core capabilities:
1. Multi-session episodic, semantic, and procedural memory recall in FalkorDB.
2. Temporal fact supersession (old facts superseded with `:SUPERSEDES` edges, not silently overwritten).
3. Evidence-grounded reasoning with citations and explainable `reasoning_paths`.
4. Tenant boundary isolation (`acme` vs `beta` graph namespaces).
5. Graph-mediated multi-agent handoffs & atomic Cypher task leases.
6. Live FalkorDB graph state inspection via `GET /v1/graph/context`.

---

## 1. Setup & Starting the Service

1. Verify FalkorDB is running:
   ```bash
   docker compose up -d falkordb
   ```
2. Initialize schema and seed data in FalkorDB:
   ```bash
   python scripts/init_schema.py
   python scripts/seed.py
   ```
3. Start the FastAPI server:
   ```bash
   python -m uvicorn app.main:app --port 8000
   ```
4. Open your browser to the Web Console:
   ```
   http://localhost:8000/ui/
   ```

---

## 2. Demonstration Scenarios

### Step 1: Semantic Recall & Current vs Superseded Facts
Ask about the version of `payments-api`:
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "X-Tenant-Key: test_acme_key" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the current version of payments-api?"}'
```
**Expected Response**:
- Answer states that current production version is **v2.4**.
- Citations point to `mem_semantic_acme_fact_payments-api-current-version-is-v24`.
- The old superseded version (v2.3) is **not** returned as the active version.

Now probe the historical supersession explicitly:
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "X-Tenant-Key: test_acme_key" \
  -H "Content-Type: application/json" \
  -d '{"message": "Why should queries about current facts not cite the v2.3 memory as active?"}'
```
**Expected Response**:
- Answer explains that v2.3 is **superseded** by v2.4 following the post-incident stabilization release.

---

### Step 2: Multi-Hop Incident & Dependency Reasoning with Explainable Paths
Ask about dependency impact:
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "X-Tenant-Key: test_acme_key" \
  -H "Content-Type: application/json" \
  -d '{"message": "If postgres-orders fails, which customer-facing application is indirectly broken?"}'
```
**Expected Response**:
- Mentions **checkout-ui** (traversing `postgres-orders` -> `payments-api` -> `checkout-ui`).
- Inspect `reasoning_paths`:
  ```json
  "reasoning_paths": [
    ["postgres-orders", "DEPENDS_ON", "payments-api", "DEPENDS_ON", "checkout-ui"]
  ]
  ```

---

### Step 3: Graph-Mediated Multi-Agent Handoffs & Atomic Task Leases
Trigger an incident report:
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "X-Tenant-Key: test_acme_key" \
  -H "Content-Type: application/json" \
  -d '{"message": "Outage on checkout: database lock contention observed on payments-api."}'
```
**Expected Response**:
- Triage agent captures incident memory, records a handoff edge:
  `(:Agent {id: 'agent_triage'})-[:HANDED_OFF_TO]->(:Agent {id: 'agent_resolver'})`.
- Resolver worker atomically claims the task lease via Cypher:
  `MATCH (t:Task) WHERE t.status = 'pending' ... SET t.status = 'claimed' RETURN t`.
- Resolver executes runbook and hands off to Curator agent for procedural documentation.
- Response contains populated `tasks` and `agent_handoffs`.

---

### Step 4: Multi-Tenant Boundary Isolation
Query private Acme records using the Beta tenant key:
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "X-Tenant-Key: test_beta_key" \
  -H "Content-Type: application/json" \
  -d '{"message": "What was the cause of incident inc-101 in checkout?"}'
```
**Expected Response**:
- System **abstains** (`"abstained": true`, `"confidence": "low"`) because incident `inc-101` belongs exclusively to tenant `acme`. Beta tenant cannot observe Acme graph nodes.

Query Beta's private version:
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "X-Tenant-Key: test_beta_key" \
  -H "Content-Type: application/json" \
  -d '{"message": "What version of payments-api is deployed in our cluster?"}'
```
**Expected Response**:
- Returns **v1.9** (Beta's isolated fact), completely distinct from Acme's v2.4.

---

### Step 5: Live FalkorDB Graph State Inspection
Inspect the tenant's live FalkorDB graph state:
```bash
curl -H "X-Tenant-Key: test_acme_key" http://localhost:8000/v1/graph/context
```
**Expected Response**:
```json
{
  "tenant_id": "acme",
  "graph_name": "tenant_acme",
  "falkordb_connected": true,
  "node_counts": {
    "Entity": 5,
    "Memory": 13,
    "Task": 1,
    "Session": 1,
    "Turn": 4,
    "Agent": 3
  },
  "edge_counts": {
    "DEPENDS_ON": 3,
    "MENTIONS": 21,
    "HAS_TURN": 4,
    "HANDED_OFF_TO": 2,
    "SUPERSEDES": 1
  },
  "recent_turns": [ ... ],
  "agent_handoffs": [ ... ],
  "indexes": [
    { "label": "Memory", "types": { "embedding": ["VECTOR"], "title": ["FULLTEXT"], "summary": ["FULLTEXT"], "id": ["RANGE"] }, "status": "OPERATIONAL" }
  ]
}
```

---

### Step 6: Persistence Across Application Restart
1. Terminate the server (`Ctrl+C`).
2. Restart the server:
   ```bash
   python -m uvicorn app.main:app --port 8000
   ```
3. Query Priya's preference:
   ```bash
   curl -X POST http://localhost:8000/v1/chat \
     -H "X-Tenant-Key: test_acme_key" \
     -H "Content-Type: application/json" \
     -d '{"message": "What format does Priya prefer for incident reviews?"}'
   ```
**Expected Response**:
- Returns "concise summaries with direct bullet points".
- Demonstrates persistent knowledge retention surviving application restarts directly inside FalkorDB.
