from __future__ import annotations

from datetime import datetime, timedelta
import re

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

    community_receipts = db.count(
        "community_financial_records",
        {"workspace_id": workspace_id, "verification_state": {"$in": ["matched", "needs_review", "unlinked"]}},
    )
    receipt_score = min(10.0, min(community_receipts, 15) * 0.6)
    evidence_trail = _build_evidence_trail(db, workspace_id=workspace_id)

    categories = [
        _category("collections", "Collections discipline", dues_ratio * 10.0, _collections_summary(dues_ratio, collection_ratio)),
        _category("verified_inflows", "Verified inflows", collection_ratio * 10.0, _inflow_summary(confirmed_dues, confirmed_contributions, total_dues + total_contributions)),
        _category("governance", "Governance activity", governance_score, _governance_summary(governance_events)),
        _category("community_signals", "Community signals", signal_score, _signal_summary(actionable_artifacts, total_artifacts)),
        _category("opportunity_access", "Opportunity access", opportunity_score, _opportunity_summary(open_opportunities, total_matches)),
        _category("receipt_trail", "Receipt trail", receipt_score, _receipt_summary(community_receipts)),
    ]

    overall_score = round(
        (
            categories[0]["score"] * 0.30
            + categories[1]["score"] * 0.20
            + categories[2]["score"] * 0.20
            + categories[3]["score"] * 0.15
            + categories[4]["score"] * 0.10
            + categories[5]["score"] * 0.05
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
            {"key": "community_receipts", "label": "Receipt trail", "value": str(community_receipts), "trend": _trend_label(receipt_score)},
        ],
        "evidence_trail": evidence_trail,
        "created_at": datetime.utcnow(),
    }


def store_financial_health_snapshot(db: MongoStore, *, snapshot: dict) -> dict:
    return db.insert("financial_health_snapshots", snapshot)


def list_financial_health_history(db: MongoStore, *, workspace_id: int, limit: int = 8) -> list[dict]:
    return list(reversed(db.find_many("financial_health_snapshots", {"workspace_id": workspace_id}, sort=[("created_at", -1)], limit=limit)))


def build_partner_profile(*, snapshot: dict, history: list[dict]) -> dict:
    current = float(snapshot.get("overall_score") or 0)
    previous = float(history[-2].get("overall_score") or current) if len(history) > 1 else current
    delta = round(current - previous, 2)
    direction = "improving" if delta > 0.2 else "softening" if delta < -0.2 else "steady"
    if current >= 8:
        confidence_label = "High confidence"
        headline = "This community shows a credible operating record."
        next_step = "Advance to a deeper underwriting or partnership review."
    elif current >= 6:
        confidence_label = "Moderate confidence"
        headline = "This community is building a usable financial record."
        next_step = "Request another reporting cycle and verify continuity of inflows."
    else:
        confidence_label = "Emerging confidence"
        headline = "This community needs a stronger operating trail."
        next_step = "Keep monitoring collections, governance records, and community receipts before escalation."
    return {
        "headline": headline,
        "confidence_label": confidence_label,
        "summary": f"Overall score is {current:.1f}/10 and the recent direction is {direction}. Community receipts, verified inflows, and governance activity are now part of the profile.",
        "strengths": list(snapshot.get("strengths") or [])[:3],
        "watchouts": list(snapshot.get("watchouts") or [])[:3],
        "recommended_next_step": next_step,
    }


def build_member_financial_profile(db: MongoStore, *, workspace_id: int, member, user, role_name: str) -> dict:
    confirmed_statuses = {"confirmed", "success", "paid"}
    member_name = str((user or {}).get("full_name") or "Member").strip() or "Member"
    member_email = str((user or {}).get("email") or "").strip().lower()

    dues_payments = db.find_many("dues_payments", {"workspace_id": workspace_id, "member_id": member.id}, sort=[("created_at", -1)], limit=50)
    cycles_by_id = {
        cycle.id: cycle
        for cycle in db.find_many(
            "dues_cycles",
            {"workspace_id": workspace_id, "id": {"$in": [payment.get("cycle_id") for payment in dues_payments if payment.get("cycle_id")]}}
            if dues_payments
            else {"workspace_id": workspace_id, "id": {"$in": []}},
        )
    }
    confirmed_dues = [payment for payment in dues_payments if str(payment.get("status") or "").strip().lower() in confirmed_statuses]
    on_time_due_count = 0
    dated_due_count = 0
    payment_history: list[dict] = []
    due_payment_ids: set[int] = set()
    for payment in dues_payments[:8]:
        due_payment_ids.add(int(payment.id))
        cycle = cycles_by_id.get(payment.get("cycle_id"))
        occurred_at = payment.get("confirmed_at") or payment.get("created_at") or datetime.utcnow()
        deadline = _parse_dateish((cycle or {}).get("deadline"))
        on_time = None
        if deadline:
            dated_due_count += 1
            on_time = occurred_at <= deadline
            if on_time:
                on_time_due_count += 1
        payment_history.append(
            {
                "id": int(payment.id),
                "cycle_name": (cycle.get("name") if cycle else None),
                "amount": float(payment.get("amount") or 0),
                "status": str(payment.get("status") or ""),
                "verification_status": payment.get("verification_status"),
                "provider": payment.get("provider") or payment.get("method"),
                "reference": payment.get("gateway_ref") or payment.get("provider_transaction_ref"),
                "on_time": on_time,
                "occurred_at": occurred_at,
            }
        )

    contributions = _member_contributions(db, workspace_id=workspace_id, member_name=member_name, member_email=member_email)
    confirmed_contributions = [item for item in contributions if str(item.get("status") or "").strip().lower() in confirmed_statuses]
    contribution_ids = {int(item.id) for item in contributions[:20]}
    contribution_record = [_contribution_record_out(db, contribution) for contribution in contributions[:8]]

    verified_proofs = _member_verified_proofs(
        db,
        workspace_id=workspace_id,
        member_name=member_name,
        due_payment_ids=due_payment_ids,
        contribution_ids=contribution_ids,
    )
    verified_proof_count = sum(
        1
        for proof in verified_proofs
        if str(proof.get("verification_state") or "").strip().lower() == "matched"
        or str(proof.get("provider_verification_status") or "").strip().lower() == "verified"
    )

    dues_ratio = (len(confirmed_dues) / len(dues_payments)) if dues_payments else (1.0 if str(member.get("dues_status") or "").lower() == "paid" else 0.0)
    timing_ratio = (on_time_due_count / dated_due_count) if dated_due_count else dues_ratio
    proof_ratio = min(1.0, verified_proof_count / max(len(confirmed_dues) + len(confirmed_contributions), 1)) if (confirmed_dues or confirmed_contributions) else 0.0
    contribution_ratio = min(1.0, len(confirmed_contributions) / 3.0)
    recent_activity_ratio = _recent_member_activity_ratio(confirmed_dues, confirmed_contributions)

    discipline_score = ((dues_ratio * 0.7) + (timing_ratio * 0.3)) * 10.0
    proof_score = proof_ratio * 10.0
    contribution_score = contribution_ratio * 10.0
    momentum_score = recent_activity_ratio * 10.0
    overall_score = round((discipline_score * 0.5) + (proof_score * 0.25) + (contribution_score * 0.15) + (momentum_score * 0.10), 2)

    categories = [
        _category(
            "payment_discipline",
            "Payment discipline",
            discipline_score,
            _member_payment_summary(len(confirmed_dues), len(dues_payments), on_time_due_count, dated_due_count),
        ),
        _category(
            "proof_trail",
            "Proof trail",
            proof_score,
            _member_proof_summary(verified_proof_count, len(verified_proofs)),
        ),
        _category(
            "contribution_record",
            "Contribution record",
            contribution_score,
            _member_contribution_summary(len(confirmed_contributions), len(contributions)),
        ),
        _category(
            "recent_activity",
            "Recent activity",
            momentum_score,
            _member_recent_activity_summary(confirmed_dues, confirmed_contributions),
        ),
    ]

    return {
        "member_id": int(member.id),
        "member_name": member_name,
        "role": role_name,
        "dues_status": str(member.get("dues_status") or "defaulter"),
        "overall_score": overall_score,
        "overall_grade": _grade(overall_score),
        "summary": _member_profile_summary(
            member_name=member_name,
            score=overall_score,
            confirmed_dues=len(confirmed_dues),
            total_dues=len(dues_payments),
            verified_proof_count=verified_proof_count,
            confirmed_contributions=len(confirmed_contributions),
        ),
        "consistency_summary": _member_consistency_summary(
            confirmed_dues=len(confirmed_dues),
            total_dues=len(dues_payments),
            on_time_due_count=on_time_due_count,
            dated_due_count=dated_due_count,
            verified_proof_count=verified_proof_count,
            confirmed_contributions=len(confirmed_contributions),
        ),
        "categories": categories,
        "key_metrics": [
            {"key": "dues_paid", "label": "Dues confirmed", "value": f"{len(confirmed_dues)}/{len(dues_payments)}", "trend": _trend_label(discipline_score)},
            {"key": "proofs", "label": "Verified proofs", "value": str(verified_proof_count), "trend": _trend_label(proof_score)},
            {"key": "contributions", "label": "Confirmed contributions", "value": str(len(confirmed_contributions)), "trend": _trend_label(contribution_score)},
            {"key": "current_status", "label": "Current dues status", "value": str(member.get("dues_status") or "defaulter").title(), "trend": _trend_label(discipline_score)},
        ],
        "payment_history": payment_history,
        "verified_proofs": [
            {
                "id": int(record.id),
                "kind": str(record.get("kind") or "payment_receipt"),
                "amount": float(record.get("amount")) if record.get("amount") not in (None, "") else None,
                "reference": record.get("reference"),
                "payment_for": record.get("payment_for"),
                "verification_state": record.get("verification_state"),
                "linked_record_label": record.get("linked_record_label"),
                "provider_note": record.get("provider_verification_note"),
                "occurred_at": record.get("created_at") or datetime.utcnow(),
            }
            for record in verified_proofs[:8]
        ],
        "contribution_record": contribution_record,
        "created_at": datetime.utcnow(),
    }


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


def _receipt_summary(community_receipts: int) -> str:
    return f"{community_receipts} receipt or contribution-proof signals have been captured from community channels so far."


def _build_evidence_trail(db: MongoStore, *, workspace_id: int, limit: int = 8) -> list[dict]:
    evidence: list[dict] = []

    for record in db.find_many("community_financial_records", {"workspace_id": workspace_id}, sort=[("created_at", -1)], limit=limit):
        amount = record.get("amount")
        amount_label = ""
        if amount not in (None, ""):
            try:
                amount_label = f"NGN {float(amount):,.0f}"
            except (TypeError, ValueError):
                amount_label = str(amount)
        payment_for = str(record.get("payment_for") or "").strip()
        detail_parts = [part for part in [amount_label, payment_for or None] if part]
        evidence.append(
            {
                "evidence_type": "community_receipt",
                "title": "Community receipt signal",
                "detail": " · ".join(detail_parts) or "Receipt or contribution proof captured from community channels.",
                "linked_record_label": record.get("linked_record_label"),
                "verification_state": record.get("verification_state"),
                "created_at": record.get("created_at") or datetime.utcnow(),
            }
        )

    for payment in db.find_many("dues_payments", {"workspace_id": workspace_id, "status": {"$in": ["confirmed", "success", "paid"]}}, sort=[("created_at", -1)], limit=3):
        evidence.append(
            {
                "evidence_type": "dues_payment",
                "title": "Verified dues payment",
                "detail": f"NGN {float(payment.get('amount') or 0):,.0f} confirmed in platform records.",
                "linked_record_label": "Dues payment",
                "verification_state": "matched",
                "created_at": payment.get("created_at") or datetime.utcnow(),
            }
        )

    for contribution in db.find_many("contributions", {"workspace_id": workspace_id, "status": {"$in": ["confirmed", "success", "paid"]}}, sort=[("created_at", -1)], limit=3):
        evidence.append(
            {
                "evidence_type": "campaign_contribution",
                "title": "Verified contribution",
                "detail": f"NGN {float(contribution.get('amount') or 0):,.0f} confirmed toward campaign inflows.",
                "linked_record_label": "Contribution",
                "verification_state": "matched",
                "created_at": contribution.get("created_at") or datetime.utcnow(),
            }
        )

    return sorted(evidence, key=lambda item: item.get("created_at") or datetime.utcnow(), reverse=True)[:limit]


def _count_status(records: list, good_statuses: set[str]) -> int:
    return sum(1 for item in records if str(item.get("status") or "").strip().lower() in good_statuses)


def _member_contributions(db: MongoStore, *, workspace_id: int, member_name: str, member_email: str) -> list:
    contributions = db.find_many("contributions", {"workspace_id": workspace_id}, sort=[("created_at", -1)], limit=80)
    name_tokens = _name_tokens(member_name)
    matched: list = []
    for contribution in contributions:
        contributor_email = str(contribution.get("contributor_email") or "").strip().lower()
        contributor_name = str(contribution.get("contributor_name") or "").strip().lower()
        email_match = bool(member_email and contributor_email and contributor_email == member_email)
        name_match = bool(name_tokens and all(token in contributor_name for token in name_tokens[:2]))
        if email_match or name_match:
            matched.append(contribution)
    return matched


def _member_verified_proofs(
    db: MongoStore,
    *,
    workspace_id: int,
    member_name: str,
    due_payment_ids: set[int],
    contribution_ids: set[int],
) -> list:
    name_tokens = _name_tokens(member_name)
    proofs: list = []
    for record in db.find_many("community_financial_records", {"workspace_id": workspace_id}, sort=[("created_at", -1)], limit=80):
        linked_type = str(record.get("linked_record_type") or "")
        linked_id = record.get("linked_record_id")
        payer = str(record.get("payer") or "").strip().lower()
        linked_match = (
            linked_type == "dues_payment" and linked_id in due_payment_ids
        ) or (
            linked_type == "contribution" and linked_id in contribution_ids
        )
        name_match = bool(payer and name_tokens and all(token in payer for token in name_tokens[:2]))
        if linked_match or name_match:
            proofs.append(record)
    return proofs


def _contribution_record_out(db: MongoStore, contribution) -> dict:
    campaign = db.find_by_id("campaigns", contribution.get("campaign_id"))
    stream = db.find_by_id("funding_streams", contribution.get("stream_id"))
    return {
        "id": int(contribution.id),
        "campaign_name": campaign.get("name") if campaign else None,
        "stream_name": stream.get("name") if stream else None,
        "amount": float(contribution.get("amount") or 0),
        "status": str(contribution.get("status") or ""),
        "verification_status": contribution.get("verification_status"),
        "reference": contribution.get("gateway_ref") or contribution.get("provider_transaction_ref"),
        "occurred_at": contribution.get("confirmed_at") or contribution.get("created_at") or datetime.utcnow(),
    }


def _recent_member_activity_ratio(confirmed_dues: list, confirmed_contributions: list) -> float:
    ninety_days_ago = datetime.utcnow() - timedelta(days=90)
    recent_items = [
        item
        for item in [*confirmed_dues, *confirmed_contributions]
        if (item.get("confirmed_at") or item.get("created_at") or datetime.utcnow()) >= ninety_days_ago
    ]
    return min(1.0, len(recent_items) / 3.0)


def _member_profile_summary(*, member_name: str, score: float, confirmed_dues: int, total_dues: int, verified_proof_count: int, confirmed_contributions: int) -> str:
    if score >= 8:
        return f"{member_name} has a strong individual operating record in Quorum, with consistent payments and a reliable proof trail."
    if score >= 6:
        return f"{member_name} has a usable financial record, but more consistent verified payments would strengthen the profile."
    if total_dues == 0 and confirmed_contributions == 0:
        return f"{member_name} does not have enough payment history in Quorum yet to establish a strong financial profile."
    return f"{member_name}'s profile is still developing. {confirmed_dues} of {total_dues or 0} dues payments and {verified_proof_count} verified proofs are currently on record."


def _member_consistency_summary(*, confirmed_dues: int, total_dues: int, on_time_due_count: int, dated_due_count: int, verified_proof_count: int, confirmed_contributions: int) -> str:
    dues_line = (
        f"{confirmed_dues} of {total_dues} dues payments are confirmed."
        if total_dues
        else "No dues payment history has been recorded yet."
    )
    timing_line = (
        f" {on_time_due_count} of {dated_due_count} deadline-based payments landed on time."
        if dated_due_count
        else ""
    )
    proof_line = f" {verified_proof_count} verified receipt or transfer proofs are linked to this member."
    contribution_line = f" {confirmed_contributions} confirmed contributions have been recorded."
    return f"{dues_line}{timing_line}{proof_line}{contribution_line}".strip()


def _member_payment_summary(confirmed_dues: int, total_dues: int, on_time_due_count: int, dated_due_count: int) -> str:
    if not total_dues:
        return "No dues payments have been recorded for this member yet."
    summary = f"{confirmed_dues} of {total_dues} dues payments are confirmed."
    if dated_due_count:
        summary += f" {on_time_due_count} landed on or before their deadlines."
    return summary


def _member_proof_summary(verified_proof_count: int, total_proofs: int) -> str:
    if not total_proofs:
        return "No receipt or transfer proofs have been linked to this member yet."
    return f"{verified_proof_count} of {total_proofs} captured proofs are already verified or matched."


def _member_contribution_summary(confirmed_contributions: int, total_contributions: int) -> str:
    if not total_contributions:
        return "No contribution activity has been tied back to this member yet."
    return f"{confirmed_contributions} of {total_contributions} contribution records are confirmed."


def _member_recent_activity_summary(confirmed_dues: list, confirmed_contributions: list) -> str:
    recent_ratio = _recent_member_activity_ratio(confirmed_dues, confirmed_contributions)
    if recent_ratio >= 0.66:
        return "This member has recent verified activity in the last 90 days."
    if recent_ratio > 0:
        return "This member has some recent verified activity, but it is still light."
    return "There is no recent verified activity in the last 90 days yet."


def _parse_dateish(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    normalized = str(value).strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _name_tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]{3,}", str(value or "").lower()) if token]
