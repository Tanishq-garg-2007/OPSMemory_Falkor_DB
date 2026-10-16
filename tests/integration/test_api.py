"""Integration tests for FastAPI endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.config import get_settings
from app.memory.repository import get_memory_repository


@pytest.mark.asyncio
async def test_api_endpoints_workflow():
    get_settings().ADMIN_API_KEY = "test-admin-key"
    repo = get_memory_repository()
    repo.register_tenant("acme", "key_acme_secret")
    repo.register_tenant("beta", "key_beta_secret")
    admin = {"X-Admin-Key": "test-admin-key"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Health
        h_res = await client.get("/healthz")
        assert h_res.status_code == 200
        assert h_res.json()["app"] == "opsmemory"

        # 2. Auth rejection on missing key
        chat_no_auth = await client.post("/v1/chat", json={"message": "hello"})
        assert chat_no_auth.status_code == 401

        # 3. Seed fixtures
        await client.post("/v1/admin/seed?tenant_id=acme", headers=admin)

        # 4. Chat endpoint with valid key
        headers = {"X-Tenant-Key": "key_acme_secret"}
        chat_res = await client.post(
            "/v1/chat",
            headers=headers,
            json={"message": "What is the current version of payments-api?"}
        )
        assert chat_res.status_code == 200
        data = chat_res.json()
        assert "v2.4" in data["answer"]
        assert len(data["citations"]) > 0
        assert "learned" in data
        assert data["learned"]["created"] == []
        assert data["learned"]["superseded"] == []
        assert data["learned"]["tasks_created"] == []

        # 4b. Chat with knowledge update
        update_res = await client.post(
            "/v1/chat",
            headers=headers,
            json={"message": "We upgraded payments-api to v2.5"}
        )
        assert update_res.status_code == 200
        u_data = update_res.json()
        assert "learned" in u_data
        assert len(u_data["learned"]["created"]) > 0
        assert len(u_data["learned"]["superseded"]) > 0

        # 4c. Chat with multi-hop dependency query
        hop_res = await client.post(
            "/v1/chat",
            headers=headers,
            json={"message": "What does checkout-ui depend on?"}
        )
        assert hop_res.status_code == 200
        h_data = hop_res.json()
        assert len(h_data["reasoning_paths"]) > 0

        # 5. Conversation retrieval
        conv_id = data["conversation_id"]
        conv_res = await client.get(f"/v1/conversations/{conv_id}", headers=headers)
        assert conv_res.status_code == 200
        assert conv_res.json()["id"] == conv_id

        # 6. List tasks
        task_res = await client.get("/v1/tasks", headers=headers)
        assert task_res.status_code == 200
        assert isinstance(task_res.json(), list)

        # 7. Agent handoffs endpoint
        handoffs_res = await client.get(f"/v1/agents/handoffs?conversation_id={conv_id}", headers=headers)
        assert handoffs_res.status_code == 200
        handoffs = handoffs_res.json()
        assert isinstance(handoffs, list)
        assert len(handoffs) > 0

        # 8. Graph context contains handoff_count
        ctx_res = await client.get("/v1/graph/context", headers=headers)
        assert ctx_res.status_code == 200
        ctx_data = ctx_res.json()
        assert "handoff_count" in ctx_data
        assert ctx_data["handoff_count"] > 0

        # 9. Entity timeline
        timeline_res = await client.get("/v1/entities/payments-api/timeline", headers=headers)
        assert timeline_res.status_code == 200
        timeline = timeline_res.json()
        assert isinstance(timeline, list)
        assert len(timeline) > 0
        assert "valid_from" in timeline[0]
        assert "status" in timeline[0]

        # 10. Entity timeline 404 for nonexistent entity
        missing_res = await client.get("/v1/entities/nonexistent-service/timeline", headers=headers)
        assert missing_res.status_code == 404

        # 11. UI check
        ui_res = await client.get("/ui/")
        assert ui_res.status_code == 200
        assert "OpsMemory" in ui_res.text


@pytest.mark.asyncio
async def test_api_returns_503_when_falkordb_is_down(monkeypatch):
    """With FalkorDB unreachable the API must fail loudly (503), never silently degrade."""
    import app.memory.repository as repo_module
    from app.config import Settings

    dead_repo = repo_module.MemoryRepository(settings=Settings(
        REAL_LLM=0, LLM_PROVIDER="mock",
        FALKORDB_HOST="127.0.0.1", FALKORDB_PORT=1, FALKORDB_TIMEOUT_SECONDS=0.5,
    ))
    monkeypatch.setattr(repo_module, "_repo", dead_repo)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        health = await client.get("/healthz")
        assert health.status_code == 503
        assert health.json()["database"]["mode"] == "falkordb_unavailable"

        res = await client.get("/v1/memories", headers={"X-Tenant-Key": "key_acme_secret"})
        assert res.status_code == 503
        assert res.json()["error"] == "DatabaseUnavailableError"