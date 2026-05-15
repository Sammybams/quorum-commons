from datetime import datetime

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
    membership=Depends(require_workspace_permission("opportunities.view")),
):
    workspace = db.find_by_id("workspaces", workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    opportunities = db.find_many("opportunities", {"workspace_id": workspace_id}, sort=[("created_at", DESC)], limit=100)
    can_manage = bool(getattr(membership, "role", None) and "opportunities.manage" in membership.role.permissions)
    return [_opportunity_out(db, opportunity, member_id=membership.id, include_all_matches=can_manage) for opportunity in opportunities]


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
        opportunity=_opportunity_out(db, opportunity, include_all_matches=True),
    )


@router.post("/{opportunity_id}/respond", response_model=schemas.OpportunityOut)
def respond_to_opportunity(
    workspace_id: int,
    opportunity_id: int,
    payload: schemas.OpportunityMemberResponseRequest,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("opportunities.view")),
):
    opportunity = db.find_one("opportunities", {"workspace_id": workspace_id, "id": opportunity_id})
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    match = db.find_one("opportunity_matches", {"workspace_id": workspace_id, "opportunity_id": opportunity_id, "member_id": membership.id})
    role = db.find_by_id("roles", membership.role_id)
    user = db.find_by_id("users", membership.user_id)
    if not user or not role:
        raise HTTPException(status_code=404, detail="Member context not found")

    if not match:
        match = db.insert(
            "opportunity_matches",
            {
                "workspace_id": workspace_id,
                "opportunity_id": opportunity_id,
                "member_id": membership.id,
                "member_name": user.full_name,
                "member_role": role.name,
                "trade_category": membership.get("trade_category"),
                "location": membership.get("location"),
                "availability": membership.get("availability"),
                "match_score": 0.45,
                "fit_label": "member interest",
                "matched_tags": [],
                "reasons": ["Member responded directly to this opportunity."],
                "status": payload.status,
                "note": payload.note.strip() if payload.note else None,
                "updated_at": datetime.utcnow(),
            },
        )
    else:
        match["status"] = payload.status
        match["note"] = payload.note.strip() if payload.note else match.get("note")
        match["updated_at"] = datetime.utcnow()
        db.save("opportunity_matches", match)

    return _opportunity_out(db, opportunity, member_id=membership.id, include_all_matches=False)


@router.post("/{opportunity_id}/matches/{match_id}/status", response_model=schemas.OpportunityMatchOut)
def update_opportunity_match_status(
    workspace_id: int,
    opportunity_id: int,
    match_id: int,
    payload: schemas.OpportunityMatchStatusUpdateRequest,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("opportunities.manage")),
):
    match = db.find_one("opportunity_matches", {"workspace_id": workspace_id, "opportunity_id": opportunity_id, "id": match_id})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    match["status"] = payload.status
    match["note"] = payload.note.strip() if payload.note else match.get("note")
    match["updated_at"] = datetime.utcnow()
    saved = db.save("opportunity_matches", match)
    return _match_out(saved)


def _opportunity_out(db: MongoStore, opportunity, *, member_id: int | None = None, include_all_matches: bool = False) -> schemas.OpportunityOut:
    matches = top_matches_for_opportunity(db, workspace_id=opportunity.workspace_id, opportunity_id=opportunity.id, limit=5)
    my_match = None
    if member_id is not None:
        found = db.find_one("opportunity_matches", {"workspace_id": opportunity.workspace_id, "opportunity_id": opportunity.id, "member_id": member_id})
        my_match = _match_out(found) if found else None
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
        matches=[_match_out(match) for match in matches] if include_all_matches else [],
        my_match=my_match,
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
        status=match.get("status") or "recommended",
        matched_tags=match.get("matched_tags") or [],
        reasons=match.get("reasons") or [],
        note=match.get("note"),
        created_at=match.created_at,
    )
