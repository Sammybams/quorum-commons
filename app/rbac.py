from fastapi import Depends, Header, HTTPException

from . import models
from .database import MongoStore, get_db
from .security import decode_access_token


OWNER_PERMISSIONS = [
    "dashboard.view",
    "members.view",
    "members.invite",
    "members.edit",
    "members.remove",
    "dues.view",
    "dues.manage",
    "dues.confirm_payment",
    "events.view",
    "events.manage",
    "events.attendance",
    "meetings.view",
    "meetings.manage",
    "meetings.publish_minutes",
    "tasks.view",
    "tasks.assign",
    "tasks.manage_all",
    "campaigns.view",
    "campaigns.manage",
    "campaigns.confirm_contribution",
    "reports.view",
    "reports.generate",
    "budgets.view",
    "budgets.manage",
    "announcements.view",
    "announcements.publish",
    "settings.view",
    "settings.edit",
    "roles.manage",
    "billing.manage",
    "integrations.manage",
    "ownership.transfer",
]

SECRETARY_PERMISSIONS = [
    "dashboard.view",
    "members.view",
    "members.invite",
    "dues.view",
    "events.view",
    "meetings.view",
    "meetings.manage",
    "meetings.publish_minutes",
    "tasks.view",
    "tasks.assign",
    "campaigns.view",
    "reports.view",
    "reports.generate",
    "budgets.view",
    "announcements.view",
    "announcements.publish",
    "settings.view",
]

CORE_MEMBER_PERMISSIONS = [
    "dashboard.view",
    "members.view",
    "dues.view",
    "events.view",
    "meetings.view",
    "tasks.view",
    "campaigns.view",
    "reports.view",
    "announcements.view",
]

DEFAULT_ROLE_DEFINITIONS = [
    ("owner", "Super Admin", "Primary workspace owner role with full access to every module and setting.", OWNER_PERMISSIONS, True),
    ("secretary", "Secretary", "System secretary role for meetings, minutes, and announcements.", SECRETARY_PERMISSIONS, True),
    ("core_member", "Core Member", "General member role with personal read access.", CORE_MEMBER_PERMISSIONS, False),
]


def ensure_default_roles(db: MongoStore, workspace_id: int) -> dict[str, models.Role]:
    roles: dict[str, models.Role] = {}
    for key, name, description, permissions, is_system_role in DEFAULT_ROLE_DEFINITIONS:
        role = db.find_one("roles", {"workspace_id": workspace_id, "key": key})
        if role is None:
            role = db.insert(
                "roles",
                {
                    "workspace_id": workspace_id,
                    "key": key,
                    "name": name,
                    "description": description,
                    "is_system_role": is_system_role,
                    "permissions": sorted(set(permissions)),
                },
            )
        elif role.get("is_system_role"):
            changed = False
            if role.name != name:
                role["name"] = name
                changed = True
            if role.get("description") != description:
                role["description"] = description
                changed = True
            normalized_permissions = sorted(set(permissions))
            if sorted(role.get("permissions", [])) != normalized_permissions:
                role["permissions"] = normalized_permissions
                changed = True
            if changed:
                db.save("roles", role)
        roles[key] = role
    return roles


def hydrate_user(db: MongoStore, user: models.User) -> models.User:
    memberships = db.find_many("workspace_members", {"user_id": user.id, "status": "active"})
    for membership in memberships:
        membership.user = user
        membership.workspace = db.find_by_id("workspaces", membership.workspace_id)
        membership.role = db.find_by_id("roles", membership.role_id)
    user.workspace_memberships = memberships
    return user


def hydrate_membership(db: MongoStore, membership: models.WorkspaceMember) -> models.WorkspaceMember:
    membership.user = db.find_by_id("users", membership.user_id)
    membership.workspace = db.find_by_id("workspaces", membership.workspace_id)
    membership.role = db.find_by_id("roles", membership.role_id)
    return membership


def get_current_user(
    authorization: str | None = Header(default=None),
    db: MongoStore = Depends(get_db),
) -> models.User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing access token")

    payload = decode_access_token(authorization.split(" ", 1)[1])
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    if db.find_one("revoked_tokens", {"jti": payload.get("jti")}):
        raise HTTPException(status_code=401, detail="Access token has been revoked")

    user = db.find_by_id("users", int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return hydrate_user(db, user)


def require_workspace_permission(permission: str):
    def dependency(
        workspace_id: int,
        user: models.User = Depends(get_current_user),
        db: MongoStore = Depends(get_db),
    ) -> models.WorkspaceMember:
        ensure_default_roles(db, workspace_id)
        membership = db.find_one("workspace_members", {"workspace_id": workspace_id, "user_id": user.id, "status": "active"})
        if not membership:
            raise HTTPException(status_code=403, detail="Insufficient permission")
        hydrate_membership(db, membership)
        if not membership.role or permission not in membership.role.permissions:
            raise HTTPException(status_code=403, detail="Insufficient permission")
        return membership

    return dependency
