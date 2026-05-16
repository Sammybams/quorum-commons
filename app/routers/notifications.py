from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from .. import schemas
from ..database import DESC, MongoStore, get_db
from ..rbac import require_workspace_permission


router = APIRouter(prefix="/workspaces/{workspace_id}/notifications", tags=["notifications"])


@router.get("", response_model=list[schemas.NotificationOut])
def list_notifications(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("dashboard.view")),
):
    notifications = db.find_many(
        "notifications",
        {"workspace_id": workspace_id, "user_id": membership.user_id},
        sort=[("created_at", DESC)],
        limit=50,
    )
    return [_notification_out(item) for item in notifications]


@router.post("/{notification_id}/read", response_model=schemas.NotificationOut)
def mark_notification_read(
    workspace_id: int,
    notification_id: int,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("dashboard.view")),
):
    notification = db.find_one("notifications", {"workspace_id": workspace_id, "id": notification_id, "user_id": membership.user_id})
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification["read_at"] = datetime.utcnow()
    saved = db.save("notifications", notification)
    return _notification_out(saved)


@router.post("/read-all")
def mark_all_notifications_read(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("dashboard.view")),
):
    notifications = db.find_many("notifications", {"workspace_id": workspace_id, "user_id": membership.user_id, "read_at": None})
    now = datetime.utcnow()
    count = 0
    for item in notifications:
        item["read_at"] = now
        db.save("notifications", item)
        count += 1
    return {"ok": True, "updated": count}


def _notification_out(item) -> schemas.NotificationOut:
    return schemas.NotificationOut(
        id=item.id,
        workspace_id=item.workspace_id,
        user_id=item.user_id,
        title=item.get("title") or "",
        body=item.get("body") or "",
        notification_type=item.get("notification_type") or "general",
        action_url=item.get("action_url"),
        read_at=item.get("read_at"),
        delivered_at=item.get("delivered_at"),
        metadata=item.get("metadata") or {},
        created_at=item.created_at,
    )
