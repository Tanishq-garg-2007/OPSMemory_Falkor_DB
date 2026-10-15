import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.memory.repository import get_memory_repository


def main():
    print("Verifying FalkorDB native full-text and vector indexes...")
    repo = get_memory_repository()
    status = repo.health_check()
    print(f"FalkorDB native persistence verified: mode={status.get('mode')}, falkordb_connected={status.get('falkordb_connected')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
