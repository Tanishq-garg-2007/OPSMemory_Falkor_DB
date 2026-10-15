import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.memory.repository import get_memory_repository


def main():
    print("Rebuilding SQLite FTS5 index...")
    repo = get_memory_repository()
    count = repo.rebuild_fts()
    print(f"Successfully rebuilt FTS5 index. Indexed {count} active memories.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
