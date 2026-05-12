from datetime import datetime

from . import models
from .database import MongoStore
from .rbac import ensure_default_roles


def sync_workspace_members_from_legacy(db: MongoStore, workspace: models.Workspace) -> None:
    roles = ensure_default_roles(db, workspace.id)
    legacy_members = db.find_many("members", {"workspace_id": workspace.id})

    for legacy_member in legacy_members:
        email = legacy_member.email.strip().lower()
        user = db.find_one("users", {"email": email})
        if user is None:
            user = db.insert(
                "users",
                {
                    "full_name": legacy_member.full_name,
                    "email": email,
                    "phone": None,
                    "password_hash": None,
                    "email_verified": False,
                },
            )

        membership = db.find_one("workspace_members", {"workspace_id": workspace.id, "user_id": user.id})
        if membership is None:
            role_key = role_key_from_input(legacy_member.role)
            db.insert(
                "workspace_members",
                {
                    "workspace_id": workspace.id,
                    "user_id": user.id,
                    "role_id": roles[role_key].id,
                    "level": legacy_member.get("level"),
                    "dues_status": legacy_member.get("dues_status", "defaulter"),
                    "is_general_member": role_key == "core_member",
                    "status": "active",
                    "joined_at": legacy_member.get("created_at") or datetime.utcnow(),
                },
            )


def role_key_from_input(role: str | None) -> str:
    normalized = (role or "").strip().lower().replace(" ", "_")
    if normalized in {"owner", "president", "lead", "super_admin", "workspace_owner"}:
        return "owner"
    if normalized in {"secretary", "general_secretary", "scribe"}:
        return "secretary"
    return "core_member"
