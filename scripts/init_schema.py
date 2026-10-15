import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.config import get_settings
from app.memory.repository import get_memory_repository
from app.core.hashing import hash_api_key
from app.core.time import utc_now_iso


def init_schema():
    print("Initializing OpsMemory persistence layer...")
    repo = get_memory_repository()
    settings = get_settings()

    # Pre-seed control tenants in SQLite
    with repo._get_sqlite_con() as con:
        cur = con.cursor()
        now = utc_now_iso()
        tenants = [
            ("acme", hash_api_key("key_acme_secret"), settings.tenant_graph_name("acme")),
            ("beta", hash_api_key("key_beta_secret"), settings.tenant_graph_name("beta")),
        ]
        for t_id, key_h, g_name in tenants:
            cur.execute("""
                INSERT INTO tenants (tenant_id, api_key_hash, graph_name, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                    api_key_hash=excluded.api_key_hash,
                    graph_name=excluded.graph_name
            """, (t_id, key_h, g_name, now))
        con.commit()

    # Idempotently initialize FalkorDB indexes for tenant graphs
    for t_id, _, _ in tenants:
        repo.init_tenant_schema(t_id)

    health = repo.check_health()
    print(f"Schema initialized. Health status: {health}")
    return 0


if __name__ == "__main__":
    sys.exit(init_schema())
