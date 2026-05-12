import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..email import send_password_reset_email, send_verification_email
from .. import models, schemas
from ..database import MongoStore, get_db
from ..demo_seed import ensure_demo_workspace
from ..membership import sync_workspace_members_from_legacy
from ..rbac import ensure_default_roles, get_current_user, hydrate_user
from ..security import (
    create_access_token,
    create_email_token,
    create_refresh_token,
    create_reset_token,
    decode_signed_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
NOISY_WORKSPACE_MARKERS = ("test", "demo", "sample", "http", "sandbox")


def _creator_title_label(value: str | None) -> str:
    mapping = {
        "president_lead": "President / Lead",
        "president": "President / Lead",
        "secretary": "Secretary",
    }
    return mapping.get((value or "").strip().lower(), "President / Lead")


def _auth_response(db: MongoStore, workspace: models.Workspace, membership: models.WorkspaceMember) -> schemas.AuthLoginResponse:
    user = db.find_by_id("users", membership.user_id)
    role = db.find_by_id("roles", membership.role_id)
    hydrate_user(db, user)
    access_token, refresh_token = _issue_session_tokens(db, user.id, workspace.id, membership.id, role.key)
    return schemas.AuthLoginResponse(
        workspace_slug=workspace.slug,
        workspace_name=workspace.name,
        member_id=membership.id,
        member_name=user.full_name,
        member_role=role.name,
        user_id=membership.user_id,
        role_key=role.key,
        access_token=access_token,
        refresh_token=refresh_token,
        workspaces=[_workspace_member_out(item) for item in user.workspace_memberships],
    )


def _workspace_member_out(membership: models.WorkspaceMember) -> schemas.AuthMeWorkspace:
    return schemas.AuthMeWorkspace(
        workspace_slug=membership.workspace.slug,
        workspace_name=membership.workspace.name,
        member_id=membership.id,
        role=membership.role.name,
        role_key=membership.role.key,
        permissions=membership.role.permissions,
    )


def _membership_sort_key(membership: models.WorkspaceMember) -> tuple[int, str]:
    workspace = membership.get("workspace")
    name = workspace.name.lower() if workspace else ""
    slug = workspace.slug.lower() if workspace else ""
    noisy = 1 if any(marker in f"{name} {slug}" for marker in NOISY_WORKSPACE_MARKERS) else 0
    return noisy, name


def _load_memberships(db: MongoStore, user_id: int) -> list[models.WorkspaceMember]:
    memberships = db.find_many("workspace_members", {"user_id": user_id, "status": "active"})
    for membership in memberships:
        membership.workspace = db.find_by_id("workspaces", membership.workspace_id)
        membership.role = db.find_by_id("roles", membership.role_id)
    memberships = [membership for membership in memberships if membership.workspace and membership.role]
    return sorted(memberships, key=_membership_sort_key)


def _sync_memberships_for_email(db: MongoStore, email: str) -> None:
    legacy_members = db.find_many("members", {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}})
    workspace_ids = {member.workspace_id for member in legacy_members if member.get("workspace_id")}
    for workspace_id in workspace_ids:
        workspace = db.find_by_id("workspaces", workspace_id)
        if not workspace:
            continue
        ensure_default_roles(db, workspace.id)
        sync_workspace_members_from_legacy(db, workspace)


def _issue_session_tokens(
    db: MongoStore,
    user_id: int,
    workspace_id: int | None,
    member_id: int | None,
    role_key: str | None,
) -> tuple[str, str]:
    access_token = create_access_token(str(user_id), {"workspace_id": workspace_id, "member_id": member_id, "role": role_key})
    refresh_token = create_refresh_token(str(user_id), {"workspace_id": workspace_id, "member_id": member_id, "role": role_key})
    access_payload = decode_signed_token(access_token, expected_type="access")
    refresh_payload = decode_signed_token(refresh_token, expected_type="refresh")
    db.insert(
        "auth_sessions",
        {
            "user_id": user_id,
            "workspace_id": workspace_id,
            "member_id": member_id,
            "role_key": role_key,
            "access_jti": access_payload["jti"] if access_payload else None,
            "refresh_jti": refresh_payload["jti"] if refresh_payload else None,
            "expires_at": datetime.utcfromtimestamp(refresh_payload["exp"]) if refresh_payload else None,
            "revoked_at": None,
        },
    )
    return access_token, refresh_token


def _create_email_verification(db: MongoStore, user: models.User) -> None:
    token = create_email_token(str(user.id))
    payload = decode_signed_token(token, expected_type="email_verification")
    db.insert(
        "email_verification_tokens",
        {
            "user_id": user.id,
            "token": token,
            "expires_at": datetime.utcfromtimestamp(payload["exp"]) if payload else None,
            "used_at": None,
        },
    )
    send_verification_email(to_email=user.email, full_name=user.full_name, token=token)


def _create_password_reset(db: MongoStore, user: models.User) -> None:
    token = create_reset_token(str(user.id))
    payload = decode_signed_token(token, expected_type="password_reset")
    db.insert(
        "password_reset_tokens",
        {
            "user_id": user.id,
            "token": token,
            "expires_at": datetime.utcfromtimestamp(payload["exp"]) if payload else None,
            "used_at": None,
        },
    )
    send_password_reset_email(to_email=user.email, full_name=user.full_name, token=token)


@router.post("/register", response_model=schemas.AuthLoginResponse, status_code=201)
def register(payload: schemas.AuthRegisterRequest, db: MongoStore = Depends(get_db)):
    workspace_slug = payload.workspace_slug.strip().lower()
    admin_email = payload.admin_email.strip().lower()

    if db.find_one("workspaces", {"slug": workspace_slug}):
        raise HTTPException(status_code=409, detail="Workspace slug already exists")
    if db.find_one("users", {"email": admin_email}):
        raise HTTPException(status_code=409, detail="This email already belongs to an account")

    description_parts = [payload.university, payload.body_type, payload.faculty]
    description = " · ".join([part.strip() for part in description_parts if part and part.strip()]) or None

    user = db.insert(
        "users",
        {
            "full_name": payload.admin_name.strip(),
            "email": admin_email,
            "phone": payload.phone_number.strip() if payload.phone_number else None,
            "password_hash": hash_password(payload.password or ""),
            "email_verified": False,
        },
    )
    workspace = db.insert(
        "workspaces",
        {"name": payload.organization_name.strip(), "slug": workspace_slug, "description": description, "owner_user_id": user.id},
    )

    roles = ensure_default_roles(db, workspace.id)
    owner_role = roles["owner"]

    membership = db.insert(
        "workspace_members",
        {
            "workspace_id": workspace.id,
            "user_id": user.id,
            "role_id": owner_role.id,
            "level": _creator_title_label(payload.admin_role),
            "dues_status": "paid",
            "is_general_member": False,
            "status": "active",
        },
    )

    db.insert(
        "members",
        {
            "workspace_id": workspace.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": owner_role.name,
            "level": _creator_title_label(payload.admin_role),
            "dues_status": "paid",
        },
    )
    _create_email_verification(db, user)

    return _auth_response(db, workspace, membership)


@router.post("/login", response_model=schemas.AuthLoginResponse)
def login(payload: schemas.AuthLoginRequest, db: MongoStore = Depends(get_db)):
    email = payload.email.strip().lower()
    workspace_slug = payload.workspace_slug.strip().lower() if payload.workspace_slug else None

    user = db.find_one("users", {"email": email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid login details")

    password = payload.password or ""
    if user.get("password_hash"):
        if not verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid login details")
    else:
        if not password:
            raise HTTPException(status_code=401, detail="Password is required")
        user["password_hash"] = hash_password(password)
        db.save("users", user)

    memberships = _load_memberships(db, user.id)
    if workspace_slug:
        memberships = [membership for membership in memberships if membership.workspace.slug == workspace_slug]

    if not memberships:
        _sync_memberships_for_email(db, email)
        memberships = _load_memberships(db, user.id)
        if workspace_slug:
            memberships = [membership for membership in memberships if membership.workspace.slug == workspace_slug]

    if not memberships:
        raise HTTPException(status_code=401, detail="No active workspace membership found")

    if workspace_slug or len(memberships) == 1:
        membership = memberships[0]
        return _auth_response(db, membership.workspace, membership)

    access_token, refresh_token = _issue_session_tokens(db, user.id, None, None, None)
    return schemas.AuthLoginResponse(
        workspace_slug="",
        workspace_name="",
        member_id=0,
        member_name=user.full_name,
        member_role="",
        user_id=user.id,
        role_key=None,
        access_token=access_token,
        refresh_token=refresh_token,
        workspaces=[_workspace_member_out(membership) for membership in memberships],
    )


@router.post("/demo-login", response_model=schemas.AuthLoginResponse)
def demo_login(db: MongoStore = Depends(get_db)):
    workspace, membership = ensure_demo_workspace(db)
    return _auth_response(db, workspace, membership)


@router.get("/me", response_model=schemas.AuthMeResponse)
def me(user: models.User = Depends(get_current_user)):
    return schemas.AuthMeResponse(
        user=user,
        workspaces=[_workspace_member_out(membership) for membership in user.workspace_memberships],
    )


@router.post("/refresh-token", response_model=schemas.AuthLoginResponse)
def refresh_token(payload: schemas.RefreshTokenRequest, db: MongoStore = Depends(get_db)):
    refresh_payload = decode_signed_token(payload.refresh_token, expected_type="refresh")
    if not refresh_payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    session = db.find_one("auth_sessions", {"refresh_jti": refresh_payload["jti"], "revoked_at": None})
    if not session:
        raise HTTPException(status_code=401, detail="Refresh session not found")

    user = db.find_by_id("users", int(refresh_payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    db.update_one("auth_sessions", {"id": session.id}, {"revoked_at": datetime.utcnow()})
    access_token, refresh_token_value = _issue_session_tokens(
        db,
        user.id,
        session.get("workspace_id"),
        session.get("member_id"),
        session.get("role_key"),
    )

    if session.get("workspace_id") and session.get("member_id"):
        workspace = db.find_by_id("workspaces", session.get("workspace_id"))
        membership = db.find_by_id("workspace_members", session.get("member_id"))
        role = db.find_by_id("roles", membership.role_id) if membership else None
        if workspace and membership and role:
            hydrate_user(db, user)
            return schemas.AuthLoginResponse(
                workspace_slug=workspace.slug,
                workspace_name=workspace.name,
                member_id=membership.id,
                member_name=user.full_name,
                member_role=role.name,
                user_id=user.id,
                role_key=role.key,
                access_token=access_token,
                refresh_token=refresh_token_value,
                workspaces=[_workspace_member_out(item) for item in user.workspace_memberships],
            )

    hydrate_user(db, user)
    return schemas.AuthLoginResponse(
        workspace_slug="",
        workspace_name="",
        member_id=0,
        member_name=user.full_name,
        member_role="",
        user_id=user.id,
        role_key=None,
        access_token=access_token,
        refresh_token=refresh_token_value,
        workspaces=[_workspace_member_out(item) for item in user.workspace_memberships],
    )


@router.post("/logout", response_model=schemas.AuthStatusResponse)
def logout(payload: schemas.LogoutRequest, db: MongoStore = Depends(get_db)):
    access_payload = decode_signed_token(payload.access_token or "", expected_type="access") if payload.access_token else None
    refresh_payload = decode_signed_token(payload.refresh_token or "", expected_type="refresh") if payload.refresh_token else None

    if access_payload:
        if not db.find_one("revoked_tokens", {"jti": access_payload["jti"]}):
            db.insert(
                "revoked_tokens",
                {
                    "jti": access_payload["jti"],
                    "expires_at": datetime.utcfromtimestamp(access_payload["exp"]),
                },
            )
    if refresh_payload:
        db.update_one("auth_sessions", {"refresh_jti": refresh_payload["jti"]}, {"revoked_at": datetime.utcnow()})
    return schemas.AuthStatusResponse(message="Signed out")


@router.post("/forgot-password", response_model=schemas.AuthStatusResponse)
def forgot_password(payload: schemas.ForgotPasswordRequest, db: MongoStore = Depends(get_db)):
    user = db.find_one("users", {"email": payload.email.strip().lower()})
    if user:
        _create_password_reset(db, user)
    return schemas.AuthStatusResponse(message="If the account exists, a reset link has been sent.")


@router.post("/reset-password", response_model=schemas.AuthStatusResponse)
def reset_password(payload: schemas.ResetPasswordRequest, db: MongoStore = Depends(get_db)):
    token_payload = decode_signed_token(payload.token, expected_type="password_reset")
    if not token_payload:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    reset_record = db.find_one("password_reset_tokens", {"token": payload.token, "used_at": None})
    if not reset_record:
        raise HTTPException(status_code=400, detail="Reset token has already been used")

    user = db.find_by_id("users", int(token_payload["sub"]))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.update_one("users", {"id": user.id}, {"password_hash": hash_password(payload.password)})
    db.update_one("password_reset_tokens", {"id": reset_record.id}, {"used_at": datetime.utcnow()})
    db.update_one("auth_sessions", {"user_id": user.id, "revoked_at": None}, {"revoked_at": datetime.utcnow()})
    return schemas.AuthStatusResponse(message="Password updated successfully.")


@router.post("/verify-email", response_model=schemas.AuthStatusResponse)
def verify_email(payload: schemas.VerifyEmailRequest, db: MongoStore = Depends(get_db)):
    token_payload = decode_signed_token(payload.token, expected_type="email_verification")
    if not token_payload:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    verification = db.find_one("email_verification_tokens", {"token": payload.token, "used_at": None})
    if not verification:
        raise HTTPException(status_code=400, detail="Verification token has already been used")
    user = db.find_by_id("users", int(token_payload["sub"]))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.update_one("users", {"id": user.id}, {"email_verified": True})
    db.update_one("email_verification_tokens", {"id": verification.id}, {"used_at": datetime.utcnow()})
    return schemas.AuthStatusResponse(message="Email verified.")
