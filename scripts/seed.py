import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import argparse
from app.config import get_settings
from app.dependencies import TenantContext
from app.memory.repository import get_memory_repository
from eval.dataset.fixtures import seed_fixtures_for_tenant, reset_tenant_data
from eval.dataset.holdout_fixtures import seed_holdout_fixtures


def main():
    parser = argparse.ArgumentParser(description="Seed OpsMemory fixtures")
    parser.add_argument("--tenant", choices=["acme", "beta", "gamma", "all"], default="all")
    parser.add_argument("--reset", action="store_true", help="Wipe and reset tenant data before seeding")
    args = parser.parse_args()

    repo = get_memory_repository()
    targets = ["acme", "beta"] if args.tenant == "all" else [args.tenant]

    for t in targets:
        ctx = TenantContext(tenant_id=t, graph_name=get_settings().tenant_graph_name(t))
        if args.reset:
            reset_tenant_data(ctx, repo)
            print(f"Reset tenant data for '{t}'.")
        stats = (seed_holdout_fixtures if t == "gamma" else seed_fixtures_for_tenant)(ctx, repo)
        print(f"Seeded tenant '{t}': {stats}")

    print("Seeding complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())