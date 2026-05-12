from datetime import datetime, timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException

from .. import models, schemas
from ..database import MongoStore, get_db
from ..email import send_invitation_email
from ..rbac import require_workspace_permission
from ..security import hash_password
from ..services.google import GoogleIntegrationError, access_token_for_integration, gmail_send_available, send_gmail_invitation
from .auth import _auth_response

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["invitations"])
public_router = APIRouter(tags=["invitations"])


@router.post("/invitations", response_model=schemas.InvitationOut, status_code=201)
def create_invitation(
    workspace_id: int,
    payload: schemas.InvitationCreate,
    db: MongoStore = Depends(get_db),
    membership: models.WorkspaceMember = Depends(require_workspace_permission("members.invite")),
):
    role = db.find_one("roles", {"workspace_id": workspace_id, "id": payload.role_id})
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    workspace = db.find_by_id("workspaces", workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    inviter = db.find_by_id("users", membership.user_id)

    invitation = db.insert(
        "invitations",
        {
            "workspace_id": workspace_id,
            "email": payload.email.strip().lower(),
            "role_id": role.id,
            "invited_by_user_id": membership.user_id,
            "token": secrets.token_urlsafe(32),
            "note": payload.note,
            "status": "pending",
            "email_delivery_status": "pending",
            "email_delivery_provider": None,
            "email_delivery_sender": None,
            "expires_at": datetime.utcnow() + timedelta(hours=72),
        },
    )
    email_result = _send_workspace_invitation_email(
        db,
        workspace=workspace,
        inviter=inviter,
        role=role,
        invitation=invitation,
    )
    invitation["email_delivery_status"] = email_result.status
    invitation["email_delivery_provider"] = email_result.provider
    invitation["email_delivery_sender"] = email_result.sender
    if email_result.error:
        invitation["email_delivery_error"] = email_result.error[:500]
    invitation = db.save("invitations", invitation)
    return _invitation_out(db, invitation)


@router.get("/invitations", response_model=list[schemas.InvitationOut])
def list_invitations(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership: models.WorkspaceMember = Depends(require_workspace_permission("members.invite")),
):
    invitations = db.find_many("invitations", {"workspace_id": workspace_id}, sort=[("created_at", -1)])
    return [_invitation_out(db, invitation) for invitation in invitations]


@router.post("/invite-links", response_model=schemas.InviteLinkOut, status_code=201)
def create_invite_link(
    workspace_id: int,
    payload: schemas.InviteLinkCreate,
    db: MongoStore = Depends(get_db),
    _membership: models.WorkspaceMember = Depends(require_workspace_permission("members.invite")),
):
    role = db.find_one("roles", {"workspace_id": workspace_id, "id": payload.role_id})
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    link = db.insert(
        "invite_links",
        {
            "workspace_id": workspace_id,
            "role_id": role.id,
            "token": secrets.token_urlsafe(32),
            "is_active": True,
            "expires_at": payload.expires_at,
        },
    )
    return _invite_link_out(db, link)


@router.get("/invite-links", response_model=list[schemas.InviteLinkOut])
def list_invite_links(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership: models.WorkspaceMember = Depends(require_workspace_permission("members.invite")),
):
    links = db.find_many("invite_links", {"workspace_id": workspace_id}, sort=[("created_at", -1)])
    return [_invite_link_out(db, link) for link in links]


@public_router.get("/invites/{token}", response_model=schemas.InvitePreview)
def preview_invitation(token: str, db: MongoStore = Depends(get_db)):
    invitation = db.find_one("invitations", {"token": token})
    if not invitation or invitation.status != "pending" or _is_expired(invitation.get("expires_at")):
        raise HTTPException(status_code=404, detail="Invitation not found or expired")

    workspace = db.find_by_id("workspaces", invitation.workspace_id)
    role = db.find_by_id("roles", invitation.role_id)
    if not workspace or not role:
        raise HTTPException(status_code=404, detail="Invitation not found")

    return schemas.InvitePreview(
        workspace_name=workspace.name,
        workspace_slug=workspace.slug,
        email=invitation.email,
        role_name=role.name,
        expires_at=invitation.expires_at,
    )


@public_router.post("/invites/{token}/accept", response_model=schemas.AuthLoginResponse)
def accept_invitation(token: str, payload: schemas.InvitationAccept, db: MongoStore = Depends(get_db)):
    invitation = db.find_one("invitations", {"token": token})
    if not invitation or invitation.status != "pending" or _is_expired(invitation.get("expires_at")):
        raise HTTPException(status_code=404, detail="Invitation not found or expired")

    workspace = db.find_by_id("workspaces", invitation.workspace_id)
    role = db.find_by_id("roles", invitation.role_id)
    if not workspace or not role:
        raise HTTPException(status_code=404, detail="Invitation not found")

    user = db.find_one("users", {"email": invitation.email})
    if user is None:
        user = db.insert(
            "users",
            {
                "full_name": payload.full_name.strip(),
                "email": invitation.email,
                "phone": payload.phone_number,
                "password_hash": hash_password(payload.password),
                "email_verified": False,
            },
        )
    else:
        user["full_name"] = payload.full_name.strip()
        user["phone"] = payload.phone_number or user.get("phone")
        user["password_hash"] = hash_password(payload.password)
        user = db.save("users", user)

    membership = _ensure_membership(db, workspace, user, role)
    invitation["status"] = "accepted"
    invitation["accepted_at"] = datetime.utcnow()
    db.save("invitations", invitation)
    return _auth_response(db, workspace, membership)


@public_router.get("/join/{token}", response_model=schemas.InvitePreview)
def preview_invite_link(token: str, db: MongoStore = Depends(get_db)):
    link = db.find_one("invite_links", {"token": token, "is_active": True})
    if not link or _is_expired(link.get("expires_at")):
        raise HTTPException(status_code=404, detail="Invite link not found or expired")

    workspace = db.find_by_id("workspaces", link.workspace_id)
    role = db.find_by_id("roles", link.role_id)
    if not workspace or not role:
        raise HTTPException(status_code=404, detail="Invite link not found")

    return schemas.InvitePreview(
        workspace_name=workspace.name,
        workspace_slug=workspace.slug,
        role_name=role.name,
        expires_at=link.expires_at,
    )


@public_router.post("/join/{token}/accept", response_model=schemas.AuthLoginResponse)
def accept_invite_link(token: str, payload: schemas.InviteLinkAccept, db: MongoStore = Depends(get_db)):
    link = db.find_one("invite_links", {"token": token, "is_active": True})
    if not link or _is_expired(link.get("expires_at")):
        raise HTTPException(status_code=404, detail="Invite link not found or expired")

    workspace = db.find_by_id("workspaces", link.workspace_id)
    role = db.find_by_id("roles", link.role_id)
    if not workspace or not role:
        raise HTTPException(status_code=404, detail="Invite link not found")

    email = payload.email.strip().lower()
    user = db.find_one("users", {"email": email})
    if user is None:
        user = db.insert(
            "users",
            {
                "full_name": payload.full_name.strip(),
                "email": email,
                "phone": payload.phone_number,
                "password_hash": hash_password(payload.password),
                "email_verified": False,
            },
        )
    else:
        user["full_name"] = payload.full_name.strip()
        user["phone"] = payload.phone_number or user.get("phone")
        user["password_hash"] = hash_password(payload.password)
        user = db.save("users", user)

    membership = _ensure_membership(db, workspace, user, role)
    return _auth_response(db, workspace, membership)


def _invitation_out(db: MongoStore, invitation: models.Invitation) -> schemas.InvitationOut:
    role = db.find_by_id("roles", invitation.role_id)
    return schemas.InvitationOut(
        id=invitation.id,
        workspace_id=invitation.workspace_id,
        email=invitation.email,
        role_id=invitation.role_id,
        role_name=role.name if role else "Unknown role",
        token=invitation.token,
        status=invitation.status,
        email_delivery_status=invitation.get("email_delivery_status"),
        email_delivery_provider=invitation.get("email_delivery_provider"),
        email_delivery_sender=invitation.get("email_delivery_sender"),
        expires_at=invitation.get("expires_at"),
        created_at=invitation.created_at,
    )


def _invite_link_out(db: MongoStore, link: models.InviteLink) -> schemas.InviteLinkOut:
    role = db.find_by_id("roles", link.role_id)
    return schemas.InviteLinkOut(
        id=link.id,
        workspace_id=link.workspace_id,
        role_id=link.role_id,
        role_name=role.name if role else "Unknown role",
        token=link.token,
        is_active=link.is_active,
        expires_at=link.get("expires_at"),
        created_at=link.created_at,
    )


def _ensure_membership(
    db: MongoStore,
    workspace: models.Workspace,
    user: models.User,
    role: models.Role,
) -> models.WorkspaceMember:
    membership = db.find_one("workspace_members", {"workspace_id": workspace.id, "user_id": user.id})
    if membership:
        membership["role_id"] = role.id
        membership["status"] = "active"
        membership["is_general_member"] = role.key == "core_member"
        return db.save("workspace_members", membership)

    return db.insert(
        "workspace_members",
        {
            "workspace_id": workspace.id,
            "user_id": user.id,
            "role_id": role.id,
            "is_general_member": role.key == "core_member",
            "dues_status": "defaulter",
            "status": "active",
            "joined_at": datetime.utcnow(),
        },
    )


def _is_expired(expires_at: datetime | None) -> bool:
    return bool(expires_at and expires_at < datetime.utcnow())


def _send_workspace_invitation_email(
    db: MongoStore,
    *,
    workspace: models.Workspace,
    inviter: models.User | None,
    role: models.Role,
    invitation: models.Invitation,
):
    integration = db.find_one("integrations", {"workspace_id": workspace.id, "provider": "google_workspace"})

    if gmail_send_available(integration):
        try:
            access_token, expires_at = access_token_for_integration(integration)
            integration["expires_at"] = expires_at
            integration["updated_at"] = datetime.utcnow()
            db.save("integrations", integration)
            google_result = send_gmail_invitation(
                access_token=access_token,
                connected_email=integration.get("connected_email") or "",
                sender_name=(inviter.full_name if inviter else None) or integration.get("connected_name") or workspace.name,
                to_email=invitation.email,
                workspace_name=workspace.name,
                role_name=role.name,
                token=invitation.token,
                note=invitation.get("note"),
                reply_to=inviter.email if inviter else None,
            )
            if google_result.status == "sent":
                return google_result
            smtp_result = send_invitation_email(
                to_email=invitation.email,
                workspace_name=workspace.name,
                role_name=role.name,
                token=invitation.token,
                note=invitation.get("note"),
                reply_to=inviter.email if inviter else None,
            )
            if smtp_result.status == "sent":
                return type(smtp_result)(
                    status=smtp_result.status,
                    error=google_result.error,
                    provider="smtp_fallback",
                    sender=smtp_result.sender,
                )
            return smtp_result
        except GoogleIntegrationError as exc:
            invitation["email_delivery_error"] = str(exc)[:500]

    return send_invitation_email(
        to_email=invitation.email,
        workspace_name=workspace.name,
        role_name=role.name,
        token=invitation.token,
        note=invitation.get("note"),
        reply_to=inviter.email if inviter else None,
    )
