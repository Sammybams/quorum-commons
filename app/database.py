import os
from datetime import datetime
from typing import Any, Iterable

from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument


load_dotenv()

MONGODB_CONNECTION_STRING = os.getenv("MONGODB_CONNECTION_STRING") or os.getenv("MONGODB_URL")
MONGODB_DATABASE_PREFIX = os.getenv("MONGODB_DATABASE_PREFIX") or os.getenv("MONGODB_DATABASE", "")

if not MONGODB_CONNECTION_STRING:
    raise RuntimeError("MONGODB_CONNECTION_STRING is required")


class Doc(dict):
    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value

    @property
    def permissions(self) -> list[str]:
        value = self.get("permissions", [])
        return value if isinstance(value, list) else []

    def set_permissions(self, permissions: list[str]) -> None:
        self["permissions"] = sorted(set(permissions))


def _as_doc(value: dict[str, Any] | None) -> Doc | None:
    if value is None:
        return None
    value.pop("_id", None)
    return Doc(value)


def _as_docs(values: Iterable[dict[str, Any]]) -> list[Doc]:
    return [doc for item in values if (doc := _as_doc(item)) is not None]


def _clean_sparse_unique_fields(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("gateway_ref") is None:
        payload.pop("gateway_ref", None)
    return payload


class MongoStore:
    collection_databases = {
        "workspaces": "communities",
        "members": "communities",
        "users": "identity",
        "roles": "identity",
        "workspace_members": "identity",
        "integrations": "identity",
        "auth_sessions": "identity",
        "revoked_tokens": "identity",
        "email_verification_tokens": "identity",
        "password_reset_tokens": "identity",
        "invitations": "identity",
        "invite_links": "identity",
        "dues_cycles": "finance",
        "dues_payments": "finance",
        "campaigns": "finance",
        "funding_streams": "finance",
        "contributions": "finance",
        "budgets": "finance",
        "budget_lines": "finance",
        "expenditures": "finance",
        "events": "engagement",
        "event_attendees": "engagement",
        "meetings": "engagement",
        "meeting_minutes": "engagement",
        "action_items": "engagement",
        "announcements": "engagement",
        "short_links": "engagement",
        "link_clicks": "engagement",
        "tasks": "engagement",
        "notifications": "engagement",
        "reports": "engagement",
        "counters": "platform",
    }

    collection_names = [
        "workspaces",
        "users",
        "roles",
        "workspace_members",
        "integrations",
        "auth_sessions",
        "revoked_tokens",
        "email_verification_tokens",
        "password_reset_tokens",
        "invitations",
        "invite_links",
        "members",
        "dues_cycles",
        "dues_payments",
        "events",
        "event_attendees",
        "campaigns",
        "funding_streams",
        "contributions",
        "budgets",
        "budget_lines",
        "expenditures",
        "meetings",
        "meeting_minutes",
        "action_items",
        "short_links",
        "link_clicks",
        "announcements",
        "tasks",
        "notifications",
        "reports",
        "counters",
    ]

    def __init__(self):
        self.client = MongoClient(MONGODB_CONNECTION_STRING)
        self.database_prefix = MONGODB_DATABASE_PREFIX
        self.ensure_indexes()

    def database_name(self, collection_name: str) -> str:
        segment = self.collection_databases.get(collection_name)
        if not segment:
            raise ValueError(f"Unknown collection: {collection_name}")
        return f"{self.database_prefix}_{segment}" if self.database_prefix else segment

    def database(self, segment: str):
        return self.client[f"{self.database_prefix}_{segment}" if self.database_prefix else segment]

    def collection(self, name: str):
        return self.client[self.database_name(name)][name]

    def ensure_indexes(self) -> None:
        self.collection("workspaces").create_index([("slug", ASCENDING)], unique=True)
        self.collection("users").create_index([("email", ASCENDING)], unique=True)
        self.collection("roles").create_index([("workspace_id", ASCENDING), ("key", ASCENDING)], unique=True)
        self.collection("workspace_members").create_index([("workspace_id", ASCENDING), ("user_id", ASCENDING)], unique=True)
        self.collection("integrations").create_index([("workspace_id", ASCENDING), ("provider", ASCENDING)], unique=True)
        self.collection("auth_sessions").create_index([("refresh_jti", ASCENDING)], unique=True)
        self.collection("revoked_tokens").create_index([("jti", ASCENDING)], unique=True)
        self.collection("email_verification_tokens").create_index([("token", ASCENDING)], unique=True)
        self.collection("password_reset_tokens").create_index([("token", ASCENDING)], unique=True)
        self.collection("invitations").create_index([("token", ASCENDING)], unique=True)
        self.collection("invite_links").create_index([("token", ASCENDING)], unique=True)
        self.collection("events").create_index([("slug", ASCENDING)], unique=True)
        self.collection("event_attendees").create_index([("event_id", ASCENDING), ("member_id", ASCENDING)], unique=True, sparse=True)
        self.collection("event_attendees").create_index([("event_id", ASCENDING), ("email", ASCENDING)], unique=True, sparse=True)
        self.collection("campaigns").create_index([("slug", ASCENDING)], unique=True)
        self.collection("contributions").create_index([("gateway_ref", ASCENDING)], unique=True, sparse=True)
        self.collection("dues_payments").create_index([("gateway_ref", ASCENDING)], unique=True, sparse=True)
        self.collection("budgets").create_index([("workspace_id", ASCENDING), ("created_at", DESCENDING)])
        self.collection("budget_lines").create_index([("budget_id", ASCENDING), ("created_at", ASCENDING)])
        self.collection("expenditures").create_index([("budget_line_id", ASCENDING), ("created_at", DESCENDING)])
        self.collection("meetings").create_index([("workspace_id", ASCENDING), ("scheduled_for", DESCENDING)])
        self.collection("meeting_minutes").create_index([("meeting_id", ASCENDING)], unique=True)
        self.collection("action_items").create_index([("meeting_id", ASCENDING), ("created_at", DESCENDING)])
        self.collection("short_links").create_index([("slug", ASCENDING)], unique=True)
        self.collection("link_clicks").create_index([("link_id", ASCENDING), ("clicked_at", DESCENDING)])
        self.collection("link_clicks").create_index([("workspace_id", ASCENDING), ("clicked_at", DESCENDING)])
        self.collection("tasks").create_index([("workspace_id", ASCENDING), ("assigned_to_member_id", ASCENDING), ("status", ASCENDING)])
        self.collection("notifications").create_index([("workspace_id", ASCENDING), ("user_id", ASCENDING), ("created_at", DESCENDING)])
        self.collection("reports").create_index([("workspace_id", ASCENDING), ("created_at", DESCENDING)])
        self.collection("reports").create_index([("workspace_id", ASCENDING), ("status", ASCENDING)])

    def next_id(self, collection_name: str) -> int:
        max_existing_doc = self.collection(collection_name).find_one(sort=[("id", DESCENDING)])
        max_existing_id = int(max_existing_doc["id"]) if max_existing_doc and max_existing_doc.get("id") is not None else 0
        counter = self.collection("counters").find_one_and_update(
            {"_id": collection_name},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        next_seq = int(counter["seq"])
        if next_seq <= max_existing_id:
            counter = self.collection("counters").find_one_and_update(
                {"_id": collection_name},
                {"$set": {"seq": max_existing_id + 1}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            next_seq = int(counter["seq"])
        return next_seq

    def insert(self, collection_name: str, doc: dict[str, Any]) -> Doc:
        payload = dict(doc)
        _clean_sparse_unique_fields(payload)
        payload.setdefault("id", self.next_id(collection_name))
        payload.setdefault("created_at", datetime.utcnow())
        self.collection(collection_name).insert_one(payload)
        return _as_doc(payload)  # type: ignore[return-value]

    def save(self, collection_name: str, doc: dict[str, Any]) -> Doc:
        payload = dict(doc)
        _clean_sparse_unique_fields(payload)
        if "id" not in payload:
            payload["id"] = self.next_id(collection_name)
        self.collection(collection_name).replace_one({"id": payload["id"]}, payload, upsert=True)
        return _as_doc(payload)  # type: ignore[return-value]

    def find_one(self, collection_name: str, filter: dict[str, Any]) -> Doc | None:
        return _as_doc(self.collection(collection_name).find_one(filter))

    def find_by_id(self, collection_name: str, item_id: int | None) -> Doc | None:
        if item_id is None:
            return None
        cursor = self.collection(collection_name).find({"id": item_id}).sort([("created_at", DESCENDING), ("_id", DESCENDING)]).limit(1)
        values = _as_docs(cursor)
        return values[0] if values else None

    def find_many(
        self,
        collection_name: str,
        filter: dict[str, Any] | None = None,
        sort: list[tuple[str, int]] | None = None,
        limit: int = 0,
    ) -> list[Doc]:
        cursor = self.collection(collection_name).find(filter or {})
        if sort:
            cursor = cursor.sort(sort)
        if limit:
            cursor = cursor.limit(limit)
        return _as_docs(cursor)

    def count(self, collection_name: str, filter: dict[str, Any] | None = None) -> int:
        return self.collection(collection_name).count_documents(filter or {})

    def update_one(self, collection_name: str, filter: dict[str, Any], update: dict[str, Any]) -> Doc | None:
        self.collection(collection_name).update_one(filter, {"$set": update})
        return self.find_one(collection_name, filter)

    def increment(self, collection_name: str, filter: dict[str, Any], field: str, amount: float | int) -> Doc | None:
        self.collection(collection_name).update_one(filter, {"$inc": {field: amount}})
        return self.find_one(collection_name, filter)

    def delete_one(self, collection_name: str, filter: dict[str, Any]) -> int:
        return self.collection(collection_name).delete_one(filter).deleted_count

    def delete_many(self, collection_name: str, filter: dict[str, Any]) -> int:
        return self.collection(collection_name).delete_many(filter).deleted_count

    def delete_all_collections(self) -> None:
        for name in self.collection_names:
            self.collection(name).delete_many({})


store = MongoStore()


def get_db():
    yield store


ASC = ASCENDING
DESC = DESCENDING
