from datetime import datetime, timedelta

from . import models
from .database import MongoStore
from .rbac import ensure_default_roles
from .services.reports import compile_report_snapshot, fallback_report_narrative


DEMO_WORKSPACE_SLUG = "engineering-faculty-council-demo"
DEMO_WORKSPACE_NAME = "Engineering Faculty Council"
DEMO_OWNER_EMAIL = "demo-chair@quorum.local"


def _ensure_user(db: MongoStore, *, full_name: str, email: str, phone: str | None = None) -> models.User:
    user = db.find_one("users", {"email": email})
    if user:
        if user.get("full_name") != full_name or user.get("phone") != phone or not user.get("email_verified"):
            user["full_name"] = full_name
            user["phone"] = phone
            user["email_verified"] = True
            db.save("users", user)
        return user

    return db.insert(
        "users",
        {
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "password_hash": None,
            "email_verified": True,
        },
    )


def _ensure_workspace(db: MongoStore) -> models.Workspace:
    workspace = db.find_one("workspaces", {"slug": DEMO_WORKSPACE_SLUG})
    if workspace:
        return workspace
    return db.insert(
        "workspaces",
        {
            "name": DEMO_WORKSPACE_NAME,
            "slug": DEMO_WORKSPACE_SLUG,
            "description": "Faculty body demo workspace with seven executive members, live finance records, and active operations.",
        },
    )


def _ensure_member_record(
    db: MongoStore,
    *,
    workspace_id: int,
    full_name: str,
    email: str,
    role_name: str,
    level: str,
    dues_status: str,
) -> None:
    if db.find_one("members", {"workspace_id": workspace_id, "email": email}):
        return
    db.insert(
        "members",
        {
            "workspace_id": workspace_id,
            "full_name": full_name,
            "email": email,
            "role": role_name,
            "level": level,
            "dues_status": dues_status,
        },
    )


def _ensure_membership(
    db: MongoStore,
    *,
    workspace: models.Workspace,
    user: models.User,
    role_id: int,
    level: str,
    dues_status: str,
    is_general_member: bool,
    joined_at: datetime,
) -> models.WorkspaceMember:
    membership = db.find_one("workspace_members", {"workspace_id": workspace.id, "user_id": user.id})
    if membership:
        membership["role_id"] = role_id
        membership["level"] = level
        membership["dues_status"] = dues_status
        membership["is_general_member"] = is_general_member
        membership["status"] = "active"
        membership["joined_at"] = membership.get("joined_at") or joined_at
        return db.save("workspace_members", membership)

    return db.insert(
        "workspace_members",
        {
            "workspace_id": workspace.id,
            "user_id": user.id,
            "role_id": role_id,
            "level": level,
            "dues_status": dues_status,
            "is_general_member": is_general_member,
            "status": "active",
            "joined_at": joined_at,
        },
    )


def _seed_members(db: MongoStore, workspace: models.Workspace) -> tuple[models.WorkspaceMember, list[models.WorkspaceMember]]:
    roles = ensure_default_roles(db, workspace.id)
    owner_role = roles["owner"]
    secretary_role = roles["secretary"]
    core_role = roles["core_member"]

    member_specs = [
        ("Ayo Owolabi", DEMO_OWNER_EMAIL, owner_role, "President", "paid"),
        ("Nneka Bassey", "secretary@efc-demo.local", secretary_role, "General Secretary", "paid"),
        ("Tomiwa Adeyemi", "treasurer@efc-demo.local", core_role, "Treasurer", "paid"),
        ("Favour Okonkwo", "welfare@efc-demo.local", core_role, "Welfare Director", "paid"),
        ("Daniel Yusuf", "projects@efc-demo.local", core_role, "Projects Lead", "paid"),
        ("Amina Bello", "events@efc-demo.local", core_role, "Events Coordinator", "defaulter"),
        ("David Omotoso", "media@efc-demo.local", core_role, "Publicity Director", "defaulter"),
    ]

    memberships: list[models.WorkspaceMember] = []
    start = datetime.utcnow() - timedelta(days=28)
    for index, (full_name, email, role, level, dues_status) in enumerate(member_specs):
        user = _ensure_user(db, full_name=full_name, email=email, phone=f"+23480100000{index}")
        membership = _ensure_membership(
            db,
            workspace=workspace,
            user=user,
            role_id=role.id,
            level=level,
            dues_status=dues_status,
            is_general_member=role.key == "core_member",
            joined_at=start + timedelta(days=index),
        )
        _ensure_member_record(
            db,
            workspace_id=workspace.id,
            full_name=full_name,
            email=email,
            role_name=role.name,
            level=level,
            dues_status=dues_status,
        )
        memberships.append(membership)

    workspace["owner_user_id"] = memberships[0].user_id
    db.save("workspaces", workspace)
    return memberships[0], memberships


def _seed_dues(db: MongoStore, workspace: models.Workspace, memberships: list[models.WorkspaceMember]) -> None:
    cycle = db.find_one("dues_cycles", {"workspace_id": workspace.id, "name": "2026 Leadership Levy"})
    if cycle is None:
        cycle = db.insert(
            "dues_cycles",
            {
                "workspace_id": workspace.id,
                "name": "2026 Leadership Levy",
                "amount": 3500,
                "deadline": "2026-05-15",
            },
        )

    if db.find_many("dues_payments", {"workspace_id": workspace.id}, limit=1):
        return

    for membership in memberships[:5]:
        db.insert(
            "dues_payments",
            {
                "workspace_id": workspace.id,
                "cycle_id": cycle.id,
                "member_id": membership.id,
                "amount": 3500,
                "method": "manual",
                "gateway_ref": f"EFC-DUES-{membership.id}",
                "status": "paid",
                "confirmed_by_user_id": memberships[0].user_id,
                "confirmed_at": datetime.utcnow() - timedelta(days=6),
            },
        )


def _seed_events(db: MongoStore, workspace: models.Workspace, memberships: list[models.WorkspaceMember]) -> None:
    if db.find_many("events", {"workspace_id": workspace.id}, limit=1):
        return

    event_specs = [
        {
            "title": "Engineering Week Town Hall",
            "slug": "efc-engineering-week-town-hall",
            "event_type": "town_hall",
            "starts_at": "2026-05-04 16:00",
            "venue": "ETF Lecture Theatre",
            "description": "Leadership briefing for Engineering Week with open questions from class reps.",
            "rsvp_enabled": True,
            "capacity": 250,
            "thumbnail_url": None,
            "rsvp_count": 7,
            "created_by_user_id": memberships[0].user_id,
        },
        {
            "title": "Treasury and Welfare Review",
            "slug": "efc-treasury-welfare-review",
            "event_type": "review",
            "starts_at": "2026-05-11 18:00",
            "venue": "Council Chamber",
            "description": "Mid-session review of dues, welfare disbursements, and sponsor commitments.",
            "rsvp_enabled": True,
            "capacity": 80,
            "thumbnail_url": None,
            "rsvp_count": 5,
            "created_by_user_id": memberships[1].user_id,
        },
    ]

    created_events = [db.insert("events", {"workspace_id": workspace.id, **spec}) for spec in event_specs]

    for index, membership in enumerate(memberships):
        user = db.find_by_id("users", membership.user_id)
        db.insert(
            "event_attendees",
            {
                "event_id": created_events[0].id,
                "workspace_id": workspace.id,
                "member_id": membership.id,
                "full_name": user.full_name if user else f"Member {membership.id}",
                "email": user.email if user else f"member-{membership.id}@example.com",
                "status": "checked_in" if index < 5 else "registered",
                "rsvp_at": datetime.utcnow() - timedelta(days=4, hours=index),
                "checked_in_at": datetime.utcnow() - timedelta(days=4, minutes=30 - index) if index < 5 else None,
            },
        )


def _seed_campaigns(db: MongoStore, workspace: models.Workspace, memberships: list[models.WorkspaceMember]) -> None:
    campaign = db.find_one("campaigns", {"workspace_id": workspace.id, "slug": "efc-engineering-week-fund"})
    if campaign is None:
        campaign = db.insert(
            "campaigns",
            {
                "workspace_id": workspace.id,
                "name": "Engineering Week Fund",
                "slug": "efc-engineering-week-fund",
                "target_amount": 1200000,
                "raised_amount": 742000,
                "status": "active",
            },
        )

    if db.find_many("funding_streams", {"campaign_id": campaign.id}, limit=1):
        return

    streams = [
        db.insert(
            "funding_streams",
            {
                "workspace_id": workspace.id,
                "campaign_id": campaign.id,
                "name": "Corporate sponsors",
                "stream_type": "sponsorship",
                "target_amount": 700000,
            },
        ),
        db.insert(
            "funding_streams",
            {
                "workspace_id": workspace.id,
                "campaign_id": campaign.id,
                "name": "Alumni support",
                "stream_type": "donation",
                "target_amount": 350000,
            },
        ),
        db.insert(
            "funding_streams",
            {
                "workspace_id": workspace.id,
                "campaign_id": campaign.id,
                "name": "Merchandise presales",
                "stream_type": "sales",
                "target_amount": 150000,
            },
        ),
    ]

    contribution_specs = [
        (streams[0].id, "TekBridge Systems", "finance@tekbridge.ng", 320000, "bank_transfer"),
        (streams[0].id, "Ace Robotics", "hello@acerobotics.ng", 180000, "manual"),
        (streams[1].id, "Evelyn Ogunleye", "evelyn@example.com", 90000, "manual"),
        (streams[1].id, "Class of 2014", "alumni2014@example.com", 72000, "manual"),
        (streams[2].id, "Hoodie presales", "sales@efc-demo.local", 80000, "manual"),
    ]

    for index, (stream_id, contributor_name, contributor_email, amount, method) in enumerate(contribution_specs, start=1):
        db.insert(
            "contributions",
            {
                "workspace_id": workspace.id,
                "campaign_id": campaign.id,
                "stream_id": stream_id,
                "contributor_name": contributor_name,
                "contributor_email": contributor_email,
                "amount": amount,
                "method": method,
                "gateway_ref": f"EFC-CONTRIB-{index}",
                "receipt_url": None,
                "is_anonymous": False,
                "status": "confirmed",
                "confirmed_by_user_id": memberships[0].user_id,
                "confirmed_at": datetime.utcnow() - timedelta(days=3),
            },
        )


def _seed_links(db: MongoStore, workspace: models.Workspace) -> None:
    if db.find_many("short_links", {"workspace_id": workspace.id}, limit=1):
        return

    db.insert(
        "short_links",
        {
            "workspace_id": workspace.id,
            "slug": "efc-levy",
            "destination_url": "https://quorum.ng/portal/engineering-faculty-council-demo",
            "title": "Pay leadership levy",
            "click_count": 184,
            "is_active": True,
        },
    )
    db.insert(
        "short_links",
        {
            "workspace_id": workspace.id,
            "slug": "efc-sponsor",
            "destination_url": "https://quorum.ng/donate/efc-engineering-week-fund",
            "title": "Sponsor Engineering Week",
            "click_count": 96,
            "is_active": True,
        },
    )


def _seed_announcements(db: MongoStore, workspace: models.Workspace) -> None:
    if db.find_many("announcements", {"workspace_id": workspace.id}, limit=1):
        return

    now = datetime.utcnow()
    db.insert(
        "announcements",
        {
            "workspace_id": workspace.id,
            "title": "Engineering Week sponsor deck is live",
            "body": "Sponsor outreach has started. Use the new fundraising link in the campaigns module for outreach follow-up.",
            "status": "published",
            "is_pinned": True,
            "published_at": now - timedelta(days=2),
            "scheduled_for": None,
            "delivered_at": now - timedelta(days=2),
            "delivery_count": 7,
            "audience": "all_members",
            "channels": ["in_app", "email"],
            "target_role_ids": [],
            "target_levels": [],
            "archived_at": None,
            "updated_at": now - timedelta(days=2),
        },
    )
    db.insert(
        "announcements",
        {
            "workspace_id": workspace.id,
            "title": "Treasury review moved to Chamber B",
            "body": "Please note the venue change for the treasury and welfare review meeting on Monday evening.",
            "status": "published",
            "is_pinned": False,
            "published_at": now - timedelta(days=1),
            "scheduled_for": None,
            "delivered_at": now - timedelta(days=1),
            "delivery_count": 7,
            "audience": "all_members",
            "channels": ["in_app"],
            "target_role_ids": [],
            "target_levels": [],
            "archived_at": None,
            "updated_at": now - timedelta(days=1),
        },
    )


def _seed_meetings_and_tasks(db: MongoStore, workspace: models.Workspace, memberships: list[models.WorkspaceMember]) -> None:
    rich_transcript = """
Nneka Bassey: We have quorum, so let's begin. Today's meeting is focused on Engineering Week execution, especially sponsor follow-up, volunteer assignments, welfare logistics, and publicity deadlines.

Ayo Owolabi: Thank you everyone. We are now ten days away from the opening event, so this meeting needs concrete ownership, not just updates. Tomiwa, start with sponsorship.

Tomiwa Adeyemi: We currently have two confirmed sponsors: TekBridge Systems at three hundred and twenty thousand naira and Ace Robotics at one hundred and eighty thousand naira. The third sponsor, NovaGrid, is interested but wants a revised benefits sheet and confirmation that the exhibition booth power setup is guaranteed.

Ayo Owolabi: What is blocking that revised benefits sheet?

Tomiwa Adeyemi: The sponsor deck still needs the final audience numbers from David and the confirmed booth layout from Daniel.

Daniel Yusuf: The booth layout is ready. I can send that tonight. We are using the faculty quadrangle and the design allows for six sponsor booths, one robotics demo lane, and a central registration point.

David Omotoso: I can update the audience projections once the class-rep circulation numbers are confirmed. Right now we have projected attendance at around six hundred across the week, but I want one clean figure before it goes out to sponsors.

Ayo Owolabi: Fine. Tomiwa, you own the final sponsor tracker. Daniel sends the layout tonight. David sends the cleaned-up audience projection tomorrow morning. Tomiwa sends the revised sponsor pack and escalation tracker by Thursday noon.

Nneka Bassey: Noted. Deadline is Thursday noon for the sponsor escalation tracker and revised sponsor pack.

Amina Bello: On volunteers, we have twenty-three sign-ups, but only twelve have selected shifts. We cannot run registration, ushering, and stage management with that level of uncertainty. I need a rota that people can see clearly by department and by day.

Ayo Owolabi: What do you need to make that happen?

Amina Bello: I need final programme blocks from Daniel and I need David to post the second volunteer call with the closing date.

Daniel Yusuf: I can share the programme block schedule tonight with the booth layout. That should be enough for the rota draft.

David Omotoso: I will push the second volunteer call tonight and pin it. Closing date should be Friday by 5 p.m.

Ayo Owolabi: Good. Amina publishes the volunteer rota draft on Friday morning and locks assignments after Sunday's briefing.

Favour Okonkwo: On refreshments and welfare, I have two vendor quotes already. One is cheaper but cannot guarantee delivery before 8 a.m. The second is more expensive but reliable and can also cover the panel session on Wednesday. I need approval to negotiate with the second vendor and lock pricing before Monday.

Ayo Owolabi: Do we have room in the budget?

Tomiwa Adeyemi: Yes, but only if media printing stays within the approved ceiling. If printing rises, welfare and stage branding start competing for the same buffer.

David Omotoso: Printing will stay within ceiling if the banners are finalised by Saturday. Late changes are what usually increase cost.

Ayo Owolabi: Then the decision is simple: Favour proceeds with the reliable vendor, but gets final sign-off once David confirms printing costs by Saturday afternoon.

Nneka Bassey: Captured. Favour negotiates and returns with final vendor recommendation. David confirms printing costs by Saturday afternoon.

Daniel Yusuf: Another point: the faculty hall inspection needs to happen on Monday. We still need facilities approval for sound and backup power.

Ayo Owolabi: Who is owning that?

Daniel Yusuf: I can take it, but I need a letter from Nneka and a representative from Favour because of crowd-flow and refreshment points.

Nneka Bassey: I will prepare the facilities request letter before close of business tomorrow.

Favour Okonkwo: I will join the inspection on Monday afternoon.

Ayo Owolabi: Good. Final item: communications cadence. We cannot assume people know the sequence of events. David should push one master timetable on Monday and then daily reminders through the week.

David Omotoso: Agreed. I will publish the master timetable once the final programme block is signed off.

Ayo Owolabi: Excellent. To close: Tomiwa handles sponsor escalation. Amina owns the volunteer rota. Favour locks the preferred vendor path. Daniel and Nneka handle facilities approval. David handles timetable and the second volunteer call. We reconvene next Tuesday at 6 p.m. for a final readiness review.
""".strip()

    minutes_content = """
## Attendance
- 7 of 7 executive members were present and quorum was confirmed at the start of the session.

## Discussion Summary
- The council reviewed sponsor commitments for Engineering Week and agreed that sponsor follow-up is now a time-sensitive revenue task, not a background item.
- Volunteer sign-ups are healthy at the top of the funnel, but conversion into actual shift ownership is weak, so the team agreed to move immediately to a rota-driven assignment model.
- Welfare and media spending were reviewed together to prevent budget spillover between refreshments and printing.
- Facilities approval for sound, backup power, and crowd-flow was escalated as an operational risk that must be closed before the week begins.

## Decisions
- Treasurer will send a revised sponsor pack and escalation tracker by Thursday noon after receiving the final audience projection and booth layout.
- Events Coordinator will publish the volunteer rota draft on Friday morning and lock assignments after Sunday's volunteer briefing.
- Welfare Director will negotiate with the more reliable vendor and return for final approval once media printing costs are confirmed.
- Secretary will issue the facilities request letter before close of business tomorrow, and Projects Lead will run the Monday inspection with Welfare present.
- Publicity Director will publish a master Engineering Week timetable on Monday and maintain daily reminder posts throughout the week.

## Next Steps
- Sponsor pipeline status should be reviewed again at the readiness meeting next Tuesday.
- Volunteer conversion and facilities approvals are the two biggest operational watch-outs before launch.
""".strip()

    action_specs = [
        ("Send revised sponsor pack and escalation tracker", memberships[2].id, "2026-05-03", "in_progress", "high"),
        ("Publish volunteer rota draft and confirm final assignments", memberships[5].id, "2026-05-04", "todo", "high"),
        ("Negotiate final refreshment vendor pricing and service window", memberships[3].id, "2026-05-04", "in_progress", "medium"),
        ("Issue facilities request letter for hall inspection", memberships[1].id, "2026-05-02", "todo", "medium"),
        ("Publish master timetable and second volunteer call", memberships[6].id, "2026-05-02", "todo", "medium"),
    ]

    meeting = db.find_one("meetings", {"workspace_id": workspace.id, "title": "Engineering Week Planning Council"})
    if meeting is None:
        meeting = db.insert(
            "meetings",
            {
                "workspace_id": workspace.id,
                "title": "Engineering Week Planning Council",
                "meeting_type": "executive",
                "scheduled_for": "2026-05-01 17:00",
                "venue": "Dean's Board Room",
                "virtual_link": "https://meet.google.com/efc-demo-week",
                "agenda": ["Sponsorship pipeline", "Volunteer assignments", "Welfare logistics", "Facilities approval", "Publicity cadence"],
                "quorum_threshold": 5,
                "status": "minutes_published",
                "transcript": rich_transcript,
                "transcript_source": "demo_seed",
                "attendee_count": 7,
                "created_by_user_id": memberships[1].user_id,
            },
        )
    else:
        meeting.update(
            {
                "meeting_type": "executive",
                "scheduled_for": "2026-05-01 17:00",
                "venue": "Dean's Board Room",
                "virtual_link": "https://meet.google.com/efc-demo-week",
                "agenda": ["Sponsorship pipeline", "Volunteer assignments", "Welfare logistics", "Facilities approval", "Publicity cadence"],
                "quorum_threshold": 5,
                "status": "minutes_published",
                "transcript": rich_transcript,
                "transcript_source": "demo_seed",
                "attendee_count": 7,
                "created_by_user_id": memberships[1].user_id,
            }
        )
        meeting = db.save("meetings", meeting)

    minutes = db.find_one("meeting_minutes", {"meeting_id": meeting.id})
    minutes_payload = {
        "meeting_id": meeting.id,
        "summary": "Council converted Engineering Week planning into concrete ownership across sponsorship, volunteer operations, welfare, facilities approval, and publicity.",
        "content": minutes_content,
        "attendance_summary": "7 of 7 executive members present.",
        "decisions": [
            "Tomiwa Adeyemi to send the revised sponsor pack and escalation tracker by Thursday noon.",
            "Amina Bello to publish the volunteer rota draft on Friday and lock assignments after Sunday's briefing.",
            "Favour Okonkwo to negotiate the preferred vendor path before the next review.",
            "Nneka Bassey to issue the facilities request letter before close of business tomorrow.",
            "David Omotoso to publish the master timetable and second volunteer call on Monday.",
        ],
        "ai_status": "published",
        "generated_by_model": "claude-sonnet-4-20250514",
        "generated_at": datetime.utcnow() - timedelta(days=3),
        "generation_error": None,
        "published_at": datetime.utcnow() - timedelta(days=3),
        "published_by_user_id": memberships[1].user_id,
        "updated_at": datetime.utcnow() - timedelta(days=3),
    }
    if minutes is None:
        db.insert("meeting_minutes", minutes_payload)
    else:
        minutes.update(minutes_payload)
        db.save("meeting_minutes", minutes)

    db.delete_many("action_items", {"meeting_id": meeting.id})
    db.delete_many("tasks", {"workspace_id": workspace.id, "linked_module": "meeting", "linked_id": meeting.id})

    for description, assigned_to_member_id, due_date, status, priority in action_specs:
        db.insert(
            "action_items",
            {
                "meeting_id": meeting.id,
                "description": description,
                "assigned_to_member_id": assigned_to_member_id,
                "due_date": due_date,
                "status": status,
                "generated_by": "claude",
            },
        )
        assignee = db.find_by_id("workspace_members", assigned_to_member_id)
        db.insert(
            "tasks",
            {
                "workspace_id": workspace.id,
                "title": description,
                "description": "Demo follow-up task extracted from the Engineering Week planning transcript.",
                "assigned_to_member_id": assigned_to_member_id,
                "due_date": due_date,
                "priority": priority,
                "status": status,
                "linked_module": "meeting",
                "linked_id": meeting.id,
                "created_by_user_id": assignee.user_id if assignee else memberships[1].user_id,
                "generated_by": "claude",
            },
        )


def _seed_budgets(db: MongoStore, workspace: models.Workspace) -> None:
    budget = db.find_one("budgets", {"workspace_id": workspace.id, "name": "Engineering Week 2026"})
    if budget is None:
        budget = db.insert(
            "budgets",
            {
                "workspace_id": workspace.id,
                "name": "Engineering Week 2026",
                "description": "Session budget for sponsor-funded Engineering Week operations.",
                "period_label": "2026 Session",
                "status": "active",
                "planned_total": 540000,
                "actual_total": 168000,
            },
        )

    if db.find_many("budget_lines", {"budget_id": budget.id}, limit=1):
        return

    lines = [
        ("Venue and stage", 180000, 90000),
        ("Media and design", 120000, 28000),
        ("Welfare and refreshments", 90000, 22000),
        ("Volunteer logistics", 150000, 28000),
    ]

    for name, planned_amount, actual_amount in lines:
        line = db.insert(
            "budget_lines",
            {
                "budget_id": budget.id,
                "name": name,
                "planned_amount": planned_amount,
                "actual_amount": actual_amount,
                "notes": "Demo seeded line item",
            },
        )
        if actual_amount:
            db.insert(
                "expenditures",
                {
                    "budget_line_id": line.id,
                    "amount": actual_amount,
                    "notes": "Demo seeded expenditure",
                    "spent_at": "2026-04-20",
                },
            )


def _seed_reports(db: MongoStore, workspace: models.Workspace, owner_membership: models.WorkspaceMember) -> None:
    if db.find_many("reports", {"workspace_id": workspace.id}, limit=1):
        return

    period_start = datetime(2026, 1, 1).date()
    period_end = datetime(2026, 5, 31).date()
    snapshot = compile_report_snapshot(
        db,
        workspace=workspace,
        period_start=period_start,
        period_end=period_end,
        enabled_categories=["membership", "dues", "events", "meetings", "fundraising", "communication", "ai_usage"],
    )
    narrative = fallback_report_narrative(
        snapshot,
        "Engineering Faculty Council focused on sponsor mobilisation, dues enforcement, and structured meeting follow-through for Engineering Week delivery.",
    )
    db.insert(
        "reports",
        {
            "workspace_id": workspace.id,
            "title": "Engineering Faculty Council Semester Audit",
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "period_label": "2025/2026 Second Semester",
            "status": "complete",
            "generated_by": owner_membership.id,
            "enabled_categories": ["membership", "dues", "events", "meetings", "fundraising", "communication", "ai_usage"],
            "context_notes": "Generated for a handover-style review before Engineering Week.",
            "generated_at": datetime.utcnow() - timedelta(days=1),
            "pdf_url": None,
            "ai_narrative": narrative,
            "data_snapshot": snapshot["categories"],
            "overall_score": snapshot["overall_score"],
            "overall_grade": snapshot["overall_grade"],
            "generation_error": None,
        },
    )


def ensure_demo_workspace(db: MongoStore) -> tuple[models.Workspace, models.WorkspaceMember]:
    workspace = _ensure_workspace(db)
    owner_membership, memberships = _seed_members(db, workspace)
    _seed_dues(db, workspace, memberships)
    _seed_events(db, workspace, memberships)
    _seed_campaigns(db, workspace, memberships)
    _seed_links(db, workspace)
    _seed_announcements(db, workspace)
    _seed_meetings_and_tasks(db, workspace, memberships)
    _seed_budgets(db, workspace)
    _seed_reports(db, workspace, owner_membership)
    return workspace, owner_membership
