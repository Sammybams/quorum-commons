from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


load_dotenv()


class FirefliesError(RuntimeError):
    pass


@dataclass
class FirefliesTranscript:
    transcript_id: str
    title: str | None
    transcript_text: str
    participants: list[str]


def fireflies_configured() -> bool:
    return bool(os.getenv("FIREFLIES_API_KEY"))


def fetch_fireflies_transcript(*, transcript_id: str) -> FirefliesTranscript:
    api_key = os.getenv("FIREFLIES_API_KEY")
    if not api_key:
        raise FirefliesError("FIREFLIES_API_KEY is not configured.")

    query = """
    query TranscriptById($transcriptId: String!) {
      transcript(id: $transcriptId) {
        id
        title
        sentences {
          text
        }
        participants
      }
    }
    """
    payload = json.dumps({"query": query, "variables": {"transcriptId": transcript_id}}).encode("utf-8")
    request = Request(
        "https://api.fireflies.ai/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FirefliesError(detail or str(exc)) from exc
    except URLError as exc:
        raise FirefliesError(str(exc.reason)) from exc

    data = json.loads(raw)
    if data.get("errors"):
        raise FirefliesError(str(data["errors"][0].get("message") or "Fireflies query failed"))
    transcript = data.get("data", {}).get("transcript")
    if not transcript:
        raise FirefliesError("Transcript not found in Fireflies.")

    transcript_text = "\n".join(
        sentence.get("text", "").strip() for sentence in transcript.get("sentences", []) if sentence.get("text")
    ).strip()
    if not transcript_text:
        raise FirefliesError("Fireflies transcript has no sentence text yet.")

    return FirefliesTranscript(
        transcript_id=str(transcript.get("id") or transcript_id),
        title=transcript.get("title"),
        transcript_text=transcript_text,
        participants=[participant for participant in transcript.get("participants", []) if participant],
    )
