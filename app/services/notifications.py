from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx

from ..database import DESC, MongoStore
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


def _whatsapp_gateway_base_url() -> str:
    return str(os.getenv("WHATSAPP_GATEWAY_INTERNAL_URL") or "http://127.0.0.1:3001").rstrip("/")


def _whatsapp_gateway_headers() -> dict[str, str]:
    token = str(os.getenv("WHATSAPP_GATEWAY_TOKEN") or "").strip()
    return {"x-internal-token": token} if token else {}


def _member_phone_number(member, user) -> str | None:
    phone = str(member.get("phone_number") or user.get("phone") or "").strip()
    return phone or None


def _workspace_whatsapp_channel(db: MongoStore, *, workspace_id: int):
    channels = db.find_many(
        "community_channels",
        {"workspace_id": workspace_id, "provider": "whatsapp", "status": "connected"},
        sort=[("connected_at", DESC), ("updated_at", DESC)],
        limit=1,
    )
    return channels[0] if channels else None


def _send_whatsapp_member_message(
    db: MongoStore,
    *,
    workspace_id: int,
    phone_number: str | None,
    text: str,
) -> bool:
    normalized_phone = str(phone_number or "").strip()
    normalized_text = str(text or "").strip()
    if not normalized_phone or not normalized_text:
        return False
    channel = _workspace_whatsapp_channel(db, workspace_id=workspace_id)
    if not channel:
        return False
    try:
        response = httpx.post(
            f"{_whatsapp_gateway_base_url()}/internal/sessions/{channel.id}/send-message",
            json={"recipientPhoneNumber": normalized_phone, "text": normalized_text[:1200]},
            headers=_whatsapp_gateway_headers(),
            timeout=20.0,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return False
    return True


def _opportunity_whatsapp_text(*, workspace_name: str, opportunity, action_url: str, prefix: str) -> str:
    title = str(opportunity.get("title") or "a community opportunity").strip()
    location = str(opportunity.get("location") or opportunity.get("venue") or "").strip()
    summary = str(opportunity.get("summary") or "").strip()
    parts = [f"{prefix} in {workspace_name}: {title}."]
    if location:
        parts.append(f"Location: {location}.")
    if summary:
        parts.append(f"{summary[:180]}.")
    parts.append(f"Open Quorum: {action_url}")
    return " ".join(part for part in parts if part).replace("..", ".")


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
    email_address = str(user.get("email") or "").strip()
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

    if email_address:
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
                    to_email=email_address,
                    full_name=user.full_name,
                    workspace_name=workspace.name,
                    task_title=str(task.get("title") or "Task"),
                    task_description=task.get("description"),
                    due_date=task.get("due_date"),
                    action_url=email_action_url,
                )
                if result.status == "sent":
                    _send_whatsapp_member_message(
                        db,
                        workspace_id=workspace_id,
                        phone_number=_member_phone_number(member, user),
                        text=f"You have been assigned a task in {workspace.name}: {str(task.get('title') or 'Task')[:140]}. Open Quorum: {email_action_url}",
                    )
                    return notification
            except GoogleIntegrationError:
                pass

        send_task_assignment_email(
            to_email=email_address,
            full_name=user.full_name,
            workspace_name=workspace.name,
            task_title=str(task.get("title") or "Task"),
            task_description=task.get("description"),
            due_date=task.get("due_date"),
            action_url=email_action_url,
        )

    _send_whatsapp_member_message(
        db,
        workspace_id=workspace_id,
        phone_number=_member_phone_number(member, user),
        text=f"You have been assigned a task in {workspace.name}: {str(task.get('title') or 'Task')[:140]}. Open Quorum: {email_action_url}",
    )
    return notification


def notify_member_opportunity_recommendation(
    db: MongoStore,
    *,
    workspace_id: int,
    member_id: int,
    opportunity,
    dedupe_key: str,
) -> dict | None:
    member = db.find_one("workspace_members", {"workspace_id": workspace_id, "id": member_id})
    if not member:
        return None
    user = db.find_by_id("users", member.user_id)
    workspace = db.find_by_id("workspaces", workspace_id)
    if not user or not workspace:
        return None

    action_url = f"/{workspace.slug}/opportunities"
    notification = create_notification(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        title="Recommended opportunity for you",
        body=f"{opportunity.get('title') or 'A community opportunity'} looks relevant to your profile.",
        notification_type="opportunity_recommendation",
        action_url=action_url,
        metadata={"opportunity_id": opportunity.id, "member_id": member_id},
        dedupe_key=dedupe_key,
    )
    _send_whatsapp_member_message(
        db,
        workspace_id=workspace_id,
        phone_number=_member_phone_number(member, user),
        text=_opportunity_whatsapp_text(
            workspace_name=workspace.name,
            opportunity=opportunity,
            action_url=_absolute_frontend_url(action_url),
            prefix="New recommended opportunity",
        ),
    )
    return notification


def notify_member_opportunity_workflow(
    db: MongoStore,
    *,
    workspace_id: int,
    member_id: int,
    opportunity,
    match_id: int,
    status: str,
) -> dict | None:
    member = db.find_one("workspace_members", {"workspace_id": workspace_id, "id": member_id})
    if not member:
        return None
    user = db.find_by_id("users", member.user_id)
    workspace = db.find_by_id("workspaces", workspace_id)
    if not user or not workspace:
        return None

    action_url = f"/{workspace.slug}/opportunities"
    body = (
        f"A community lead has contacted you about {opportunity.get('title') or 'an opportunity'}."
        if status == "contacted"
        else f"You have been assigned to {opportunity.get('title') or 'an opportunity'}."
    )
    notification = create_notification(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        title="Opportunity update",
        body=body,
        notification_type="opportunity_workflow",
        action_url=action_url,
        metadata={"opportunity_id": opportunity.id, "match_id": match_id, "status": status},
        dedupe_key=f"match-status:{match_id}:{status}",
    )
    _send_whatsapp_member_message(
        db,
        workspace_id=workspace_id,
        phone_number=_member_phone_number(member, user),
        text=_opportunity_whatsapp_text(
            workspace_name=workspace.name,
            opportunity=opportunity,
            action_url=_absolute_frontend_url(action_url),
            prefix="Opportunity update",
        ),
    )
    return notification
