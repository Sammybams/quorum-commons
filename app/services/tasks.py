from __future__ import annotations

import re
from typing import Any

from ..database import MongoStore
from ..rbac import role_display_name


def suggest_task_assignee(
    db: MongoStore,
    *,
    workspace_id: int,
    text: str,
    extracted_payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    members = db.find_many("workspace_members", {"workspace_id": workspace_id, "status": "active"})
    lowered = str(text or "").lower()
    assignee_hint = str((extracted_payload or {}).get("assignee_hint") or "").strip().lower()
    best: dict[str, Any] | None = None
    best_score = 0.0

    for member in members:
        user = db.find_by_id("users", member.user_id)
        role = db.find_by_id("roles", member.role_id)
        if not user or not role:
            continue
        score = 0.0
        reasons: list[str] = []

        role_name = role_display_name(role).lower()
        role_key = str(role.get("key") or "").lower()
        full_name = str(user.full_name or "").strip().lower()
        first_name = full_name.split(" ", 1)[0] if full_name else ""
        trade_category = str(member.get("trade_category") or "").strip().lower()
        level = str(member.get("level") or "").strip().lower()

        if assignee_hint and assignee_hint in {role_name, role_key, trade_category, level, first_name}:
            score += 0.78
            reasons.append(f"Matched explicit assignee hint: {assignee_hint}.")
        elif assignee_hint and assignee_hint in lowered and assignee_hint in f"{role_name} {role_key} {trade_category} {level} {full_name}":
            score += 0.7
            reasons.append(f"Message references {assignee_hint}.")

        if first_name and re.search(rf"\b{re.escape(first_name)}\b", lowered):
            score += 0.7
            reasons.append("First name is mentioned in the message.")
        if full_name and re.search(rf"\b{re.escape(full_name)}\b", lowered):
            score += 0.82
            reasons.append("Full name is mentioned in the message.")

        for candidate in {role_name, role_key, trade_category, level}:
            if candidate and candidate in lowered:
                score += 0.45
                reasons.append(f"Message references {candidate}.")
                break

        if member.get("availability"):
            score += 0.05
        if user.get("email"):
            score += 0.03

        if score > best_score:
            best_score = score
            best = {
                "member_id": member.id,
                "member_name": user.full_name,
                "member_role": role_display_name(role),
                "score": round(score, 2),
                "reasons": reasons[:2],
            }

    return best if best and best_score >= 0.6 else None
