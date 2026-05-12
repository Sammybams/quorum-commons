from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import store
from app.demo_seed import ensure_demo_workspace


def main() -> None:
    store.delete_all_collections()
    workspace, _membership = ensure_demo_workspace(store)
    print(f"Database reset complete. Demo workspace ready: {workspace.name} ({workspace.slug})")


if __name__ == "__main__":
    main()
