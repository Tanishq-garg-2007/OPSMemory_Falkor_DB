import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.memory.repository import get_memory_repository


def init_schema():
    """Register demo tenants (hashed keys) and idempotently create FalkorDB indexes/agents per tenant graph."""
    print("Initializing OpsMemory FalkorDB schema...")
    repo = get_memory_repository()
    health = repo.check_health()
    if not health["ok"]:
        print(f"FalkorDB is unreachable: {health}")
        return 1
    # Demo keys for local use. Override via env; never ship the defaults to production.
    tenants = [
        ("acme", os.environ.get("OPSMEMORY_KEY_ACME", "key_acme_secret")),
        ("beta", os.environ.get("OPSMEMORY_KEY_BETA", "key_beta_secret")),
        ("gamma", os.environ.get("OPSMEMORY_KEY_GAMMA", "key_gamma_secret")),  # hold-out tenant
    ]
    for tenant_id, api_key in tenants:
        repo.register_tenant(tenant_id, api_key)
        repo.init_tenant_schema(tenant_id)
    print(f"Schema initialized. Health status: {repo.check_health()}")
    return 0


if __name__ == "__main__":
    sys.exit(init_schema())