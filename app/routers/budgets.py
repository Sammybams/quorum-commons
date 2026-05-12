from fastapi import APIRouter, Depends, HTTPException, Response

from .. import schemas
from ..database import DESC, MongoStore, get_db
from ..rbac import require_workspace_permission

router = APIRouter(prefix="/workspaces/{workspace_id}/budgets", tags=["budgets"])


def _budget_out(db: MongoStore, budget) -> schemas.BudgetOut:
    lines = db.find_many("budget_lines", {"budget_id": budget.id})
    planned_total = sum(float(line.get("planned_amount", 0)) for line in lines)
    actual_total = sum(float(line.get("actual_amount", 0)) for line in lines)
    return schemas.BudgetOut(
        id=budget.id,
        workspace_id=budget.workspace_id,
        name=budget.name,
        description=budget.get("description"),
        period_label=budget.get("period_label"),
        status=budget.get("status", "draft"),
        planned_total=planned_total,
        actual_total=actual_total,
        created_at=budget.created_at,
    )


def _line_out(line) -> schemas.BudgetLineOut:
    return schemas.BudgetLineOut(
        id=line.id,
        budget_id=line.budget_id,
        name=line.name,
        planned_amount=float(line.get("planned_amount", 0)),
        actual_amount=float(line.get("actual_amount", 0)),
        notes=line.get("notes"),
        created_at=line.created_at,
    )


def _budget_or_404(db: MongoStore, workspace_id: int, budget_id: int):
    budget = db.find_one("budgets", {"id": budget_id, "workspace_id": workspace_id})
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


@router.get("", response_model=list[schemas.BudgetOut])
def list_budgets(workspace_id: int, db: MongoStore = Depends(get_db)):
    budgets = db.find_many("budgets", {"workspace_id": workspace_id}, sort=[("created_at", DESC)])
    return [_budget_out(db, budget) for budget in budgets]


@router.post("", response_model=schemas.BudgetOut, status_code=201)
def create_budget(
    workspace_id: int,
    payload: schemas.BudgetCreate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("budgets.manage")),
):
    budget = db.insert("budgets", {"workspace_id": workspace_id, "status": "draft", **payload.model_dump()})
    return _budget_out(db, budget)


@router.get("/{budget_id}", response_model=schemas.BudgetDetailOut)
def get_budget(workspace_id: int, budget_id: int, db: MongoStore = Depends(get_db)):
    budget = _budget_or_404(db, workspace_id, budget_id)
    lines = db.find_many("budget_lines", {"budget_id": budget.id}, sort=[("created_at", DESC)])
    return schemas.BudgetDetailOut(**_budget_out(db, budget).model_dump(), lines=[_line_out(line) for line in lines])


@router.patch("/{budget_id}", response_model=schemas.BudgetOut)
def update_budget(
    workspace_id: int,
    budget_id: int,
    payload: schemas.BudgetUpdate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("budgets.manage")),
):
    budget = _budget_or_404(db, workspace_id, budget_id)
    budget.update(payload.model_dump(exclude_unset=True))
    budget = db.save("budgets", budget)
    return _budget_out(db, budget)


@router.post("/{budget_id}/lines", response_model=schemas.BudgetLineOut, status_code=201)
def create_budget_line(
    workspace_id: int,
    budget_id: int,
    payload: schemas.BudgetLineCreate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("budgets.manage")),
):
    _budget_or_404(db, workspace_id, budget_id)
    line = db.insert(
        "budget_lines",
        {
            "budget_id": budget_id,
            "workspace_id": workspace_id,
            "name": payload.name.strip(),
            "planned_amount": payload.planned_amount,
            "actual_amount": 0,
            "notes": payload.notes,
        },
    )
    return _line_out(line)


@router.post("/{budget_id}/lines/{line_id}/expenditures", response_model=schemas.BudgetLineOut, status_code=201)
def log_expenditure(
    workspace_id: int,
    budget_id: int,
    line_id: int,
    payload: schemas.ExpenditureCreate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("budgets.manage")),
):
    _budget_or_404(db, workspace_id, budget_id)
    line = db.find_one("budget_lines", {"id": line_id, "budget_id": budget_id, "workspace_id": workspace_id})
    if not line:
        raise HTTPException(status_code=404, detail="Budget line not found")
    db.insert(
        "expenditures",
        {
            "budget_line_id": line_id,
            "budget_id": budget_id,
            "workspace_id": workspace_id,
            "amount": payload.amount,
            "notes": payload.notes,
            "spent_at": payload.spent_at,
        },
    )
    line["actual_amount"] = float(line.get("actual_amount", 0)) + payload.amount
    line = db.save("budget_lines", line)
    return _line_out(line)


@router.get("/{budget_id}/export")
def export_budget(
    workspace_id: int,
    budget_id: int,
    db: MongoStore = Depends(get_db),
):
    budget = _budget_or_404(db, workspace_id, budget_id)
    lines = db.find_many("budget_lines", {"budget_id": budget.id}, sort=[("created_at", DESC)])
    rows = ["name,planned_amount,actual_amount,notes"]
    for line in lines:
        safe_name = str(line.name).replace('"', '""')
        safe_notes = str(line.get("notes") or "").replace('"', '""')
        rows.append(
            ",".join(
                [
                    f'"{safe_name}"',
                    str(float(line.get("planned_amount", 0))),
                    str(float(line.get("actual_amount", 0))),
                    f'"{safe_notes}"',
                ]
            )
        )
    return Response(
        "\n".join(rows),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{budget.name.lower().replace(" ", "-")}-budget.csv"'},
    )
