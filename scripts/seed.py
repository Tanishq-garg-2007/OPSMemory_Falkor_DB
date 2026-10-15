import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import argparse
from app.dependencies import TenantContext
from app.memory.repository import get_memory_repository
from eval.dataset.fixtures import seed_fixtures_for_tenant


def main():
    parser = argparse.ArgumentParser(description="Seed OpsMemory fixtures")
    parser.add_argument("--tenant", choices=["acme", "beta", "all"], default="all")
    args = parser.parse_args()

    repo = get_memory_repository()
    targets = ["acme", "beta"] if args.tenant == "all" else [args.tenant]

    for t in targets:
        ctx = TenantContext(tenant_id=t, graph_name=f"tenant_{t}")
        stats = seed_fixtures_for_tenant(ctx, repo)
        print(f"Seeded tenant '{t}': {stats}")

    print("Seeding complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
