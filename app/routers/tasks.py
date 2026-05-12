from fastapi import APIRouter, Depends, HTTPException

from .. import schemas
from ..database import DESC, MongoStore, get_db
from ..rbac import get_current_user, require_workspace_permission

router = APIRouter(prefix="/workspaces/{workspace_id}/tasks", tags=["tasks"])


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


@router.get("", response_model=list[schemas.TaskOut])
def list_tasks(workspace_id: int, db: MongoStore = Depends(get_db)):
    tasks = db.find_many("tasks", {"workspace_id": workspace_id}, sort=[("created_at", DESC)])
    return [_task_out(db, task) for task in tasks]


@router.get("/my", response_model=list[schemas.TaskOut])
def my_tasks(
    workspace_id: int,
    user=Depends(get_current_user),
    db: MongoStore = Depends(get_db),
):
    membership = db.find_one("workspace_members", {"workspace_id": workspace_id, "user_id": user.id, "status": "active"})
    if not membership:
        raise HTTPException(status_code=403, detail="Membership not found")
    tasks = db.find_many("tasks", {"workspace_id": workspace_id, "assigned_to_member_id": membership.id}, sort=[("created_at", DESC)])
    return [_task_out(db, task) for task in tasks]


@router.post("", response_model=schemas.TaskOut, status_code=201)
def create_task(
    workspace_id: int,
    payload: schemas.TaskCreate,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("tasks.assign")),
):
    task = db.insert(
        "tasks",
        {"workspace_id": workspace_id, "created_by_user_id": membership.user_id, **payload.model_dump()},
    )
    return _task_out(db, task)


@router.patch("/{task_id}", response_model=schemas.TaskOut)
def update_task(
    workspace_id: int,
    task_id: int,
    payload: schemas.TaskUpdate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("tasks.assign")),
):
    task = db.find_one("tasks", {"id": task_id, "workspace_id": workspace_id})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.update(payload.model_dump(exclude_unset=True))
    task = db.save("tasks", task)
    return _task_out(db, task)
