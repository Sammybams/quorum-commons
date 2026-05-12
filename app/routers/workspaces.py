from fastapi import APIRouter, Depends, HTTPException

from .. import schemas
from ..database import DESC, MongoStore, get_db
from ..membership import sync_workspace_members_from_legacy
from ..rbac import require_workspace_permission
from ..security import verify_password

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=schemas.WorkspaceOut)
def create_workspace(payload: schemas.WorkspaceCreate, db: MongoStore = Depends(get_db)):
    if db.find_one("workspaces", {"slug": payload.slug}):
        raise HTTPException(status_code=409, detail="Workspace slug already exists")
    return db.insert("workspaces", payload.model_dump())


@router.get("", response_model=list[schemas.WorkspaceOut])
def list_workspaces(db: MongoStore = Depends(get_db)):
    return db.find_many("workspaces", sort=[("created_at", DESC)])


@router.get("/slug/{slug}", response_model=schemas.WorkspaceOut)
def get_workspace_by_slug(slug: str, db: MongoStore = Depends(get_db)):
    workspace = db.find_one("workspaces", {"slug": slug})
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.get("/slug/{slug}/overview", response_model=schemas.WorkspaceOverview)
def get_workspace_overview(slug: str, db: MongoStore = Depends(get_db)):
    workspace = db.find_one("workspaces", {"slug": slug})
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    sync_workspace_members_from_legacy(db, workspace)

    active_filter = {"workspace_id": workspace.id, "status": "active"}
    member_count = db.count("workspace_members", active_filter)
    paid_members = db.count("workspace_members", {**active_filter, "dues_status": "paid"})
    recent_activity = []

    for event in db.find_many("events", {"workspace_id": workspace.id}, sort=[("created_at", DESC)], limit=3):
        recent_activity.append(
            schemas.RecentActivityItem(
                type="event",
                title=event.title,
                description=f"Event scheduled for {event.starts_at}",
                created_at=event.created_at,
            )
        )
    for payment in db.find_many("dues_payments", {"workspace_id": workspace.id}, sort=[("created_at", DESC)], limit=3):
        recent_activity.append(
            schemas.RecentActivityItem(
                type="dues_payment",
                title="Dues payment recorded",
                description=f"NGN {payment.amount:,.0f} · {payment.status}",
                created_at=payment.created_at,
            )
        )
    for announcement in db.find_many("announcements", {"workspace_id": workspace.id}, sort=[("created_at", DESC)], limit=3):
        recent_activity.append(
            schemas.RecentActivityItem(
                type="announcement",
                title=announcement.title,
                description=announcement.get("status", "published").title(),
                created_at=announcement.created_at,
            )
        )
    latest_report = db.find_many("reports", {"workspace_id": workspace.id}, sort=[("created_at", DESC)], limit=1)
    if latest_report:
        report = latest_report[0]
        recent_activity.append(
            schemas.RecentActivityItem(
                type="report",
                title=report.title,
                description=f"{report.get('overall_grade') or report.get('status', 'pending').title()} report",
                created_at=report.get("generated_at") or report.created_at,
            )
        )
    recent_activity = sorted(recent_activity, key=lambda item: item.created_at, reverse=True)[:6]

    return schemas.WorkspaceOverview(
        workspace=workspace,
        counts=schemas.DashboardCounts(
            members=member_count,
            dues_cycles=db.count("dues_cycles", {"workspace_id": workspace.id}),
            events=db.count("events", {"workspace_id": workspace.id}),
            campaigns=db.count("campaigns", {"workspace_id": workspace.id}),
            links=db.count("short_links", {"workspace_id": workspace.id}),
            reports=db.count("reports", {"workspace_id": workspace.id}),
            paid_members=paid_members,
            pending_members=max(member_count - paid_members, 0),
            tasks=db.count("tasks", {"workspace_id": workspace.id}),
            pending_tasks=db.count("tasks", {"workspace_id": workspace.id, "status": {"$in": ["todo", "in_progress"]}}),
            meetings=db.count("meetings", {"workspace_id": workspace.id}),
        ),
        recent_events=db.find_many("events", {"workspace_id": workspace.id}, sort=[("created_at", DESC)], limit=4),
        active_campaigns=db.find_many("campaigns", {"workspace_id": workspace.id}, sort=[("created_at", DESC)], limit=4),
        dues_cycles=db.find_many("dues_cycles", {"workspace_id": workspace.id}, sort=[("created_at", DESC)], limit=4),
        links=db.find_many("short_links", {"workspace_id": workspace.id}, sort=[("created_at", DESC)], limit=4),
        announcements=db.find_many(
            "announcements",
            {"workspace_id": workspace.id, "status": "published"},
            sort=[("is_pinned", DESC), ("published_at", DESC)],
            limit=4,
        ),
        recent_activity=recent_activity,
        latest_report=schemas.WorkspaceLatestReport(
            id=latest_report[0].id,
            title=latest_report[0].title,
            period_label=latest_report[0].get("period_label"),
            status=latest_report[0].get("status", "pending"),
            overall_score=latest_report[0].get("overall_score"),
            overall_grade=latest_report[0].get("overall_grade"),
            generated_at=latest_report[0].get("generated_at"),
        )
        if latest_report
        else None,
    )


@router.get("/{workspace_id}", response_model=schemas.WorkspaceOut)
def get_workspace(workspace_id: int, db: MongoStore = Depends(get_db)):
    workspace = db.find_by_id("workspaces", workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.patch("/{workspace_id}", response_model=schemas.WorkspaceOut)
def update_workspace(
    workspace_id: int,
    payload: schemas.WorkspaceUpdate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("settings.edit")),
):
    workspace = db.find_by_id("workspaces", workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    values = payload.model_dump(exclude_unset=True)
    if values.get("slug") and values["slug"] != workspace.slug:
        if db.find_one("workspaces", {"slug": values["slug"]}):
            raise HTTPException(status_code=409, detail="Workspace slug already exists")
        workspace["slug"] = values["slug"].strip().lower()
    if "name" in values and values["name"] is not None:
        workspace["name"] = values["name"].strip()
    if "description" in values:
        workspace["description"] = values["description"]

    return db.save("workspaces", workspace)


@router.post("/{workspace_id}/transfer-ownership", response_model=schemas.AuthStatusResponse)
def transfer_ownership(
    workspace_id: int,
    payload: schemas.TransferOwnershipRequest,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("ownership.transfer")),
):
    workspace = db.find_by_id("workspaces", workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    acting_user = db.find_by_id("users", membership.user_id)
    if not acting_user or not verify_password(payload.password, acting_user.get("password_hash")):
        raise HTTPException(status_code=401, detail="Password confirmation failed")

    target_membership = db.find_one("workspace_members", {"id": payload.target_member_id, "workspace_id": workspace_id, "status": "active"})
    if not target_membership:
        raise HTTPException(status_code=404, detail="Target member not found")

    owner_role = db.find_one("roles", {"workspace_id": workspace_id, "key": "owner"})
    fallback_role = db.find_by_id("roles", payload.fallback_role_id) if payload.fallback_role_id else db.find_one("roles", {"workspace_id": workspace_id, "key": "core_member"})
    if not owner_role or not fallback_role:
        raise HTTPException(status_code=404, detail="Required roles not found")

    current_owner_membership = db.find_one("workspace_members", {"workspace_id": workspace_id, "user_id": acting_user.id})
    if current_owner_membership:
        current_owner_membership["role_id"] = fallback_role.id
        current_owner_membership["is_general_member"] = fallback_role.key == "core_member"
        db.save("workspace_members", current_owner_membership)

    target_membership["role_id"] = owner_role.id
    target_membership["is_general_member"] = False
    db.save("workspace_members", target_membership)
    workspace["owner_user_id"] = target_membership.user_id
    db.save("workspaces", workspace)
    return schemas.AuthStatusResponse(message="Ownership transferred.")
