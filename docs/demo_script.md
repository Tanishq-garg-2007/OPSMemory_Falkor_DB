# OpsMemory Interactive Demo Script

This script walks through an end-to-end demonstration of OpsMemory's core capabilities:
1. Multi-session episodic, semantic, and procedural memory recall.
2. Temporal fact supersession (old facts superseded, not silently overwritten).
3. Evidence-grounded reasoning with citations.
4. Tenant boundary isolation (`acme` vs `beta`).
5. Persistent restart resilience.

---

## 1. Setup & Starting the Service

1. Ensure the schema and seed data are initialized:
   ```bash
   python scripts/init_schema.py
   python scripts/seed.py
   ```
2. Start the FastAPI server:
   ```bash
   python -m uvicorn app.main:app --port 8000
   ```
3. Open your browser to the Web Console:
   ```
   http://localhost:8000/ui/
   ```
   *(Or interact via `curl` terminal commands below).*

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

### Step 2: Multi-Hop Incident & Dependency Reasoning
Ask about dependency impact:
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "X-Tenant-Key: test_acme_key" \
  -H "Content-Type: application/json" \
  -d '{"message": "If postgres-orders fails, which customer-facing application is indirectly broken?"}'
```
**Expected Response**:
- Mentions **checkout-ui** (traversing `postgres-orders` -> `payments-api` -> `checkout-ui`).

---

### Step 3: Procedural Memory (Runbook Recall)
Ask for incident remediation procedures:
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "X-Tenant-Key: test_acme_key" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the safe rollback procedure for payments-api?"}'
```
**Expected Response**:
- Returns step-by-step procedure: canary traffic to 0%, helm rollback, DB migration rollback check, `/healthz` validation.
- Citation links `mem_procedural_acme_runbook_safe-rollback-procedure-for-payments`.

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

### Step 5: Persistence Across App Restart
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
- Demonstrates persistent cross-session knowledge retention surviving application restarts.
