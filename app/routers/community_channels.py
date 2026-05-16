from __future__ import annotations

import os
import secrets
from datetime import datetime
import re

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from .. import schemas
from ..database import DESC, MongoStore, get_db
from ..payments import PaymentInitializationError, squad_configured, verify_squad_transaction
from ..rbac import require_workspace_permission
from ..services.community_intelligence import CommunityIntelligenceError, analyze_message
from ..services.notifications import create_notification, notify_task_assignee, notify_workspace_admins
from ..services.opportunities import refresh_opportunity_matches
from ..services.tasks import suggest_task_assignee
from ..services.telegram import (
    TelegramServiceError,
    telegram_list_groups,
    telegram_session_complete,
    telegram_session_start,
    telegram_sync_group_messages,
)


router = APIRouter(prefix="/workspaces/{workspace_id}/community-channels", tags=["community-channels"])
inbound_router = APIRouter(prefix="/community-channels", tags=["community-channels"])


def _telegram_backend_missing_fields() -> list[str]:
    missing: list[str] = []
    if not os.getenv("TELEGRAM_API_ID"):
        missing.append("TELEGRAM_API_ID")
    if not os.getenv("TELEGRAM_API_HASH"):
        missing.append("TELEGRAM_API_HASH")
    return missing


def _telegram_backend_credentials() -> tuple[int, str]:
    missing = _telegram_backend_missing_fields()
    if missing:
        raise TelegramServiceError(
            "Telegram sign-in is blocked until the backend owner configures: " + ", ".join(missing)
        )
    return int(os.getenv("TELEGRAM_API_ID") or "0"), str(os.getenv("TELEGRAM_API_HASH") or "")


def _whatsapp_gateway_base_url() -> str:
    return str(os.getenv("WHATSAPP_GATEWAY_INTERNAL_URL") or "http://127.0.0.1:3001").rstrip("/")


def _whatsapp_gateway_headers() -> dict[str, str]:
    token = str(os.getenv("WHATSAPP_GATEWAY_TOKEN") or "").strip()
    return {"x-internal-token": token} if token else {}


async def _whatsapp_gateway_request(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{_whatsapp_gateway_base_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, json=payload, headers=_whatsapp_gateway_headers())
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        raise HTTPException(status_code=503, detail=f"WhatsApp gateway request failed: {detail}")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"WhatsApp gateway unavailable: {str(exc)}")


def _clear_whatsapp_session_fields(channel, *, status: str, last_error: str | None = None) -> None:
    channel["status"] = status
    channel["display_name"] = None
    channel["phone_number"] = None
    channel["whatsapp_jid"] = None
    channel["qr_code_data_url"] = None
    channel["qr_updated_at"] = None
    channel["connected_at"] = None if status in {"configured", "disconnected"} else channel.get("connected_at")
    channel["updated_at"] = datetime.utcnow()
    channel["last_error"] = last_error


def _apply_whatsapp_gateway_status(channel, payload: dict) -> None:
    channel["status"] = str(payload.get("state") or channel.get("status") or "configured")
    channel["display_name"] = str(payload.get("displayName") or channel.get("display_name") or "").strip() or None
    channel["phone_number"] = str(payload.get("phoneNumber") or channel.get("phone_number") or "").strip() or None
    channel["whatsapp_jid"] = str(payload.get("jid") or channel.get("whatsapp_jid") or "").strip() or None
    channel["pairing_mode"] = "qr"
    channel["qr_code_data_url"] = str(payload.get("qrCodeDataUrl") or "").strip() or None
    channel["last_error"] = str(payload.get("lastError") or "").strip() or None

    for source_key, target_key in {
        "connectedAt": "connected_at",
        "updatedAt": "updated_at",
        "qrUpdatedAt": "qr_updated_at",
    }.items():
        raw_value = str(payload.get(source_key) or "").strip()
        if not raw_value:
            continue
        try:
            channel[target_key] = datetime.fromisoformat(raw_value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue


def _upsert_whatsapp_groups(db: MongoStore, *, channel, groups: list[schemas.WhatsAppDiscoveredGroupIn]) -> int:
    seen_at = datetime.utcnow()
    for item in groups:
        _discover_or_update_group(
            db,
            workspace_id=channel.workspace_id,
            channel_id=channel.id,
            provider="whatsapp",
            external_group_id=item.external_group_id,
            group_name=item.group_name,
            seen_at=seen_at,
        )
    _refresh_channel_counts(db, channel)
    return int(channel.get("discovered_group_count") or 0)


def _channel_out(channel) -> schemas.CommunityChannelOut:
    metadata = {
        "webhook_url": channel.get("webhook_url"),
        "telegram_username": channel.get("telegram_username"),
        "telegram_user_id": channel.get("telegram_user_id"),
        "phone_number": channel.get("phone_number"),
        "group_type": channel.get("group_type"),
        "display_name": channel.get("display_name"),
        "selected_group_count": channel.get("selected_group_count", 0),
        "discovered_group_count": channel.get("discovered_group_count", 0),
        "last_error": channel.get("last_error"),
        "webhook_secret": channel.get("webhook_secret"),
        "whatsapp_jid": channel.get("whatsapp_jid"),
        "pairing_mode": channel.get("pairing_mode"),
        "qr_code_data_url": channel.get("qr_code_data_url"),
        "qr_updated_at": channel.get("qr_updated_at").isoformat() if channel.get("qr_updated_at") else None,
    }
    return schemas.CommunityChannelOut(
        id=channel.id,
        workspace_id=channel.workspace_id,
        provider=channel.provider,
        label=channel.label,
        status=channel.status,
        connected_at=channel.get("connected_at"),
        metadata={key: value for key, value in metadata.items() if value not in (None, "")},
        created_at=channel.created_at,
    )


def _group_out(link) -> schemas.ChannelGroupLinkOut:
    return schemas.ChannelGroupLinkOut(
        id=link.id,
        workspace_id=link.workspace_id,
        channel_id=link.channel_id,
        provider=link.provider,
        external_group_id=link.external_group_id,
        group_name=link.group_name,
        sync_enabled=bool(link.get("sync_enabled")),
        last_seen_at=link.get("last_seen_at"),
        last_message_at=link.get("last_message_at"),
        message_count=int(link.get("message_count") or 0),
        created_at=link.created_at,
    )


def _discover_or_update_group(
    db: MongoStore,
    *,
    workspace_id: int,
    channel_id: int,
    provider: str,
    external_group_id: str,
    group_name: str,
    seen_at: datetime,
):
    group = db.find_one(
        "channel_group_links",
        {"workspace_id": workspace_id, "channel_id": channel_id, "external_group_id": external_group_id},
    )
    if group:
        group["group_name"] = group_name or group.get("group_name") or external_group_id
        group["last_seen_at"] = seen_at
        db.save("channel_group_links", group)
        return group

    return db.insert(
        "channel_group_links",
        {
            "workspace_id": workspace_id,
            "channel_id": channel_id,
            "provider": provider,
            "external_group_id": external_group_id,
            "group_name": group_name or external_group_id,
            "sync_enabled": False,
            "last_seen_at": seen_at,
            "last_message_at": None,
            "message_count": 0,
        },
    )


def _persist_channel_message(
    db: MongoStore,
    *,
    workspace_id: int,
    channel_id: int,
    group_link,
    provider: str,
    external_message_id: str | None,
    sender_name: str | None,
    sender_handle: str | None,
    message_type: str,
    text: str,
    raw_payload: dict,
    received_at: datetime,
):
    message_key = f"{group_link.external_group_id}:{external_message_id}" if external_message_id else None
    if message_key and db.find_one("channel_messages", {"workspace_id": workspace_id, "external_message_id": message_key}):
        return None

    message = db.insert(
        "channel_messages",
        {
            "workspace_id": workspace_id,
            "channel_id": channel_id,
            "group_link_id": group_link.id,
            "provider": provider,
            "external_group_id": group_link.external_group_id,
            "external_message_id": message_key,
            "sender_name": sender_name,
            "sender_handle": sender_handle,
            "message_type": message_type,
            "text": text,
            "raw_payload": raw_payload,
            "received_at": received_at,
        },
    )
    group_link["last_message_at"] = received_at
    group_link["last_seen_at"] = received_at
    group_link["message_count"] = int(group_link.get("message_count") or 0) + 1
    db.save("channel_group_links", group_link)
    return message


def _analyze_and_store_artifact(db: MongoStore, *, message, group_name: str | None = None):
    existing = db.find_one("message_artifacts", {"workspace_id": message.workspace_id, "message_id": message.id})
    if existing:
        return existing
    workspace = db.find_by_id("workspaces", message.workspace_id)

    recent_context_messages = [
        str(item.get("text") or "").strip()
        for item in db.find_many(
            "channel_messages",
            {
                "workspace_id": message.workspace_id,
                "channel_id": message.channel_id,
                "external_group_id": message.external_group_id,
            },
            sort=[("received_at", DESC)],
            limit=6,
        )
        if item.id != message.id and str(item.get("text") or "").strip()
    ][:5]

    sync_source = str((message.get("raw_payload") or {}).get("sync_source") or "live").strip().lower()
    try:
        artifact = analyze_message(
            text=message.text,
            provider=message.provider,
            group_name=group_name,
            workspace_type=workspace.get("workspace_type") if workspace else None,
            community_profile=workspace.get("community_profile") if workspace else None,
            message_type=message.message_type,
            attachment_name=str((message.get("raw_payload") or {}).get("attachment_name") or "").strip() or None,
            attachment_mime_type=str((message.get("raw_payload") or {}).get("attachment_mime_type") or "").strip() or None,
            attachment_base64=str((message.get("raw_payload") or {}).get("attachment_base64") or "").strip() or None,
            recent_messages=list(reversed(recent_context_messages)),
            prefer_lightweight=sync_source == "history",
        )
    except CommunityIntelligenceError as exc:
        return db.insert(
            "message_artifacts",
            {
                "workspace_id": message.workspace_id,
                "message_id": message.id,
                "artifact_type": "other",
                "confidence": 0.0,
                "summary": f"Analysis failed: {str(exc)[:180]}",
                "extracted_payload": {},
                "status": "analysis_failed",
                "reviewed_at": None,
                "reviewed_by_user_id": None,
                "review_note": None,
            },
        )

    raw_payload = message.get("raw_payload") or {}
    has_media_context = bool(raw_payload.get("attachment_mime_type") or raw_payload.get("attachment_name") or raw_payload.get("attachment_base64"))
    if artifact.artifact_type == "other" and message.message_type in {"image", "document"} and has_media_context:
        artifact = schemas.CommunityArtifact(
            artifact_type="other",
            confidence=max(float(artifact.confidence or 0), 0.22),
            summary="media needs review",
            extracted_payload={
                **(artifact.extracted_payload or {}),
                "attachment_text_excerpt": (artifact.extracted_payload or {}).get("attachment_text_excerpt"),
                "attachment_skipped_reason": raw_payload.get("attachment_skipped_reason"),
            },
        )

    status = _artifact_initial_status(artifact.artifact_type, artifact.confidence)
    if artifact.artifact_type == "other" and message.message_type in {"image", "document"} and has_media_context:
        status = "needs_review"
    stored = db.insert(
        "message_artifacts",
        {
            "workspace_id": message.workspace_id,
            "message_id": message.id,
            "artifact_type": artifact.artifact_type,
            "confidence": artifact.confidence,
            "summary": artifact.summary,
            "extracted_payload": artifact.extracted_payload,
            "status": status,
            "reviewed_at": None,
            "reviewed_by_user_id": None,
            "review_note": None,
        },
    )
    if status == "ready":
        _apply_artifact_outcome(db, artifact=stored, message=message)
    _notify_for_high_value_artifact(db, artifact=stored, message=message, group_name=group_name)
    return stored


def _artifact_initial_status(artifact_type: str, confidence: float) -> str:
    normalized_type = str(artifact_type or "other").strip().lower()
    if normalized_type == "other":
        return "ignored"
    if confidence >= 0.75:
        return "ready"
    return "needs_review"


def _clean_source_excerpt(text: str, *, limit: int = 240) -> str:
    cleaned = re.sub(r"[*_~`]+", "", str(text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= limit:
        return cleaned
    shortened = cleaned[:limit].rsplit(" ", 1)[0].strip()
    return f"{shortened}..." if shortened else f"{cleaned[:limit]}..."


def _apply_artifact_outcome(db: MongoStore, *, artifact, message):
    if artifact.artifact_type in {"payment_receipt", "contribution_signal"}:
        _store_financial_record_from_artifact(db, artifact=artifact, message=message)
        return None
    if artifact.artifact_type == "task_signal":
        return _create_or_update_task_from_artifact(db, artifact=artifact, message=message)
    if artifact.artifact_type != "opportunity":
        return None
    existing = db.find_one("opportunities", {"workspace_id": message.workspace_id, "message_id": message.id})
    if existing:
        refresh_opportunity_matches(db, opportunity=existing)
        return existing

    payload = artifact.get("extracted_payload") or {}
    created = db.insert(
        "opportunities",
        {
            "workspace_id": message.workspace_id,
            "message_id": message.id,
            "source": message.provider,
            "title": str(payload.get("title") or artifact.get("summary") or message.text[:120]),
            "description": str(payload.get("summary") or artifact.get("summary") or _clean_source_excerpt(message.text, limit=220)),
            "summary": str(payload.get("summary") or "").strip() or None,
            "organization": payload.get("organization"),
            "location": payload.get("location"),
            "venue": payload.get("venue"),
            "trade_tags": payload.get("trade_tags") or [],
            "key_points": payload.get("key_points") or [],
            "event_date": payload.get("event_date"),
            "deadline": payload.get("deadline"),
            "contact": payload.get("contact"),
            "action_url": payload.get("action_url"),
            "source_excerpt": _clean_source_excerpt(message.text, limit=420),
            "status": "open",
        },
    )
    refresh_opportunity_matches(db, opportunity=created)
    return created


def _create_or_update_task_from_artifact(
    db: MongoStore,
    *,
    artifact,
    message,
    created_by_user_id: int | None = None,
    override_assignee_member_id: int | None = None,
    override_due_date: str | None = None,
    override_priority: str | None = None,
    note: str | None = None,
):
    existing = db.find_one("tasks", {"workspace_id": message.workspace_id, "linked_module": "community_artifact", "linked_id": artifact.id})
    if existing:
        return existing

    payload = artifact.get("extracted_payload") or {}
    suggestion = suggest_task_assignee(db, workspace_id=message.workspace_id, text=message.text, extracted_payload=payload)
    assigned_to_member_id = override_assignee_member_id if override_assignee_member_id is not None else (suggestion.get("member_id") if suggestion else None)
    task_title = str(payload.get("title") or artifact.get("summary") or _clean_source_excerpt(message.text, limit=120)).strip()[:180]
    task_description_parts = [
        str(payload.get("summary") or "").strip() or None,
        note.strip() if note else None,
        f"Source: {_clean_source_excerpt(message.text, limit=320)}",
    ]
    task = db.insert(
        "tasks",
        {
            "workspace_id": message.workspace_id,
            "title": task_title,
            "description": "\n\n".join(part for part in task_description_parts if part) or None,
            "assigned_to_member_id": assigned_to_member_id,
            "due_date": override_due_date or payload.get("due_hint") or payload.get("deadline") or payload.get("event_date"),
            "priority": str(override_priority or payload.get("priority") or "medium").strip().lower(),
            "status": "todo",
            "linked_module": "community_artifact",
            "linked_id": artifact.id,
            "created_by_user_id": created_by_user_id,
        },
    )
    if assigned_to_member_id:
        notify_task_assignee(
            db,
            workspace_id=message.workspace_id,
            member_id=assigned_to_member_id,
            task=task,
            title="Task assigned from community inbox",
        )
    return task


def _store_financial_record_from_artifact(db: MongoStore, *, artifact, message):
    payload = artifact.get("extracted_payload") or {}
    existing = db.find_one(
        "community_financial_records",
        {"workspace_id": message.workspace_id, "message_id": message.id, "artifact_id": artifact.id},
    )
    if existing:
        return existing

    reference = str(payload.get("reference") or "").strip() or None
    amount_raw = payload.get("amount")
    amount = None
    if amount_raw not in (None, ""):
        try:
            amount = float(str(amount_raw).replace(",", ""))
        except ValueError:
            amount = None
    squad_verification = _verify_squad_receipt_against_squad(reference=reference, expected_amount=amount)
    linked = None
    linked_type = None
    verification_state = "unlinked"
    if reference:
        candidate_refs = [reference]
        provider_reference = str((squad_verification or {}).get("provider_transaction_ref") or "").strip()
        verified_reference = str((squad_verification or {}).get("reference") or "").strip()
        for candidate in [provider_reference, verified_reference]:
            if candidate and candidate not in candidate_refs:
                candidate_refs.append(candidate)
        for candidate_ref in candidate_refs:
            linked = (
                db.find_one("dues_payments", {"workspace_id": message.workspace_id, "gateway_ref": candidate_ref})
                or db.find_one("dues_payments", {"workspace_id": message.workspace_id, "provider_transaction_ref": candidate_ref})
                or db.find_one("contributions", {"workspace_id": message.workspace_id, "gateway_ref": candidate_ref})
                or db.find_one("contributions", {"workspace_id": message.workspace_id, "provider_transaction_ref": candidate_ref})
            )
            if linked:
                break
        if linked:
            linked_type = "dues_payment" if linked.get("cycle_id") else "contribution"
            verification_state = "matched" if (squad_verification or {}).get("status") == "verified" else "needs_review"
    if not linked and amount is not None:
        linked = db.find_one("contributions", {"workspace_id": message.workspace_id, "amount": amount}) or db.find_one(
            "dues_payments", {"workspace_id": message.workspace_id, "amount": amount}
        )
        if linked:
            linked_type = "contribution" if linked.get("campaign_id") is not None or linked.get("donor_name") is not None else "dues_payment"
            verification_state = "needs_review"

    if not linked:
        inferred = _infer_financial_target(db, message=message, payload=payload, amount=amount)
        if inferred:
            linked = inferred["record"]
            linked_type = inferred["record_type"]
            verification_state = "needs_review"

    if squad_verification:
        status = str(squad_verification.get("status") or "").strip().lower()
        if status == "verified":
            verification_state = "matched" if linked and linked_type in {"dues_payment", "contribution"} else "needs_review"
        elif status in {"amount_mismatch", "reference_not_confirmed"}:
            verification_state = "needs_review"
        elif status == "reference_not_found" and verification_state == "unlinked":
            verification_state = "unlinked"

    return db.insert(
        "community_financial_records",
        {
            "workspace_id": message.workspace_id,
            "message_id": message.id,
            "artifact_id": artifact.id,
            "kind": artifact.artifact_type,
            "amount": amount,
            "payer": payload.get("payer") or payload.get("contributor_name"),
            "reference": reference,
            "bank": payload.get("bank"),
            "transaction_date": payload.get("transaction_date"),
            "linked_record_type": linked_type,
            "linked_record_id": linked.id if linked else None,
            "verification_state": verification_state,
            "linked_record_label": _financial_record_label(db, record_type=linked_type, record=linked) if linked else None,
            "provider_name": "squad" if squad_verification else None,
            "provider_verification_status": (squad_verification or {}).get("status"),
            "provider_verification_note": (squad_verification or {}).get("note"),
            "provider_verified_amount": (squad_verification or {}).get("amount"),
            "provider_verified_reference": (squad_verification or {}).get("reference"),
            "provider_transaction_ref": (squad_verification or {}).get("provider_transaction_ref"),
            "attachment_name": (message.get("raw_payload") or {}).get("attachment_name"),
            "attachment_text_excerpt": payload.get("attachment_text_excerpt"),
            "payment_for": payload.get("payment_for") or payload.get("cycle_hint"),
        },
    )


def _verify_squad_receipt_against_squad(*, reference: str | None, expected_amount: float | None) -> dict[str, object] | None:
    normalized_reference = str(reference or "").strip()
    if not normalized_reference or not squad_configured():
        return None
    try:
        verification = verify_squad_transaction(normalized_reference)
    except PaymentInitializationError:
        return {
            "status": "verification_unavailable",
            "note": "Live Squad verification is unavailable right now.",
            "reference": normalized_reference,
        }
    if not verification:
        return {
            "status": "verification_unavailable",
            "note": "Live Squad verification is unavailable right now.",
            "reference": normalized_reference,
        }

    verification_status = str(verification.status or "").strip().lower()
    result: dict[str, object] = {
        "reference": verification.reference or normalized_reference,
        "provider_transaction_ref": verification.provider_transaction_ref,
        "amount": verification.amount,
    }
    if verification_status not in {"success", "successful", "paid", "approved"}:
        return {
            **result,
            "status": "reference_not_confirmed" if verification_status != "unknown" else "reference_not_found",
            "note": f"Squad returned status: {verification_status.replace('_', ' ')}." if verification_status != "unknown" else "Squad could not confirm this reference.",
        }
    if expected_amount is not None and verification.amount is not None and abs(float(verification.amount) - float(expected_amount)) >= 0.01:
        return {
            **result,
            "status": "amount_mismatch",
            "note": f"Squad found this reference, but the verified amount was NGN {float(verification.amount):,.0f}.",
        }
    return {
        **result,
        "status": "verified",
        "note": f"Matched against Squad transaction data for NGN {float(verification.amount or expected_amount or 0):,.0f}.",
    }


def _infer_financial_target(db: MongoStore, *, message, payload: dict, amount: float | None):
    workspace_id = message.workspace_id
    context_text = " ".join(
        [
            str(message.get("text") or ""),
            str(payload.get("payment_for") or ""),
            str(payload.get("attachment_text_excerpt") or ""),
            str(payload.get("raw_excerpt") or ""),
            str(payload.get("cycle_hint") or ""),
        ]
    ).strip()
    lowered = context_text.lower()
    member = _find_member_candidate(db, workspace_id=workspace_id, payload=payload, message=message, lowered=lowered)
    cycle = _find_dues_cycle_candidate(db, workspace_id=workspace_id, lowered=lowered)
    if cycle and member:
        payment = _find_dues_payment_candidate(db, workspace_id=workspace_id, cycle_id=cycle.id, member_id=member.id, amount=amount)
        if payment:
            return {"record": payment, "record_type": "dues_payment", "verification_state": "matched_existing_record"}
        return {"record": cycle, "record_type": "dues_cycle", "verification_state": "matched_due_cycle"}

    contribution = _find_contribution_candidate(db, workspace_id=workspace_id, payload=payload, lowered=lowered, amount=amount)
    if contribution:
        return {"record": contribution, "record_type": "contribution", "verification_state": "matched_existing_record"}

    campaign = _find_campaign_candidate(db, workspace_id=workspace_id, lowered=lowered)
    if campaign:
        return {"record": campaign, "record_type": "campaign", "verification_state": "matched_campaign"}
    return None


def _find_member_candidate(db: MongoStore, *, workspace_id: int, payload: dict, message, lowered: str):
    candidates = [
        str(payload.get("payer") or "").strip(),
        str(payload.get("contributor_name") or "").strip(),
        str(message.get("sender_name") or "").strip(),
    ]
    memberships = db.find_many("workspace_members", {"workspace_id": workspace_id, "status": "active"})
    for membership in memberships:
        user = db.find_by_id("users", membership.user_id)
        if not user:
            continue
        full_name = str(user.get("full_name") or "").strip()
        if not full_name:
            continue
        name_tokens = [token for token in re.findall(r"[a-z0-9]{3,}", full_name.lower()) if token]
        if any(candidate and candidate.lower() in full_name.lower() for candidate in candidates):
            return membership
        if name_tokens and all(token in lowered for token in name_tokens[:2]):
            return membership
    return None


def _find_dues_cycle_candidate(db: MongoStore, *, workspace_id: int, lowered: str):
    cycles = db.find_many("dues_cycles", {"workspace_id": workspace_id})
    best = None
    best_score = 0
    for cycle in cycles:
        cycle_name = str(cycle.get("name") or "").strip().lower()
        if not cycle_name:
            continue
        tokens = [token for token in re.findall(r"[a-z0-9]{3,}", cycle_name) if token]
        score = sum(1 for token in tokens if token in lowered)
        if cycle_name in lowered:
            score += 3
        if score > best_score:
            best = cycle
            best_score = score
    return best if best_score > 0 else None


def _find_dues_payment_candidate(db: MongoStore, *, workspace_id: int, cycle_id: int, member_id: int, amount: float | None):
    payments = db.find_many("dues_payments", {"workspace_id": workspace_id, "cycle_id": cycle_id, "member_id": member_id}, sort=[("created_at", DESC)], limit=8)
    if amount is None:
        return payments[0] if payments else None
    for payment in payments:
        try:
            if abs(float(payment.get("amount") or 0) - amount) < 0.01:
                return payment
        except (TypeError, ValueError):
            continue
    return payments[0] if payments else None


def _find_contribution_candidate(db: MongoStore, *, workspace_id: int, payload: dict, lowered: str, amount: float | None):
    contributions = db.find_many("contributions", {"workspace_id": workspace_id}, sort=[("created_at", DESC)], limit=20)
    best = None
    best_score = -1
    payer = str(payload.get("payer") or payload.get("contributor_name") or "").strip().lower()
    for contribution in contributions:
        score = 0
        contributor_name = str(contribution.get("contributor_name") or "").strip().lower()
        if amount is not None:
            try:
                if abs(float(contribution.get("amount") or 0) - amount) < 0.01:
                    score += 3
            except (TypeError, ValueError):
                pass
        if payer and contributor_name and payer in contributor_name:
            score += 3
        stream = db.find_by_id("funding_streams", contribution.get("stream_id"))
        campaign = db.find_by_id("campaigns", contribution.get("campaign_id"))
        for label in [str(stream.get("name") or "") if stream else "", str(campaign.get("name") or "") if campaign else ""]:
            normalized = label.strip().lower()
            if normalized and normalized in lowered:
                score += 2
        if score > best_score:
            best = contribution
            best_score = score
    return best if best_score > 1 else None


def _find_campaign_candidate(db: MongoStore, *, workspace_id: int, lowered: str):
    campaigns = db.find_many("campaigns", {"workspace_id": workspace_id})
    best = None
    best_score = 0
    for campaign in campaigns:
        name = str(campaign.get("name") or "").strip().lower()
        if not name:
            continue
        score = 3 if name in lowered else sum(1 for token in re.findall(r"[a-z0-9]{3,}", name) if token in lowered)
        if score > best_score:
            best = campaign
            best_score = score
    return best if best_score > 0 else None


def _financial_record_label(db: MongoStore, *, record_type: str | None, record) -> str | None:
    if not record_type or not record:
        return None
    if record_type == "dues_payment":
        cycle = db.find_by_id("dues_cycles", record.get("cycle_id"))
        return f"Dues payment · {cycle.name}" if cycle else "Dues payment"
    if record_type == "dues_cycle":
        return f"Dues cycle · {record.get('name') or 'Untitled'}"
    if record_type == "contribution":
        campaign = db.find_by_id("campaigns", record.get("campaign_id"))
        return f"Contribution · {campaign.name}" if campaign else "Contribution"
    if record_type == "campaign":
        return f"Campaign · {record.get('name') or 'Untitled'}"
    return None


def _notify_for_high_value_artifact(db: MongoStore, *, artifact, message, group_name: str | None = None):
    if artifact.get("status") not in {"ready", "needs_review"}:
        return
    artifact_type = str(artifact.get("artifact_type") or "other")
    payload = artifact.get("extracted_payload") or {}
    amount = None
    raw_amount = payload.get("amount")
    if raw_amount not in (None, ""):
        try:
            amount = float(str(raw_amount).replace(",", ""))
        except ValueError:
            amount = None
    is_high_value = artifact_type in {"disbursement_request", "opportunity"} or (
        artifact_type in {"payment_receipt", "contribution_signal"} and amount is not None and amount >= 25000
    )
    text_lowered = str(message.get("text") or "").lower()
    if artifact_type in {"payment_receipt", "contribution_signal"} and any(keyword in text_lowered for keyword in {"repayment", "loan", "installment", "settlement"}):
        is_high_value = True
    if not is_high_value:
        return
    title_map = {
        "payment_receipt": "High-value receipt captured",
        "contribution_signal": "High-value contribution signal",
        "opportunity": "Priority opportunity extracted",
        "disbursement_request": "Disbursement request extracted",
    }
    body_parts = [group_name or message.get("external_group_id") or "Synced group"]
    if amount is not None:
        body_parts.append(f"NGN {amount:,.0f}")
    body_parts.append(str(message.get("text") or "")[:120])
    notify_workspace_admins(
        db,
        workspace_id=message.workspace_id,
        title=title_map.get(artifact_type, "Important community signal"),
        body=" · ".join(part for part in body_parts if part),
        notification_type="community_signal",
        action_url=f"/{db.find_by_id('workspaces', message.workspace_id).slug}/community-inbox" if db.find_by_id("workspaces", message.workspace_id) else None,
        metadata={"artifact_type": artifact_type, "message_id": message.id, "artifact_id": artifact.id},
        dedupe_key=f"artifact:{artifact.id}",
    )


def _gateway_config_out(channel, selected_groups: list[str]) -> schemas.WhatsAppGatewayConfigOut:
    return schemas.WhatsAppGatewayConfigOut(
        channel_id=channel.id,
        inbound_url=channel.get("webhook_url") or "",
        shared_secret=channel.get("webhook_secret") or "",
        selected_group_ids=selected_groups,
    )


def _message_out(db: MongoStore, message) -> schemas.ChannelMessageOut:
    group = db.find_by_id("channel_group_links", message.get("group_link_id"))
    artifact_count = db.count("message_artifacts", {"workspace_id": message.workspace_id, "message_id": message.id})
    return schemas.ChannelMessageOut(
        id=message.id,
        workspace_id=message.workspace_id,
        channel_id=message.channel_id,
        provider=message.provider,
        external_group_id=message.external_group_id,
        group_name=group.group_name if group else None,
        sender_name=message.get("sender_name"),
        sender_handle=message.get("sender_handle"),
        message_type=message.message_type,
        text=message.text,
        artifact_count=artifact_count,
        received_at=message.received_at,
        created_at=message.created_at,
    )


def _artifact_out(artifact) -> schemas.MessageArtifactOut:
    return schemas.MessageArtifactOut(
        id=artifact.id,
        workspace_id=artifact.workspace_id,
        message_id=artifact.message_id,
        artifact_type=artifact.artifact_type,
        confidence=float(artifact.get("confidence") or 0),
        summary=artifact.get("summary"),
        extracted_payload=artifact.get("extracted_payload") or {},
        status=artifact.get("status") or "ready",
        reviewed_at=artifact.get("reviewed_at"),
        reviewed_by_user_id=artifact.get("reviewed_by_user_id"),
        review_note=artifact.get("review_note"),
        created_at=artifact.created_at,
    )


def _audit_trail_out(db: MongoStore, *, workspace_id: int, limit: int = 12) -> list[schemas.CommunityInboxAuditItemOut]:
    items: list[schemas.CommunityInboxAuditItemOut] = []
    reviewed_artifacts = db.find_many(
        "message_artifacts",
        {"workspace_id": workspace_id, "reviewed_at": {"$ne": None}},
        sort=[("reviewed_at", DESC)],
        limit=limit,
    )
    for artifact in reviewed_artifacts:
        actor = db.find_one("users", {"id": artifact.get("reviewed_by_user_id")}) if artifact.get("reviewed_by_user_id") else None
        items.append(
            schemas.CommunityInboxAuditItemOut(
                item_type="artifact_review",
                title=f"{str(artifact.get('status') or 'reviewed').replace('_', ' ').title()} {str(artifact.get('artifact_type') or 'signal').replace('_', ' ')}",
                detail=artifact.get("review_note") or artifact.get("summary") or "Community signal reviewed.",
                actor_name=actor.full_name if actor else None,
                created_at=artifact.get("reviewed_at") or artifact.created_at,
            )
        )

    created_tasks = db.find_many(
        "tasks",
        {"workspace_id": workspace_id, "linked_module": "community_artifact"},
        sort=[("created_at", DESC)],
        limit=limit,
    )
    for task in created_tasks:
        creator = db.find_one("users", {"id": task.get("created_by_user_id")}) if task.get("created_by_user_id") else None
        assignee_name = None
        if task.get("assigned_to_member_id"):
            assignee_member = db.find_by_id("workspace_members", task.get("assigned_to_member_id"))
            assignee_user = db.find_by_id("users", assignee_member.user_id) if assignee_member else None
            assignee_name = assignee_user.full_name if assignee_user else None
        detail = f"Task created from community signal: {task.get('title') or 'Untitled task'}"
        if assignee_name:
            detail = f"{detail} · Assigned to {assignee_name}"
        items.append(
            schemas.CommunityInboxAuditItemOut(
                item_type="task_creation",
                title="Task created from inbox",
                detail=detail,
                actor_name=creator.full_name if creator else None,
                created_at=task.created_at,
            )
        )

    return sorted(items, key=lambda item: item.created_at, reverse=True)[:limit]


def _task_out(db: MongoStore, task) -> schemas.TaskOut:
    member = db.find_by_id("workspace_members", task.get("assigned_to_member_id"))
    user = db.find_by_id("users", member.user_id) if member else None
    return schemas.TaskOut(
        id=task.id,
        workspace_id=task.workspace_id,
        title=task.title,
        description=task.get("description"),
        assigned_to_member_id=task.get("assigned_to_member_id"),
        assigned_to_name=user.full_name if user else None,
        due_date=task.get("due_date"),
        priority=task.get("priority", "medium"),
        status=task.get("status", "todo"),
        linked_module=task.get("linked_module"),
        linked_id=task.get("linked_id"),
        created_by_user_id=task.get("created_by_user_id"),
        created_at=task.created_at,
    )


def _highlight_out(db: MongoStore, message, artifact, *, group_name: str | None = None) -> schemas.CommunityHighlightOut:
    financial_record = db.find_one(
        "community_financial_records",
        {"workspace_id": message.workspace_id, "message_id": message.id, "artifact_id": artifact.id},
    )
    linked_task = db.find_one(
        "tasks",
        {"workspace_id": message.workspace_id, "linked_module": "community_artifact", "linked_id": artifact.id},
    )
    suggested_assignee = suggest_task_assignee(
        db,
        workspace_id=message.workspace_id,
        text=message.text,
        extracted_payload=artifact.get("extracted_payload") or {},
    ) if artifact.artifact_type == "task_signal" and not linked_task else None
    return schemas.CommunityHighlightOut(
        message_id=message.id,
        workspace_id=message.workspace_id,
        channel_id=message.channel_id,
        provider=message.provider,
        external_group_id=message.external_group_id,
        group_name=group_name,
        sender_name=message.get("sender_name"),
        sender_handle=message.get("sender_handle"),
        message_type=message.message_type,
        text=message.text,
        received_at=message.received_at,
        artifact_id=artifact.id,
        artifact_type=artifact.artifact_type,
        confidence=float(artifact.get("confidence") or 0),
        summary=artifact.get("summary"),
        extracted_payload=artifact.get("extracted_payload") or {},
        status=artifact.get("status") or "ready",
        reviewed_at=artifact.get("reviewed_at"),
        reviewed_by_user_id=artifact.get("reviewed_by_user_id"),
        review_note=artifact.get("review_note"),
        linked_record_type=financial_record.get("linked_record_type") if financial_record else None,
        linked_record_label=financial_record.get("linked_record_label") if financial_record else None,
        verification_state=financial_record.get("verification_state") if financial_record else None,
        provider_verification_status=financial_record.get("provider_verification_status") if financial_record else None,
        provider_verification_note=financial_record.get("provider_verification_note") if financial_record else None,
        provider_verified_amount=float(financial_record.get("provider_verified_amount") or 0) if financial_record and financial_record.get("provider_verified_amount") is not None else None,
        linked_task_id=linked_task.id if linked_task else None,
        linked_task_title=linked_task.get("title") if linked_task else None,
        suggested_assignee_member_id=suggested_assignee.get("member_id") if suggested_assignee else None,
        suggested_assignee_name=suggested_assignee.get("member_name") if suggested_assignee else None,
        created_at=artifact.created_at,
    )


def _should_include_highlight(artifact) -> bool:
    if artifact.status in {"ignored", "rejected"}:
        return False
    if artifact.status in {"needs_review", "analysis_failed"}:
        return True
    return artifact.artifact_type != "other"


def _refresh_channel_counts(db: MongoStore, channel):
    discovered = db.count("channel_group_links", {"workspace_id": channel.workspace_id, "channel_id": channel.id})
    selected = db.count(
        "channel_group_links",
        {"workspace_id": channel.workspace_id, "channel_id": channel.id, "sync_enabled": True},
    )
    channel["discovered_group_count"] = discovered
    channel["selected_group_count"] = selected
    channel["updated_at"] = datetime.utcnow()
    db.save("community_channels", channel)


async def _discover_telegram_groups(db: MongoStore, channel) -> int:
    api_id, api_hash = _telegram_backend_credentials()
    groups = await telegram_list_groups(
        api_id=api_id,
        api_hash=api_hash,
        session_string=str(channel.get("telegram_session_string") or ""),
    )
    for group in groups:
        seen_at = datetime.utcnow()
        link = _discover_or_update_group(
            db,
            workspace_id=channel.workspace_id,
            channel_id=channel.id,
            provider="telegram",
            external_group_id=group.external_group_id,
            group_name=group.group_name,
            seen_at=seen_at,
        )
        link["username"] = group.username
        link["group_type"] = group.group_type
        db.save("channel_group_links", link)
    _refresh_channel_counts(db, channel)
    return len(groups)


async def _refresh_whatsapp_channel_status(db: MongoStore, channel):
    try:
        payload = await _whatsapp_gateway_request("GET", f"/internal/sessions/{channel.id}")
    except HTTPException as exc:
        detail = str(exc.detail or "")
        if exc.status_code == 503 and "session_not_found" in detail:
            _clear_whatsapp_session_fields(channel, status="disconnected", last_error="WhatsApp session not active. Reconnect to resume live sync.")
            db.save("community_channels", channel)
        return channel
    _apply_whatsapp_gateway_status(channel, payload)
    db.save("community_channels", channel)
    return channel


@router.get("", response_model=list[schemas.CommunityChannelOut])
async def list_community_channels(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channels = db.find_many("community_channels", {"workspace_id": workspace_id}, sort=[("created_at", DESC)])
    for channel in channels:
        _refresh_channel_counts(db, channel)
        if channel.provider == "whatsapp":
            await _refresh_whatsapp_channel_status(db, channel)
    refreshed = db.find_many("community_channels", {"workspace_id": workspace_id}, sort=[("created_at", DESC)])
    return [_channel_out(channel) for channel in refreshed]


@router.get("/telegram/setup-status", response_model=schemas.TelegramSetupStatusOut)
def telegram_setup_status(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    if not db.find_by_id("workspaces", workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    missing = _telegram_backend_missing_fields()
    ready = not missing
    return schemas.TelegramSetupStatusOut(
        ready=ready,
        missing_fields=missing,
        message=(
            "Telegram account sign-in is ready. Users only need their phone number, login code, and optional 2FA password."
            if ready
            else "Telegram account sign-in is blocked until the backend owner configures the Telegram app credentials."
        ),
        instructions_url="https://my.telegram.org/apps" if missing else None,
    )


@router.post("/telegram", response_model=schemas.CommunityChannelOut, status_code=201)
def connect_telegram_channel(
    workspace_id: int,
    payload: schemas.TelegramChannelConnectRequest,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    if not db.find_by_id("workspaces", workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        _telegram_backend_credentials()
    except TelegramServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = db.find_one(
        "community_channels",
        {"workspace_id": workspace_id, "provider": "telegram", "label": payload.label.strip()},
    )
    channel_id = existing.id if existing else db.next_id("community_channels")
    record = {
        "id": channel_id,
        "workspace_id": workspace_id,
        "provider": "telegram",
        "label": payload.label.strip(),
        "status": "configured",
        "phone_number": payload.phone_number,
        "temp_session": None,
        "phone_code_hash": None,
        "telegram_session_string": existing.get("telegram_session_string") if existing else None,
        "telegram_user_id": existing.get("telegram_user_id") if existing else None,
        "telegram_username": existing.get("telegram_username") if existing else None,
        "display_name": existing.get("display_name") if existing else None,
        "webhook_url": None,
        "webhook_secret": existing.get("webhook_secret") if existing else secrets.token_urlsafe(24),
        "connected_at": existing.get("connected_at") if existing else None,
        "updated_at": datetime.utcnow(),
        "selected_group_count": existing.get("selected_group_count", 0) if existing else 0,
        "discovered_group_count": existing.get("discovered_group_count", 0) if existing else 0,
        "last_error": None,
    }
    if existing:
        existing.update(record)
        channel = db.save("community_channels", existing)
    else:
        channel = db.insert("community_channels", record)
    return _channel_out(channel)


@router.post("/{channel_id}/telegram/session/start", response_model=schemas.AuthStatusResponse)
async def start_telegram_channel_session(
    workspace_id: int,
    channel_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id, "provider": "telegram"})
    if not channel:
        raise HTTPException(status_code=404, detail="Telegram channel not found")
    try:
        api_id, api_hash = _telegram_backend_credentials()
    except TelegramServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = await telegram_session_start(
            api_id=api_id,
            api_hash=api_hash,
            phone_number=str(channel.get("phone_number") or ""),
        )
    except TelegramServiceError as exc:
        channel["status"] = "error"
        channel["last_error"] = str(exc)
        db.save("community_channels", channel)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    channel["temp_session"] = result.temp_session
    channel["phone_code_hash"] = result.phone_code_hash
    channel["status"] = "code_sent"
    channel["last_error"] = None
    channel["updated_at"] = datetime.utcnow()
    db.save("community_channels", channel)
    return schemas.AuthStatusResponse(message="Telegram login code sent. Complete the session with the code from Telegram.")


@router.post("/{channel_id}/telegram/session/complete", response_model=schemas.CommunityChannelOut)
async def complete_telegram_channel_session(
    workspace_id: int,
    channel_id: int,
    payload: schemas.TelegramChannelSessionCompleteRequest,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id, "provider": "telegram"})
    if not channel:
        raise HTTPException(status_code=404, detail="Telegram channel not found")
    try:
        api_id, api_hash = _telegram_backend_credentials()
    except TelegramServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    temp_session = str(channel.get("temp_session") or "")
    phone_code_hash = str(channel.get("phone_code_hash") or "")
    if not temp_session or not phone_code_hash:
        raise HTTPException(status_code=400, detail="Start Telegram login first before completing the session.")
    try:
        result = await telegram_session_complete(
            api_id=api_id,
            api_hash=api_hash,
            temp_session=temp_session,
            phone_number=str(channel.get("phone_number") or ""),
            code=payload.code,
            phone_code_hash=phone_code_hash,
            password=payload.password,
        )
    except TelegramServiceError as exc:
        channel["status"] = "error"
        channel["last_error"] = str(exc)
        channel["updated_at"] = datetime.utcnow()
        db.save("community_channels", channel)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    channel["telegram_session_string"] = result.session_string
    channel["telegram_user_id"] = result.user_id
    channel["telegram_username"] = result.username
    channel["display_name"] = result.display_name
    channel["temp_session"] = None
    channel["phone_code_hash"] = None
    channel["status"] = "connected"
    channel["connected_at"] = datetime.utcnow()
    channel["updated_at"] = datetime.utcnow()
    channel["last_error"] = None
    db.save("community_channels", channel)
    try:
        discovered_groups = await _discover_telegram_groups(db, channel)
    except TelegramServiceError as exc:
        channel["status"] = "connected"
        channel["last_error"] = str(exc)
        channel["updated_at"] = datetime.utcnow()
        db.save("community_channels", channel)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    channel["discovered_group_count"] = discovered_groups
    db.save("community_channels", channel)
    return _channel_out(channel)


@router.post("/{channel_id}/telegram/discover-groups", response_model=schemas.ChannelSyncResultOut)
async def discover_telegram_groups(
    workspace_id: int,
    channel_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id, "provider": "telegram"})
    if not channel:
        raise HTTPException(status_code=404, detail="Telegram channel not found")
    if not channel.get("telegram_session_string"):
        raise HTTPException(status_code=400, detail="Connect the Telegram account before discovering groups.")
    try:
        _telegram_backend_credentials()
    except TelegramServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        discovered = await _discover_telegram_groups(db, channel)
    except TelegramServiceError as exc:
        channel["last_error"] = str(exc)
        channel["updated_at"] = datetime.utcnow()
        db.save("community_channels", channel)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    channel["status"] = "connected"
    channel["last_error"] = None
    db.save("community_channels", channel)
    return schemas.ChannelSyncResultOut(message="Telegram groups refreshed.", discovered_groups=discovered)


@router.post("/{channel_id}/telegram/sync", response_model=schemas.ChannelSyncResultOut)
async def sync_telegram_channel(
    workspace_id: int,
    channel_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id, "provider": "telegram"})
    if not channel:
        raise HTTPException(status_code=404, detail="Telegram channel not found")
    if not channel.get("telegram_session_string"):
        raise HTTPException(status_code=400, detail="Connect the Telegram account before syncing messages.")
    try:
        api_id, api_hash = _telegram_backend_credentials()
    except TelegramServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    groups = db.find_many(
        "channel_group_links",
        {"workspace_id": workspace_id, "channel_id": channel_id, "sync_enabled": True},
        sort=[("created_at", DESC)],
    )
    if not groups:
        return schemas.ChannelSyncResultOut(message="No Telegram groups have sync enabled yet.")

    last_synced_message_ids = {
        str(group.external_group_id): int(group.get("last_synced_message_id") or 0)
        for group in groups
    }
    try:
        messages = await telegram_sync_group_messages(
            api_id=api_id,
            api_hash=api_hash,
            session_string=str(channel.get("telegram_session_string") or ""),
            external_group_ids=[str(group.external_group_id) for group in groups],
            last_synced_message_ids=last_synced_message_ids,
        )
    except TelegramServiceError as exc:
        channel["last_error"] = str(exc)
        channel["updated_at"] = datetime.utcnow()
        db.save("community_channels", channel)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    group_by_external_id = {str(group.external_group_id): group for group in groups}
    stored_count = 0
    artifact_count = 0
    for item in messages:
        group = group_by_external_id.get(item.external_group_id)
        if not group:
            continue
        stored_message = _persist_channel_message(
            db,
            workspace_id=workspace_id,
            channel_id=channel_id,
            group_link=group,
            provider="telegram",
            external_message_id=item.external_message_id,
            sender_name=item.sender_name,
            sender_handle=item.sender_handle,
            message_type=item.message_type,
            text=item.text,
            raw_payload=item.raw_payload,
            received_at=item.received_at,
        )
        if not stored_message:
            continue
        stored_count += 1
        group["last_synced_message_id"] = int(item.external_message_id)
        group["last_synced_at"] = datetime.utcnow()
        db.save("channel_group_links", group)
        _analyze_and_store_artifact(db, message=stored_message, group_name=group.group_name)
        artifact_count += 1

    channel["status"] = "connected"
    channel["last_error"] = None
    channel["updated_at"] = datetime.utcnow()
    db.save("community_channels", channel)
    return schemas.ChannelSyncResultOut(
        message="Telegram sync complete.",
        discovered_groups=int(channel.get("discovered_group_count") or 0),
        synced_messages=stored_count,
        analyzed_messages=artifact_count,
    )


@router.post("/whatsapp", response_model=schemas.CommunityChannelOut, status_code=201)
def connect_whatsapp_channel(
    workspace_id: int,
    payload: schemas.WhatsAppChannelConnectRequest,
    request: Request,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    if not db.find_by_id("workspaces", workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")

    existing = db.find_one(
        "community_channels",
        {"workspace_id": workspace_id, "provider": "whatsapp", "label": payload.label.strip()},
    )
    if existing:
        raise HTTPException(status_code=409, detail="A WhatsApp source with this label already exists.")
    channel_id = db.next_id("community_channels")
    secret = secrets.token_urlsafe(24)
    inbound_url = str(request.url_for("whatsapp_channel_inbound", channel_id=channel_id))
    record = {
        "id": channel_id,
        "workspace_id": workspace_id,
        "provider": "whatsapp",
        "label": payload.label.strip(),
        "status": "configured",
        "webhook_url": inbound_url,
        "webhook_secret": secret,
        "connected_at": None,
        "updated_at": datetime.utcnow(),
        "selected_group_count": 0,
        "discovered_group_count": 0,
        "last_error": None,
        "pairing_mode": "qr",
        "qr_code_data_url": None,
        "qr_updated_at": None,
        "whatsapp_jid": None,
        "display_name": None,
        "phone_number": None,
    }
    channel = db.insert("community_channels", record)
    return _channel_out(channel)


@router.post("/{channel_id}/whatsapp/session/start", response_model=schemas.CommunityChannelOut)
async def start_whatsapp_channel_session(
    workspace_id: int,
    channel_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id, "provider": "whatsapp"})
    if not channel:
        raise HTTPException(status_code=404, detail="WhatsApp channel not found")
    payload = await _whatsapp_gateway_request(
        "POST",
        "/internal/sessions/connect",
        {
            "channelId": channel.id,
            "label": channel.label,
            "sharedSecret": str(channel.get("webhook_secret") or ""),
            "pairingMode": "qr",
        },
    )
    _apply_whatsapp_gateway_status(channel, payload)
    db.save("community_channels", channel)
    return _channel_out(channel)


@router.get("/{channel_id}/whatsapp/session/status", response_model=schemas.CommunityChannelOut)
async def get_whatsapp_channel_session_status(
    workspace_id: int,
    channel_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id, "provider": "whatsapp"})
    if not channel:
        raise HTTPException(status_code=404, detail="WhatsApp channel not found")
    channel = await _refresh_whatsapp_channel_status(db, channel)
    return _channel_out(channel)


@router.post("/{channel_id}/whatsapp/discover-groups", response_model=schemas.ChannelSyncResultOut)
async def discover_whatsapp_groups(
    workspace_id: int,
    channel_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id, "provider": "whatsapp"})
    if not channel:
        raise HTTPException(status_code=404, detail="WhatsApp channel not found")
    payload = await _whatsapp_gateway_request("GET", f"/internal/sessions/{channel.id}/groups")
    groups = [
        schemas.WhatsAppDiscoveredGroupIn(
            external_group_id=str(group.get("external_group_id") or ""),
            group_name=str(group.get("group_name") or ""),
        )
        for group in payload.get("groups") or []
        if str(group.get("external_group_id") or "").endswith("@g.us") and str(group.get("group_name") or "").strip()
    ]
    discovered = _upsert_whatsapp_groups(db, channel=channel, groups=groups)
    channel["last_error"] = None
    db.save("community_channels", channel)
    return schemas.ChannelSyncResultOut(message="WhatsApp groups refreshed.", discovered_groups=discovered)


@router.post("/{channel_id}/whatsapp/sync", response_model=schemas.ChannelSyncResultOut)
async def sync_whatsapp_channel(
    workspace_id: int,
    channel_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id, "provider": "whatsapp"})
    if not channel:
        raise HTTPException(status_code=404, detail="WhatsApp channel not found")
    channel = await _refresh_whatsapp_channel_status(db, channel)
    return schemas.ChannelSyncResultOut(
        message="WhatsApp is now in live-only mode. New messages in enabled groups will sync automatically.",
        discovered_groups=int(channel.get("discovered_group_count") or 0),
        synced_messages=0,
    )


@router.post("/{channel_id}/whatsapp/session/disconnect", response_model=schemas.AuthStatusResponse)
async def disconnect_whatsapp_channel_session(
    workspace_id: int,
    channel_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id, "provider": "whatsapp"})
    if not channel:
        raise HTTPException(status_code=404, detail="WhatsApp channel not found")
    await _whatsapp_gateway_request("POST", f"/internal/sessions/{channel.id}/disconnect", {})
    _clear_whatsapp_session_fields(channel, status="disconnected")
    db.save("community_channels", channel)
    return schemas.AuthStatusResponse(message="WhatsApp session disconnected.")


@router.post("/{channel_id}/whatsapp/session/reset", response_model=schemas.AuthStatusResponse)
async def reset_whatsapp_channel_session(
    workspace_id: int,
    channel_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id, "provider": "whatsapp"})
    if not channel:
        raise HTTPException(status_code=404, detail="WhatsApp channel not found")
    await _whatsapp_gateway_request("POST", f"/internal/sessions/{channel.id}/reset", {})
    _clear_whatsapp_session_fields(channel, status="configured")
    db.save("community_channels", channel)
    return schemas.AuthStatusResponse(message="WhatsApp session reset. Scan a fresh QR code to reconnect.")


@router.delete("/{channel_id}", response_model=schemas.AuthStatusResponse)
def disconnect_channel(
    workspace_id: int,
    channel_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    db.delete_many("channel_group_links", {"workspace_id": workspace_id, "channel_id": channel_id})
    db.delete_many("channel_messages", {"workspace_id": workspace_id, "channel_id": channel_id})
    db.delete_one("community_channels", {"workspace_id": workspace_id, "id": channel_id})
    return schemas.AuthStatusResponse(message="Channel disconnected.")


@router.get("/{channel_id}/groups", response_model=list[schemas.ChannelGroupLinkOut])
def list_channel_groups(
    workspace_id: int,
    channel_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    groups = db.find_many(
        "channel_group_links",
        {"workspace_id": workspace_id, "channel_id": channel_id},
        sort=[("last_seen_at", DESC), ("created_at", DESC)],
    )
    return [_group_out(group) for group in groups]


@router.get("/{channel_id}/gateway-config", response_model=schemas.WhatsAppGatewayConfigOut)
def get_whatsapp_gateway_config(
    workspace_id: int,
    channel_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id, "provider": "whatsapp"})
    if not channel:
        raise HTTPException(status_code=404, detail="WhatsApp channel not found")
    selected_groups = [
        group.external_group_id
        for group in db.find_many(
            "channel_group_links",
            {"workspace_id": workspace_id, "channel_id": channel_id, "sync_enabled": True},
            sort=[("created_at", DESC)],
        )
    ]
    return _gateway_config_out(channel, selected_groups)


@inbound_router.get("/whatsapp/{channel_id}/gateway-config", response_model=schemas.WhatsAppGatewayConfigOut)
def get_whatsapp_gateway_config_internal(
    channel_id: int,
    x_quorum_channel_secret: str | None = Header(default=None),
    db: MongoStore = Depends(get_db),
):
    channel = db.find_one("community_channels", {"id": channel_id, "provider": "whatsapp"})
    if not channel:
        raise HTTPException(status_code=404, detail="WhatsApp channel not found")
    if channel.get("webhook_secret") and channel.get("webhook_secret") != x_quorum_channel_secret:
        raise HTTPException(status_code=403, detail="Invalid WhatsApp channel secret")
    selected_groups = [
        group.external_group_id
        for group in db.find_many(
            "channel_group_links",
            {"workspace_id": channel.workspace_id, "channel_id": channel.id, "sync_enabled": True},
            sort=[("created_at", DESC)],
        )
    ]
    return _gateway_config_out(channel, selected_groups)


@router.patch("/{channel_id}/groups/{group_id}", response_model=schemas.ChannelGroupLinkOut)
def update_channel_group_sync(
    workspace_id: int,
    channel_id: int,
    group_id: int,
    payload: schemas.ChannelGroupSyncUpdate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    group = db.find_one("channel_group_links", {"workspace_id": workspace_id, "channel_id": channel_id, "id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    group["sync_enabled"] = payload.sync_enabled
    group["updated_at"] = datetime.utcnow()
    db.save("channel_group_links", group)
    _refresh_channel_counts(db, channel)
    return _group_out(group)


@router.get("/messages", response_model=list[schemas.ChannelMessageOut])
def list_channel_messages(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    messages = db.find_many("channel_messages", {"workspace_id": workspace_id}, sort=[("received_at", DESC)], limit=100)
    return [_message_out(db, message) for message in messages]


@router.get("/artifacts", response_model=list[schemas.MessageArtifactOut])
def list_message_artifacts(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    artifacts = db.find_many("message_artifacts", {"workspace_id": workspace_id}, sort=[("created_at", DESC)], limit=100)
    return [_artifact_out(artifact) for artifact in artifacts]


@router.get("/feed", response_model=schemas.CommunityInboxFeedOut)
def get_community_inbox_feed(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    artifacts = db.find_many("message_artifacts", {"workspace_id": workspace_id}, sort=[("created_at", DESC)], limit=240)
    highlights: list[schemas.CommunityHighlightOut] = []
    review_queue: list[schemas.CommunityHighlightOut] = []
    seen_highlight_messages: set[int] = set()
    seen_review_messages: set[int] = set()

    for artifact in artifacts:
        if not _should_include_highlight(artifact):
            continue
        message = db.find_one("channel_messages", {"workspace_id": workspace_id, "id": artifact.message_id})
        if not message:
            continue
        group = db.find_by_id("channel_group_links", message.get("group_link_id"))
        highlight = _highlight_out(db, message, artifact, group_name=group.group_name if group else None)
        if highlight.message_id not in seen_highlight_messages and len(highlights) < 80:
            highlights.append(highlight)
            seen_highlight_messages.add(highlight.message_id)
        if (
            artifact.status in {"needs_review", "analysis_failed"}
            and highlight.message_id not in seen_review_messages
            and len(review_queue) < 40
        ):
            review_queue.append(highlight)
            seen_review_messages.add(highlight.message_id)
        if len(highlights) >= 80 and len(review_queue) >= 40:
            break

    return schemas.CommunityInboxFeedOut(
        highlights=highlights,
        review_queue=review_queue,
        audit_trail=_audit_trail_out(db, workspace_id=workspace_id),
        refreshed_at=datetime.utcnow(),
    )


@router.get("/review-queue", response_model=list[schemas.MessageArtifactOut])
def list_review_queue(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    artifacts = db.find_many(
        "message_artifacts",
        {"workspace_id": workspace_id, "status": {"$in": ["needs_review", "analysis_failed"]}},
        sort=[("created_at", DESC)],
        limit=100,
    )
    return [_artifact_out(artifact) for artifact in artifacts]


@router.post("/artifacts/review-bulk", response_model=list[schemas.MessageArtifactOut])
def bulk_review_artifacts(
    workspace_id: int,
    payload: schemas.ArtifactBulkReviewRequest,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("integrations.manage")),
):
    results: list[schemas.MessageArtifactOut] = []
    for artifact_id in payload.artifact_ids[:50]:
        artifact = db.find_one("message_artifacts", {"workspace_id": workspace_id, "id": artifact_id})
        if not artifact:
            continue
        if payload.action == "approve":
            message = db.find_one("channel_messages", {"workspace_id": workspace_id, "id": artifact.message_id})
            if not message:
                continue
            artifact["status"] = "approved"
            artifact["reviewed_at"] = datetime.utcnow()
            artifact["reviewed_by_user_id"] = membership.user_id
            artifact["review_note"] = artifact.get("review_note")
            db.save("message_artifacts", artifact)
            _apply_artifact_outcome(db, artifact=artifact, message=message)
        else:
            artifact["status"] = "rejected"
            artifact["reviewed_at"] = datetime.utcnow()
            artifact["reviewed_by_user_id"] = membership.user_id
            artifact["review_note"] = artifact.get("review_note")
            db.save("message_artifacts", artifact)
        results.append(_artifact_out(artifact))
    return results


@router.post("/messages/{message_id}/analyze", response_model=schemas.MessageArtifactOut)
def analyze_channel_message(
    workspace_id: int,
    message_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    message = db.find_one("channel_messages", {"workspace_id": workspace_id, "id": message_id})
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    group = db.find_by_id("channel_group_links", message.get("group_link_id"))
    artifact = _analyze_and_store_artifact(db, message=message, group_name=group.group_name if group else None)
    return _artifact_out(artifact)


@router.post("/artifacts/{artifact_id}/approve", response_model=schemas.MessageArtifactOut)
def approve_message_artifact(
    workspace_id: int,
    artifact_id: int,
    payload: schemas.ArtifactReviewDecisionRequest,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("integrations.manage")),
):
    artifact = db.find_one("message_artifacts", {"workspace_id": workspace_id, "id": artifact_id})
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    message = db.find_one("channel_messages", {"workspace_id": workspace_id, "id": artifact.message_id})
    if not message:
        raise HTTPException(status_code=404, detail="Message not found for artifact")
    artifact["status"] = "approved"
    artifact["reviewed_at"] = datetime.utcnow()
    artifact["reviewed_by_user_id"] = membership.user_id
    artifact["review_note"] = payload.note.strip() if payload.note else None
    db.save("message_artifacts", artifact)
    _apply_artifact_outcome(db, artifact=artifact, message=message)
    return _artifact_out(artifact)


@router.post("/artifacts/{artifact_id}/reject", response_model=schemas.MessageArtifactOut)
def reject_message_artifact(
    workspace_id: int,
    artifact_id: int,
    payload: schemas.ArtifactReviewDecisionRequest,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("integrations.manage")),
):
    artifact = db.find_one("message_artifacts", {"workspace_id": workspace_id, "id": artifact_id})
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact["status"] = "rejected"
    artifact["reviewed_at"] = datetime.utcnow()
    artifact["reviewed_by_user_id"] = membership.user_id
    artifact["review_note"] = payload.note.strip() if payload.note else None
    db.save("message_artifacts", artifact)
    return _artifact_out(artifact)


@router.post("/artifacts/{artifact_id}/create-task", response_model=schemas.TaskOut, status_code=201)
def create_task_from_artifact(
    workspace_id: int,
    artifact_id: int,
    payload: schemas.CommunityArtifactTaskCreateRequest,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("tasks.assign")),
):
    artifact = db.find_one("message_artifacts", {"workspace_id": workspace_id, "id": artifact_id})
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    message = db.find_one("channel_messages", {"workspace_id": workspace_id, "id": artifact.message_id})
    if not message:
        raise HTTPException(status_code=404, detail="Message not found for artifact")

    existing = db.find_one("tasks", {"workspace_id": workspace_id, "linked_module": "community_artifact", "linked_id": artifact_id})
    if existing:
        return _task_out(db, existing)

    task = _create_or_update_task_from_artifact(
        db,
        artifact=artifact,
        message=message,
        created_by_user_id=membership.user_id,
        override_assignee_member_id=payload.assigned_to_member_id,
        override_due_date=payload.due_date,
        override_priority=payload.priority,
        note=payload.note,
    )
    if payload.title:
        task["title"] = payload.title.strip()[:180]
        db.save("tasks", task)
    artifact["status"] = "approved"
    artifact["reviewed_at"] = datetime.utcnow()
    artifact["reviewed_by_user_id"] = membership.user_id
    artifact["review_note"] = payload.note.strip() if payload.note else artifact.get("review_note")
    db.save("message_artifacts", artifact)

    return _task_out(db, task)


@inbound_router.post("/telegram/{channel_id}/webhook", name="telegram_channel_webhook")
async def telegram_channel_webhook(
    channel_id: int,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    db: MongoStore = Depends(get_db),
):
    channel = db.find_one("community_channels", {"id": channel_id, "provider": "telegram"})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.get("webhook_secret") and channel.get("webhook_secret") != x_telegram_bot_api_secret_token:
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret")
    return {
        "ok": True,
        "status": "telegram_uses_telethon_session_sync",
        "message": "Telegram channels now sync through the Telethon session flow, not Bot API webhooks.",
    }


@inbound_router.post("/whatsapp/{channel_id}/discover-groups")
async def whatsapp_channel_discover_groups(
    channel_id: int,
    payload: schemas.WhatsAppDiscoveredGroupsIn,
    x_quorum_channel_secret: str | None = Header(default=None),
    db: MongoStore = Depends(get_db),
):
    channel = db.find_one("community_channels", {"id": channel_id, "provider": "whatsapp"})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.get("webhook_secret") and channel.get("webhook_secret") != x_quorum_channel_secret:
        raise HTTPException(status_code=403, detail="Invalid WhatsApp channel secret")
    discovered = _upsert_whatsapp_groups(db, channel=channel, groups=payload.groups)
    channel["last_error"] = None
    db.save("community_channels", channel)
    return {"ok": True, "discovered_groups": discovered}


@inbound_router.post("/whatsapp/{channel_id}/inbound", name="whatsapp_channel_inbound")
async def whatsapp_channel_inbound(
    channel_id: int,
    request: Request,
    x_quorum_channel_secret: str | None = Header(default=None),
    db: MongoStore = Depends(get_db),
):
    channel = db.find_one("community_channels", {"id": channel_id, "provider": "whatsapp"})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.get("webhook_secret") and channel.get("webhook_secret") != x_quorum_channel_secret:
        raise HTTPException(status_code=403, detail="Invalid WhatsApp channel secret")

    payload = await request.json()
    remote_jid = str(payload.get("remote_jid") or "").strip()
    if not remote_jid.endswith("@g.us"):
        return {"ok": True, "status": "ignored_non_group"}

    message_type = str(payload.get("message_type") or "text").strip().lower()
    text = str(payload.get("body") or payload.get("caption") or "").strip()
    if not text and message_type in {"image", "document", "video"}:
        attachment_name = str(payload.get("attachment_name") or "").strip()
        text = f"Shared {message_type}{f': {attachment_name}' if attachment_name else ''}"
    if not text:
        return {"ok": True, "status": "ignored_empty"}
    sync_source = str(payload.get("sync_source") or "live").strip().lower()

    received_at_raw = payload.get("received_at")
    if received_at_raw:
        received_at = datetime.fromisoformat(str(received_at_raw).replace("Z", "+00:00")).replace(tzinfo=None)
    else:
        received_at = datetime.utcnow()

    group = _discover_or_update_group(
        db,
        workspace_id=channel.workspace_id,
        channel_id=channel.id,
        provider="whatsapp",
        external_group_id=remote_jid,
        group_name=str(payload.get("chat_name") or payload.get("group_name") or remote_jid),
        seen_at=received_at,
    )
    _refresh_channel_counts(db, channel)
    if not group.get("sync_enabled"):
        return {"ok": True, "status": "ignored_unselected_group"}

    stored_message = _persist_channel_message(
        db,
        workspace_id=channel.workspace_id,
        channel_id=channel.id,
        group_link=group,
        provider="whatsapp",
        external_message_id=str(payload.get("message_id")) if payload.get("message_id") else None,
        sender_name=payload.get("push_name"),
        sender_handle=payload.get("sender_jid") or payload.get("phone_number"),
        message_type=message_type,
        text=text,
        raw_payload=payload,
        received_at=received_at,
    )
    if stored_message:
        _analyze_and_store_artifact(db, message=stored_message, group_name=group.group_name)
    channel["status"] = "connected"
    channel["last_error"] = None
    db.save("community_channels", channel)
    return {"ok": True, "status": "stored"}
