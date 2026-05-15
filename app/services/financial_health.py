from __future__ import annotations

from datetime import datetime, timedelta

from ..database import MongoStore


def build_financial_health_snapshot(db: MongoStore, *, workspace) -> dict:
    workspace_id = workspace.id
    active_members = db.find_many("workspace_members", {"workspace_id": workspace_id, "status": "active"})
    member_count = len(active_members)
    paid_members = len([member for member in active_members if str(member.get("dues_status") or "").lower() == "paid"])
    dues_ratio = (paid_members / member_count) if member_count else 0.0

    confirmed_dues = _count_status(db.find_many("dues_payments", {"workspace_id": workspace_id}), {"confirmed", "success", "paid"})
    total_dues = db.count("dues_payments", {"workspace_id": workspace_id})
    confirmed_contributions = _count_status(db.find_many("contributions", {"workspace_id": workspace_id}), {"confirmed", "success", "paid"})
    total_contributions = db.count("contributions", {"workspace_id": workspace_id})
    collection_ratio = ((confirmed_dues + confirmed_contributions) / max(total_dues + total_contributions, 1)) if (total_dues + total_contributions) else dues_ratio

    ninety_days_ago = datetime.utcnow() - timedelta(days=90)
    governance_events = (
        db.count("meetings", {"workspace_id": workspace_id, "created_at": {"$gte": ninety_days_ago}})
        + db.count("announcements", {"workspace_id": workspace_id, "created_at": {"$gte": ninety_days_ago}})
        + db.count("reports", {"workspace_id": workspace_id, "created_at": {"$gte": ninety_days_ago}})
    )
    governance_score = min(10.0, 3.0 + governance_events * 1.2)

    actionable_artifacts = db.count(
        "message_artifacts",
        {"workspace_id": workspace_id, "status": {"$in": ["ready", "approved"]}, "artifact_type": {"$ne": "other"}},
    )
    total_artifacts = db.count("message_artifacts", {"workspace_id": workspace_id})
    signal_ratio = (actionable_artifacts / total_artifacts) if total_artifacts else 0.0
    signal_score = min(10.0, (signal_ratio * 7.0) + min(actionable_artifacts, 12) * 0.25)

    open_opportunities = db.count("opportunities", {"workspace_id": workspace_id, "status": {"$ne": "closed"}})
    total_matches = db.count("opportunity_matches", {"workspace_id": workspace_id})
    opportunity_score = min(10.0, (open_opportunities * 1.4) + min(total_matches, 12) * 0.45)

    categories = [
        _category("collections", "Collections discipline", dues_ratio * 10.0, _collections_summary(dues_ratio, collection_ratio)),
        _category("verified_inflows", "Verified inflows", collection_ratio * 10.0, _inflow_summary(confirmed_dues, confirmed_contributions, total_dues + total_contributions)),
        _category("governance", "Governance activity", governance_score, _governance_summary(governance_events)),
        _category("community_signals", "Community signals", signal_score, _signal_summary(actionable_artifacts, total_artifacts)),
        _category("opportunity_access", "Opportunity access", opportunity_score, _opportunity_summary(open_opportunities, total_matches)),
    ]

    overall_score = round(
        (
            categories[0]["score"] * 0.30
            + categories[1]["score"] * 0.20
            + categories[2]["score"] * 0.20
            + categories[3]["score"] * 0.15
            + categories[4]["score"] * 0.15
        ),
        2,
    )

    strengths = [item["summary"] for item in categories if item["score"] >= 7.5][:3]
    watchouts = [item["summary"] for item in categories if item["score"] < 5.5][:3]
    if not strengths:
        strengths.append("The workspace is building a usable operating record across finance and community activity.")
    if not watchouts:
        watchouts.append("The next improvement is consistency: keep financial records and community activity tightly connected.")

    return {
        "workspace_id": workspace_id,
        "overall_score": overall_score,
        "overall_grade": _grade(overall_score),
        "summary": _summary_for_score(overall_score, dues_ratio, actionable_artifacts, open_opportunities),
        "strengths": strengths,
        "watchouts": watchouts,
        "categories": categories,
        "key_metrics": [
            {"key": "members_paid", "label": "Members paid", "value": f"{paid_members}/{member_count or 0}", "trend": _trend_label(dues_ratio * 10.0)},
            {"key": "verified_collections", "label": "Verified collections", "value": f"{confirmed_dues + confirmed_contributions}", "trend": _trend_label(collection_ratio * 10.0)},
            {"key": "actionable_signals", "label": "Actionable signals", "value": str(actionable_artifacts), "trend": _trend_label(signal_score)},
            {"key": "member_matches", "label": "Opportunity matches", "value": str(total_matches), "trend": _trend_label(opportunity_score)},
        ],
        "created_at": datetime.utcnow(),
    }


def store_financial_health_snapshot(db: MongoStore, *, snapshot: dict) -> dict:
    return db.insert("financial_health_snapshots", snapshot)


def _category(key: str, title: str, score: float, summary: str) -> dict:
    rounded = round(score, 2)
    return {
        "category_key": key,
        "title": title,
        "score": rounded,
        "status": _trend_label(rounded),
        "summary": summary,
    }


def _grade(score: float) -> str:
    if score >= 8.5:
        return "Strong"
    if score >= 6.5:
        return "Good"
    if score >= 4.5:
        return "Developing"
    return "At risk"


def _trend_label(score: float) -> str:
    if score >= 8:
        return "strong"
    if score >= 6:
        return "steady"
    if score >= 4:
        return "watch"
    return "risk"


def _summary_for_score(score: float, dues_ratio: float, actionable_artifacts: int, open_opportunities: int) -> str:
    if score >= 8:
        return f"This community has a credible operating record, with {int(round(dues_ratio * 100))}% dues discipline and visible activity flowing from chat into Quorum."
    if score >= 6:
        return f"The foundation is usable, but the community still needs more consistency across payments, governance, and follow-through on opportunities."
    return f"The current record is still fragile. Quorum is capturing {actionable_artifacts} useful signals, but the financial and governance picture needs tighter discipline."


def _collections_summary(dues_ratio: float, collection_ratio: float) -> str:
    return f"Dues discipline is at {int(round(dues_ratio * 100))}%, while verified collections are landing at {int(round(collection_ratio * 100))}%."


def _inflow_summary(confirmed_dues: int, confirmed_contributions: int, total: int) -> str:
    return f"{confirmed_dues + confirmed_contributions} of {total or 0} recorded inflows have been verified through Quorum."


def _governance_summary(governance_events: int) -> str:
    return f"{governance_events} governance records were created in the last 90 days across meetings, announcements, and reports."


def _signal_summary(actionable_artifacts: int, total_artifacts: int) -> str:
    return f"{actionable_artifacts} of {total_artifacts or 0} analyzed community signals were useful enough to keep as structured records."


def _opportunity_summary(open_opportunities: int, total_matches: int) -> str:
    return f"{open_opportunities} open opportunities have produced {total_matches} member match suggestions so far."


def _count_status(records: list, good_statuses: set[str]) -> int:
    return sum(1 for item in records if str(item.get("status") or "").strip().lower() in good_statuses)
