from __future__ import annotations

import os
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from .. import schemas
from ..database import MongoStore, get_db
from ..rbac import require_workspace_permission
from ..security import create_signed_token, decode_signed_token
from ..services.google import (
    GOOGLE_SCOPES,
    GoogleIntegrationError,
    build_google_authorization_url,
    exchange_google_code,
    gmail_send_available,
    get_google_profile,
    google_configured,
)
from ..services.fireflies import fireflies_configured


router = APIRouter(prefix="/workspaces/{workspace_id}/integrations", tags=["integrations"])
callback_router = APIRouter(tags=["integrations"])


def _frontend_base() -> str:
    return (
        os.getenv("FRONTEND_URL")
        or os.getenv("PUBLIC_APP_URL")
        or os.getenv("APP_URL")
        or "http://localhost:3000"
    ).rstrip("/")


def _google_integration_out(workspace_id: int, integration) -> schemas.IntegrationOut:
    metadata = {
        "meet": "available",
        "drive": "available",
        "gmail": "available" if gmail_send_available(integration) else ("reconnect_required" if integration else "available"),
    }
    return schemas.IntegrationOut(
        provider="google_workspace",
        status=integration.get("status", "not_connected") if integration else "not_connected",
        configured=google_configured(),
        connected_email=integration.get("connected_email") if integration else None,
        scopes=str(integration.get("scope") or "").split() if integration else [],
        connected_at=integration.get("connected_at") if integration else None,
        expires_at=integration.get("expires_at") if integration else None,
        metadata={**((integration.get("metadata") if integration else None) or {}), **metadata},
    )


@router.get("", response_model=list[schemas.IntegrationOut])
def list_integrations(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    google = db.find_one("integrations", {"workspace_id": workspace_id, "provider": "google_workspace"})
    return [
        _google_integration_out(workspace_id, google),
        schemas.IntegrationOut(
            provider="fireflies",
            status="configured" if fireflies_configured() else "not_configured",
            configured=fireflies_configured(),
            connected_email=None,
            scopes=[],
            connected_at=None,
            expires_at=None,
            metadata={"mode": "server_key", "import": "transcript_id"},
        ),
    ]


@router.post("/google/oauth/start", response_model=schemas.GoogleOAuthStartOut)
def start_google_oauth(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("integrations.manage")),
):
    workspace = db.find_by_id("workspaces", workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if not google_configured():
        raise HTTPException(status_code=400, detail="Google OAuth is not configured on the server")

    state = create_signed_token(
        str(workspace_id),
        900,
        {
            "type": "google_oauth",
            "workspace_id": workspace_id,
            "workspace_slug": workspace.slug,
            "user_id": membership.user_id,
        },
    )
    return schemas.GoogleOAuthStartOut(authorization_url=build_google_authorization_url(state=state))


@router.delete("/google", response_model=schemas.AuthStatusResponse)
def disconnect_google(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    db.delete_one("integrations", {"workspace_id": workspace_id, "provider": "google_workspace"})
    return schemas.AuthStatusResponse(message="Google Workspace disconnected.")


@callback_router.get("/integrations/google/callback")
def google_oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None, db: MongoStore = Depends(get_db)):
    if not state:
        raise HTTPException(status_code=400, detail="Missing OAuth state.")
    state_payload = decode_signed_token(state, expected_type="google_oauth")
    if not state_payload:
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")

    workspace_id = int(state_payload["workspace_id"])
    workspace_slug = state_payload.get("workspace_slug") or ""
    redirect_base = f"{_frontend_base()}/{workspace_slug}/settings/integrations"
    if error:
        return RedirectResponse(url=f"{redirect_base}?provider=google_workspace&status=error&message={quote(error)}", status_code=302)
    if not code:
        return RedirectResponse(url=f"{redirect_base}?provider=google_workspace&status=error&message={quote('Missing OAuth code')}", status_code=302)

    try:
        tokens = exchange_google_code(code=code)
        profile = get_google_profile(access_token=tokens.access_token)
    except GoogleIntegrationError as exc:
        return RedirectResponse(
            url=f"{redirect_base}?provider=google_workspace&status=error&message={quote(str(exc)[:180])}",
            status_code=302,
        )

    existing = db.find_one("integrations", {"workspace_id": workspace_id, "provider": "google_workspace"})
    payload = {
        "workspace_id": workspace_id,
        "provider": "google_workspace",
        "status": "connected",
        "connected_email": profile.email,
        "connected_name": profile.name,
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token or (existing.get("refresh_token") if existing else None),
        "expires_at": tokens.expires_at,
        "scope": tokens.scope or " ".join(GOOGLE_SCOPES),
        "metadata": {"meet": "available", "drive": "available", "gmail": "available"},
        "connected_at": existing.get("connected_at") if existing else datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    if existing:
        existing.update(payload)
        db.save("integrations", existing)
    else:
        db.insert("integrations", payload)

    return RedirectResponse(url=f"{redirect_base}?provider=google_workspace&status=connected", status_code=302)
