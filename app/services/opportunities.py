from __future__ import annotations

import re
from typing import Any

from ..database import DESC, MongoStore


def refresh_opportunity_matches(db: MongoStore, *, opportunity) -> list[dict[str, Any]]:
    workspace_id = opportunity.workspace_id
    db.delete_many("opportunity_matches", {"workspace_id": workspace_id, "opportunity_id": opportunity.id})

    members = db.find_many("workspace_members", {"workspace_id": workspace_id, "status": "active"})
    created: list[dict[str, Any]] = []
    for member in members:
        candidate = _score_member_for_opportunity(member=member, opportunity=opportunity, db=db)
        if not candidate:
            continue
        created.append(
            db.insert(
                "opportunity_matches",
                {
                    "workspace_id": workspace_id,
                    "opportunity_id": opportunity.id,
                    "member_id": member.id,
                    **candidate,
                },
            )
        )

    return sorted(created, key=lambda item: float(item.get("match_score") or 0), reverse=True)


def top_matches_for_opportunity(db: MongoStore, *, workspace_id: int, opportunity_id: int, limit: int = 5) -> list[dict[str, Any]]:
    return db.find_many(
        "opportunity_matches",
        {"workspace_id": workspace_id, "opportunity_id": opportunity_id},
        sort=[("match_score", DESC), ("created_at", DESC)],
        limit=limit,
    )


def _score_member_for_opportunity(*, member, opportunity, db: MongoStore) -> dict[str, Any] | None:
    user = db.find_by_id("users", member.user_id)
    role = db.find_by_id("roles", member.role_id)
    if not user or not role:
        return None

    opportunity_tags = _token_set(" ".join(
        [
            *(opportunity.get("trade_tags") or []),
            str(opportunity.get("title") or ""),
            str(opportunity.get("description") or ""),
            str(opportunity.get("location") or ""),
        ]
    ))
    member_trade = _token_set(str(member.get("trade_category") or ""))
    member_prefs = _token_set(" ".join(member.get("opportunity_preferences") or []))
    member_location = str(member.get("location") or "").strip().lower()
    opportunity_location = str(opportunity.get("location") or "").strip().lower()
    availability = str(member.get("availability") or "").strip()
    dues_status = str(member.get("dues_status") or "").strip().lower()

    score = 0.0
    reasons: list[str] = []
    matched_tags = sorted((member_trade | member_prefs) & opportunity_tags)

    if matched_tags:
        score += 0.48
        reasons.append(f"Profile aligns with {', '.join(matched_tags[:3])}.")
    elif member_trade and _text_overlap(" ".join(member_trade), str(opportunity.get("description") or "")):
        score += 0.34
        reasons.append("Trade category overlaps with the opportunity description.")

    if member_location and opportunity_location and (member_location in opportunity_location or opportunity_location in member_location):
        score += 0.16
        reasons.append("Member location matches the opportunity location.")

    if availability:
        score += 0.11
        reasons.append("Availability details are present for quick follow-up.")

    if user.get("phone") or member.get("phone_number"):
        score += 0.08
        reasons.append("Reachable contact details are available.")

    if dues_status == "paid":
        score += 0.05
        reasons.append("Member has an up-to-date contribution record.")

    score = min(score, 0.96)
    if score < 0.35:
        return None

    return {
        "member_name": user.full_name,
        "member_role": role.name,
        "trade_category": member.get("trade_category"),
        "location": member.get("location"),
        "availability": member.get("availability"),
        "match_score": round(score, 2),
        "fit_label": _fit_label(score),
        "matched_tags": matched_tags[:6],
        "reasons": reasons[:3] or ["Member profile is a possible fit based on available context."],
    }


def _fit_label(score: float) -> str:
    if score >= 0.78:
        return "strong fit"
    if score >= 0.58:
        return "good fit"
    return "possible fit"


def _token_set(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]{3,}", value.lower()) if token not in _STOP_WORDS}


def _text_overlap(left: str, right: str) -> bool:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    return bool(left_tokens & right_tokens)


_STOP_WORDS = {
    "and",
    "the",
    "for",
    "with",
    "that",
    "this",
    "from",
    "have",
    "will",
    "into",
    "your",
    "their",
    "about",
    "them",
    "just",
    "need",
}
