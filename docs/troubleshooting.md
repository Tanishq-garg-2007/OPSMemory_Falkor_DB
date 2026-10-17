# OpsMemory Troubleshooting Guide

Common issues, diagnosis steps, and solutions when running or developing OpsMemory on FalkorDB.

---

## 1. FalkorDB Connection Issues & Docker Setup

### Symptom
- Log message: `FalkorDB unavailable on localhost:6379 (...)`
- Connection error or socket failure on port 6379.

### Cause
The local FalkorDB Docker container is not running on port 6379, or Docker Desktop is offline.

### Solution
1. Start the FalkorDB container using Docker Compose:
   ```bash
   docker compose up -d falkordb
   ```
2. Verify connectivity from Python:
   ```bash
   python -c "import socket; s=socket.create_connection(('localhost', 6379), timeout=3); print('FALKORDB_PORT_OK'); s.close()"
   ```
3. Initialize the schema and indexes:
   ```bash
   python scripts/init_schema.py
   python scripts/seed.py
   ```

---

## 2. Inspecting FalkorDB Graph State & Indexes

### Symptom
Uncertain whether range, full-text, and vector indexes are operational in FalkorDB.

### Solution
1. Use the judge graph inspection endpoint:
   ```bash
   curl -H "X-Tenant-Key: test_acme_key" http://localhost:8000/v1/graph/context
   ```
2. Inspect indexes directly via FalkorDB Cypher:
   ```bash
   python -c "
   from app.memory.repository import get_memory_repository
   repo = get_memory_repository()
   graph = repo._get_graph('tenant_acme')
   res = graph.query('CALL db.indexes()')
   for row in res.result_set:
       print(row[0], row[2], row[7] if len(row) > 7 else '')
   "
   ```
   **Expected**: Shows `OPERATIONAL` status for `Memory` with `VECTOR`, `FULLTEXT`, and `RANGE` index types.

---

## 3. LLM Gateway & Provider Configuration

### Diagnosis
Run the diagnostic script:
```bash
python scripts/check_llm.py
```

### Solution
1. **High-Speed Cloud Tier (Groq - Primary)**:
   In .env:
   `ini
   REAL_LLM=1
   LLM_PROVIDER=groq
   GROQ_API_KEY=gsk_your_key_here
   GROQ_PRIMARY_MODEL=qwen/qwen3.8-27b
   GROQ_FALLBACK_MODEL=openai/gpt-oss-20b
   `
2. **Deterministic Mock (Sub-millisecond testing & CI/CD)**:
   In `.env`:
   ```ini
   REAL_LLM=0
   ```
3. **Local Sovereign (Ollama / Local Gemma)**:
   Ensure Ollama is running (`ollama serve`), then in `.env`:
   ```ini
   REAL_LLM=1
   LLM_PROVIDER=ollama
   OLLAMA_MODEL_ID=gemma4-e2b:latest
   OLLAMA_BASE_URL=http://localhost:11434
   ```
4. **Cloud Tier (Google GenAI)**:
   In `.env`:
   ```ini
   REAL_LLM=1
   LLM_PROVIDER=google_genai
   LLM_MODEL_ID=gemma-4-31b-it
   GOOGLE_API_KEY=your_key_here
   ```

---

## 4. Port Conflicts (Port 8000)

### Symptom
`uvicorn app.main:app` fails with `[Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000)`.

### Solution
Run the server on an alternative port:
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

---

## 5. Resetting & Reseeding Graph Data

To clear all test memories and restore deterministic test state:
```bash
# Via script
python scripts/init_schema.py
python scripts/seed.py

# Via API (authorized)
curl -X POST http://localhost:8000/v1/admin/reset -H "X-Tenant-Key: test_admin_key"
curl -X POST http://localhost:8000/v1/admin/seed -H "X-Tenant-Key: test_admin_key"
```
