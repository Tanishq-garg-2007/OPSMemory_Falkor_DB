import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.config import get_settings
from app.dependencies import TenantContext
from app.memory.repository import get_memory_repository


def main():
    """Verify FalkorDB native full-text and vector indexes exist (no derived/secondary store to rebuild)."""
    repo = get_memory_repository()
    status = repo.check_health()
    print(f"FalkorDB: mode={status['mode']}, connected={status['falkordb_connected']}")
    if not status["ok"]:
        return 1
    settings = get_settings()
    for tenant_id in ("acme", "beta"):
        ctx = TenantContext(tenant_id=tenant_id, graph_name=settings.tenant_graph_name(tenant_id))
        indexes = repo.get_graph_context(ctx)["indexes"]
        print(f"  {ctx.graph_name}: {len(indexes)} indexes")
        for idx in indexes:
            print(f"    - {idx['label']} {idx['properties']} {idx['types']} [{idx['status']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())