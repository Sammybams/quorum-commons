import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv()

from app.database import MongoStore, store  # noqa: E402


def migrate(source_database: str, replace: bool) -> dict[str, tuple[str, int]]:
    source = store.client[source_database]
    counts: dict[str, tuple[str, int]] = {}

    if replace:
        store.delete_all_collections()

    for collection_name in MongoStore.collection_names:
        target = store.collection(collection_name)
        docs = list(source[collection_name].find({}))
        for doc in docs:
            doc.pop("_id", None)
        if docs:
            target.insert_many(docs, ordered=False)
        counts[collection_name] = (store.database_name(collection_name), len(docs))

    store.ensure_indexes()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Move Quorum data from one MongoDB database into segmented domain databases.")
    parser.add_argument("--source-db", default="quorum", help="Existing single MongoDB database to read from.")
    parser.add_argument("--replace", action="store_true", help="Clear segmented Quorum databases before importing.")
    args = parser.parse_args()

    counts = migrate(args.source_db, args.replace)
    print("Migrated MongoDB data into segmented databases:")
    for collection, (database, count) in counts.items():
        print(f"- {database}.{collection}: {count}")


if __name__ == "__main__":
    main()
