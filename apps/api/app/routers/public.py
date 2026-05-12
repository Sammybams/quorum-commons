from datetime import datetime
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from .. import schemas
from ..database import DESC, MongoStore, get_db
from ..payments import PaymentInitializationError, initialize_paystack_transaction, payment_callback_url
from .campaigns import _contribution_out, _stream_out

router = APIRouter(prefix="/public", tags=["public"])


def _referer_platform(referer: str | None) -> str:
    if not referer or referer == "direct":
        return "direct"
    host = urlparse(referer).netloc.lower()
    if "instagram" in host:
        return "instagram"
    if "facebook" in host or "fb." in host:
        return "facebook"
    if "twitter" in host or "x.com" in host:
        return "x"
    if "linkedin" in host:
        return "linkedin"
    if "whatsapp" in host:
        return "whatsapp"
    return host or "unknown"


def _is_expired(short_link) -> bool:
    expires_at = short_link.get("expires_at")
    if not expires_at:
        return False
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return False
    if getattr(expires_at, "tzinfo", None):
        expires_at = expires_at.replace(tzinfo=None)
    return expires_at < datetime.utcnow()


@router.get("/e/{event_slug}")
def get_public_event(event_slug: str, db: MongoStore = Depends(get_db)):
    event = db.find_one("events", {"slug": event_slug})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    workspace = db.find_by_id("workspaces", event.workspace_id)
    return {
        "title": event.title,
        "slug": event.slug,
        "event_type": event.event_type,
        "starts_at": event.starts_at,
        "venue": event.get("venue"),
        "description": event.get("description"),
        "rsvp_enabled": event.get("rsvp_enabled", True),
        "rsvp_count": event.get("rsvp_count", 0),
        "thumbnail_url": event.get("thumbnail_url"),
        "workspace_name": workspace.name if workspace else "Quorum",
        "workspace_slug": workspace.slug if workspace else "",
    }


@router.post("/e/{event_slug}/rsvp", response_model=schemas.EventAttendeeOut, status_code=201)
def public_event_rsvp(event_slug: str, payload: schemas.EventAttendeeCreate, db: MongoStore = Depends(get_db)):
    event = db.find_one("events", {"slug": event_slug})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not event.get("rsvp_enabled", True):
        raise HTTPException(status_code=400, detail="RSVP is disabled for this event")

    attendee = db.find_one("event_attendees", {"event_id": event.id, "email": payload.email.strip().lower()})
    if attendee:
        return schemas.EventAttendeeOut(
            id=attendee.id,
            event_id=attendee.event_id,
            workspace_id=attendee.workspace_id,
            member_id=attendee.get("member_id"),
            full_name=attendee.full_name,
            email=attendee.email,
            status=attendee.get("status", "registered"),
            rsvp_at=attendee.rsvp_at,
            checked_in_at=attendee.get("checked_in_at"),
        )

    attendee = db.insert(
        "event_attendees",
        {
            "event_id": event.id,
            "workspace_id": event.workspace_id,
            "member_id": None,
            "full_name": payload.full_name.strip(),
            "email": payload.email.strip().lower(),
            "status": "registered",
            "rsvp_at": datetime.utcnow(),
            "checked_in_at": None,
        },
    )
    db.increment("events", {"id": event.id}, "rsvp_count", 1)
    return schemas.EventAttendeeOut(
        id=attendee.id,
        event_id=attendee.event_id,
        workspace_id=attendee.workspace_id,
        member_id=None,
        full_name=attendee.full_name,
        email=attendee.email,
        status=attendee.status,
        rsvp_at=attendee.rsvp_at,
        checked_in_at=attendee.get("checked_in_at"),
    )


@router.get("/donate/{campaign_slug}")
def get_public_campaign(campaign_slug: str, db: MongoStore = Depends(get_db)):
    campaign = db.find_one("campaigns", {"slug": campaign_slug})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    workspace = db.find_by_id("workspaces", campaign.workspace_id)
    streams = db.find_many("funding_streams", {"campaign_id": campaign.id})
    contributions = db.find_many("contributions", {"campaign_id": campaign.id, "status": "confirmed"})
    confirmed_contributors = {
        contribution.get("contributor_email") or contribution.get("contributor_name") or str(contribution.id)
        for contribution in contributions
    }
    return {
        "name": campaign.name,
        "slug": campaign.slug,
        "target_amount": campaign.target_amount,
        "raised_amount": campaign.get("raised_amount", 0),
        "status": campaign.status,
        "progress_pct": min(100, round((campaign.get("raised_amount", 0) / campaign.target_amount) * 100)) if campaign.target_amount else 0,
        "workspace_name": workspace.name,
        "workspace_slug": workspace.slug,
        "workspace": {"name": workspace.name, "slug": workspace.slug},
        "funding_streams": [_stream_out(db, stream).model_dump() for stream in streams],
        "contributor_count": len(confirmed_contributors),
    }


@router.post("/donate/{campaign_slug}/submissions", response_model=schemas.PublicContributionResponse)
def submit_public_contribution(
    campaign_slug: str,
    payload: schemas.PublicContributionCreate,
    db: MongoStore = Depends(get_db),
):
    campaign = db.find_one("campaigns", {"slug": campaign_slug})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != "active":
        raise HTTPException(status_code=400, detail="Campaign is not accepting contributions")

    if payload.stream_id:
        stream = db.find_one(
            "funding_streams",
            {"id": payload.stream_id, "campaign_id": campaign.id, "workspace_id": campaign.workspace_id},
        )
        if not stream:
            raise HTTPException(status_code=404, detail="Funding stream not found")

    reference = f"QRM-CAMP-{uuid4().hex[:14].upper()}"
    checkout = None
    if payload.contributor_email:
        try:
            checkout = initialize_paystack_transaction(
                email=payload.contributor_email,
                amount=payload.amount,
                reference=reference,
                callback_url=payment_callback_url(f"/donate/{campaign.slug}"),
                metadata={
                    "type": "campaign_contribution",
                    "campaign_id": campaign.id,
                    "campaign_slug": campaign.slug,
                    "workspace_id": campaign.workspace_id,
                    "stream_id": payload.stream_id,
                },
            )
        except PaymentInitializationError as exc:
            raise HTTPException(status_code=502, detail=f"Unable to initialize payment: {exc}") from exc

    contribution = db.insert(
        "contributions",
        {
            "workspace_id": campaign.workspace_id,
            "campaign_id": campaign.id,
            "stream_id": payload.stream_id,
            "contributor_name": payload.contributor_name,
            "contributor_email": payload.contributor_email,
            "amount": payload.amount,
            "method": "paystack" if checkout else "public",
            "gateway_ref": reference,
            "receipt_url": None,
            "is_anonymous": payload.is_anonymous,
            "status": "pending",
            "confirmed_by_user_id": None,
            "confirmed_at": None,
        },
    )

    return schemas.PublicContributionResponse(
        contribution=_contribution_out(db, contribution),
        payment_reference=reference,
        checkout_url=checkout.authorization_url if checkout else None,
        access_code=checkout.access_code if checkout else None,
    )


@router.get("/portal/{workspace_slug}")
def get_public_portal(workspace_slug: str, db: MongoStore = Depends(get_db)):
    workspace = db.find_one("workspaces", {"slug": workspace_slug})
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    links = db.find_many("short_links", {"workspace_id": workspace.id, "is_active": True}, sort=[("created_at", DESC)])
    events = db.find_many("events", {"workspace_id": workspace.id}, sort=[("created_at", DESC)], limit=5)
    announcements = db.find_many(
        "announcements",
        {"workspace_id": workspace.id, "status": "published"},
        sort=[("is_pinned", DESC), ("published_at", DESC)],
        limit=5,
    )

    return {
        "workspace": {"name": workspace.name, "slug": workspace.slug, "description": workspace.get("description")},
        "links": [
            {
                "id": item.id,
                "slug": item.slug,
                "title": item.get("title"),
                "destination_url": item.destination_url,
                "click_count": item.get("click_count", 0),
                "expires_at": item.get("expires_at"),
            }
            for item in links
            if not _is_expired(item)
        ],
        "events": [
            {
                "title": item.title,
                "slug": item.slug,
                "starts_at": item.starts_at,
                "venue": item.get("venue"),
                "thumbnail_url": item.get("thumbnail_url"),
            }
            for item in events
        ],
        "announcements": [
            {"title": item.title, "body": item.body, "is_pinned": item.get("is_pinned", False), "published_at": item.get("published_at")}
            for item in announcements
        ],
    }


@router.get("/resolve/{slug}")
def resolve_public_short_link(slug: str, db: MongoStore = Depends(get_db)):
    short_link = db.find_one("short_links", {"slug": slug, "is_active": True})
    if not short_link:
        raise HTTPException(status_code=404, detail="Short link not found")
    if _is_expired(short_link):
        raise HTTPException(status_code=410, detail="Short link has expired")
    return {
        "link_id": short_link.id,
        "slug": short_link.slug,
        "destination": short_link.destination_url,
        "destination_url": short_link.destination_url,
    }


@router.post("/click")
def log_short_link_click(payload: schemas.ClickRequest, db: MongoStore = Depends(get_db)):
    short_link = db.find_one("short_links", {"id": payload.link_id, "is_active": True})
    if not short_link:
        raise HTTPException(status_code=404, detail="Short link not found")
    if _is_expired(short_link):
        raise HTTPException(status_code=410, detail="Short link has expired")

    db.insert(
        "link_clicks",
        {
            "link_id": short_link.id,
            "workspace_id": short_link.workspace_id,
            "slug": short_link.slug,
            "referer": payload.referer or "direct",
            "platform": _referer_platform(payload.referer),
            "user_agent": payload.user_agent,
            "clicked_at": datetime.utcnow(),
        },
    )
    updated = db.increment("short_links", {"id": short_link.id}, "click_count", 1)
    return {"ok": True, "click_count": updated.get("click_count", 0) if updated else short_link.get("click_count", 0) + 1}


@router.get("/r/{slug}")
def resolve_short_link(slug: str, db: MongoStore = Depends(get_db)):
    short_link = db.find_one("short_links", {"slug": slug, "is_active": True})
    if not short_link:
        raise HTTPException(status_code=404, detail="Short link not found")
    if _is_expired(short_link):
        raise HTTPException(status_code=410, detail="Short link has expired")
    db.increment("short_links", {"id": short_link.id}, "click_count", 1)
    short_link["click_count"] = short_link.get("click_count", 0) + 1
    return {"destination_url": short_link.destination_url, "click_count": short_link.click_count}
