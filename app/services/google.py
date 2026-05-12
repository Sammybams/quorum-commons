from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from ..email import EmailResult, build_invitation_email


load_dotenv()


GOOGLE_GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"

GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/meetings.space.created",
    "https://www.googleapis.com/auth/meetings.space.readonly",
    GOOGLE_GMAIL_SEND_SCOPE,
]


class GoogleIntegrationError(RuntimeError):
    pass


@dataclass
class GoogleTokenBundle:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scope: str
    id_token: str | None = None


@dataclass
class GoogleUserProfile:
    email: str | None
    name: str | None


@dataclass
class GoogleMeetSpace:
    name: str
    meeting_uri: str


def google_scope_set(scope_value: str | None) -> set[str]:
    return {scope.strip() for scope in (scope_value or "").split() if scope.strip()}


def google_configured() -> bool:
    return bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))


def google_redirect_uri() -> str:
    explicit = os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
    if explicit:
        return explicit
    backend_base = os.getenv("BACKEND_PUBLIC_URL") or "http://localhost:8000"
    api_prefix = (os.getenv("API_PREFIX") or "/api/v1").rstrip("/")
    return f"{backend_base.rstrip('/')}{api_prefix}/integrations/google/callback"


def build_google_authorization_url(*, state: str) -> str:
    if not google_configured():
        raise GoogleIntegrationError("Google OAuth is not configured.")
    query = urlencode(
        {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "redirect_uri": google_redirect_uri(),
            "response_type": "code",
            "scope": " ".join(GOOGLE_SCOPES),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
    )
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"


def exchange_google_code(*, code: str) -> GoogleTokenBundle:
    if not google_configured():
        raise GoogleIntegrationError("Google OAuth is not configured.")
    payload = urlencode(
        {
            "code": code,
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "redirect_uri": google_redirect_uri(),
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    data = _google_request("https://oauth2.googleapis.com/token", method="POST", data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
    return _token_bundle(data)


def refresh_google_token(*, refresh_token: str) -> GoogleTokenBundle:
    payload = urlencode(
        {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    data = _google_request("https://oauth2.googleapis.com/token", method="POST", data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
    return _token_bundle(data)


def get_google_profile(*, access_token: str) -> GoogleUserProfile:
    data = _google_request(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    return GoogleUserProfile(email=data.get("email"), name=data.get("name"))


def create_google_meet_space(*, access_token: str) -> GoogleMeetSpace:
    data = _google_request(
        "https://meet.googleapis.com/v2/spaces",
        method="POST",
        data=json.dumps({}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )
    return GoogleMeetSpace(name=data["name"], meeting_uri=data["meetingUri"])


def latest_conference_record_for_space(*, access_token: str, space_name: str) -> dict | None:
    filter_query = urlencode({"pageSize": 10, "filter": f'space.name = "{space_name}"'})
    data = _google_request(
        f"https://meet.googleapis.com/v2/conferenceRecords?{filter_query}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    records = data.get("conferenceRecords") or []
    return records[0] if records else None


def latest_transcript_for_conference(*, access_token: str, conference_record_name: str) -> dict | None:
    data = _google_request(
        f"https://meet.googleapis.com/v2/{conference_record_name}/transcripts?pageSize=10",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    transcripts = data.get("transcripts") or []
    file_ready = [item for item in transcripts if item.get("state") == "FILE_GENERATED"]
    return (file_ready or transcripts or [None])[0]


def google_doc_text(*, access_token: str, document_id: str) -> str:
    document = _google_request(
        f"https://docs.googleapis.com/v1/documents/{document_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    body = document.get("body", {}).get("content", [])
    parts: list[str] = []
    for item in body:
        paragraph = item.get("paragraph")
        if not paragraph:
            continue
        text_run = []
        for element in paragraph.get("elements", []):
            content = element.get("textRun", {}).get("content")
            if content:
                text_run.append(content)
        block = "".join(text_run).strip()
        if block:
            parts.append(block)
    return "\n".join(parts).strip()


def access_token_for_integration(integration) -> tuple[str, datetime | None]:
    access_token = integration.get("access_token")
    expires_at = integration.get("expires_at")
    refresh_token = integration.get("refresh_token")
    now = datetime.utcnow() + timedelta(seconds=60)
    if access_token and (expires_at is None or expires_at > now):
        return access_token, expires_at
    if not refresh_token:
        raise GoogleIntegrationError("Google connection has expired and no refresh token is stored.")
    refreshed = refresh_google_token(refresh_token=refresh_token)
    integration["access_token"] = refreshed.access_token
    if refreshed.refresh_token:
        integration["refresh_token"] = refreshed.refresh_token
    integration["expires_at"] = refreshed.expires_at
    integration["scope"] = refreshed.scope
    integration["updated_at"] = datetime.utcnow()
    return refreshed.access_token, refreshed.expires_at


def gmail_send_available(integration) -> bool:
    if not integration or integration.get("status") != "connected":
        return False
    return GOOGLE_GMAIL_SEND_SCOPE in google_scope_set(integration.get("scope"))


def send_gmail_invitation(
    *,
    access_token: str,
    connected_email: str,
    sender_name: str,
    to_email: str,
    workspace_name: str,
    role_name: str,
    token: str,
    note: str | None = None,
    reply_to: str | None = None,
) -> EmailResult:
    if not connected_email:
        return EmailResult(status="failed", error="Connected Google account email was not available.", provider="google")

    message = build_invitation_email(
        to_email=to_email,
        workspace_name=workspace_name,
        role_name=role_name,
        token=token,
        note=note,
        reply_to=reply_to,
        from_email=connected_email,
        from_name=sender_name,
    )

    try:
        send_gmail_message(access_token=access_token, message=message)
    except GoogleIntegrationError as exc:
        return EmailResult(status="failed", error=str(exc)[:500], provider="google", sender=connected_email)

    return EmailResult(status="sent", provider="google", sender=connected_email)


def send_gmail_message(*, access_token: str, message: EmailMessage) -> dict:
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8").rstrip("=")
    return _google_request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        method="POST",
        data=json.dumps({"raw": raw_message}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )


def _google_request(url: str, *, method: str = "GET", data: bytes | None = None, headers: dict[str, str] | None = None) -> dict:
    request = Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GoogleIntegrationError(detail or str(exc)) from exc
    except URLError as exc:
        raise GoogleIntegrationError(str(exc.reason)) from exc
    return json.loads(raw)


def _token_bundle(payload: dict) -> GoogleTokenBundle:
    expires_in = payload.get("expires_in")
    expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in)) if expires_in else None
    return GoogleTokenBundle(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=expires_at,
        scope=payload.get("scope", ""),
        id_token=payload.get("id_token"),
    )
