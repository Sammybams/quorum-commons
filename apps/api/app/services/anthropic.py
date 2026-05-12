from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


load_dotenv()


class AnthropicGenerationError(RuntimeError):
    pass


@dataclass
class GeneratedActionItem:
    description: str
    assigned_to_member_id: int | None = None
    due_date: str | None = None
    priority: str = "medium"


@dataclass
class MeetingMinutesDraft:
    summary: str
    content: str
    attendance_summary: str | None
    decisions: list[str]
    action_items: list[GeneratedActionItem]
    model: str
    raw_text: str


def anthropic_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def anthropic_model() -> str:
    return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


def generate_meeting_minutes(*, transcript: str, meeting_title: str, agenda: list[str], member_roster: list[dict]) -> MeetingMinutesDraft:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise AnthropicGenerationError("ANTHROPIC_API_KEY is not configured.")

    roster_block = json.dumps(member_roster, ensure_ascii=True)
    agenda_block = json.dumps(agenda, ensure_ascii=True)
    prompt = (
        "You are drafting formal student-body meeting minutes.\n"
        "Return only valid JSON with this exact shape:\n"
        "{"
        '"summary": string, '
        '"attendance_summary": string, '
        '"decisions": string[], '
        '"minutes_markdown": string, '
        '"action_items": [{"description": string, "assigned_to_member_id": number|null, "due_date": string|null, "priority": "low"|"medium"|"high"}]'
        "}\n"
        "Rules:\n"
        "- Use only member IDs present in the roster.\n"
        "- If an owner is unclear, set assigned_to_member_id to null.\n"
        "- due_date must be YYYY-MM-DD or null.\n"
        "- minutes_markdown should be concise but complete, with sections for Attendance, Agenda, Discussion, Decisions, and Next Steps.\n"
        "- Do not include any prose outside the JSON object.\n\n"
        f"Meeting title: {meeting_title}\n"
        f"Agenda: {agenda_block}\n"
        f"Member roster: {roster_block}\n"
        "Transcript:\n"
        f"{transcript}"
    )

    payload = {
        "model": anthropic_model(),
        "max_tokens": 2200,
        "temperature": 0.2,
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
        with urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AnthropicGenerationError(detail or str(exc)) from exc
    except URLError as exc:
        raise AnthropicGenerationError(str(exc.reason)) from exc

    data = json.loads(raw)
    raw_text = _anthropic_text(data)
    parsed = _parse_json_object(raw_text)
    action_items = []
    valid_member_ids = {item["id"] for item in member_roster}
    for item in parsed.get("action_items", []):
        assigned_to_member_id = item.get("assigned_to_member_id")
        if assigned_to_member_id not in valid_member_ids:
            assigned_to_member_id = None
        due_date = item.get("due_date")
        if due_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_date):
            due_date = None
        action_items.append(
            GeneratedActionItem(
                description=str(item.get("description", "")).strip(),
                assigned_to_member_id=assigned_to_member_id,
                due_date=due_date,
                priority=str(item.get("priority", "medium")).lower() if item.get("priority") else "medium",
            )
        )

    return MeetingMinutesDraft(
        summary=str(parsed.get("summary", "")).strip(),
        content=str(parsed.get("minutes_markdown", "")).strip(),
        attendance_summary=_optional_text(parsed.get("attendance_summary")),
        decisions=[str(item).strip() for item in parsed.get("decisions", []) if str(item).strip()],
        action_items=[item for item in action_items if item.description],
        model=anthropic_model(),
        raw_text=raw_text,
    )


def _anthropic_text(payload: dict) -> str:
    content = payload.get("content", [])
    chunks = []
    for item in content:
        if item.get("type") == "text" and item.get("text"):
            chunks.append(item["text"])
    if not chunks:
        raise AnthropicGenerationError("Anthropic returned no text content.")
    return "\n".join(chunks).strip()


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

    raise AnthropicGenerationError("Could not parse JSON from Anthropic response.")


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
