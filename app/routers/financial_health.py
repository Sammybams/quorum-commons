from fastapi import APIRouter, Depends, HTTPException

from .. import schemas
from ..database import DESC, MongoStore, get_db
from ..rbac import require_workspace_permission
from ..services.financial_health import (
    build_financial_health_snapshot,
    build_partner_profile,
    list_financial_health_history,
    store_financial_health_snapshot,
)


router = APIRouter(prefix="/workspaces/{workspace_id}/financial-health", tags=["financial-health"])


@router.get("", response_model=schemas.FinancialHealthSnapshotOut)
def get_financial_health(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("reports.view")),
):
    workspace = db.find_by_id("workspaces", workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    latest = db.find_many("financial_health_snapshots", {"workspace_id": workspace_id}, sort=[("created_at", DESC)], limit=1)
    snapshot = latest[0] if latest else build_financial_health_snapshot(db, workspace=workspace)
    history = list_financial_health_history(db, workspace_id=workspace_id)
    return _snapshot_out(snapshot, history=history or [snapshot])


@router.post("/refresh", response_model=schemas.FinancialHealthSnapshotOut)
def refresh_financial_health(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("reports.generate")),
):
    workspace = db.find_by_id("workspaces", workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    snapshot = build_financial_health_snapshot(db, workspace=workspace)
    stored = store_financial_health_snapshot(db, snapshot=snapshot)
    history = list_financial_health_history(db, workspace_id=workspace_id)
    return _snapshot_out(stored, history=history)


def _snapshot_out(snapshot, *, history: list[dict] | None = None) -> schemas.FinancialHealthSnapshotOut:
    history_items = history or [snapshot]
    return schemas.FinancialHealthSnapshotOut(
        id=snapshot.get("id"),
        workspace_id=int(snapshot.get("workspace_id") or 0),
        overall_score=float(snapshot.get("overall_score") or 0),
        overall_grade=snapshot.get("overall_grade") or "Developing",
        summary=snapshot.get("summary") or "",
        strengths=snapshot.get("strengths") or [],
        watchouts=snapshot.get("watchouts") or [],
        categories=[
            schemas.FinancialHealthCategoryOut(
                category_key=item.get("category_key") or "",
                title=item.get("title") or "",
                score=float(item.get("score") or 0),
                status=item.get("status") or "watch",
                summary=item.get("summary") or "",
            )
            for item in (snapshot.get("categories") or [])
        ],
        key_metrics=[
            schemas.FinancialHealthMetricOut(
                key=item.get("key") or "",
                label=item.get("label") or "",
                value=item.get("value") or "",
                trend=item.get("trend") or "steady",
            )
            for item in (snapshot.get("key_metrics") or [])
        ],
        evidence_trail=[
            schemas.FinancialHealthEvidenceOut(
                evidence_type=item.get("evidence_type") or "general",
                title=item.get("title") or "",
                detail=item.get("detail") or "",
                linked_record_label=item.get("linked_record_label"),
                verification_state=item.get("verification_state"),
                created_at=item.get("created_at"),
            )
            for item in (snapshot.get("evidence_trail") or [])
        ],
        history=[
            schemas.FinancialHealthHistoryPointOut(
                label=item.get("created_at").strftime("%b %d") if item.get("created_at") else "Now",
                overall_score=float(item.get("overall_score") or 0),
                overall_grade=item.get("overall_grade") or "Developing",
                created_at=item.get("created_at"),
            )
            for item in history_items
        ],
        partner_profile=schemas.FinancialHealthPartnerProfileOut(**build_partner_profile(snapshot=snapshot, history=history_items)),
        created_at=snapshot.get("created_at"),
    )
