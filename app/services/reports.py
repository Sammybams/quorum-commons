from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta
from statistics import mean
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from ..database import MongoStore


load_dotenv()


CATEGORY_ORDER = [
    "membership",
    "dues",
    "events",
    "meetings",
    "fundraising",
    "communication",
    "ai_usage",
]

CATEGORY_META = {
    "membership": {"title": "Membership & Engagement", "weight": 0.15},
    "dues": {"title": "Dues Collection", "weight": 0.25},
    "events": {"title": "Events & Programs", "weight": 0.20},
    "meetings": {"title": "Meetings & Governance", "weight": 0.20},
    "fundraising": {"title": "Fundraising & Finance", "weight": 0.10},
    "communication": {"title": "Communication & Announcements", "weight": 0.05},
    "ai_usage": {"title": "AI & Platform Usage", "weight": 0.05},
}

REPORT_SYSTEM_PROMPT = """
You are an expert organisational analyst writing an end-of-period audit report for a student body
at a Nigerian university. You are given structured Quorum data with metric scores already computed.

Write clearly, honestly, and specifically. Use the actual numbers provided. Do not use generic
management language. If performance is weak, say so plainly and explain why it matters for a
student leadership team.

Context:
- Student bodies often operate on semester cycles and leadership handovers.
- Dues collection below 70% is a serious governance issue.
- Dues collection above 85% is strong.
- WhatsApp is often the primary communication channel outside the platform.
- The incoming exco needs concrete guidance, not vague praise.

Return only valid JSON with this exact shape:
{
  "executive_summary": [string, string, string],
  "period_highlights": [string, string, string],
  "categories": [
    {
      "category_key": string,
      "title": string,
      "headline_verdict": string,
      "went_well": [string, string],
      "underperformed": [string, string],
      "watch_out_flag": string|null
    }
  ],
  "recommendations": [
    {
      "data_finding": string,
      "action": string,
      "expected_outcome": string,
      "priority": "high"|"medium"|"low",
      "responsible_role": string
    }
  ],
  "handover_note": [string, string]
}
"""


class ReportGenerationError(RuntimeError):
    pass


def report_model() -> str:
    return os.getenv("ANTHROPIC_REPORT_MODEL") or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


def report_ai_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def compile_report_snapshot(
    db: MongoStore,
    *,
    workspace,
    period_start: date,
    period_end: date,
    enabled_categories: list[str] | None = None,
) -> dict[str, Any]:
    categories = [item for item in (enabled_categories or CATEGORY_ORDER) if item in CATEGORY_META]
    if not categories:
        categories = CATEGORY_ORDER[:]

    start_dt = datetime.combine(period_start, time.min)
    end_dt = datetime.combine(period_end, time.max)
    period_days = max((period_end - period_start).days + 1, 1)
    previous_end = start_dt - timedelta(seconds=1)
    previous_start = previous_end - timedelta(days=period_days - 1)

    context = {
      "db": db,
      "workspace": workspace,
      "workspace_id": workspace.id,
      "start_dt": start_dt,
      "end_dt": end_dt,
      "previous_start": previous_start,
      "previous_end": previous_end,
      "period_days": period_days,
      "memberships": db.find_many("workspace_members", {"workspace_id": workspace.id, "status": "active"}),
      "users": {},
    }

    for membership in context["memberships"]:
        user = db.find_by_id("users", membership.user_id)
        if user:
            context["users"][membership.id] = user

    compiled_categories = []
    for category_key in categories:
        if category_key == "membership":
            metrics = _membership_metrics(context)
        elif category_key == "dues":
            metrics = _dues_metrics(context)
        elif category_key == "events":
            metrics = _events_metrics(context)
        elif category_key == "meetings":
            metrics = _meetings_metrics(context)
        elif category_key == "fundraising":
            metrics = _fundraising_metrics(context)
        elif category_key == "communication":
            metrics = _communication_metrics(context)
        else:
            metrics = _ai_usage_metrics(context)

        compiled_categories.append(
            {
                "category_key": category_key,
                "title": CATEGORY_META[category_key]["title"],
                "weight": CATEGORY_META[category_key]["weight"],
                "category_score": round(_category_score(metrics) * 10, 2),
                "metrics": metrics,
            }
        )

    overall_score = _overall_score(compiled_categories)

    return {
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "slug": workspace.slug,
            "description": workspace.get("description"),
        },
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
            "label": _period_label(period_start, period_end),
            "days": period_days,
        },
        "overall_score": overall_score,
        "overall_grade": _grade_for_score(overall_score),
        "categories": compiled_categories,
    }


def fallback_report_narrative(snapshot: dict[str, Any], context_notes: str | None = None) -> dict[str, Any]:
    categories = snapshot.get("categories", [])
    scored_categories = sorted(categories, key=lambda item: item.get("category_score", 0), reverse=True)
    strongest = scored_categories[0] if scored_categories else None
    weakest = scored_categories[-1] if scored_categories else None

    executive_summary = [
        (
            f"{snapshot['workspace']['name']} recorded an overall performance score of "
            f"{snapshot['overall_score']:.1f}/10 for {snapshot['period']['label']}, graded "
            f"{snapshot['overall_grade']}. The period shows a real operating structure in place, but not every core area performed evenly."
        ),
        (
            f"The clearest strength was {strongest['title'].lower()} at {strongest['category_score']:.1f}/10."
            if strongest
            else "The strongest signals came from the categories that maintained steady execution and visible follow-through."
        ),
        (
            f"The weakest area was {weakest['title'].lower()} at {weakest['category_score']:.1f}/10, which means the next leadership cycle should treat it as a priority instead of a background issue."
            if weakest
            else "The biggest risk is inconsistency across modules rather than a total lack of activity."
        ),
    ]

    if context_notes:
        executive_summary[2] += f" Context provided by the workspace also points to: {context_notes.strip()[:180]}."

    category_narratives = []
    highlights: list[str] = []
    recommendations: list[dict[str, str]] = []
    for category in categories:
        good_metrics = [metric for metric in category["metrics"] if metric["status"] in {"excellent", "good"}]
        weak_metrics = [metric for metric in category["metrics"] if metric["status"] in {"below_target", "critical"}]
        if good_metrics:
            highlights.append(f"{category['title']}: {good_metrics[0]['label']} stood out at {good_metrics[0]['actual_value']}.")
        category_narratives.append(
            {
                "category_key": category["category_key"],
                "title": category["title"],
                "headline_verdict": _category_verdict(category["title"], category["category_score"]),
                "went_well": [
                    f"{metric['label']} came in at {metric['actual_value']}."
                    for metric in good_metrics[:2]
                ]
                or ["The period still produced usable operating data in this category."],
                "underperformed": [
                    f"{metric['label']} landed at {metric['actual_value']}, against a target of {metric['target_value']}."
                    for metric in weak_metrics[:2]
                ]
                or ["No serious underperformance was recorded in this category."],
                "watch_out_flag": weak_metrics[0]["label"] if any(metric["status"] == "critical" for metric in weak_metrics) else None,
            }
        )
        for metric in weak_metrics[:2]:
            recommendations.append(
                {
                    "data_finding": f"{category['title']}: {metric['label']} was {metric['actual_value']}.",
                    "action": f"Set a recovery plan around {metric['label'].lower()} with weekly ownership and visible follow-up.",
                    "expected_outcome": "The next leadership team gets a clearer operating baseline and fewer hidden gaps.",
                    "priority": "high" if metric["status"] == "critical" else "medium",
                    "responsible_role": _responsible_role_for_category(category["category_key"]),
                }
            )

    if not recommendations:
        recommendations.append(
            {
                "data_finding": "Operational data is now available across multiple Quorum modules.",
                "action": "Use the report at handover and review it again mid-cycle with updated targets.",
                "expected_outcome": "Leadership decisions stay tied to real evidence instead of assumptions.",
                "priority": "medium",
                "responsible_role": "Super Admin",
            }
        )

    while len(highlights) < 3:
        highlights.append("Operational reporting is now available across members, meetings, finance, and communication.")

    return {
        "executive_summary": executive_summary[:3],
        "period_highlights": highlights[:5],
        "categories": category_narratives,
        "recommendations": recommendations[:6],
        "handover_note": [
            (
                "Incoming exco members are inheriting more than isolated records. They are inheriting a visible operating history across people, meetings, finance, and communication. Use that visibility early instead of waiting for issues to become political or urgent."
            ),
            (
                "The right next move is to treat the weakest category in this report as an explicit first-quarter priority, while preserving the strongest one as a working standard for the rest of the team."
            ),
        ],
    }


def generate_report_narrative(snapshot: dict[str, Any], context_notes: str | None = None) -> dict[str, Any]:
    if not report_ai_configured():
        return fallback_report_narrative(snapshot, context_notes)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    prompt = (
        "Generate a student-body audit report from this structured data.\n"
        "Use the metric scores and targets already provided instead of recalculating them.\n"
        "If a category is weak, be explicit about it.\n"
        "Context notes from the workspace should influence tone and recommendations where relevant.\n\n"
        f"Context notes: {context_notes or 'None provided.'}\n\n"
        f"Snapshot JSON:\n{json.dumps(snapshot, ensure_ascii=True)}"
    )
    payload = {
        "model": report_model(),
        "max_tokens": 4200,
        "temperature": 0.25,
        "system": REPORT_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }
    request = Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ReportGenerationError(detail or str(exc)) from exc
    except URLError as exc:
        raise ReportGenerationError(str(exc.reason)) from exc

    parsed = json.loads(raw)
    text = _anthropic_text(parsed)
    narrative = _parse_json_object(text)
    return {
        "executive_summary": list(narrative.get("executive_summary", []))[:3] or fallback_report_narrative(snapshot, context_notes)["executive_summary"],
        "period_highlights": list(narrative.get("period_highlights", []))[:5] or fallback_report_narrative(snapshot, context_notes)["period_highlights"],
        "categories": narrative.get("categories", []),
        "recommendations": narrative.get("recommendations", []),
        "handover_note": list(narrative.get("handover_note", []))[:2] or fallback_report_narrative(snapshot, context_notes)["handover_note"],
    }


def _membership_metrics(context: dict[str, Any]) -> list[dict[str, Any]]:
    memberships = context["memberships"]
    previous_memberships = _memberships_in_range(memberships, context["previous_start"], context["previous_end"])
    current_memberships = _memberships_in_range(memberships, context["start_dt"], context["end_dt"])
    total_members = len(memberships)
    previous_count = len(previous_memberships)
    growth_rate = round(((len(current_memberships) - previous_count) / previous_count) * 100, 1) if previous_count else (100.0 if current_memberships else 0.0)

    sessions = context["db"].find_many("auth_sessions", {"workspace_id": context["workspace_id"]})
    active_users = {
        session.user_id
        for session in sessions
        if _within_period(session.get("created_at"), context["start_dt"], context["end_dt"])
    }
    active_rate = round((len(active_users) / total_members) * 100, 1) if total_members else 0.0

    event_attendees = context["db"].find_many("event_attendees", {"workspace_id": context["workspace_id"]})
    dues_payments = context["db"].find_many("dues_payments", {"workspace_id": context["workspace_id"], "status": {"$in": ["paid", "confirmed"]}})
    engaged_members = {
        attendee.member_id
        for attendee in event_attendees
        if attendee.get("member_id") and _within_period(attendee.get("rsvp_at") or attendee.get("created_at"), context["start_dt"], context["end_dt"])
    }
    engaged_members.update(
        payment.member_id
        for payment in dues_payments
        if payment.get("member_id") and _within_period(payment.get("confirmed_at") or payment.get("created_at"), context["start_dt"], context["end_dt"])
    )
    engaged_rate = round((len(engaged_members) / total_members) * 100, 1) if total_members else 0.0

    admin_member_ids = {member.id for member in memberships if not member.get("is_general_member")}
    admin_records = [
        attendee
        for attendee in event_attendees
        if attendee.get("member_id") in admin_member_ids and _within_period(attendee.get("rsvp_at") or attendee.get("created_at"), context["start_dt"], context["end_dt"])
    ]
    admin_checked_in = [attendee for attendee in admin_records if attendee.get("status") == "checked_in" or attendee.get("checked_in_at")]
    admin_attendance_rate = round((len(admin_checked_in) / len(admin_records)) * 100, 1) if admin_records else 0.0

    return [
        _metric("Total registered members", "total_registered_members", total_members, None, "informational", format_type="count"),
        _metric("Member growth rate", "member_growth_rate", growth_rate, 10, ">=", format_type="percent"),
        _metric("Active members", "active_members_rate", active_rate, 70, ">=", format_type="percent"),
        _metric("General member engagement", "member_engagement_rate", engaged_rate, 50, ">=", format_type="percent"),
        _metric("Admin attendance at events", "admin_event_attendance_rate", admin_attendance_rate, 80, ">=", format_type="percent"),
    ]


def _dues_metrics(context: dict[str, Any]) -> list[dict[str, Any]]:
    memberships = context["memberships"]
    total_members = len(memberships)
    cycles = context["db"].find_many("dues_cycles", {"workspace_id": context["workspace_id"]})
    payments = context["db"].find_many("dues_payments", {"workspace_id": context["workspace_id"], "status": {"$in": ["paid", "confirmed"]}})
    period_payments = [
        payment
        for payment in payments
        if _within_period(payment.get("confirmed_at") or payment.get("created_at"), context["start_dt"], context["end_dt"])
    ]
    paid_member_ids = {payment.member_id for payment in period_payments if payment.get("member_id")}
    collection_rate = round((len(paid_member_ids) / total_members) * 100, 1) if total_members else 0.0
    defaulter_rate = round(((total_members - len(paid_member_ids)) / total_members) * 100, 1) if total_members else 0.0

    cycle_lookup = {cycle.id: cycle for cycle in cycles}
    avg_days = []
    for payment in period_payments:
        cycle = cycle_lookup.get(payment.cycle_id)
        confirmed_at = _parse_timestamp(payment.get("confirmed_at") or payment.get("created_at"))
        cycle_opened = _parse_timestamp(cycle.get("published_at") or cycle.get("created_at")) if cycle else None
        if confirmed_at and cycle_opened:
            avg_days.append((confirmed_at - cycle_opened).total_seconds() / 86400)
    average_days = round(mean(avg_days), 1) if avg_days else 0.0

    amount_collected = sum(float(payment.get("amount", 0) or 0) for payment in period_payments)
    expected_target = sum(float(cycle.get("amount", 0) or 0) for cycle in cycles) * max(total_members, 1)
    amount_vs_target = round((amount_collected / expected_target) * 100, 1) if expected_target else 0.0

    breakdown = {}
    member_lookup = {member.id: member for member in memberships}
    for payment in period_payments:
        member = member_lookup.get(payment.get("member_id"))
        if not member:
            continue
        level = member.get("level") or "Unspecified"
        entry = breakdown.setdefault(level, {"eligible": 0, "paid": 0})
        entry["paid"] += 1
    for member in memberships:
        level = member.get("level") or "Unspecified"
        entry = breakdown.setdefault(level, {"eligible": 0, "paid": 0})
        entry["eligible"] += 1
    weakest_level = 100.0
    for level_data in breakdown.values():
        rate = (level_data["paid"] / level_data["eligible"] * 100) if level_data["eligible"] else 0
        weakest_level = min(weakest_level, rate)
    weakest_level = round(weakest_level if breakdown else 0.0, 1)

    return [
        _metric("Overall collection rate", "dues_collection_rate", collection_rate, 80, ">=", format_type="percent"),
        _metric("Weakest level collection rate", "dues_collection_by_level", weakest_level, 75, ">=", format_type="percent"),
        _metric("Average days to payment", "dues_avg_days_to_payment", average_days, 14, "<=", format_type="days"),
        _metric("Defaulter rate", "dues_defaulter_rate", defaulter_rate, 20, "<=", format_type="percent"),
        _metric("Amount collected vs target", "dues_amount_vs_target", amount_vs_target, 90, ">=", format_type="percent"),
        _metric("Dues cycles run", "dues_cycles_run", len(cycles), None, "informational", format_type="count"),
    ]


def _events_metrics(context: dict[str, Any]) -> list[dict[str, Any]]:
    events = [
        event
        for event in context["db"].find_many("events", {"workspace_id": context["workspace_id"]})
        if _within_period(event.get("created_at"), context["start_dt"], context["end_dt"])
        or _within_period(event.get("starts_at"), context["start_dt"], context["end_dt"])
    ]
    attendees = context["db"].find_many("event_attendees", {"workspace_id": context["workspace_id"]})
    total_events = len(events)
    checked_in = 0
    rsvps = 0
    completed_events = 0
    event_types = set()
    for event in events:
        event_types.add((event.get("event_type") or "general").lower())
        event_attendees = [item for item in attendees if item.event_id == event.id]
        checked_in += len([item for item in event_attendees if item.get("checked_in_at") or item.get("status") == "checked_in"])
        rsvps += max(int(event.get("rsvp_count", 0) or 0), len(event_attendees))
        event_dt = _parse_timestamp(event.get("starts_at"))
        if event_dt and event_dt <= datetime.utcnow():
            completed_events += 1

    attendance_rate = round((checked_in / max(rsvps, 1)) * 100, 1) if rsvps else 0.0
    conversion_rate = attendance_rate
    type_diversity = len(event_types)
    completion_rate = round((completed_events / total_events) * 100, 1) if total_events else 0.0

    return [
        _metric("Total events organised", "events_total", total_events, 4, ">=", format_type="count"),
        _metric("Average attendance rate", "events_attendance_rate", attendance_rate, 40, ">=", format_type="percent"),
        _metric("RSVP to attendance conversion", "events_rsvp_conversion", conversion_rate, 60, ">=", format_type="percent"),
        _metric("Event type diversity", "events_type_diversity", type_diversity, 2, ">=", format_type="count"),
        _metric("Events completed vs planned", "events_completion_rate", completion_rate, 80, ">=", format_type="percent"),
    ]


def _meetings_metrics(context: dict[str, Any]) -> list[dict[str, Any]]:
    meetings = [
        meeting
        for meeting in context["db"].find_many("meetings", {"workspace_id": context["workspace_id"]})
        if _within_period(meeting.get("scheduled_for"), context["start_dt"], context["end_dt"])
        or _within_period(meeting.get("created_at"), context["start_dt"], context["end_dt"])
    ]
    total_meetings = len(meetings)
    minutes_docs = {item.meeting_id: item for item in context["db"].find_many("meeting_minutes", {})}
    action_items = context["db"].find_many("action_items", {"workspace_id": context["workspace_id"]})
    tasks = context["db"].find_many("tasks", {"workspace_id": context["workspace_id"]})

    quorum_reached = 0
    published_minutes = 0
    publish_delays = []
    tasks_generated = 0
    action_done = 0
    for meeting in meetings:
        if meeting.get("quorum_threshold") and int(meeting.get("attendee_count", 0) or 0) >= int(meeting.get("quorum_threshold") or 0):
            quorum_reached += 1
        minutes = minutes_docs.get(meeting.id)
        if minutes and minutes.get("published_at"):
            published_minutes += 1
            published_at = _parse_timestamp(minutes.get("published_at"))
            scheduled_for = _parse_timestamp(meeting.get("scheduled_for"))
            if published_at and scheduled_for:
                publish_delays.append((published_at - scheduled_for).total_seconds() / 3600)
        linked_tasks = [task for task in tasks if task.get("linked_module") == "meeting" and task.get("linked_id") == meeting.id]
        tasks_generated += len(linked_tasks)

    for item in action_items:
        if item.get("status") in {"done", "completed"}:
            action_done += 1
    quorum_rate = round((quorum_reached / total_meetings) * 100, 1) if total_meetings else 0.0
    minutes_rate = round((published_minutes / total_meetings) * 100, 1) if total_meetings else 0.0
    avg_hours = round(mean(publish_delays), 1) if publish_delays else 0.0
    completion_rate = round((action_done / max(len(action_items), 1)) * 100, 1) if action_items else 0.0
    tasks_per_meeting = round(tasks_generated / total_meetings, 1) if total_meetings else 0.0

    return [
        _metric("Total meetings held", "meetings_total", total_meetings, 6, ">=", format_type="count"),
        _metric("Average quorum achievement", "meetings_quorum_rate", quorum_rate, 90, ">=", format_type="percent"),
        _metric("Minutes published rate", "meetings_minutes_published_rate", minutes_rate, 95, ">=", format_type="percent"),
        _metric("Average time to publish minutes", "meetings_minutes_publish_time", avg_hours, 48, "<=", format_type="hours"),
        _metric("Action item completion rate", "meetings_action_completion_rate", completion_rate, 70, ">=", format_type="percent"),
        _metric("Average tasks generated per meeting", "meetings_tasks_generated", tasks_per_meeting, None, "informational", format_type="number"),
    ]


def _fundraising_metrics(context: dict[str, Any]) -> list[dict[str, Any]]:
    campaigns = context["db"].find_many("campaigns", {"workspace_id": context["workspace_id"]})
    contributions = [
        contribution
        for contribution in context["db"].find_many("contributions", {"workspace_id": context["workspace_id"], "status": "confirmed"})
        if _within_period(contribution.get("confirmed_at") or contribution.get("created_at"), context["start_dt"], context["end_dt"])
    ]
    funding_streams = context["db"].find_many("funding_streams", {"workspace_id": context["workspace_id"]})
    budgets = context["db"].find_many("budgets", {"workspace_id": context["workspace_id"]})
    budget_lines = []
    for budget in budgets:
        budget_lines.extend(context["db"].find_many("budget_lines", {"budget_id": budget.id}))

    total_raised = sum(float(item.get("amount", 0) or 0) for item in contributions)
    goal_hits = 0
    for campaign in campaigns:
        target = float(campaign.get("target_amount", 0) or 0)
        raised = float(campaign.get("raised_amount", 0) or 0)
        if target and raised >= target * 0.8:
            goal_hits += 1
    goal_rate = round((goal_hits / len(campaigns)) * 100, 1) if campaigns else 0.0
    unique_donors = len({(item.get("contributor_email") or item.get("contributor_name") or "").strip().lower() for item in contributions if (item.get("contributor_email") or item.get("contributor_name"))})
    donor_share = round((unique_donors / max(len(context["memberships"]), 1)) * 100, 1) if context["memberships"] else 0.0
    avg_streams = round(mean([len([stream for stream in funding_streams if stream.campaign_id == campaign.id]) for campaign in campaigns]), 1) if campaigns else 0.0

    planned_total = sum(float(line.get("planned_amount", 0) or 0) for line in budget_lines)
    actual_total = sum(float(line.get("actual_amount", 0) or 0) for line in budget_lines)
    budget_adherence = round((actual_total / planned_total) * 100, 1) if planned_total else 0.0
    variance_count = len(
        [
            line
            for line in budget_lines
            if float(line.get("planned_amount", 0) or 0) > 0
            and float(line.get("actual_amount", 0) or 0) > float(line.get("planned_amount", 0) or 0) * 1.2
            and not (line.get("notes") or "").strip()
        ]
    )

    return [
        _metric("Total amount raised", "fundraising_total_raised", total_raised, None, "informational", format_type="currency"),
        _metric("Campaign goal achievement rate", "fundraising_goal_rate", goal_rate, 80, ">=", format_type="percent"),
        _metric("Unique donor coverage", "fundraising_unique_donor_share", donor_share, 30, ">=", format_type="percent"),
        _metric("Funding stream diversification", "fundraising_stream_diversification", avg_streams, 2, ">=", format_type="number"),
        _metric("Budget adherence", "fundraising_budget_adherence", budget_adherence, 110, "<=", format_type="percent"),
        _metric("Unexplained variance items", "fundraising_variance_items", variance_count, 0, "=", format_type="count"),
    ]


def _communication_metrics(context: dict[str, Any]) -> list[dict[str, Any]]:
    announcements = [
        announcement
        for announcement in context["db"].find_many("announcements", {"workspace_id": context["workspace_id"]})
        if _within_period(announcement.get("published_at") or announcement.get("created_at"), context["start_dt"], context["end_dt"])
    ]
    events = [
        event
        for event in context["db"].find_many("events", {"workspace_id": context["workspace_id"]})
        if _within_period(event.get("created_at"), context["start_dt"], context["end_dt"])
        or _within_period(event.get("starts_at"), context["start_dt"], context["end_dt"])
    ]
    links = context["db"].find_many("short_links", {"workspace_id": context["workspace_id"]})
    months_in_period = max(round(context["period_days"] / 30), 1)
    announcement_target = 2 * months_in_period
    avg_delivery_rate = round(mean([(float(item.get("delivery_count", 0) or 0) / max(len(context["memberships"]), 1)) * 100 for item in announcements]), 1) if announcements else 0.0
    pinned_active = len([item for item in announcements if item.get("is_pinned")])
    shareable_events = len([event for event in events if event.get("slug")])
    event_link_usage = round((shareable_events / len(events)) * 100, 1) if events else 0.0
    click_volume = sum(int(link.get("click_count", 0) or 0) for link in links)

    return [
        _metric("Announcements published", "communication_announcements_total", len(announcements), announcement_target, ">=", format_type="count"),
        _metric("Average delivery coverage", "communication_delivery_coverage", avg_delivery_rate, 60, ">=", format_type="percent"),
        _metric("Active pinned announcements", "communication_pinned_announcements", pinned_active, 3, "<=", format_type="count"),
        _metric("Shareable event link usage", "communication_event_link_usage", event_link_usage, 80, ">=", format_type="percent"),
        _metric("Short link click activity", "communication_link_clicks", click_volume, None, "informational", format_type="count"),
    ]


def _ai_usage_metrics(context: dict[str, Any]) -> list[dict[str, Any]]:
    meetings = [
        meeting
        for meeting in context["db"].find_many("meetings", {"workspace_id": context["workspace_id"]})
        if _within_period(meeting.get("scheduled_for"), context["start_dt"], context["end_dt"])
        or _within_period(meeting.get("created_at"), context["start_dt"], context["end_dt"])
    ]
    meeting_ids = {meeting.id for meeting in meetings}
    minutes = [item for item in context["db"].find_many("meeting_minutes", {}) if item.meeting_id in meeting_ids]
    tasks = context["db"].find_many("tasks", {"workspace_id": context["workspace_id"]})
    reports = [
        report
        for report in context["db"].find_many("reports", {"workspace_id": context["workspace_id"]})
        if _within_period(report.get("generated_at") or report.get("created_at"), context["start_dt"], context["end_dt"])
    ]
    ai_minutes = len([item for item in minutes if item.get("generated_by_model")])
    ai_minutes_rate = round((ai_minutes / len(meetings)) * 100, 1) if meetings else 0.0
    transcript_coverage = len([meeting for meeting in meetings if meeting.get("transcript")])
    transcript_rate = round((transcript_coverage / len(meetings)) * 100, 1) if meetings else 0.0
    ai_task_count = len(
        [
            task
            for task in tasks
            if task.get("linked_module") == "meeting"
            and task.get("generated_by") in {"anthropic", "claude"}
            and task.get("linked_id") in meeting_ids
        ]
    )

    return [
        _metric("AI-generated meeting minutes", "ai_minutes_generated_rate", ai_minutes_rate, 70, ">=", format_type="percent"),
        _metric("Meetings with transcript coverage", "ai_transcript_coverage_rate", transcript_rate, 70, ">=", format_type="percent"),
        _metric("Tasks auto-created from meetings", "ai_tasks_auto_created", ai_task_count, None, "informational", format_type="count"),
        _metric("Analytics reports generated", "ai_reports_generated", len(reports), None, "informational", format_type="count"),
    ]


def _metric(
    label: str,
    metric_key: str,
    actual: float | int,
    target: float | int | None,
    operator: str,
    *,
    format_type: str = "number",
) -> dict[str, Any]:
    actual_number = float(actual)
    if operator == "informational" or target is None:
        score = None
        met_target = None
        status = "informational"
    else:
        target_number = float(target)
        score = _score_value(actual_number, target_number, operator)
        met_target = score >= 1.0 - 1e-9
        status = _status_for_score(score)
    return {
        "metric_key": metric_key,
        "label": label,
        "actual_value": _format_metric(actual_number, format_type),
        "target_value": _format_metric(float(target), format_type) if target is not None and operator != "informational" else None,
        "met_target": met_target,
        "score": round(score, 2) if score is not None else None,
        "status": status,
        "operator": operator,
        "raw_actual": round(actual_number, 2),
        "raw_target": float(target) if target is not None else None,
    }


def _score_value(actual: float, target: float, operator: str) -> float:
    if operator == ">=":
        if target <= 0:
            return 1.0
        return max(0.0, min(actual / target, 1.0))
    if operator == "<=":
        if actual <= target:
            return 1.0
        if actual <= 0:
            return 1.0
        return max(0.0, min(target / actual, 1.0))
    if operator == "=":
        return 1.0 if abs(actual - target) < 1e-9 else 0.0
    return 0.0


def _status_for_score(score: float) -> str:
    if score >= 0.98:
        return "excellent"
    if score >= 0.75:
        return "good"
    if score >= 0.4:
        return "below_target"
    return "critical"


def _format_metric(value: float, format_type: str) -> str:
    if format_type == "currency":
        return f"NGN {value:,.0f}"
    if format_type == "percent":
        return f"{value:.1f}%"
    if format_type == "days":
        return f"{value:.1f} days"
    if format_type == "hours":
        return f"{value:.1f} hours"
    if format_type == "count":
        return f"{int(round(value))}"
    if format_type == "number":
        return f"{value:.1f}"
    return str(value)


def _memberships_in_range(memberships: list[Any], start_dt: datetime, end_dt: datetime) -> list[Any]:
    return [membership for membership in memberships if _within_period(membership.get("joined_at") or membership.get("created_at"), start_dt, end_dt)]


def _within_period(value: Any, start_dt: datetime, end_dt: datetime) -> bool:
    parsed = _parse_timestamp(value)
    return bool(parsed and start_dt <= parsed <= end_dt)


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _category_score(metrics: list[dict[str, Any]]) -> float:
    scored = [metric["score"] for metric in metrics if metric.get("score") is not None]
    return round(mean(scored), 4) if scored else 0.0


def _overall_score(categories: list[dict[str, Any]]) -> float:
    weights = sum(category["weight"] for category in categories if category.get("category_score") is not None)
    if weights <= 0:
        return 0.0
    weighted_total = sum((category["category_score"] / 10) * category["weight"] for category in categories)
    return round((weighted_total / weights) * 10, 2)


def _grade_for_score(score: float) -> str:
    if score >= 9:
        return "Exceptional"
    if score >= 7.5:
        return "Strong"
    if score >= 6:
        return "Good"
    if score >= 4:
        return "Needs Improvement"
    return "Poor"


def _period_label(period_start: date, period_end: date) -> str:
    if period_start.year == period_end.year:
        return f"{period_start.strftime('%b %Y')} - {period_end.strftime('%b %Y')}"
    return f"{period_start.isoformat()} - {period_end.isoformat()}"


def _responsible_role_for_category(category_key: str) -> str:
    return {
        "membership": "President / Lead",
        "dues": "Treasurer",
        "events": "Events Lead",
        "meetings": "Secretary",
        "fundraising": "Treasurer",
        "communication": "Publicity Director",
        "ai_usage": "Secretary",
    }.get(category_key, "Super Admin")


def _category_verdict(title: str, category_score: float) -> str:
    if category_score >= 8.5:
        return f"{title} was a clear strength this period with strong execution against target."
    if category_score >= 6.5:
        return f"{title} was functional but still had visible room for tighter execution."
    if category_score >= 4.0:
        return f"{title} showed activity, but the results were inconsistent and below the standard expected of a disciplined student leadership team."
    return f"{title} was a weak point this period and needs direct corrective attention from the next leadership cycle."


def _anthropic_text(payload: dict[str, Any]) -> str:
    content = payload.get("content", [])
    text_chunks = [item.get("text", "") for item in content if item.get("type") == "text" and item.get("text")]
    if not text_chunks:
        raise ReportGenerationError("Anthropic returned no text content.")
    return "\n".join(text_chunks).strip()


def _parse_json_object(value: str) -> dict[str, Any]:
    cleaned = value.strip()
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return json.loads(cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        return json.loads(cleaned[start : end + 1])
    raise ReportGenerationError("Could not parse report JSON from Anthropic response.")
