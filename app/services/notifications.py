from __future__ import annotations

import os
from datetime import datetime

from ..database import MongoStore
from ..email import send_task_assignment_email
from .google import (
    GoogleIntegrationError,
    access_token_for_integration,
    gmail_send_available,
    send_gmail_task_assignment,
)


def create_notification(
    db: MongoStore,
    *,
    workspace_id: int,
    user_id: int,
    title: str,
    body: str,
    notification_type: str,
    action_url: str | None = None,
    metadata: dict[str, object] | None = None,
    dedupe_key: str | None = None,
) -> dict:
    if dedupe_key:
        existing = db.find_one(
            "notifications",
            {"workspace_id": workspace_id, "user_id": user_id, "notification_type": notification_type, "dedupe_key": dedupe_key},
        )
        if existing:
            return existing
    return db.insert(
        "notifications",
        {
            "workspace_id": workspace_id,
            "user_id": user_id,
            "title": title.strip(),
            "body": body.strip(),
            "notification_type": notification_type,
            "action_url": action_url,
            "metadata": metadata or {},
            "read_at": None,
            "delivered_at": datetime.utcnow(),
            "channels": ["in_app"],
            "dedupe_key": dedupe_key,
        },
    )


def notify_workspace_admins(
    db: MongoStore,
    *,
    workspace_id: int,
    title: str,
    body: str,
    notification_type: str,
    action_url: str | None = None,
    metadata: dict[str, object] | None = None,
    dedupe_key: str | None = None,
) -> list[dict]:
    recipients = db.find_many("workspace_members", {"workspace_id": workspace_id, "status": "active"})
    created: list[dict] = []
    for membership in recipients:
        if membership.get("is_general_member", False):
            continue
        created.append(
            create_notification(
                db,
                workspace_id=workspace_id,
                user_id=membership.user_id,
                title=title,
                body=body,
                notification_type=notification_type,
                action_url=action_url,
                metadata=metadata,
                dedupe_key=f"{dedupe_key}:{membership.user_id}" if dedupe_key else None,
            )
        )
    return created


def _absolute_frontend_url(path: str) -> str:
    base = (
        os.getenv("FRONTEND_URL")
        or os.getenv("PUBLIC_APP_URL")
        or os.getenv("APP_URL")
        or "http://localhost:3000"
    ).rstrip("/")
    return f"{base}/{path.lstrip('/')}"


def notify_task_assignee(
    db: MongoStore,
    *,
    workspace_id: int,
    member_id: int,
    task,
    title: str | None = None,
) -> dict | None:
    member = db.find_one("workspace_members", {"workspace_id": workspace_id, "id": member_id})
    if not member:
        return None
    user = db.find_by_id("users", member.user_id)
    workspace = db.find_by_id("workspaces", workspace_id)
    if not user or not workspace:
        return None

    action_url = f"/{workspace.slug}/tasks"
    email_action_url = _absolute_frontend_url(action_url)
    notification = create_notification(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        title=title or "Task assigned to you",
        body=f"You have been assigned: {str(task.get('title') or 'A task')[:120]}",
        notification_type="task_assignment",
        action_url=action_url,
        metadata={"task_id": task.id, "member_id": member_id},
        dedupe_key=f"task-assignment:{task.id}:{user.id}",
    )

    integration = db.find_one("integrations", {"workspace_id": workspace_id, "provider": "google_workspace"})
    if gmail_send_available(integration):
        try:
            access_token, expires_at = access_token_for_integration(integration)
            integration["expires_at"] = expires_at
            integration["updated_at"] = datetime.utcnow()
            db.save("integrations", integration)
            result = send_gmail_task_assignment(
                access_token=access_token,
                connected_email=integration.get("connected_email") or "",
                sender_name=integration.get("connected_name") or workspace.name,
                to_email=user.email,
                full_name=user.full_name,
                workspace_name=workspace.name,
                task_title=str(task.get("title") or "Task"),
                task_description=task.get("description"),
                due_date=task.get("due_date"),
                action_url=email_action_url,
            )
            if result.status == "sent":
                return notification
        except GoogleIntegrationError:
            pass

    send_task_assignment_email(
        to_email=user.email,
        full_name=user.full_name,
        workspace_name=workspace.name,
        task_title=str(task.get("title") or "Task"),
        task_description=task.get("description"),
        due_date=task.get("due_date"),
        action_url=email_action_url,
    )
    return notification
