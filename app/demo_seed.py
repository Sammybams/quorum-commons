from copy import deepcopy
from datetime import datetime, timedelta

from . import models
from .database import MongoStore
from .rbac import ensure_default_roles
from .rbac import MEMBER_ROLE_KEY
from .services.financial_health import build_financial_health_snapshot
from .services.notifications import create_notification
from .services.opportunities import refresh_opportunity_matches
from .services.reports import compile_report_snapshot, fallback_report_narrative


DEMO_WORKSPACE_SLUG = "engineering-faculty-council-demo"
DEMO_WORKSPACE_NAME = "Engineering Faculty Council"
DEMO_OWNER_EMAIL = "demo-chair@quorum.local"
DEMO_SEED_VERSION = 3


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
        workspace["description"] = "Faculty body demo workspace with Squad-backed finance, synced community inbox highlights, extracted opportunities, and AI-assisted operations."
        db.save("workspaces", workspace)
        return workspace
    return db.insert(
        "workspaces",
        {
            "name": DEMO_WORKSPACE_NAME,
            "slug": DEMO_WORKSPACE_SLUG,
            "description": "Faculty body demo workspace with Squad-backed finance, synced community inbox highlights, extracted opportunities, and AI-assisted operations.",
            "demo_seed_version": None,
        },
    )


def _existing_demo_membership(db: MongoStore, workspace: models.Workspace) -> models.WorkspaceMember | None:
    owner = db.find_one("users", {"email": DEMO_OWNER_EMAIL})
    if not owner:
        return None
    membership = db.find_one("workspace_members", {"workspace_id": workspace.id, "user_id": owner.id, "status": "active"})
    return membership


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
    trade_category: str | None = None,
    location: str | None = None,
    availability: str | None = None,
    contribution_capacity: str | None = None,
    opportunity_preferences: list[str] | None = None,
    phone_number: str | None = None,
) -> models.WorkspaceMember:
    membership = db.find_one("workspace_members", {"workspace_id": workspace.id, "user_id": user.id})
    if membership:
        membership["role_id"] = role_id
        membership["level"] = level
        membership["dues_status"] = dues_status
        membership["is_general_member"] = is_general_member
        membership["status"] = "active"
        membership["joined_at"] = membership.get("joined_at") or joined_at
        membership["trade_category"] = trade_category
        membership["location"] = location
        membership["availability"] = availability
        membership["contribution_capacity"] = contribution_capacity
        membership["opportunity_preferences"] = opportunity_preferences or []
        membership["phone_number"] = phone_number or membership.get("phone_number") or user.get("phone")
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
            "trade_category": trade_category,
            "location": location,
            "availability": availability,
            "contribution_capacity": contribution_capacity,
            "opportunity_preferences": opportunity_preferences or [],
            "phone_number": phone_number or user.get("phone"),
        },
    )


def _seed_members(db: MongoStore, workspace: models.Workspace) -> tuple[models.WorkspaceMember, list[models.WorkspaceMember]]:
    roles = ensure_default_roles(db, workspace.id)
    owner_role = roles["owner"]
    secretary_role = roles["secretary"]
    core_role = roles[MEMBER_ROLE_KEY]

    member_specs = [
        {
            "full_name": "Ayo Owolabi",
            "email": DEMO_OWNER_EMAIL,
            "role": owner_role,
            "level": "President",
            "dues_status": "paid",
            "trade_category": "leadership sponsorship strategy partnerships",
            "location": "Akoka, Lagos",
            "availability": "Weekday evenings",
            "contribution_capacity": "High",
            "opportunity_preferences": ["partnerships", "community leadership", "public speaking"],
        },
        {
            "full_name": "Nneka Bassey",
            "email": "secretary@efc-demo.local",
            "role": secretary_role,
            "level": "General Secretary",
            "dues_status": "paid",
            "trade_category": "operations administration documentation coordination",
            "location": "Yaba, Lagos",
            "availability": "Daily by 4pm",
            "contribution_capacity": "Medium",
            "opportunity_preferences": ["operations", "project coordination", "documentation"],
        },
        {
            "full_name": "Tomiwa Adeyemi",
            "email": "treasurer@efc-demo.local",
            "role": core_role,
            "level": "Treasurer",
            "dues_status": "paid",
            "trade_category": "finance budgeting sponsorship fundraising",
            "location": "Surulere, Lagos",
            "availability": "Weekends and evenings",
            "contribution_capacity": "High",
            "opportunity_preferences": ["finance", "grant support", "sponsorship"],
        },
        {
            "full_name": "Favour Okonkwo",
            "email": "welfare@efc-demo.local",
            "role": core_role,
            "level": "Welfare Director",
            "dues_status": "paid",
            "trade_category": "vendor management welfare hospitality catering",
            "location": "Akoka, Lagos",
            "availability": "Flexible",
            "contribution_capacity": "Medium",
            "opportunity_preferences": ["hospitality", "vendor sourcing", "community care"],
        },
        {
            "full_name": "Daniel Yusuf",
            "email": "projects@efc-demo.local",
            "role": core_role,
            "level": "Projects Lead",
            "dues_status": "defaulter",
            "trade_category": "logistics operations project management facilities",
            "location": "Bariga, Lagos",
            "availability": "Morning and late afternoon",
            "contribution_capacity": "Medium",
            "opportunity_preferences": ["operations", "logistics", "field coordination"],
        },
        {
            "full_name": "Amina Bello",
            "email": "events@efc-demo.local",
            "role": core_role,
            "level": "Events Coordinator",
            "dues_status": "paid",
            "trade_category": "events volunteer management community outreach",
            "location": "Yaba, Lagos",
            "availability": "Weekends",
            "contribution_capacity": "Medium",
            "opportunity_preferences": ["events", "community programs", "volunteer coordination"],
        },
        {
            "full_name": "David Omotoso",
            "email": "media@efc-demo.local",
            "role": core_role,
            "level": "Publicity Director",
            "dues_status": "defaulter",
            "trade_category": "media design graphics publicity marketing",
            "location": "UNILAG Campus",
            "availability": "Evenings",
            "contribution_capacity": "Low",
            "opportunity_preferences": ["media", "design", "communications", "digital marketing"],
        },
    ]

    memberships: list[models.WorkspaceMember] = []
    start = datetime.utcnow() - timedelta(days=28)
    for index, spec in enumerate(member_specs):
        user = _ensure_user(db, full_name=spec["full_name"], email=spec["email"], phone=f"+23480100000{index}")
        membership = _ensure_membership(
            db,
            workspace=workspace,
            user=user,
            role_id=spec["role"].id,
            level=spec["level"],
            dues_status=spec["dues_status"],
            is_general_member=spec["role"].key == MEMBER_ROLE_KEY,
            joined_at=start + timedelta(days=index),
            trade_category=spec["trade_category"],
            location=spec["location"],
            availability=spec["availability"],
            contribution_capacity=spec["contribution_capacity"],
            opportunity_preferences=spec["opportunity_preferences"],
            phone_number=user.get("phone"),
        )
        _ensure_member_record(
            db,
            workspace_id=workspace.id,
            full_name=spec["full_name"],
            email=spec["email"],
            role_name=spec["role"].name,
            level=spec["level"],
            dues_status=spec["dues_status"],
        )
        memberships.append(membership)

    workspace["owner_user_id"] = memberships[0].user_id
    db.save("workspaces", workspace)
    return memberships[0], memberships


def _seed_squad_integration(db: MongoStore, workspace: models.Workspace) -> None:
    existing = db.find_one("integrations", {"workspace_id": workspace.id, "provider": "squad"})
    payload = {
        "workspace_id": workspace.id,
        "provider": "squad",
        "status": "connected",
        "merchant_name": "Engineering Faculty Council Collections",
        "beneficiary_account": "1029384756",
        "collection_mode": "dynamic_virtual_account",
        "default_duration_seconds": 86400,
        "connected_at": existing.get("connected_at") if existing else datetime.utcnow() - timedelta(days=14),
        "updated_at": datetime.utcnow() - timedelta(hours=2),
    }
    if existing:
        existing.update(payload)
        db.save("integrations", existing)
    else:
        db.insert("integrations", payload)


def _seed_member_invites(db: MongoStore, workspace: models.Workspace, owner: models.WorkspaceMember) -> None:
    member_role = ensure_default_roles(db, workspace.id)[MEMBER_ROLE_KEY]
    db.delete_many("invitations", {"workspace_id": workspace.id})
    db.insert(
        "invitations",
        {
            "workspace_id": workspace.id,
            "email": "new.member@efc-demo.local",
            "phone_number": "+2348095550101",
            "role_id": member_role.id,
            "invited_by_user_id": owner.user_id,
            "token": "demo-member-invite-token",
            "note": "You will receive task and opportunity updates by email and WhatsApp after joining.",
            "status": "pending",
            "email_delivery_status": "sent",
            "email_delivery_provider": "google",
            "email_delivery_sender": "demo-chair@quorum.local",
            "expires_at": datetime.utcnow() + timedelta(days=3),
        },
    )


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
    else:
        cycle.update({"amount": 3500, "deadline": "2026-05-15"})
        cycle = db.save("dues_cycles", cycle)

    db.delete_many("dues_payments", {"workspace_id": workspace.id})
    db.delete_many("virtual_accounts", {"workspace_id": workspace.id, "target_type": "dues_payment"})

    payment_specs = [
        (memberships[0], 3500, "paid", "QRM-DUES-EFC-AYO-2026", "SQD-EFC-DUES-001", "3049910021"),
        (memberships[1], 3500, "paid", "QRM-DUES-EFC-NNEKA-2026", "SQD-EFC-DUES-002", "3049910022"),
        (memberships[2], 3500, "paid", "QRM-DUES-EFC-TOMIWA-2026", "SQD-EFC-DUES-003", "3049910023"),
        (memberships[3], 3500, "paid", "QRM-DUES-EFC-FAVOUR-2026", "SQD-EFC-DUES-004", "3049910024"),
        (memberships[5], 3500, "paid", "QRM-DUES-EFC-AMINA-2026", "SQD-EFC-DUES-005", "3049910025"),
        (memberships[4], 3500, "initiated", "QRM-DUES-EFC-DANIEL-2026", None, "3049910026"),
        (memberships[6], 3500, "initiated", "QRM-DUES-EFC-DAVID-2026", None, "3049910027"),
    ]

    for index, (membership, amount, status, reference, provider_ref, account_number) in enumerate(payment_specs, start=1):
        confirmed_at = datetime.utcnow() - timedelta(days=6 - index) if status == "paid" else None
        payment = db.insert(
            "dues_payments",
            {
                "workspace_id": workspace.id,
                "cycle_id": cycle.id,
                "member_id": membership.id,
                "amount": amount,
                "method": "squad",
                "provider": "squad",
                "gateway_ref": reference,
                "provider_transaction_ref": provider_ref,
                "virtual_account_number": account_number,
                "account_name": "Engineering Faculty Council",
                "bank_name": "Wema Bank",
                "expires_at": "2026-05-20T18:00:00" if status != "paid" else None,
                "verification_status": "verified" if status == "paid" else "pending",
                "receipt_url": None,
                "status": status,
                "confirmed_by_user_id": memberships[0].user_id if status == "paid" else None,
                "confirmed_at": confirmed_at,
            },
        )
        db.insert(
            "virtual_accounts",
            {
                "workspace_id": workspace.id,
                "provider": "squad",
                "target_type": "dues_payment",
                "target_id": payment.id,
                "reference": reference,
                "external_account_number": account_number,
                "account_name": "Engineering Faculty Council",
                "bank_name": "Wema Bank",
                "expected_amount": amount,
                "expires_at": "2026-05-20T18:00:00" if status != "paid" else None,
                "status": "settled" if status == "paid" else "active",
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
    else:
        campaign.update(
            {
                "name": "Engineering Week Fund",
                "target_amount": 1200000,
                "raised_amount": 742000,
                "status": "active",
            }
        )
        campaign = db.save("campaigns", campaign)

    db.delete_many("contributions", {"workspace_id": workspace.id, "campaign_id": campaign.id})
    existing_streams = db.find_many("funding_streams", {"campaign_id": campaign.id})
    for stream in existing_streams:
        db.delete_many("funding_streams", {"id": stream.id})
    db.delete_many("virtual_accounts", {"workspace_id": workspace.id, "target_type": "campaign_contribution"})

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
        (streams[0].id, "TekBridge Systems", "finance@tekbridge.ng", 320000, "squad", "confirmed", "QRM-CAMP-EFC-001", "SQD-EFC-CAMP-001", "3056610001"),
        (streams[0].id, "Ace Robotics", "hello@acerobotics.ng", 180000, "squad", "confirmed", "QRM-CAMP-EFC-002", "SQD-EFC-CAMP-002", "3056610002"),
        (streams[1].id, "Evelyn Ogunleye", "evelyn@example.com", 90000, "manual", "confirmed", "QRM-CAMP-EFC-003", None, None),
        (streams[1].id, "Class of 2014", "alumni2014@example.com", 72000, "manual", "confirmed", "QRM-CAMP-EFC-004", None, None),
        (streams[2].id, "Hoodie presales", "sales@efc-demo.local", 80000, "manual", "confirmed", "QRM-CAMP-EFC-005", None, None),
        (streams[0].id, "NovaGrid Energy", "accounts@novagrid.ng", 120000, "squad", "pending", "QRM-CAMP-EFC-006", None, "3056610003"),
    ]

    for stream_id, contributor_name, contributor_email, amount, method, status, reference, provider_ref, account_number in contribution_specs:
        contribution = db.insert(
            "contributions",
            {
                "workspace_id": workspace.id,
                "campaign_id": campaign.id,
                "stream_id": stream_id,
                "contributor_name": contributor_name,
                "contributor_email": contributor_email,
                "amount": amount,
                "method": method,
                "provider": "squad" if method == "squad" else method,
                "gateway_ref": reference,
                "provider_transaction_ref": provider_ref,
                "virtual_account_number": account_number,
                "account_name": "Engineering Faculty Council",
                "bank_name": "Wema Bank" if account_number else None,
                "expires_at": "2026-05-21T18:00:00" if status != "confirmed" and account_number else None,
                "verification_status": "verified" if status == "confirmed" else "pending",
                "receipt_url": None,
                "is_anonymous": False,
                "status": status,
                "confirmed_by_user_id": memberships[0].user_id if status == "confirmed" else None,
                "confirmed_at": datetime.utcnow() - timedelta(days=3) if status == "confirmed" else None,
            },
        )
        if account_number:
            db.insert(
                "virtual_accounts",
                {
                    "workspace_id": workspace.id,
                    "provider": "squad",
                    "target_type": "campaign_contribution",
                    "target_id": contribution.id,
                    "reference": reference,
                    "external_account_number": account_number,
                    "account_name": "Engineering Faculty Council",
                    "bank_name": "Wema Bank",
                    "expected_amount": amount,
                    "expires_at": "2026-05-21T18:00:00" if status != "confirmed" else None,
                    "status": "settled" if status == "confirmed" else "active",
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
    db.delete_many("reports", {"workspace_id": workspace.id})

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


def _seed_community_intelligence(db: MongoStore, workspace: models.Workspace, memberships: list[models.WorkspaceMember]) -> None:
    db.delete_many("community_channels", {"workspace_id": workspace.id})
    db.delete_many("channel_group_links", {"workspace_id": workspace.id})
    db.delete_many("channel_messages", {"workspace_id": workspace.id})
    db.delete_many("message_artifacts", {"workspace_id": workspace.id})
    db.delete_many("community_financial_records", {"workspace_id": workspace.id})
    db.delete_many("opportunity_matches", {"workspace_id": workspace.id})
    db.delete_many("opportunities", {"workspace_id": workspace.id})
    db.delete_many("notifications", {"workspace_id": workspace.id})
    db.delete_many("tasks", {"workspace_id": workspace.id, "linked_module": "community_artifact"})

    owner = memberships[0]
    secretary = memberships[1]
    treasurer = memberships[2]
    welfare = memberships[3]
    projects = memberships[4]
    events = memberships[5]
    media = memberships[6]

    whatsapp = db.insert(
        "community_channels",
        {
            "workspace_id": workspace.id,
            "provider": "whatsapp",
            "label": "Community WhatsApp",
            "status": "connected",
            "connected_at": datetime.utcnow() - timedelta(days=4),
            "display_name": "EFC Operations Desk",
            "phone_number": "2348169427605",
            "whatsapp_jid": "2348169427605@s.whatsapp.net",
            "pairing_mode": "qr",
            "selected_group_count": 2,
            "discovered_group_count": 3,
            "last_error": None,
            "webhook_url": f"https://api.quorum.demo/api/v1/community-channels/whatsapp/{workspace.id}/inbound",
            "webhook_secret": "demo-whatsapp-secret",
        },
    )

    executive_group = db.insert(
        "channel_group_links",
        {
            "workspace_id": workspace.id,
            "channel_id": whatsapp.id,
            "provider": "whatsapp",
            "external_group_id": "120363300100001@g.us",
            "group_name": "EFC Executive Council",
            "sync_enabled": True,
            "last_seen_at": datetime.utcnow() - timedelta(hours=1),
            "last_message_at": datetime.utcnow() - timedelta(hours=1),
            "message_count": 6,
        },
    )
    volunteers_group = db.insert(
        "channel_group_links",
        {
            "workspace_id": workspace.id,
            "channel_id": whatsapp.id,
            "provider": "whatsapp",
            "external_group_id": "120363300100002@g.us",
            "group_name": "Engineering Week Volunteers",
            "sync_enabled": True,
            "last_seen_at": datetime.utcnow() - timedelta(hours=2),
            "last_message_at": datetime.utcnow() - timedelta(hours=2),
            "message_count": 2,
        },
    )
    db.insert(
        "channel_group_links",
        {
            "workspace_id": workspace.id,
            "channel_id": whatsapp.id,
            "provider": "whatsapp",
            "external_group_id": "120363300100003@g.us",
            "group_name": "Faculty Congress Broadcast",
            "sync_enabled": False,
            "last_seen_at": datetime.utcnow() - timedelta(days=1),
            "last_message_at": datetime.utcnow() - timedelta(days=1),
            "message_count": 1,
        },
    )

    sponsor_message = db.insert(
        "channel_messages",
        {
            "workspace_id": workspace.id,
            "channel_id": whatsapp.id,
            "group_link_id": executive_group.id,
            "provider": "whatsapp",
            "external_group_id": executive_group.external_group_id,
            "external_message_id": f"{executive_group.external_group_id}:MSG-001",
            "sender_name": "Samuel Bamgbola",
            "sender_handle": "2348124940281@s.whatsapp.net",
            "message_type": "text",
            "text": "Need a student design lead and publicity support for the Engineering Week sponsor deck refresh. Paid micro-contract, deadline Tuesday 6pm. Must handle Canva or Figma, social rollout, and sponsor one-pager updates.",
            "raw_payload": {"sync_source": "live"},
            "received_at": datetime.utcnow() - timedelta(hours=8),
        },
    )
    sponsor_artifact = db.insert(
        "message_artifacts",
        {
            "workspace_id": workspace.id,
            "message_id": sponsor_message.id,
            "artifact_type": "opportunity",
            "confidence": 0.92,
            "summary": "design lead opening",
            "extracted_payload": {
                "title": "Design lead and publicity support for sponsor deck",
                "summary": "Paid student contract to refresh sponsor deck assets and publicity rollout for Engineering Week.",
                "organization": "Engineering Faculty Council",
                "location": "UNILAG, Lagos",
                "venue": "Engineering Faculty Council office",
                "event_date": "2026-05-20 18:00",
                "deadline": "Tuesday 6pm",
                "trade_tags": ["media", "design", "graphics", "publicity", "canva", "figma"],
                "contact": "Samuel Bamgbola",
                "action_url": "https://bit.ly/efc-sponsor-creative",
                "key_points": [
                    "Refresh sponsor deck visuals",
                    "Design social media rollout assets",
                    "Update one-page sponsor sheet",
                ],
            },
            "status": "approved",
            "reviewed_at": datetime.utcnow() - timedelta(hours=7, minutes=45),
            "reviewed_by_user_id": owner.user_id,
            "review_note": "Keep this on the opportunities board for media volunteers.",
        },
    )
    sponsor_opportunity = db.insert(
        "opportunities",
        {
            "workspace_id": workspace.id,
            "message_id": sponsor_message.id,
            "source": "whatsapp",
            "title": "Design lead and publicity support for sponsor deck",
            "description": "Paid student contract to refresh sponsor deck assets and publicity rollout for Engineering Week.",
            "summary": "Paid student contract for sponsor-deck refresh and rollout support.",
            "organization": "Engineering Faculty Council",
            "location": "UNILAG, Lagos",
            "venue": "Engineering Faculty Council office",
            "trade_tags": ["media", "design", "graphics", "publicity", "canva", "figma"],
            "key_points": [
                "Refresh sponsor deck visuals",
                "Design social media rollout assets",
                "Update one-page sponsor sheet",
            ],
            "event_date": "2026-05-20 18:00",
            "deadline": "Tuesday 6pm",
            "contact": "Samuel Bamgbola",
            "action_url": "https://bit.ly/efc-sponsor-creative",
            "source_excerpt": sponsor_message.text,
            "status": "in_progress",
        },
    )
    sponsor_matches = refresh_opportunity_matches(db, opportunity=sponsor_opportunity)
    for match in sponsor_matches:
        if match.member_id == media.id:
            match["status"] = "assigned"
            match["note"] = "David already owns publicity and graphics."
            db.save("opportunity_matches", match)
        elif match.member_id == events.id:
            match["status"] = "contacted"
            match["note"] = "Amina can support volunteer-facing comms."
            db.save("opportunity_matches", match)

    ops_message = db.insert(
        "channel_messages",
        {
            "workspace_id": workspace.id,
            "channel_id": whatsapp.id,
            "group_link_id": volunteers_group.id,
            "provider": "whatsapp",
            "external_group_id": volunteers_group.external_group_id,
            "external_message_id": f"{volunteers_group.external_group_id}:MSG-002",
            "sender_name": "Samuel Bamgbola",
            "sender_handle": "2348124940281@s.whatsapp.net",
            "message_type": "text",
            "text": "Looking for two logistics coordinators and one registration desk lead for the AI for STEM Research workshop on Monday by 2pm at UNILAG Window on America. Small stipend available.",
            "raw_payload": {"sync_source": "live"},
            "received_at": datetime.utcnow() - timedelta(hours=6),
        },
    )
    ops_artifact = db.insert(
        "message_artifacts",
        {
            "workspace_id": workspace.id,
            "message_id": ops_message.id,
            "artifact_type": "opportunity",
            "confidence": 0.89,
            "summary": "logistics coordinators needed",
            "extracted_payload": {
                "title": "Logistics coordinators and registration lead for workshop",
                "summary": "Community opportunity for operations-focused members to support workshop logistics and registration.",
                "organization": "American Spaces x EFC",
                "location": "UNILAG, Lagos",
                "venue": "UNILAG Window on America",
                "event_date": "2026-05-18 14:00",
                "deadline": "Monday 10am",
                "trade_tags": ["logistics", "operations", "registration", "events", "coordination"],
                "contact": "Samuel Bamgbola",
                "action_url": "https://bit.ly/efc-ops-call",
                "key_points": [
                    "Support registration flow",
                    "Coordinate workshop check-in",
                    "Assist with floor logistics",
                ],
            },
            "status": "approved",
            "reviewed_at": datetime.utcnow() - timedelta(hours=5, minutes=50),
            "reviewed_by_user_id": owner.user_id,
            "review_note": "This is a good member-facing ops opportunity.",
        },
    )
    ops_opportunity = db.insert(
        "opportunities",
        {
            "workspace_id": workspace.id,
            "message_id": ops_message.id,
            "source": "whatsapp",
            "title": "Logistics coordinators and registration lead for workshop",
            "description": "Community opportunity for operations-focused members to support workshop logistics and registration.",
            "summary": "Workshop operations support roles for members with logistics and events capacity.",
            "organization": "American Spaces x EFC",
            "location": "UNILAG, Lagos",
            "venue": "UNILAG Window on America",
            "trade_tags": ["logistics", "operations", "registration", "events", "coordination"],
            "key_points": [
                "Support registration flow",
                "Coordinate workshop check-in",
                "Assist with floor logistics",
            ],
            "event_date": "2026-05-18 14:00",
            "deadline": "Monday 10am",
            "contact": "Samuel Bamgbola",
            "action_url": "https://bit.ly/efc-ops-call",
            "source_excerpt": ops_message.text,
            "status": "open",
        },
    )
    refresh_opportunity_matches(db, opportunity=ops_opportunity)

    secretary_task_message = db.insert(
        "channel_messages",
        {
            "workspace_id": workspace.id,
            "channel_id": whatsapp.id,
            "group_link_id": executive_group.id,
            "provider": "whatsapp",
            "external_group_id": executive_group.external_group_id,
            "external_message_id": f"{executive_group.external_group_id}:MSG-003",
            "sender_name": "Ayo Owolabi",
            "sender_handle": "234801000000@s.whatsapp.net",
            "message_type": "text",
            "text": "Secretary, please send the sponsor follow-up letter and revised agenda to the Dean's office before tomorrow 10am.",
            "raw_payload": {"sync_source": "live"},
            "received_at": datetime.utcnow() - timedelta(hours=4, minutes=45),
        },
    )
    secretary_task_artifact = db.insert(
        "message_artifacts",
        {
            "workspace_id": workspace.id,
            "message_id": secretary_task_message.id,
            "artifact_type": "task_signal",
            "confidence": 0.95,
            "summary": "send sponsor follow-up letter",
            "extracted_payload": {
                "title": "Send sponsor follow-up letter and revised agenda",
                "summary": "Deliver the sponsor follow-up letter and updated agenda to the Dean's office.",
                "due_hint": "Tomorrow 10am",
                "assignee_hint": "Secretary",
                "priority": "high",
            },
            "status": "approved",
            "reviewed_at": datetime.utcnow() - timedelta(hours=4, minutes=30),
            "reviewed_by_user_id": owner.user_id,
            "review_note": "Auto-created as a task for the secretary.",
        },
    )
    secretary_task = db.insert(
        "tasks",
        {
            "workspace_id": workspace.id,
            "title": "Send sponsor follow-up letter and revised agenda",
            "description": "Created from the Executive Council WhatsApp group.\n\nSource: Secretary, please send the sponsor follow-up letter and revised agenda to the Dean's office before tomorrow 10am.",
            "assigned_to_member_id": secretary.id,
            "due_date": "2026-05-17 10:00",
            "priority": "high",
            "status": "todo",
            "linked_module": "community_artifact",
            "linked_id": secretary_task_artifact.id,
            "created_by_user_id": owner.user_id,
        },
    )
    create_notification(
        db,
        workspace_id=workspace.id,
        user_id=secretary.user_id,
        title="Task assigned from community inbox",
        body="You have been assigned: Send sponsor follow-up letter and revised agenda.",
        notification_type="task_assignment",
        action_url=f"/{workspace.slug}/tasks",
        metadata={"task_id": secretary_task.id, "artifact_id": secretary_task_artifact.id},
        dedupe_key=f"demo-task:{secretary_task.id}:{secretary.user_id}",
    )

    media_task_message = db.insert(
        "channel_messages",
        {
            "workspace_id": workspace.id,
            "channel_id": whatsapp.id,
            "group_link_id": executive_group.id,
            "provider": "whatsapp",
            "external_group_id": executive_group.external_group_id,
            "external_message_id": f"{executive_group.external_group_id}:MSG-004",
            "sender_name": "Amina Bello",
            "sender_handle": "234801000005@s.whatsapp.net",
            "message_type": "text",
            "text": "David, publish the volunteer call graphics tonight and pin the final timetable in the main group before 8pm.",
            "raw_payload": {"sync_source": "live"},
            "received_at": datetime.utcnow() - timedelta(hours=3, minutes=50),
        },
    )
    media_task_artifact = db.insert(
        "message_artifacts",
        {
            "workspace_id": workspace.id,
            "message_id": media_task_message.id,
            "artifact_type": "task_signal",
            "confidence": 0.94,
            "summary": "publish volunteer graphics",
            "extracted_payload": {
                "title": "Publish volunteer call graphics and pin timetable",
                "summary": "Release volunteer graphics and pin the final timetable in the main group.",
                "due_hint": "Tonight 8pm",
                "assignee_hint": "David",
                "priority": "high",
            },
            "status": "approved",
            "reviewed_at": datetime.utcnow() - timedelta(hours=3, minutes=45),
            "reviewed_by_user_id": owner.user_id,
            "review_note": "Assigned directly to media.",
        },
    )
    media_task = db.insert(
        "tasks",
        {
            "workspace_id": workspace.id,
            "title": "Publish volunteer call graphics and pin timetable",
            "description": "Created from the Executive Council WhatsApp group.\n\nSource: David, publish the volunteer call graphics tonight and pin the final timetable in the main group before 8pm.",
            "assigned_to_member_id": media.id,
            "due_date": "2026-05-16 20:00",
            "priority": "high",
            "status": "in_progress",
            "linked_module": "community_artifact",
            "linked_id": media_task_artifact.id,
            "created_by_user_id": owner.user_id,
        },
    )
    create_notification(
        db,
        workspace_id=workspace.id,
        user_id=media.user_id,
        title="Task assigned from community inbox",
        body="You have been assigned: Publish volunteer call graphics and pin timetable.",
        notification_type="task_assignment",
        action_url=f"/{workspace.slug}/tasks",
        metadata={"task_id": media_task.id, "artifact_id": media_task_artifact.id},
        dedupe_key=f"demo-task:{media_task.id}:{media.user_id}",
    )

    dues_receipt_message = db.insert(
        "channel_messages",
        {
            "workspace_id": workspace.id,
            "channel_id": whatsapp.id,
            "group_link_id": executive_group.id,
            "provider": "whatsapp",
            "external_group_id": executive_group.external_group_id,
            "external_message_id": f"{executive_group.external_group_id}:MSG-005",
            "sender_name": "Amina Bello",
            "sender_handle": "234801000005@s.whatsapp.net",
            "message_type": "image",
            "text": "Paid my leadership levy. Ref: QRM-DUES-EFC-AMINA-2026. Amount: ₦3,500.",
            "raw_payload": {"sync_source": "live", "attachment_name": "levy-payment-proof.jpg", "attachment_mime_type": "image/jpeg"},
            "received_at": datetime.utcnow() - timedelta(hours=2, minutes=40),
        },
    )
    dues_receipt_artifact = db.insert(
        "message_artifacts",
        {
            "workspace_id": workspace.id,
            "message_id": dues_receipt_message.id,
            "artifact_type": "payment_receipt",
            "confidence": 0.91,
            "summary": "levy receipt",
            "extracted_payload": {
                "amount": 3500,
                "payer": "Amina Bello",
                "reference": "QRM-DUES-EFC-AMINA-2026",
                "bank": "Wema Bank",
                "transaction_date": "2026-05-16",
                "payment_for": "2026 Leadership Levy",
                "attachment_text_excerpt": "Transfer success. NGN 3,500. Ref QRM-DUES-EFC-AMINA-2026.",
            },
            "status": "approved",
            "reviewed_at": datetime.utcnow() - timedelta(hours=2, minutes=35),
            "reviewed_by_user_id": treasurer.user_id,
            "review_note": "Verified against Squad reference.",
        },
    )
    dues_payment = db.find_one("dues_payments", {"workspace_id": workspace.id, "gateway_ref": "QRM-DUES-EFC-AMINA-2026"})
    db.insert(
        "community_financial_records",
        {
            "workspace_id": workspace.id,
            "message_id": dues_receipt_message.id,
            "artifact_id": dues_receipt_artifact.id,
            "kind": "payment_receipt",
            "amount": 3500,
            "payer": "Amina Bello",
            "reference": "QRM-DUES-EFC-AMINA-2026",
            "bank": "Wema Bank",
            "transaction_date": "2026-05-16",
            "linked_record_type": "dues_payment",
            "linked_record_id": dues_payment.id if dues_payment else None,
            "verification_state": "matched",
            "linked_record_label": "Dues payment · 2026 Leadership Levy",
            "provider_name": "squad",
            "provider_verification_status": "verified",
            "provider_verification_note": "Matched against Squad transaction data for NGN 3,500.",
            "provider_verified_amount": 3500,
            "provider_verified_reference": "QRM-DUES-EFC-AMINA-2026",
            "provider_transaction_ref": "SQD-EFC-DUES-005",
            "attachment_name": "levy-payment-proof.jpg",
            "attachment_text_excerpt": "Transfer success. NGN 3,500. Ref QRM-DUES-EFC-AMINA-2026.",
            "payment_for": "2026 Leadership Levy",
        },
    )

    sponsor_receipt_message = db.insert(
        "channel_messages",
        {
            "workspace_id": workspace.id,
            "channel_id": whatsapp.id,
            "group_link_id": executive_group.id,
            "provider": "whatsapp",
            "external_group_id": executive_group.external_group_id,
            "external_message_id": f"{executive_group.external_group_id}:MSG-006",
            "sender_name": "Tomiwa Adeyemi",
            "sender_handle": "234801000002@s.whatsapp.net",
            "message_type": "document",
            "text": "TekBridge balance landed. Ref: QRM-CAMP-EFC-001. Amount: ₦320,000 for Engineering Week sponsors.",
            "raw_payload": {"sync_source": "live", "attachment_name": "tekbridge-receipt.pdf", "attachment_mime_type": "application/pdf"},
            "received_at": datetime.utcnow() - timedelta(hours=2),
        },
    )
    sponsor_receipt_artifact = db.insert(
        "message_artifacts",
        {
            "workspace_id": workspace.id,
            "message_id": sponsor_receipt_message.id,
            "artifact_type": "contribution_signal",
            "confidence": 0.9,
            "summary": "sponsorship payment",
            "extracted_payload": {
                "amount": 320000,
                "contributor_name": "TekBridge Systems",
                "reference": "QRM-CAMP-EFC-001",
                "bank": "Wema Bank",
                "transaction_date": "2026-05-15",
                "payment_for": "Engineering Week sponsors",
                "attachment_text_excerpt": "Transfer success NGN 320000 Ref QRM-CAMP-EFC-001",
            },
            "status": "approved",
            "reviewed_at": datetime.utcnow() - timedelta(hours=1, minutes=55),
            "reviewed_by_user_id": treasurer.user_id,
            "review_note": "Matched to sponsor contribution.",
        },
    )
    campaign_contribution = db.find_one("contributions", {"workspace_id": workspace.id, "gateway_ref": "QRM-CAMP-EFC-001"})
    db.insert(
        "community_financial_records",
        {
            "workspace_id": workspace.id,
            "message_id": sponsor_receipt_message.id,
            "artifact_id": sponsor_receipt_artifact.id,
            "kind": "contribution_signal",
            "amount": 320000,
            "payer": "TekBridge Systems",
            "reference": "QRM-CAMP-EFC-001",
            "bank": "Wema Bank",
            "transaction_date": "2026-05-15",
            "linked_record_type": "contribution",
            "linked_record_id": campaign_contribution.id if campaign_contribution else None,
            "verification_state": "matched",
            "linked_record_label": "Contribution · Engineering Week Fund",
            "provider_name": "squad",
            "provider_verification_status": "verified",
            "provider_verification_note": "Matched against Squad transaction data for NGN 320,000.",
            "provider_verified_amount": 320000,
            "provider_verified_reference": "QRM-CAMP-EFC-001",
            "provider_transaction_ref": "SQD-EFC-CAMP-001",
            "attachment_name": "tekbridge-receipt.pdf",
            "attachment_text_excerpt": "Transfer success NGN 320000 Ref QRM-CAMP-EFC-001",
            "payment_for": "Engineering Week sponsors",
        },
    )

    disbursement_message = db.insert(
        "channel_messages",
        {
            "workspace_id": workspace.id,
            "channel_id": whatsapp.id,
            "group_link_id": executive_group.id,
            "provider": "whatsapp",
            "external_group_id": executive_group.external_group_id,
            "external_message_id": f"{executive_group.external_group_id}:MSG-007",
            "sender_name": "Favour Okonkwo",
            "sender_handle": "234801000003@s.whatsapp.net",
            "message_type": "text",
            "text": "Can we release ₦85,000 to Havilah Caterers today so they can lock Tuesday breakfast and panel refreshments?",
            "raw_payload": {"sync_source": "live"},
            "received_at": datetime.utcnow() - timedelta(hours=1, minutes=20),
        },
    )
    db.insert(
        "message_artifacts",
        {
            "workspace_id": workspace.id,
            "message_id": disbursement_message.id,
            "artifact_type": "disbursement_request",
            "confidence": 0.63,
            "summary": "refreshment disbursement",
            "extracted_payload": {
                "amount": 85000,
                "purpose": "Tuesday breakfast and panel refreshments",
                "beneficiary": "Havilah Caterers",
            },
            "status": "needs_review",
            "reviewed_at": None,
            "reviewed_by_user_id": None,
            "review_note": None,
        },
    )

    announcement_message = db.insert(
        "channel_messages",
        {
            "workspace_id": workspace.id,
            "channel_id": whatsapp.id,
            "group_link_id": volunteers_group.id,
            "provider": "whatsapp",
            "external_group_id": volunteers_group.external_group_id,
            "external_message_id": f"{volunteers_group.external_group_id}:MSG-008",
            "sender_name": "David Omotoso",
            "sender_handle": "234801000006@s.whatsapp.net",
            "message_type": "text",
            "text": "Volunteer orientation has been moved to 5pm on Sunday at the Council Chamber. Please come with your departmental tags.",
            "raw_payload": {"sync_source": "live"},
            "received_at": datetime.utcnow() - timedelta(minutes=55),
        },
    )
    db.insert(
        "message_artifacts",
        {
            "workspace_id": workspace.id,
            "message_id": announcement_message.id,
            "artifact_type": "announcement",
            "confidence": 0.84,
            "summary": "orientation moved to 5pm",
            "extracted_payload": {
                "title": "Volunteer orientation moved to 5pm",
                "audience": "Engineering Week volunteers",
                "action_required": "Come with departmental tags",
            },
            "status": "ready",
            "reviewed_at": None,
            "reviewed_by_user_id": None,
            "review_note": None,
        },
    )

    create_notification(
        db,
        workspace_id=workspace.id,
        user_id=owner.user_id,
        title="High-value contribution signal",
        body="TekBridge sponsorship receipt was verified against Squad and linked to Engineering Week Fund.",
        notification_type="community_signal",
        action_url=f"/{workspace.slug}/community-inbox",
        metadata={"artifact_id": sponsor_receipt_artifact.id},
        dedupe_key="demo-community-signal-sponsor",
    )
    create_notification(
        db,
        workspace_id=workspace.id,
        user_id=treasurer.user_id,
        title="Receipt matched to levy record",
        body="Amina Bello's leadership levy proof was matched and verified against Squad.",
        notification_type="community_signal",
        action_url=f"/{workspace.slug}/community-inbox",
        metadata={"artifact_id": dues_receipt_artifact.id},
        dedupe_key="demo-community-signal-dues",
    )


def _grade_label(score: float) -> str:
    if score >= 8.5:
        return "Strong"
    if score >= 6.5:
        return "Good"
    if score >= 4.5:
        return "Developing"
    return "At risk"


def _seed_financial_health_snapshots(db: MongoStore, workspace: models.Workspace) -> None:
    db.delete_many("financial_health_snapshots", {"workspace_id": workspace.id})
    current = build_financial_health_snapshot(db, workspace=workspace)
    adjustments = [
        (21, -0.8),
        (10, -0.35),
        (0, 0.0),
    ]
    for days_ago, delta in adjustments:
        snapshot = deepcopy(current)
        snapshot["overall_score"] = round(max(0.0, min(10.0, float(current.get("overall_score") or 0) + delta)), 2)
        snapshot["overall_grade"] = _grade_label(snapshot["overall_score"])
        snapshot["created_at"] = datetime.utcnow() - timedelta(days=days_ago)
        db.insert("financial_health_snapshots", snapshot)


def ensure_demo_workspace(db: MongoStore) -> tuple[models.Workspace, models.WorkspaceMember]:
    workspace = _ensure_workspace(db)
    if int(workspace.get("demo_seed_version") or 0) == DEMO_SEED_VERSION:
        membership = _existing_demo_membership(db, workspace)
        if membership:
            return workspace, membership
    owner_membership, memberships = _seed_members(db, workspace)
    _seed_member_invites(db, workspace, owner_membership)
    _seed_squad_integration(db, workspace)
    _seed_dues(db, workspace, memberships)
    _seed_events(db, workspace, memberships)
    _seed_campaigns(db, workspace, memberships)
    _seed_links(db, workspace)
    _seed_announcements(db, workspace)
    _seed_meetings_and_tasks(db, workspace, memberships)
    _seed_budgets(db, workspace)
    _seed_community_intelligence(db, workspace, memberships)
    _seed_reports(db, workspace, owner_membership)
    _seed_financial_health_snapshots(db, workspace)
    workspace["demo_seed_version"] = DEMO_SEED_VERSION
    db.save("workspaces", workspace)
    return workspace, owner_membership
