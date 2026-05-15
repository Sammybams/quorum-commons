from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .anthropic import anthropic_configured, anthropic_model


class CommunityIntelligenceError(RuntimeError):
    pass


@dataclass
class CommunityArtifact:
    artifact_type: str
    confidence: float
    summary: str
    extracted_payload: dict[str, object]


def analyze_message(
    *,
    text: str,
    provider: str,
    group_name: str | None = None,
    workspace_type: str | None = None,
    community_profile: dict[str, str] | None = None,
    message_type: str | None = None,
    attachment_name: str | None = None,
    recent_messages: list[str] | None = None,
    prefer_lightweight: bool = False,
) -> CommunityArtifact:
    cleaned = text.strip()
    if not cleaned:
      return CommunityArtifact("other", 0.0, "Empty message", {})

    contextual_messages = [item.strip() for item in (recent_messages or []) if item and item.strip()]
    if anthropic_configured() and not prefer_lightweight:
        return _analyze_with_anthropic(
            text=cleaned,
            provider=provider,
            group_name=group_name,
            workspace_type=workspace_type,
            community_profile=community_profile,
            message_type=message_type,
            attachment_name=attachment_name,
            recent_messages=contextual_messages,
        )
    return _analyze_with_heuristics(
        cleaned,
        contextual_messages,
        workspace_type=workspace_type,
        community_profile=community_profile,
        message_type=message_type,
        attachment_name=attachment_name,
    )


def _analyze_with_anthropic(
    *,
    text: str,
    provider: str,
    group_name: str | None = None,
    workspace_type: str | None = None,
    community_profile: dict[str, str] | None = None,
    message_type: str | None = None,
    attachment_name: str | None = None,
    recent_messages: list[str] | None = None,
) -> CommunityArtifact:
    import os

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise CommunityIntelligenceError("ANTHROPIC_API_KEY is not configured")

    context_block = "\n".join(f"- {item}" for item in (recent_messages or [])[:6]).strip() or "- No prior context available"
    profile_block = ", ".join(
        f"{key}={value}"
        for key, value in sorted((community_profile or {}).items())
        if value and str(value).strip()
    ) or "None"
    extraction_rules = _community_type_prompt_rules(workspace_type)

    prompt = (
        "You classify operational community chat messages and return only valid JSON.\n"
        "Use both the current message and the recent message context from the same group.\n"
        "The final classification should still describe the current message, but you can use the surrounding messages to disambiguate what is happening.\n"
        "Schema:\n"
        "{"
        '"artifact_type":"payment_receipt"|"contribution_signal"|"opportunity"|"announcement"|"disbursement_request"|"other",'
        '"confidence":number,'
        '"summary":string,'
        '"extracted_payload":object'
        "}\n"
        "Rules:\n"
        "- summary must be brief, tag-like, and under 8 words.\n"
        "- confidence must be between 0 and 1.\n"
        "- extracted_payload should contain only fields directly supported by the message.\n"
        "- For opportunity include title, location, trade_tags, deadline, contact.\n"
        "- For contribution_signal include amount, contributor_name, cycle_hint.\n"
        "- For payment_receipt include amount, payer, reference, bank, transaction_date.\n"
        "- For announcement include title, audience, action_required.\n"
        "- For disbursement_request include amount, purpose, beneficiary.\n"
        "- If a message is an image or document, use that attachment context while still being conservative.\n"
        "- Receipt-like attachments or bank-alert screenshots should normally map to payment_receipt when supported by the text/context.\n"
        f"{extraction_rules}\n"
        "- If the message is conversational or unclear, return artifact_type as other.\n\n"
        f"Provider: {provider}\n"
        f"Group: {group_name or 'Unknown'}\n"
        f"Workspace type: {workspace_type or 'student_body'}\n"
        f"Community profile: {profile_block}\n"
        f"Message type: {message_type or 'text'}\n"
        f"Attachment name: {attachment_name or 'None'}\n"
        "Recent message context from the same group:\n"
        f"{context_block}\n\n"
        "Message:\n"
        f"{text}"
    )

    payload = {
        "model": anthropic_model(),
        "max_tokens": 220,
        "temperature": 0,
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
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise CommunityIntelligenceError(detail or str(exc)) from exc
    except URLError as exc:
        raise CommunityIntelligenceError(str(exc.reason)) from exc

    data = json.loads(raw)
    content = "\n".join(
        item.get("text", "").strip()
        for item in data.get("content", [])
        if item.get("type") == "text" and item.get("text")
    ).strip()
    parsed = _parse_json_object(content)
    summary = str(parsed.get("summary") or "").strip()
    summary = summary[:80]

    return CommunityArtifact(
        artifact_type=str(parsed.get("artifact_type") or "other").strip().lower(),
        confidence=max(0.0, min(1.0, float(parsed.get("confidence") or 0))),
        summary=summary,
        extracted_payload=parsed.get("extracted_payload") if isinstance(parsed.get("extracted_payload"), dict) else {},
    )


def _analyze_with_heuristics(
    text: str,
    recent_messages: list[str] | None = None,
    *,
    workspace_type: str | None = None,
    community_profile: dict[str, str] | None = None,
    message_type: str | None = None,
    attachment_name: str | None = None,
) -> CommunityArtifact:
    context_text = " ".join(recent_messages or [])
    lowered = text.lower()
    contextual_lowered = f"{context_text.lower()} {lowered}".strip()
    attachment_hint = str(attachment_name or "").lower()
    workspace_hint = str(workspace_type or "student_body").strip().lower()
    profile_hint = " ".join(str(value).lower() for value in (community_profile or {}).values())
    enriched_text = f"{profile_hint} {contextual_lowered}".strip()
    amount_match = re.search(r"(?:ngn|₦|n)\s*([\d,]+(?:\.\d{1,2})?)", lowered)
    amount = amount_match.group(1).replace(",", "") if amount_match else None

    opportunity_keywords = {
        "job", "opportunity", "vacancy", "apply", "supplier needed", "needed urgently",
        "buyer", "client", "bulk order", "contract", "partnership", "vendor", "sponsorship", "volunteer",
    }
    if workspace_hint in {"cooperative", "market_association", "trade_group", "savings_circle"}:
        opportunity_keywords.update({"stock", "dispatch", "supply", "delivery", "market day", "customer"})
    if any(keyword in enriched_text for keyword in opportunity_keywords):
        return CommunityArtifact(
            artifact_type="opportunity",
            confidence=0.68 if recent_messages else 0.62,
            summary="opportunity lead",
            extracted_payload={"title": text[:120], "amount": amount, "trade_tags": _keyword_tags(enriched_text, workspace_hint)},
        )
    payment_keywords = {"paid", "payment", "receipt", "transfer", "contribution sent", "dues sent"}
    if workspace_hint in {"cooperative", "market_association", "trade_group", "savings_circle"}:
        payment_keywords.update({"ajo", "thrift", "esusu", "repayment", "installment", "weekly contribution"})
    if any(keyword in enriched_text for keyword in payment_keywords):
        return CommunityArtifact(
            artifact_type="contribution_signal" if any(keyword in enriched_text for keyword in ["contribution", "dues", "ajo", "thrift", "esusu", "repayment"]) else "payment_receipt",
            confidence=0.66 if recent_messages else 0.58,
            summary="payment signal",
            extracted_payload={"amount": amount, "raw_excerpt": text[:160]},
        )
    if any(keyword in enriched_text for keyword in {"loan request", "send to", "disburse", "withdraw", "cash out", "vendor payment", "settle supplier"}):
        return CommunityArtifact(
            artifact_type="disbursement_request",
            confidence=0.63 if recent_messages else 0.56,
            summary="disbursement request",
            extracted_payload={"amount": amount, "purpose": text[:120]},
        )
    if (message_type in {"image", "document"} and any(keyword in f"{attachment_hint} {contextual_lowered}" for keyword in ["receipt", "transfer", "alert", "payment", "bank"])) or (
        message_type in {"image", "document"} and amount
    ):
        return CommunityArtifact(
            artifact_type="payment_receipt",
            confidence=0.61 if recent_messages else 0.54,
            summary="receipt file",
            extracted_payload={"amount": amount, "attachment_name": attachment_name},
        )
    if any(keyword in contextual_lowered for keyword in ["meeting", "announcement", "notice", "reminder", "tomorrow", "attend"]):
        return CommunityArtifact(
            artifact_type="announcement",
            confidence=0.61 if recent_messages else 0.55,
            summary="announcement",
            extracted_payload={"title": text[:120]},
        )
    return CommunityArtifact("other", 0.3, "general chat", {})


def _keyword_tags(text: str, workspace_type: str | None = None) -> list[str]:
    tags = []
    candidates = ["tailor", "fashion", "food", "driver", "cleaning", "logistics", "teacher", "design", "sales"]
    if workspace_type in {"cooperative", "market_association", "trade_group", "savings_circle"}:
        candidates.extend(["wholesale", "retail", "fabric", "beauty", "catering", "delivery", "trading", "supply"])
    if workspace_type == "student_body":
        candidates.extend(["media", "ushering", "speaker", "partnership", "sponsorship", "volunteer"])
    for candidate in candidates:
        if candidate in text:
            tags.append(candidate)
    return tags


def _community_type_prompt_rules(workspace_type: str | None) -> str:
    normalized = str(workspace_type or "student_body").strip().lower()
    if normalized in {"cooperative", "market_association", "trade_group", "savings_circle"}:
        return (
            "- For cooperatives, market associations, trade groups, and savings circles: treat buyer leads, supplier requests, "
            "bulk orders, stock requests, transport/logistics requests, thrift contributions, repayment signals, and vendor settlement requests as operationally important.\n"
            "- Loan repayment and thrift/ajo/esusu updates usually map to contribution_signal or payment_receipt, not opportunity.\n"
            "- Supplier sourcing, buyer leads, stock requests, and paid delivery/dispatch jobs usually map to opportunity."
        )
    if normalized == "student_body":
        return (
            "- For student or campus communities: treat volunteer requests, sponsorship leads, vendor sourcing, event staffing, partnership outreach, "
            "and paid campus gigs as operationally important opportunities.\n"
            "- Meeting reminders, turnout requests, and election/admin notices usually map to announcement unless they contain a concrete opportunity."
        )
    return (
        "- For general community workspaces: prioritize concrete opportunities, verified inflow signals, announcements, and requests that imply money movement or member assignment."
    )


def _parse_json_object(value: str) -> dict:
    direct = value.strip()
    if direct.startswith("{") and direct.endswith("}"):
        return json.loads(direct)

    fenced = re.search(r"```json\s*(\{.*\})\s*```", value, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))

    object_match = re.search(r"(\{.*\})", value, re.DOTALL)
    if object_match:
        return json.loads(object_match.group(1))

    raise CommunityIntelligenceError("Could not parse JSON from AI response.")
