import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv()

from app.database import store  # noqa: E402


TABLES = [
    "workspaces",
    "users",
    "roles",
    "workspace_members",
    "invitations",
    "invite_links",
    "members",
    "dues_cycles",
    "dues_payments",
    "events",
    "campaigns",
    "funding_streams",
    "contributions",
    "short_links",
    "announcements",
]

DATETIME_FIELDS = {
    "created_at",
    "updated_at",
    "joined_at",
    "expires_at",
    "accepted_at",
    "revoked_at",
    "confirmed_at",
    "published_at",
    "archived_at",
}

BOOLEAN_FIELDS = {
    "email_verified",
    "is_system_role",
    "is_general_member",
    "is_active",
    "rsvp_enabled",
    "is_anonymous",
    "is_pinned",
}

DROP_NONE_FIELDS = {"gateway_ref"}


def parse_datetime(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return value

    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            return value


def table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


def normalize_row(table: str, row: sqlite3.Row) -> dict[str, Any]:
    doc = dict(row)

    if table == "roles":
        raw_permissions = doc.pop("permissions_json", "[]")
        try:
            doc["permissions"] = sorted(set(json.loads(raw_permissions or "[]")))
        except json.JSONDecodeError:
            doc["permissions"] = []

    if table == "workspace_members" and "created_at" not in doc:
        doc["created_at"] = doc.get("joined_at") or datetime.utcnow()

    for field in DATETIME_FIELDS:
        if field in doc:
            doc[field] = parse_datetime(doc[field])

    for field in BOOLEAN_FIELDS:
        if field in doc and doc[field] is not None:
            doc[field] = bool(doc[field])

    for field in DROP_NONE_FIELDS:
        if field in doc and doc[field] is None:
            doc.pop(field)

    return doc


def migrate(sqlite_path: Path, replace: bool) -> dict[str, int]:
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")

    connection = sqlite3.connect(sqlite_path)
    connection.row_factory = sqlite3.Row

    existing_tables = table_names(connection)
    counts: dict[str, int] = {}

    if replace:
        store.delete_all_collections()

    for table in TABLES:
        if table not in existing_tables:
            counts[table] = 0
            continue

        rows = connection.execute(f"SELECT * FROM {table}").fetchall()
        docs = [normalize_row(table, row) for row in rows]
        if docs:
            store.collection(table).insert_many(docs, ordered=False)
        counts[table] = len(docs)

        max_id = max((int(doc["id"]) for doc in docs if doc.get("id") is not None), default=0)
        if max_id:
            store.collection("counters").replace_one({"_id": table}, {"_id": table, "seq": max_id}, upsert=True)

    store.ensure_indexes()
    connection.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Quorum data from SQLite into MongoDB.")
    parser.add_argument("--sqlite", default="quorum.db", help="Path to the SQLite database file.")
    parser.add_argument("--replace", action="store_true", help="Clear Quorum MongoDB collections before importing.")
    args = parser.parse_args()

    counts = migrate(Path(args.sqlite), args.replace)
    print("Migrated SQLite data into MongoDB:")
    for collection, count in counts.items():
        print(f"- {collection}: {count}")


if __name__ == "__main__":
    main()
