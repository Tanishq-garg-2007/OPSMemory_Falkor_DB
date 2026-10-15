"""Integration tests for FastAPI endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_api_endpoints_workflow():
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
        await client.post("/v1/admin/seed?tenant_id=acme")

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

        # 5. Conversation retrieval
        conv_id = data["conversation_id"]
        conv_res = await client.get(f"/v1/conversations/{conv_id}", headers=headers)
        assert conv_res.status_code == 200
        assert conv_res.json()["id"] == conv_id

        # 6. List tasks
        task_res = await client.get("/v1/tasks", headers=headers)
        assert task_res.status_code == 200
        assert isinstance(task_res.json(), list)

        # 7. UI check
        ui_res = await client.get("/ui/")
        assert ui_res.status_code == 200
        assert "OpsMemory" in ui_res.text
