import re

from fastapi import APIRouter, Depends, HTTPException

from .. import models, schemas
from ..database import ASC, MongoStore, get_db
from ..rbac import ensure_default_roles, require_workspace_permission

router = APIRouter(prefix="/workspaces/{workspace_id}/roles", tags=["roles"])


@router.get("", response_model=list[schemas.RoleOut])
def list_roles(workspace_id: int, db: MongoStore = Depends(get_db)):
    ensure_default_roles(db, workspace_id)
    roles = db.find_many("roles", {"workspace_id": workspace_id}, sort=[("created_at", ASC)])
    return [_role_out(role) for role in roles]


@router.post("", response_model=schemas.RoleOut)
def create_role(
    workspace_id: int,
    payload: schemas.RoleCreate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("roles.manage")),
):
    if not db.find_by_id("workspaces", workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")

    key = _slugify(payload.name)
    if db.find_one("roles", {"workspace_id": workspace_id, "key": key}):
        raise HTTPException(status_code=409, detail="Role already exists")

    role = db.insert(
        "roles",
        {
            "workspace_id": workspace_id,
            "key": key,
            "name": payload.name.strip(),
            "description": payload.description,
            "is_system_role": False,
            "permissions": sorted(set(payload.permissions)),
        },
    )
    return _role_out(role)


@router.patch("/{role_id}", response_model=schemas.RoleOut)
def update_role(
    workspace_id: int,
    role_id: int,
    payload: schemas.RoleUpdate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("roles.manage")),
):
    role = db.find_one("roles", {"workspace_id": workspace_id, "id": role_id})
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if payload.name is not None:
        role["name"] = payload.name.strip()
        if not role.get("is_system_role"):
            role["key"] = _slugify(payload.name)
    if payload.description is not None:
        role["description"] = payload.description
    if payload.permissions is not None:
        role["permissions"] = sorted(set(payload.permissions))

    return _role_out(db.save("roles", role))


def _role_out(role: models.Role) -> schemas.RoleOut:
    return schemas.RoleOut(
        id=role.id,
        workspace_id=role.workspace_id,
        key=role.key,
        name=role.name,
        description=role.get("description"),
        is_system_role=role.get("is_system_role", False),
        permissions=role.permissions,
        created_at=role.created_at,
    )


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return normalized.strip("_") or "custom_role"
