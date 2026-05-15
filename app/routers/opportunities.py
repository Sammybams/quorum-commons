from fastapi import APIRouter, Depends, HTTPException

from .. import schemas
from ..database import DESC, MongoStore, get_db
from ..rbac import require_workspace_permission
from ..services.opportunities import refresh_opportunity_matches, top_matches_for_opportunity


router = APIRouter(prefix="/workspaces/{workspace_id}/opportunities", tags=["opportunities"])


@router.get("", response_model=list[schemas.OpportunityOut])
def list_opportunities(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("opportunities.view")),
):
    workspace = db.find_by_id("workspaces", workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    opportunities = db.find_many("opportunities", {"workspace_id": workspace_id}, sort=[("created_at", DESC)], limit=100)
    return [_opportunity_out(db, opportunity) for opportunity in opportunities]


@router.post("/{opportunity_id}/refresh-matches", response_model=schemas.OpportunityMatchRefreshResult)
def refresh_matches(
    workspace_id: int,
    opportunity_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("opportunities.manage")),
):
    opportunity = db.find_one("opportunities", {"workspace_id": workspace_id, "id": opportunity_id})
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    refresh_opportunity_matches(db, opportunity=opportunity)
    return schemas.OpportunityMatchRefreshResult(
        message="Opportunity matches refreshed.",
        opportunity=_opportunity_out(db, opportunity),
    )


def _opportunity_out(db: MongoStore, opportunity) -> schemas.OpportunityOut:
    matches = top_matches_for_opportunity(db, workspace_id=opportunity.workspace_id, opportunity_id=opportunity.id, limit=5)
    return schemas.OpportunityOut(
        id=opportunity.id,
        workspace_id=opportunity.workspace_id,
        message_id=opportunity.get("message_id"),
        source=opportunity.get("source") or "manual",
        title=opportunity.title,
        description=opportunity.get("description") or "",
        location=opportunity.get("location"),
        trade_tags=opportunity.get("trade_tags") or [],
        deadline=opportunity.get("deadline"),
        contact=opportunity.get("contact"),
        status=opportunity.get("status") or "open",
        match_count=db.count("opportunity_matches", {"workspace_id": opportunity.workspace_id, "opportunity_id": opportunity.id}),
        matches=[_match_out(match) for match in matches],
        created_at=opportunity.created_at,
    )


def _match_out(match) -> schemas.OpportunityMatchOut:
    return schemas.OpportunityMatchOut(
        id=match.id,
        workspace_id=match.workspace_id,
        opportunity_id=match.opportunity_id,
        member_id=match.member_id,
        member_name=match.get("member_name") or "Unknown member",
        member_role=match.get("member_role") or "Member",
        trade_category=match.get("trade_category"),
        location=match.get("location"),
        availability=match.get("availability"),
        match_score=float(match.get("match_score") or 0),
        fit_label=match.get("fit_label") or "possible fit",
        matched_tags=match.get("matched_tags") or [],
        reasons=match.get("reasons") or [],
        created_at=match.created_at,
    )
