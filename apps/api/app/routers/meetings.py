from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from .. import schemas
from ..database import DESC, MongoStore, get_db
from ..rbac import require_workspace_permission
from ..services.anthropic import AnthropicGenerationError, anthropic_configured, generate_meeting_minutes
from ..services.fireflies import FirefliesError, fetch_fireflies_transcript
from ..services.google import (
    GoogleIntegrationError,
    access_token_for_integration,
    create_google_meet_space,
    google_doc_text,
    latest_conference_record_for_space,
    latest_transcript_for_conference,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/meetings", tags=["meetings"])


def _meeting_out(db: MongoStore, meeting) -> schemas.MeetingOut:
    return schemas.MeetingOut(
        id=meeting.id,
        workspace_id=meeting.workspace_id,
        title=meeting.title,
        meeting_type=meeting.get("meeting_type", "general"),
        scheduled_for=meeting.scheduled_for,
        venue=meeting.get("venue"),
        virtual_link=meeting.get("virtual_link"),
        agenda=meeting.get("agenda", []),
        quorum_threshold=meeting.get("quorum_threshold"),
        status=meeting.get("status", "draft"),
        transcript=meeting.get("transcript"),
        transcript_source=meeting.get("transcript_source"),
        attendee_count=meeting.get("attendee_count", 0),
        created_by_user_id=meeting.get("created_by_user_id"),
        created_at=meeting.created_at,
    )


def _minutes_out(minutes) -> schemas.MeetingMinutesOut:
    return schemas.MeetingMinutesOut(
        id=minutes.id,
        meeting_id=minutes.meeting_id,
        summary=minutes.get("summary"),
        content=minutes.get("content"),
        attendance_summary=minutes.get("attendance_summary"),
        decisions=minutes.get("decisions", []),
        ai_status=minutes.get("ai_status", "draft"),
        generated_by_model=minutes.get("generated_by_model"),
        generated_at=minutes.get("generated_at"),
        generation_error=minutes.get("generation_error"),
        published_at=minutes.get("published_at"),
        published_by_user_id=minutes.get("published_by_user_id"),
        created_at=minutes.created_at,
        updated_at=minutes.get("updated_at") or minutes.created_at,
    )


def _action_item_out(db: MongoStore, item) -> schemas.ActionItemOut:
    member = db.find_by_id("workspace_members", item.get("assigned_to_member_id"))
    user = db.find_by_id("users", member.user_id) if member else None
    return schemas.ActionItemOut(
        id=item.id,
        meeting_id=item.meeting_id,
        description=item.description,
        assigned_to_member_id=item.get("assigned_to_member_id"),
        assigned_to_name=user.full_name if user else None,
        due_date=item.get("due_date"),
        status=item.get("status", "open"),
        generated_by=item.get("generated_by"),
        created_at=item.created_at,
    )


def _meeting_or_404(db: MongoStore, workspace_id: int, meeting_id: int):
    meeting = db.find_one("meetings", {"id": meeting_id, "workspace_id": workspace_id})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


def _member_roster(db: MongoStore, workspace_id: int) -> list[dict]:
    members = db.find_many("workspace_members", {"workspace_id": workspace_id, "status": "active"})
    roster = []
    for member in members:
        user = db.find_by_id("users", member.user_id)
        role = db.find_by_id("roles", member.role_id)
        if not user:
            continue
        roster.append(
            {
                "id": member.id,
                "name": user.full_name,
                "email": user.email,
                "role": role.name if role else None,
            }
        )
    return roster


def _delete_generated_meeting_actions(db: MongoStore, workspace_id: int, meeting_id: int) -> None:
    db.delete_many("action_items", {"workspace_id": workspace_id, "meeting_id": meeting_id, "generated_by": "anthropic"})
    db.delete_many(
        "tasks",
        {"workspace_id": workspace_id, "linked_module": "meeting", "linked_id": meeting_id, "generated_by": "anthropic"},
    )


def _create_action_item_and_task(
    db: MongoStore,
    *,
    workspace_id: int,
    meeting_id: int,
    created_by_user_id: int | None,
    description: str,
    assigned_to_member_id: int | None,
    due_date: str | None,
    priority: str = "medium",
    generated_by: str = "manual",
):
    action_item = db.insert(
        "action_items",
        {
            "meeting_id": meeting_id,
            "workspace_id": workspace_id,
            "description": description.strip(),
            "assigned_to_member_id": assigned_to_member_id,
            "due_date": due_date,
            "status": "open",
            "generated_by": generated_by,
        },
    )
    db.insert(
        "tasks",
        {
            "workspace_id": workspace_id,
            "title": description.strip(),
            "description": f"Action item from meeting #{meeting_id}",
            "assigned_to_member_id": assigned_to_member_id,
            "due_date": due_date,
            "priority": priority,
            "status": "todo",
            "linked_module": "meeting",
            "linked_id": meeting_id,
            "created_by_user_id": created_by_user_id,
            "generated_by": generated_by,
        },
    )
    return action_item


def _fallback_minutes(minutes, transcript: str, error_message: str | None = None):
    summary = transcript.strip().split(".")[0][:240]
    minutes["summary"] = summary
    minutes["content"] = transcript.strip()
    minutes["attendance_summary"] = "Attendance details were not extracted automatically."
    minutes["decisions"] = []
    minutes["ai_status"] = "manual_draft" if not error_message else "generation_failed"
    minutes["generated_by_model"] = None
    minutes["generated_at"] = datetime.utcnow() if not error_message else None
    minutes["generation_error"] = error_message
    minutes["updated_at"] = datetime.utcnow()
    return minutes


def _generate_minutes_for_meeting(db: MongoStore, meeting, minutes):
    transcript = (meeting.get("transcript") or "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Upload a transcript before generating minutes")

    if not anthropic_configured():
        minutes = _fallback_minutes(minutes, transcript)
        return db.save("meeting_minutes", minutes)

    try:
        draft = generate_meeting_minutes(
            transcript=transcript,
            meeting_title=meeting.title,
            agenda=meeting.get("agenda", []),
            member_roster=_member_roster(db, meeting.workspace_id),
        )
        minutes["summary"] = draft.summary
        minutes["content"] = draft.content
        minutes["attendance_summary"] = draft.attendance_summary
        minutes["decisions"] = draft.decisions
        minutes["ai_status"] = "generated"
        minutes["generated_by_model"] = draft.model
        minutes["generated_at"] = datetime.utcnow()
        minutes["generation_error"] = None
        minutes["updated_at"] = datetime.utcnow()
        minutes = db.save("meeting_minutes", minutes)

        _delete_generated_meeting_actions(db, meeting.workspace_id, meeting.id)
        for item in draft.action_items:
            _create_action_item_and_task(
                db,
                workspace_id=meeting.workspace_id,
                meeting_id=meeting.id,
                created_by_user_id=meeting.get("created_by_user_id"),
                description=item.description,
                assigned_to_member_id=item.assigned_to_member_id,
                due_date=item.due_date,
                priority=item.priority,
                generated_by="anthropic",
            )
        return minutes
    except AnthropicGenerationError as exc:
        minutes = _fallback_minutes(minutes, transcript, str(exc)[:240])
        return db.save("meeting_minutes", minutes)


@router.get("", response_model=list[schemas.MeetingOut])
def list_meetings(workspace_id: int, db: MongoStore = Depends(get_db)):
    meetings = db.find_many("meetings", {"workspace_id": workspace_id}, sort=[("created_at", DESC)])
    return [_meeting_out(db, meeting) for meeting in meetings]


@router.post("", response_model=schemas.MeetingOut, status_code=201)
def create_meeting(
    workspace_id: int,
    payload: schemas.MeetingCreate,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("meetings.manage")),
):
    meeting = db.insert(
        "meetings",
        {
            "workspace_id": workspace_id,
            "meeting_type": payload.meeting_type,
            "scheduled_for": payload.scheduled_for,
            "venue": payload.venue,
            "virtual_link": payload.virtual_link,
            "agenda": payload.agenda,
            "quorum_threshold": payload.quorum_threshold,
            "status": "scheduled",
            "created_by_user_id": membership.user_id,
            "title": payload.title,
            "transcript": None,
            "transcript_source": None,
        },
    )
    minutes = db.insert(
        "meeting_minutes",
        {
            "meeting_id": meeting.id,
            "summary": None,
            "content": None,
            "ai_status": "draft",
            "published_at": None,
            "published_by_user_id": None,
            "updated_at": datetime.utcnow(),
        },
    )
    meeting["minutes_id"] = minutes.id
    db.save("meetings", meeting)
    return _meeting_out(db, meeting)


@router.get("/{meeting_id}", response_model=schemas.MeetingDetailOut)
def get_meeting(workspace_id: int, meeting_id: int, db: MongoStore = Depends(get_db)):
    meeting = _meeting_or_404(db, workspace_id, meeting_id)
    minutes = db.find_one("meeting_minutes", {"meeting_id": meeting.id})
    action_items = db.find_many("action_items", {"meeting_id": meeting.id}, sort=[("created_at", DESC)])
    return schemas.MeetingDetailOut(
        **_meeting_out(db, meeting).model_dump(),
        minutes=_minutes_out(minutes) if minutes else None,
        action_items=[_action_item_out(db, item) for item in action_items],
    )


@router.patch("/{meeting_id}", response_model=schemas.MeetingOut)
def update_meeting(
    workspace_id: int,
    meeting_id: int,
    payload: schemas.MeetingUpdate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("meetings.manage")),
):
    meeting = _meeting_or_404(db, workspace_id, meeting_id)
    meeting.update(payload.model_dump(exclude_unset=True))
    meeting = db.save("meetings", meeting)
    return _meeting_out(db, meeting)


@router.post("/{meeting_id}/transcript", response_model=schemas.MeetingDetailOut)
def upload_transcript(
    workspace_id: int,
    meeting_id: int,
    payload: schemas.TranscriptUpload,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("meetings.manage")),
):
    meeting = _meeting_or_404(db, workspace_id, meeting_id)
    meeting["transcript"] = payload.transcript.strip()
    meeting["transcript_source"] = "manual"
    meeting["status"] = "completed"
    db.save("meetings", meeting)

    minutes = db.find_one("meeting_minutes", {"meeting_id": meeting.id})
    if minutes:
        minutes = _generate_minutes_for_meeting(db, meeting, minutes)
    else:
        minutes = None

    action_items = db.find_many("action_items", {"meeting_id": meeting.id}, sort=[("created_at", DESC)])
    return schemas.MeetingDetailOut(
        **_meeting_out(db, meeting).model_dump(),
        minutes=_minutes_out(minutes) if minutes else None,
        action_items=[_action_item_out(db, item) for item in action_items],
    )


@router.post("/{meeting_id}/generate-minutes", response_model=schemas.MeetingDetailOut)
def generate_minutes(
    workspace_id: int,
    meeting_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("meetings.manage")),
):
    meeting = _meeting_or_404(db, workspace_id, meeting_id)
    minutes = db.find_one("meeting_minutes", {"meeting_id": meeting.id})
    if not minutes:
        raise HTTPException(status_code=404, detail="Meeting minutes not found")
    minutes = _generate_minutes_for_meeting(db, meeting, minutes)
    action_items = db.find_many("action_items", {"meeting_id": meeting.id}, sort=[("created_at", DESC)])
    return schemas.MeetingDetailOut(
        **_meeting_out(db, meeting).model_dump(),
        minutes=_minutes_out(minutes),
        action_items=[_action_item_out(db, item) for item in action_items],
    )


@router.patch("/{meeting_id}/minutes", response_model=schemas.MeetingMinutesOut)
def update_minutes(
    workspace_id: int,
    meeting_id: int,
    payload: schemas.MeetingMinutesUpdate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("meetings.manage")),
):
    _meeting_or_404(db, workspace_id, meeting_id)
    minutes = db.find_one("meeting_minutes", {"meeting_id": meeting_id})
    if not minutes:
        raise HTTPException(status_code=404, detail="Meeting minutes not found")
    minutes.update(payload.model_dump(exclude_unset=True))
    minutes["updated_at"] = datetime.utcnow()
    minutes = db.save("meeting_minutes", minutes)
    return _minutes_out(minutes)


@router.post("/{meeting_id}/minutes/publish", response_model=schemas.MeetingMinutesOut)
def publish_minutes(
    workspace_id: int,
    meeting_id: int,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("meetings.publish_minutes")),
):
    _meeting_or_404(db, workspace_id, meeting_id)
    minutes = db.find_one("meeting_minutes", {"meeting_id": meeting_id})
    if not minutes:
        raise HTTPException(status_code=404, detail="Meeting minutes not found")
    minutes["published_at"] = datetime.utcnow()
    minutes["published_by_user_id"] = membership.user_id
    minutes["ai_status"] = "published"
    minutes["updated_at"] = datetime.utcnow()
    minutes = db.save("meeting_minutes", minutes)
    return _minutes_out(minutes)


@router.post("/{meeting_id}/action-items", response_model=schemas.ActionItemOut, status_code=201)
def create_action_item(
    workspace_id: int,
    meeting_id: int,
    payload: schemas.ActionItemCreate,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("meetings.manage")),
):
    _meeting_or_404(db, workspace_id, meeting_id)
    item = _create_action_item_and_task(
        db,
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        created_by_user_id=membership.user_id,
        description=payload.description,
        assigned_to_member_id=payload.assigned_to_member_id,
        due_date=payload.due_date,
        generated_by="manual",
    )
    return _action_item_out(db, item)


@router.post("/{meeting_id}/google-meet", response_model=schemas.MeetingOut)
def attach_google_meet_link(
    workspace_id: int,
    meeting_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    meeting = _meeting_or_404(db, workspace_id, meeting_id)
    integration = db.find_one("integrations", {"workspace_id": workspace_id, "provider": "google_workspace"})
    if not integration or integration.get("status") != "connected":
        raise HTTPException(status_code=400, detail="Connect Google Workspace before creating a Meet link.")
    try:
        access_token, expires_at = access_token_for_integration(integration)
        integration["expires_at"] = expires_at
        db.save("integrations", integration)
        meet_space = create_google_meet_space(access_token=access_token)
    except GoogleIntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    meeting["virtual_link"] = meet_space.meeting_uri
    meeting["virtual_link_provider"] = "google_meet"
    meeting["google_space_name"] = meet_space.name
    meeting = db.save("meetings", meeting)
    return _meeting_out(db, meeting)


@router.post("/{meeting_id}/sync-transcript/google", response_model=schemas.MeetingDetailOut)
def sync_google_transcript(
    workspace_id: int,
    meeting_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    meeting = _meeting_or_404(db, workspace_id, meeting_id)
    if not meeting.get("google_space_name"):
        raise HTTPException(status_code=400, detail="This meeting does not have a linked Google Meet space.")
    integration = db.find_one("integrations", {"workspace_id": workspace_id, "provider": "google_workspace"})
    if not integration or integration.get("status") != "connected":
        raise HTTPException(status_code=400, detail="Connect Google Workspace before syncing transcripts.")
    try:
        access_token, expires_at = access_token_for_integration(integration)
        integration["expires_at"] = expires_at
        db.save("integrations", integration)
        record = latest_conference_record_for_space(access_token=access_token, space_name=meeting.get("google_space_name"))
        if not record:
            raise HTTPException(status_code=404, detail="No Google Meet conference record found yet for this meeting.")
        transcript = latest_transcript_for_conference(access_token=access_token, conference_record_name=record["name"])
        if not transcript:
            raise HTTPException(status_code=404, detail="No Google Meet transcript is available yet.")
        docs_destination = transcript.get("docsDestination") or {}
        document_ref = docs_destination.get("document") or ""
        document_id = document_ref.split("/")[-1] if document_ref else ""
        if not document_id:
            raise HTTPException(status_code=400, detail="Google transcript document reference was not available.")
        transcript_text = google_doc_text(access_token=access_token, document_id=document_id)
    except GoogleIntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    meeting["transcript"] = transcript_text
    meeting["transcript_source"] = "google_meet"
    meeting["status"] = "completed"
    meeting["google_conference_record"] = record["name"]
    db.save("meetings", meeting)
    minutes = db.find_one("meeting_minutes", {"meeting_id": meeting.id})
    if minutes:
        minutes = _generate_minutes_for_meeting(db, meeting, minutes)
    action_items = db.find_many("action_items", {"meeting_id": meeting.id}, sort=[("created_at", DESC)])
    return schemas.MeetingDetailOut(
        **_meeting_out(db, meeting).model_dump(),
        minutes=_minutes_out(minutes) if minutes else None,
        action_items=[_action_item_out(db, item) for item in action_items],
    )


@router.post("/{meeting_id}/sync-transcript/fireflies", response_model=schemas.MeetingDetailOut)
def import_fireflies_transcript(
    workspace_id: int,
    meeting_id: int,
    payload: schemas.FirefliesTranscriptImportRequest,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    meeting = _meeting_or_404(db, workspace_id, meeting_id)
    try:
        transcript = fetch_fireflies_transcript(transcript_id=payload.transcript_id)
    except FirefliesError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    meeting["transcript"] = transcript.transcript_text
    meeting["transcript_source"] = "fireflies"
    meeting["status"] = "completed"
    meeting["fireflies_transcript_id"] = transcript.transcript_id
    if transcript.title and not meeting.get("title"):
        meeting["title"] = transcript.title
    db.save("meetings", meeting)
    minutes = db.find_one("meeting_minutes", {"meeting_id": meeting.id})
    if minutes:
        minutes = _generate_minutes_for_meeting(db, meeting, minutes)
    action_items = db.find_many("action_items", {"meeting_id": meeting.id}, sort=[("created_at", DESC)])
    return schemas.MeetingDetailOut(
        **_meeting_out(db, meeting).model_dump(),
        minutes=_minutes_out(minutes) if minutes else None,
        action_items=[_action_item_out(db, item) for item in action_items],
    )
