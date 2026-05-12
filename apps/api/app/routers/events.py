from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from .. import schemas
from ..database import DESC, MongoStore, get_db
from ..rbac import require_workspace_permission

router = APIRouter(prefix="/workspaces/{workspace_id}/events", tags=["events"])


def _event_or_404(db: MongoStore, workspace_id: int, event_id: int):
    event = db.find_one("events", {"id": event_id, "workspace_id": workspace_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def _attendee_out(attendee) -> schemas.EventAttendeeOut:
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


@router.post("", response_model=schemas.EventOut)
def create_event(
    workspace_id: int,
    payload: schemas.EventCreate,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("events.manage")),
):
    if not db.find_by_id("workspaces", workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    if db.find_one("events", {"slug": payload.slug}):
        raise HTTPException(status_code=409, detail="Event slug already exists")

    return db.insert(
        "events",
        {"workspace_id": workspace_id, "rsvp_count": 0, "created_by_user_id": membership.user_id, **payload.model_dump()},
    )


@router.get("", response_model=list[schemas.EventOut])
def list_events(workspace_id: int, db: MongoStore = Depends(get_db)):
    return db.find_many("events", {"workspace_id": workspace_id}, sort=[("created_at", DESC)])


@router.get("/{event_id}", response_model=schemas.EventDetailOut)
def get_event(workspace_id: int, event_id: int, db: MongoStore = Depends(get_db)):
    event = _event_or_404(db, workspace_id, event_id)
    attendees = db.find_many("event_attendees", {"event_id": event.id}, sort=[("rsvp_at", DESC)])
    return schemas.EventDetailOut(**event, attendees=[_attendee_out(attendee) for attendee in attendees])


@router.patch("/{event_id}", response_model=schemas.EventOut)
def update_event(
    workspace_id: int,
    event_id: int,
    payload: schemas.EventUpdate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("events.manage")),
):
    event = _event_or_404(db, workspace_id, event_id)
    values = payload.model_dump(exclude_unset=True)
    event.update(values)
    return db.save("events", event)


@router.delete("/{event_id}")
def delete_event(
    workspace_id: int,
    event_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("events.manage")),
):
    _event_or_404(db, workspace_id, event_id)
    db.delete_one("events", {"id": event_id, "workspace_id": workspace_id})
    db.delete_many("event_attendees", {"event_id": event_id})
    return {"ok": True}


@router.post("/{event_id}/rsvp", response_model=schemas.EventAttendeeOut, status_code=201)
def rsvp_to_event(
    workspace_id: int,
    event_id: int,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("events.view")),
):
    event = _event_or_404(db, workspace_id, event_id)
    attendee = db.find_one("event_attendees", {"event_id": event.id, "member_id": membership.id})
    if attendee:
        return _attendee_out(attendee)
    user = db.find_by_id("users", membership.user_id)
    attendee = db.insert(
        "event_attendees",
        {
            "event_id": event.id,
            "workspace_id": workspace_id,
            "member_id": membership.id,
            "full_name": user.full_name if user else "Member",
            "email": user.email if user else "",
            "status": "registered",
            "rsvp_at": datetime.utcnow(),
            "checked_in_at": None,
        },
    )
    db.increment("events", {"id": event.id}, "rsvp_count", 1)
    return _attendee_out(attendee)


@router.delete("/{event_id}/rsvp")
def cancel_rsvp(
    workspace_id: int,
    event_id: int,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("events.view")),
):
    event = _event_or_404(db, workspace_id, event_id)
    deleted = db.delete_one("event_attendees", {"event_id": event.id, "member_id": membership.id})
    if deleted:
        db.increment("events", {"id": event.id}, "rsvp_count", -1)
    return {"ok": True}


@router.get("/{event_id}/attendees", response_model=list[schemas.EventAttendeeOut])
def list_attendees(
    workspace_id: int,
    event_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("events.attendance")),
):
    event = _event_or_404(db, workspace_id, event_id)
    attendees = db.find_many("event_attendees", {"event_id": event.id}, sort=[("rsvp_at", DESC)])
    return [_attendee_out(attendee) for attendee in attendees]


@router.post("/{event_id}/check-in/{attendee_id}", response_model=schemas.EventAttendeeOut)
def check_in_attendee(
    workspace_id: int,
    event_id: int,
    attendee_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("events.attendance")),
):
    _event_or_404(db, workspace_id, event_id)
    attendee = db.find_one("event_attendees", {"id": attendee_id, "event_id": event_id, "workspace_id": workspace_id})
    if not attendee:
        raise HTTPException(status_code=404, detail="Attendee not found")
    attendee["status"] = "checked_in"
    attendee["checked_in_at"] = datetime.utcnow()
    attendee = db.save("event_attendees", attendee)
    return _attendee_out(attendee)


@router.get("/analytics/summary", response_model=schemas.EventAnalyticsOut)
def event_analytics(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("events.attendance")),
):
    events = db.find_many("events", {"workspace_id": workspace_id})
    attendees = db.find_many("event_attendees", {"workspace_id": workspace_id})
    by_type: dict[str, int] = {}
    for event in events:
        label = event.get("event_type", "general")
        by_type[label] = by_type.get(label, 0) + 1
    return schemas.EventAnalyticsOut(
        total_events=len(events),
        total_rsvps=len(attendees),
        total_checked_in=sum(1 for attendee in attendees if attendee.get("checked_in_at")),
        by_type=[schemas.EventAnalyticsPoint(label=label, value=value) for label, value in sorted(by_type.items())],
    )
