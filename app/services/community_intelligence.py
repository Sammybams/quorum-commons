from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
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
    attachment_mime_type: str | None = None,
    attachment_base64: str | None = None,
    recent_messages: list[str] | None = None,
    prefer_lightweight: bool = False,
) -> CommunityArtifact:
    cleaned = text.strip()
    if not cleaned:
      return CommunityArtifact("other", 0.0, "Empty message", {})

    contextual_messages = [item.strip() for item in (recent_messages or []) if item and item.strip()]
    attachment_text = _extract_attachment_text(
        text=cleaned,
        attachment_name=attachment_name,
        attachment_mime_type=attachment_mime_type,
        attachment_base64=attachment_base64,
        prefer_lightweight=prefer_lightweight,
    )
    if anthropic_configured() and not prefer_lightweight:
        return _analyze_with_anthropic(
            text=cleaned,
            provider=provider,
            group_name=group_name,
            workspace_type=workspace_type,
            community_profile=community_profile,
            message_type=message_type,
            attachment_name=attachment_name,
            attachment_mime_type=attachment_mime_type,
            attachment_text=attachment_text,
            recent_messages=contextual_messages,
        )
    return _analyze_with_heuristics(
        cleaned,
        contextual_messages,
        workspace_type=workspace_type,
        community_profile=community_profile,
        message_type=message_type,
        attachment_name=attachment_name,
        attachment_text=attachment_text,
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
    attachment_mime_type: str | None = None,
    attachment_text: str | None = None,
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
        '"artifact_type":"payment_receipt"|"contribution_signal"|"opportunity"|"announcement"|"disbursement_request"|"task_signal"|"other",'
        '"confidence":number,'
        '"summary":string,'
        '"extracted_payload":object'
        "}\n"
        "Rules:\n"
        "- summary must be brief, tag-like, and under 8 words.\n"
        "- confidence must be between 0 and 1.\n"
        "- extracted_payload should contain only fields directly supported by the message.\n"
        "- For opportunity include title, summary, organization, location, venue, event_date, trade_tags, deadline, contact, action_url, key_points.\n"
        "- For contribution_signal include amount, contributor_name, cycle_hint, payment_for.\n"
        "- For payment_receipt include amount, payer, reference, bank, transaction_date, payment_for.\n"
        "- For announcement include title, audience, action_required.\n"
        "- For disbursement_request include amount, purpose, beneficiary.\n"
        "- For task_signal include title, summary, due_hint, assignee_hint, priority.\n"
        "- If a message is an image or document, use that attachment context while still being conservative.\n"
        "- Receipt-like attachments or bank-alert screenshots should normally map to payment_receipt when supported by the text/context.\n"
        "- If OCR text is available from the attachment, use it to extract amount, payer, reference, bank, and transaction_date when supported.\n"
        f"{extraction_rules}\n"
        "- If the message is conversational or unclear, return artifact_type as other.\n\n"
        f"Provider: {provider}\n"
        f"Group: {group_name or 'Unknown'}\n"
        f"Workspace type: {workspace_type or 'student_body'}\n"
        f"Community profile: {profile_block}\n"
        f"Message type: {message_type or 'text'}\n"
        f"Attachment name: {attachment_name or 'None'}\n"
        f"Attachment mime type: {attachment_mime_type or 'None'}\n"
        f"Attachment OCR text: {attachment_text or 'None'}\n"
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
    extracted_payload = parsed.get("extracted_payload") if isinstance(parsed.get("extracted_payload"), dict) else {}
    if attachment_text:
        extracted_payload = _merge_receipt_hints(extracted_payload, attachment_text)

    return CommunityArtifact(
        artifact_type=str(parsed.get("artifact_type") or "other").strip().lower(),
        confidence=max(0.0, min(1.0, float(parsed.get("confidence") or 0))),
        summary=summary,
        extracted_payload=extracted_payload,
    )


def _analyze_with_heuristics(
    text: str,
    recent_messages: list[str] | None = None,
    *,
    workspace_type: str | None = None,
    community_profile: dict[str, str] | None = None,
    message_type: str | None = None,
    attachment_name: str | None = None,
    attachment_text: str | None = None,
) -> CommunityArtifact:
    context_text = " ".join(recent_messages or [])
    lowered = text.lower()
    attachment_lowered = str(attachment_text or "").lower()
    contextual_lowered = f"{context_text.lower()} {attachment_lowered} {lowered}".strip()
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
        deadline_hint = _extract_due_hint(enriched_text)
        location_hint = _extract_location_hint(text)
        action_url = _extract_first_url(text)
        summary = _summarize_text(text)
        title = _best_title_from_text(text)
        return CommunityArtifact(
            artifact_type="opportunity",
            confidence=0.68 if recent_messages else 0.62,
            summary="opportunity lead",
            extracted_payload={
                "title": title,
                "summary": summary,
                "location": location_hint,
                "trade_tags": _keyword_tags(enriched_text, workspace_hint),
                "deadline": deadline_hint,
                "event_date": deadline_hint,
                "contact": action_url,
                "action_url": action_url,
                "key_points": _key_points_from_text(text),
            },
        )
    payment_keywords = {"paid", "payment", "receipt", "transfer", "contribution sent", "dues sent"}
    if workspace_hint in {"cooperative", "market_association", "trade_group", "savings_circle"}:
        payment_keywords.update({"ajo", "thrift", "esusu", "repayment", "installment", "weekly contribution"})
    if any(keyword in enriched_text for keyword in payment_keywords):
        payload = {"amount": amount, "raw_excerpt": text[:160], "payment_for": text[:120]}
        if attachment_text:
            payload = _merge_receipt_hints(payload, attachment_text)
        return CommunityArtifact(
            artifact_type="contribution_signal" if any(keyword in enriched_text for keyword in ["contribution", "dues", "ajo", "thrift", "esusu", "repayment"]) else "payment_receipt",
            confidence=0.66 if recent_messages else 0.58,
            summary="payment signal",
            extracted_payload=payload,
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
            extracted_payload=_merge_receipt_hints({"amount": amount, "attachment_name": attachment_name, "payment_for": text[:120]}, attachment_text or ""),
        )
    if any(keyword in contextual_lowered for keyword in ["meeting", "announcement", "notice", "reminder", "tomorrow", "attend"]):
        return CommunityArtifact(
            artifact_type="announcement",
            confidence=0.61 if recent_messages else 0.55,
            summary="announcement",
            extracted_payload={"title": _best_title_from_text(text), "action_required": _extract_action_requirement(text)},
        )
    if any(keyword in contextual_lowered for keyword in {"can someone", "please handle", "follow up", "assign", "who can", "need volunteer", "help with", "take this up", "work on", "prepare", "submit"}) and len(text.split()) >= 4:
        due_hint = _extract_due_hint(text)
        assignee_hint = _extract_assignee_hint(text)
        confidence = 0.82 if assignee_hint or due_hint else (0.72 if recent_messages else 0.66)
        return CommunityArtifact(
            artifact_type="task_signal",
            confidence=confidence,
            summary="task to assign",
            extracted_payload={
                "title": _best_title_from_text(text),
                "summary": _summarize_text(text),
                "due_hint": due_hint,
                "priority": "high" if any(keyword in contextual_lowered for keyword in {"urgent", "asap", "today", "immediately"}) else "medium",
                "assignee_hint": assignee_hint,
            },
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


def _clean_chat_text(value: str) -> str:
    cleaned = re.sub(r"[*_~`]+", "", str(value or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _best_title_from_text(text: str) -> str:
    lines = [_clean_chat_text(line) for line in str(text or "").splitlines() if _clean_chat_text(line)]
    if lines:
        title = lines[0]
        if len(title) <= 110:
            return title
    sentence = re.split(r"[.!?]\s+", _clean_chat_text(text), maxsplit=1)[0].strip()
    return sentence[:110] if sentence else _clean_chat_text(text)[:110]


def _summarize_text(text: str, *, limit: int = 220) -> str:
    cleaned = _clean_chat_text(text)
    if len(cleaned) <= limit:
        return cleaned
    shortened = cleaned[:limit].rsplit(" ", 1)[0].strip()
    return f"{shortened}..." if shortened else f"{cleaned[:limit]}..."


def _extract_first_url(text: str) -> str | None:
    match = re.search(r"(https?://\S+|bit\.ly/\S+|tinyurl\.com/\S+)", str(text or ""), re.IGNORECASE)
    return match.group(1).rstrip(").,") if match else None


def _extract_due_hint(text: str) -> str | None:
    patterns = [
        r"(?:deadline|due|before)\s*[:\-]?\s*([A-Z][A-Za-z]{2,9}\s+\d{1,2}(?:,\s*\d{4})?)",
        r"((?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s+[A-Z][a-z]{2,9}\s+\d{1,2})",
        r"((?:today|tomorrow|this weekend|next week))",
    ]
    lowered = str(text or "")
    for pattern in patterns:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if match:
            return _clean_chat_text(match.group(1))
    return None


def _extract_location_hint(text: str) -> str | None:
    for pattern in [
        r"(?:venue|location)\s*[:\-]?\s*([A-Z0-9][^\n,.]{4,90})",
        r"\b(?:at|in)\s+([A-Z][A-Za-z0-9&,'()/.\- ]{4,80})",
    ]:
        match = re.search(pattern, str(text or ""))
        if match:
            return _clean_chat_text(match.group(1))
    return None


def _extract_action_requirement(text: str) -> str | None:
    lowered = str(text or "").lower()
    if "register" in lowered:
        return "Register"
    if "apply" in lowered:
        return "Apply"
    if "attend" in lowered:
        return "Attend"
    if "reply" in lowered:
        return "Reply"
    return None


def _extract_assignee_hint(text: str) -> str | None:
    match = re.search(r"\b(secretary|treasurer|media|volunteer|designer|developer|teacher|driver|usher|officer)\b", str(text or ""), re.IGNORECASE)
    return _clean_chat_text(match.group(1)) if match else None


def _key_points_from_text(text: str) -> list[str]:
    cleaned = _clean_chat_text(text)
    points: list[str] = []
    for value in filter(None, [_extract_due_hint(text), _extract_location_hint(text), _extract_first_url(text)]):
        if value not in points:
            points.append(value)
    lines = [_clean_chat_text(line) for line in str(text or "").splitlines() if _clean_chat_text(line)]
    for line in lines[1:4]:
        if len(line) > 12 and line not in points:
            points.append(line[:80])
        if len(points) >= 4:
            break
    return points[:4]


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


def _extract_attachment_text(
    *,
    text: str,
    attachment_name: str | None = None,
    attachment_mime_type: str | None = None,
    attachment_base64: str | None = None,
    prefer_lightweight: bool = False,
) -> str | None:
    if prefer_lightweight or not attachment_base64 or not anthropic_configured():
        return None
    mime = str(attachment_mime_type or "").strip().lower()
    if not mime.startswith("image/"):
        return None
    import os

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    prompt = (
        "Read this attachment conservatively. If it appears to be a bank alert, transfer receipt, teller, or payment proof, "
        "extract the visible text exactly and keep it concise. If it is not readable, return: unreadable."
    )
    payload = {
        "model": anthropic_model(),
        "max_tokens": 220,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image", "source": {"type": "base64", "media_type": mime, "data": attachment_base64}},
                ],
            }
        ],
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
        with urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8")
    except Exception:
        return None
    data = json.loads(raw)
    extracted = _anthropic_text_content(data)
    extracted = extracted.strip()
    if not extracted or extracted.lower() == "unreadable":
        return None
    return extracted[:1800]


def _anthropic_text_content(payload: dict) -> str:
    return "\n".join(
        item.get("text", "").strip()
        for item in payload.get("content", [])
        if item.get("type") == "text" and item.get("text")
    ).strip()


def _merge_receipt_hints(payload: dict[str, object], source_text: str) -> dict[str, object]:
    text = str(source_text or "").strip()
    if not text:
        return payload
    merged = dict(payload)
    amount_match = re.search(r"(?:ngn|₦|n)\s*([\d,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
    if amount_match and not merged.get("amount"):
        merged["amount"] = amount_match.group(1).replace(",", "")
    reference_match = re.search(r"(?:ref(?:erence)?|trx|transaction id)[:\s#-]*([A-Z0-9-]{5,})", text, re.IGNORECASE)
    if reference_match and not merged.get("reference"):
        merged["reference"] = reference_match.group(1).strip()
    bank_match = re.search(r"([A-Z][A-Za-z& ]+bank)", text, re.IGNORECASE)
    if bank_match and not merged.get("bank"):
        merged["bank"] = bank_match.group(1).strip()
    payer_match = re.search(r"(?:from|payer|account name)[:\s-]*([A-Z][A-Za-z .'-]{3,})", text, re.IGNORECASE)
    if payer_match and not merged.get("payer"):
        merged["payer"] = payer_match.group(1).strip()
    contributor_match = re.search(r"(?:paid by|from|payer|account name)[:\s-]*([A-Z][A-Za-z .'-]{3,})", text, re.IGNORECASE)
    if contributor_match and not merged.get("contributor_name"):
        merged["contributor_name"] = contributor_match.group(1).strip()
    date_match = re.search(r"(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text)
    if date_match and not merged.get("transaction_date"):
        merged["transaction_date"] = _normalize_date(date_match.group(1))
    merged.setdefault("attachment_text_excerpt", text[:240])
    return merged


def _normalize_date(value: str) -> str:
    raw = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw


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
