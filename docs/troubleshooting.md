# OpsMemory Troubleshooting Guide

Common issues, diagnosis steps, and solutions when running or developing OpsMemory.

---

## 1. FalkorDB Connection Issues & Docker Setup

### Symptom
- Log message: `FalkorDB unavailable on localhost:6379 (...). Using embedded durable persistence.`
- Health check shows: `"mode": "sqlite_standalone"`.

### Cause
The local FalkorDB instance is not running on port 6379, or Docker Desktop is offline.

### Solution
1. Start the container using Docker Compose:
   ```bash
   docker compose up -d falkordb
   ```
2. Verify the port is listening:
   ```bash
   # Linux/macOS
   curl -v telnet://localhost:6379
   # Windows PowerShell
   Test-NetConnection -ComputerName localhost -Port 6379
   ```
3. **Graceful Degradation**: OpsMemory features dual-tier persistence. Even if FalkorDB is offline, all memories, entities, relationships, and tasks continue to persist durably in `opsmemory.db` via embedded SQLite + FTS5 without crashing.

---

## 2. LLM Gateway & Google GenAI Configuration

### Symptom
- `scripts/check_llm.py` exits with code 2: `GOOGLE_API_KEY environment variable is not set.`
- Or model request times out.

### Diagnosis
Run the diagnostic script:
```bash
python scripts/check_llm.py
```

### Solution
1. For zero-cost local testing and benchmarks, ensure `REAL_LLM=0` in `.env`. OpsMemory will use the deterministic mock provider.
2. For real model inference with Gemma 4 31B:
   ```bash
   # In .env
   REAL_LLM=1
   LLM_PROVIDER=google_genai
   LLM_MODEL_ID=gemma-4-31b-it
   GOOGLE_API_KEY=your_google_ai_studio_api_key_here
   ```
3. Test connectivity:
   ```bash
   python scripts/check_llm.py
   ```

---

## 3. SQLite FTS5 Out of Sync

### Symptom
Memories exist in the graph or SQLite table, but keyword searches in `/v1/chat` return insufficient evidence or abstain.

### Solution
Rebuild the derived SQLite FTS5 table directly from persistent storage:
```bash
python scripts/rebuild_fts.py
```
This utility truncates `memory_fts` and reindexes all non-deleted memories across all tenants.

---

## 4. Port Conflicts (Port 8000)

### Symptom
`uvicorn app.main:app` fails with `[Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000): only one usage of each socket address is normally permitted`.

### Solution
Run the server on an alternative port:
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

---

## 5. Resetting Database Fixtures

To clear all test memories and restore deterministic test state:
```bash
# Via script
python scripts/seed.py

# Via API (authorized)
curl -X POST http://localhost:8000/v1/admin/reset -H "X-Tenant-Key: test_admin_key"
curl -X POST http://localhost:8000/v1/admin/seed -H "X-Tenant-Key: test_admin_key"
```
