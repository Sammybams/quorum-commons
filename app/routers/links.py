from datetime import datetime, timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Response

from .. import schemas
from ..database import DESC, MongoStore, get_db
from ..rbac import require_workspace_permission
from ..utils.revalidate import revalidate_path
from ..utils.slugify import slugify, unique_slug

router = APIRouter(prefix="/workspaces/{workspace_id}/links", tags=["links"])

RESERVED_SLUGS = {
    "api",
    "dashboard",
    "login",
    "register",
    "signup",
    "settings",
    "members",
    "events",
    "dues",
    "fundraising",
    "campaigns",
    "announcements",
    "links",
    "portal",
    "donate",
    "e",
    "r",
    "link-expired",
    "_next",
    "favicon.ico",
}


def _validate_destination(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="Destination URL must start with http:// or https://")
    return url


def _normalize_slug(raw_slug: str) -> str:
    slug = slugify(raw_slug)
    if slug in RESERVED_SLUGS:
        raise HTTPException(status_code=400, detail="That slug is reserved")
    return slug


def _link_or_404(db: MongoStore, workspace_id: int, link_id: int):
    link = db.find_one("short_links", {"id": link_id, "workspace_id": workspace_id})
    if not link:
        raise HTTPException(status_code=404, detail="Short link not found")
    return link


@router.post("", response_model=schemas.LinkOut)
def create_link(
    workspace_id: int,
    payload: schemas.LinkCreate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("settings.edit")),
):
    if not db.find_by_id("workspaces", workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")

    slug = unique_slug(db.collection("short_links"), _normalize_slug(payload.slug))
    destination_url = _validate_destination(payload.destination_url)
    link = db.insert(
        "short_links",
        {
            "workspace_id": workspace_id,
            "click_count": 0,
            "is_active": True,
            **payload.model_dump(),
            "slug": slug,
            "destination_url": destination_url,
        },
    )
    revalidate_path(f"/portal/{db.find_by_id('workspaces', workspace_id).slug}")
    return link


@router.get("", response_model=list[schemas.LinkOut])
def list_links(workspace_id: int, db: MongoStore = Depends(get_db)):
    return db.find_many("short_links", {"workspace_id": workspace_id}, sort=[("created_at", DESC)])


@router.patch("/{link_id}", response_model=schemas.LinkOut)
def update_link(
    workspace_id: int,
    link_id: int,
    payload: schemas.LinkUpdate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("settings.edit")),
):
    link = _link_or_404(db, workspace_id, link_id)
    update = payload.model_dump(exclude_unset=True)

    if "slug" in update and update["slug"]:
        slug = _normalize_slug(update["slug"])
        existing = db.find_one("short_links", {"slug": slug})
        if existing and existing.id != link.id:
            raise HTTPException(status_code=409, detail="Short link slug already exists")
        update["slug"] = slug

    if "destination_url" in update and update["destination_url"]:
        update["destination_url"] = _validate_destination(update["destination_url"])

    update["updated_at"] = datetime.utcnow()
    updated = db.update_one("short_links", {"id": link.id, "workspace_id": workspace_id}, update)
    workspace = db.find_by_id("workspaces", workspace_id)
    if workspace:
        revalidate_path(f"/portal/{workspace.slug}")
    return updated


@router.delete("/{link_id}", status_code=204)
def delete_link(
    workspace_id: int,
    link_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("settings.edit")),
):
    link = _link_or_404(db, workspace_id, link_id)
    db.delete_one("short_links", {"id": link.id, "workspace_id": workspace_id})
    db.delete_many("link_clicks", {"link_id": link.id})
    workspace = db.find_by_id("workspaces", workspace_id)
    if workspace:
        revalidate_path(f"/portal/{workspace.slug}")
    return Response(status_code=204)


@router.get("/{link_id}/analytics", response_model=schemas.LinkAnalyticsOut)
def link_analytics(
    workspace_id: int,
    link_id: int,
    db: MongoStore = Depends(get_db),
):
    link = _link_or_404(db, workspace_id, link_id)
    start = datetime.utcnow() - timedelta(days=29)
    clicks = db.find_many("link_clicks", {"link_id": link.id, "clicked_at": {"$gte": start}})
    counts = {(start + timedelta(days=offset)).date().isoformat(): 0 for offset in range(30)}

    for click in clicks:
        clicked_at = click.get("clicked_at")
        if isinstance(clicked_at, datetime):
            day = clicked_at.date().isoformat()
            counts[day] = counts.get(day, 0) + 1

    return schemas.LinkAnalyticsOut(
        link_id=link.id,
        total=db.count("link_clicks", {"link_id": link.id}),
        daily=[schemas.DailyClickCount(day=day, count=count) for day, count in counts.items()],
    )
