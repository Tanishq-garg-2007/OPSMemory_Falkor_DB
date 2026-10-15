import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app


async def run_smoke():
    print("Starting OpsMemory E2E HTTP Smoke Test...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Health check
        res = await client.get("/healthz")
        assert res.status_code == 200, f"Health check failed: {res.status_code}"
        health_data = res.json()
        print(f"  [PASS] /healthz returned 200 (mode: {health_data['database']['mode']})")

        # 2. Seed Acme fixtures
        res = await client.post("/v1/admin/seed?tenant_id=acme")
        assert res.status_code == 200, f"Seed failed: {res.status_code}"
        print(f"  [PASS] /v1/admin/seed seeded Acme fixtures successfully")

        # 3. Chat query
        headers = {"X-Tenant-Key": "key_acme_secret"}
        chat_payload = {"message": "What is the current version of payments-api?"}
        res = await client.post("/v1/chat", headers=headers, json=chat_payload)
        assert res.status_code == 200, f"Chat failed: {res.status_code}"
        chat_data = res.json()
        assert "answer" in chat_data, "Missing answer in chat response"
        assert len(chat_data["citations"]) > 0, "Expected at least one citation"
        print(f"  [PASS] /v1/chat responded with answer and citations: {chat_data['citations']}")

        # 4. Memory inspector
        res = await client.get("/v1/memories", headers=headers)
        assert res.status_code == 200, f"List memories failed: {res.status_code}"
        memories = res.json()
        assert len(memories) >= 5, f"Expected >= 5 memories, got {len(memories)}"
        print(f"  [PASS] /v1/memories listed {len(memories)} persistent memories")

        # 5. Tasks inspector
        res = await client.get("/v1/tasks", headers=headers)
        assert res.status_code == 200, f"List tasks failed: {res.status_code}"
        tasks = res.json()
        print(f"  [PASS] /v1/tasks listed {len(tasks)} coordination tasks")

        # 6. Tenant Isolation check: Acme cannot see Beta data
        beta_headers = {"X-Tenant-Key": "key_beta_secret"}
        await client.post("/v1/admin/seed?tenant_id=beta")
        leak_check = await client.post("/v1/chat", headers=headers, json={"message": "What is Beta Secret Database Password?"})
        leak_data = leak_check.json()
        assert "beta-secret-pw-999" not in leak_data["answer"], "CRITICAL: Cross-tenant leakage detected!"
        print("  [PASS] Cross-tenant isolation verified: Acme cannot retrieve Beta secret data")

        # 7. UI Static check
        ui_res = await client.get("/ui/")
        assert ui_res.status_code == 200, f"UI route failed: {ui_res.status_code}"
        assert "OpsMemory" in ui_res.text, "UI HTML missing title"
        assert "chat-messages" in ui_res.text, "UI HTML missing chat container"
        print("  [PASS] /ui/ served static UI bundle with required layout panels")

    print("\nALL SMOKE CHECKS PASSED SUCCESSFULLY.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_smoke()))
