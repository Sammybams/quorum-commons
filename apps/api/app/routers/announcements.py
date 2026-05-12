from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from .. import schemas
from ..database import DESC, MongoStore, get_db
from ..rbac import require_workspace_permission
from ..email import send_announcement_email

router = APIRouter(prefix="/workspaces/{workspace_id}/announcements", tags=["announcements"])

VALID_STATUSES = {"draft", "scheduled", "published", "archived"}
VALID_AUDIENCES = {"all_members", "admins", "general_members", "paid_members", "dues_defaulters", "roles", "levels"}
VALID_CHANNELS = {"in_app", "email"}


def _workspace_or_404(db: MongoStore, workspace_id: int):
    workspace = db.find_by_id("workspaces", workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


def _announcement_or_404(db: MongoStore, workspace_id: int, announcement_id: int):
    announcement = db.find_one("announcements", {"id": announcement_id, "workspace_id": workspace_id})
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return announcement


def _validate_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid announcement status")
    return normalized


def _validate_audience(audience: str) -> str:
    normalized = audience.strip().lower()
    if normalized not in VALID_AUDIENCES:
        raise HTTPException(status_code=400, detail="Invalid announcement audience")
    return normalized


def _normalize_channels(channels: list[str]) -> list[str]:
    normalized = []
    for channel in channels:
        value = channel.strip().lower()
        if value not in VALID_CHANNELS:
            raise HTTPException(status_code=400, detail=f"Invalid announcement channel: {channel}")
        if value not in normalized:
            normalized.append(value)
    return normalized or ["in_app"]


def _eligible_members(db: MongoStore, workspace_id: int, announcement) -> list:
    audience = announcement.get("audience", "all_members")
    target_role_ids = set(announcement.get("target_role_ids") or [])
    target_levels = {str(level).strip().lower() for level in announcement.get("target_levels") or []}
    memberships = db.find_many("workspace_members", {"workspace_id": workspace_id, "status": "active"})
    eligible = []
    for membership in memberships:
        if audience == "admins" and membership.get("is_general_member", False):
            continue
        if audience == "general_members" and not membership.get("is_general_member", False):
            continue
        if audience == "paid_members" and membership.get("dues_status") != "paid":
            continue
        if audience == "dues_defaulters" and membership.get("dues_status") == "paid":
            continue
        if audience == "roles" and membership.role_id not in target_role_ids:
            continue
        if audience == "levels" and str(membership.get("level") or "").strip().lower() not in target_levels:
            continue
        eligible.append(membership)
    return eligible


def _deliver_announcement(db: MongoStore, workspace, announcement) -> None:
    now = datetime.utcnow()
    channels = _normalize_channels(announcement.get("channels") or ["in_app"])
    deliveries = 0
    for membership in _eligible_members(db, workspace.id, announcement):
        user = db.find_by_id("users", membership.user_id)
        if not user:
            continue
        notification = db.find_one(
            "notifications",
            {"workspace_id": workspace.id, "user_id": user.id, "announcement_id": announcement.id},
        )
        if not notification:
            db.insert(
                "notifications",
                {
                    "workspace_id": workspace.id,
                    "user_id": user.id,
                    "announcement_id": announcement.id,
                    "title": announcement.title,
                    "body": announcement.body,
                    "channels": channels,
                    "read_at": None,
                    "delivered_at": now,
                },
            )
        if "email" in channels and user.get("email"):
            send_announcement_email(
                to_email=user.email,
                full_name=user.full_name,
                workspace_name=workspace.name,
                title=announcement.title,
                body=announcement.body,
            )
        deliveries += 1
    announcement["status"] = "published"
    announcement["published_at"] = announcement.get("published_at") or now
    announcement["delivered_at"] = now
    announcement["delivery_count"] = deliveries
    announcement["updated_at"] = now
    db.save("announcements", announcement)


def _process_scheduled_announcements(db: MongoStore, workspace_id: int) -> None:
    workspace = _workspace_or_404(db, workspace_id)
    now = datetime.utcnow()
    scheduled = db.find_many(
        "announcements",
        {"workspace_id": workspace_id, "status": "scheduled"},
        sort=[("scheduled_for", DESC), ("created_at", DESC)],
    )
    for announcement in scheduled:
        scheduled_for = announcement.get("scheduled_for")
        if scheduled_for and scheduled_for <= now:
            _deliver_announcement(db, workspace, announcement)


@router.post("", response_model=schemas.AnnouncementOut, status_code=201)
def create_announcement(
    workspace_id: int,
    payload: schemas.AnnouncementCreate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("announcements.publish")),
):
    workspace = _workspace_or_404(db, workspace_id)
    status = _validate_status(payload.status)
    now = datetime.utcnow()
    audience = _validate_audience(payload.audience)
    announcement = db.insert(
        "announcements",
        {
            "workspace_id": workspace_id,
            "title": payload.title.strip(),
            "body": payload.body.strip(),
            "status": status,
            "is_pinned": payload.is_pinned,
            "published_at": payload.published_at or (now if status == "published" else None),
            "scheduled_for": payload.scheduled_for,
            "delivered_at": now if status == "published" else None,
            "delivery_count": 0,
            "audience": audience,
            "channels": _normalize_channels(payload.channels),
            "target_role_ids": payload.target_role_ids,
            "target_levels": payload.target_levels,
            "archived_at": now if status == "archived" else None,
            "updated_at": now,
        },
    )
    if status == "published":
        _deliver_announcement(db, workspace, announcement)
        announcement = _announcement_or_404(db, workspace_id, announcement.id)
    return announcement


@router.get("", response_model=list[schemas.AnnouncementOut])
def list_announcements(workspace_id: int, db: MongoStore = Depends(get_db)):
    _workspace_or_404(db, workspace_id)
    _process_scheduled_announcements(db, workspace_id)
    return db.find_many("announcements", {"workspace_id": workspace_id}, sort=[("is_pinned", DESC), ("created_at", DESC)])


@router.patch("/{announcement_id}", response_model=schemas.AnnouncementOut)
def update_announcement(
    workspace_id: int,
    announcement_id: int,
    payload: schemas.AnnouncementUpdate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("announcements.publish")),
):
    workspace = _workspace_or_404(db, workspace_id)
    announcement = _announcement_or_404(db, workspace_id, announcement_id)
    values = payload.model_dump(exclude_unset=True)
    now = datetime.utcnow()

    if "title" in values and values["title"] is not None:
        announcement["title"] = values["title"].strip()
    if "body" in values and values["body"] is not None:
        announcement["body"] = values["body"].strip()
    if "is_pinned" in values and values["is_pinned"] is not None:
        announcement["is_pinned"] = values["is_pinned"]
    if "published_at" in values:
        announcement["published_at"] = values["published_at"]
    if "scheduled_for" in values:
        announcement["scheduled_for"] = values["scheduled_for"]
    if "audience" in values and values["audience"] is not None:
        announcement["audience"] = _validate_audience(values["audience"])
    if "channels" in values and values["channels"] is not None:
        announcement["channels"] = _normalize_channels(values["channels"])
    if "target_role_ids" in values and values["target_role_ids"] is not None:
        announcement["target_role_ids"] = values["target_role_ids"]
    if "target_levels" in values and values["target_levels"] is not None:
        announcement["target_levels"] = values["target_levels"]
    if "status" in values and values["status"] is not None:
        status = _validate_status(values["status"])
        announcement["status"] = status
        if status == "published" and announcement.get("published_at") is None:
            announcement["published_at"] = now
        if status == "archived":
            announcement["archived_at"] = now
            announcement["is_pinned"] = False
        elif announcement.get("archived_at") is not None:
            announcement["archived_at"] = None
    announcement["updated_at"] = now
    announcement = db.save("announcements", announcement)
    if announcement.status == "published" and announcement.get("delivered_at") is None:
        _deliver_announcement(db, workspace, announcement)
        announcement = _announcement_or_404(db, workspace_id, announcement.id)
    return announcement


@router.post("/process-scheduled", response_model=schemas.AuthStatusResponse)
def process_scheduled_announcements(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("announcements.publish")),
):
    _process_scheduled_announcements(db, workspace_id)
    return schemas.AuthStatusResponse(message="Scheduled announcements processed.")
