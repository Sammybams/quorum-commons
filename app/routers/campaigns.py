from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from .. import models, schemas
from ..database import DESC, MongoStore, get_db
from ..rbac import require_workspace_permission

router = APIRouter(prefix="/workspaces/{workspace_id}/campaigns", tags=["campaigns"])


def _campaign_or_404(db: MongoStore, workspace_id: int, campaign_id: int) -> models.Campaign:
    campaign = db.find_one("campaigns", {"id": campaign_id, "workspace_id": workspace_id})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _contribution_out(db: MongoStore, contribution: models.Contribution) -> schemas.ContributionOut:
    stream = db.find_by_id("funding_streams", contribution.get("stream_id"))
    return schemas.ContributionOut(
        id=contribution.id,
        workspace_id=contribution.workspace_id,
        campaign_id=contribution.campaign_id,
        stream_id=contribution.get("stream_id"),
        stream_name=stream.name if stream else None,
        contributor_name=None if contribution.get("is_anonymous") else contribution.get("contributor_name"),
        contributor_email=contribution.get("contributor_email"),
        amount=contribution.amount,
        method=contribution.method,
        gateway_ref=contribution.get("gateway_ref"),
        receipt_url=contribution.get("receipt_url"),
        is_anonymous=contribution.get("is_anonymous", False),
        status=contribution.status,
        confirmed_by_user_id=contribution.get("confirmed_by_user_id"),
        confirmed_at=contribution.get("confirmed_at"),
        created_at=contribution.created_at,
    )


def _stream_out(db: MongoStore, stream: models.FundingStream) -> schemas.FundingStreamOut:
    contributions = db.find_many("contributions", {"stream_id": stream.id, "status": "confirmed"})
    return schemas.FundingStreamOut(
        id=stream.id,
        workspace_id=stream.workspace_id,
        campaign_id=stream.campaign_id,
        name=stream.name,
        stream_type=stream.stream_type,
        target_amount=stream.get("target_amount"),
        raised_amount=sum(contribution.amount for contribution in contributions),
        created_at=stream.created_at,
    )


def _campaign_detail(db: MongoStore, campaign: models.Campaign) -> schemas.CampaignDetailOut:
    streams = db.find_many("funding_streams", {"campaign_id": campaign.id}, sort=[("created_at", DESC)])
    contributions = db.find_many("contributions", {"campaign_id": campaign.id}, sort=[("created_at", DESC)])
    confirmed_contributors = {
        contribution.get("contributor_email") or contribution.get("contributor_name") or str(contribution.id)
        for contribution in contributions
        if contribution.status == "confirmed"
    }
    return schemas.CampaignDetailOut(
        id=campaign.id,
        workspace_id=campaign.workspace_id,
        name=campaign.name,
        slug=campaign.slug,
        target_amount=campaign.target_amount,
        raised_amount=campaign.get("raised_amount", 0),
        status=campaign.status,
        created_at=campaign.created_at,
        funding_streams=[_stream_out(db, stream) for stream in streams],
        contributions=[_contribution_out(db, contribution) for contribution in contributions],
        contributor_count=len(confirmed_contributors),
    )


def _validate_stream(db: MongoStore, workspace_id: int, campaign_id: int, stream_id: int | None):
    if stream_id is None:
        return None
    stream = db.find_one("funding_streams", {"id": stream_id, "workspace_id": workspace_id, "campaign_id": campaign_id})
    if not stream:
        raise HTTPException(status_code=404, detail="Funding stream not found")
    return stream


@router.post("", response_model=schemas.CampaignOut)
def create_campaign(
    workspace_id: int,
    payload: schemas.CampaignCreate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("campaigns.manage")),
):
    if not db.find_by_id("workspaces", workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    if db.find_one("campaigns", {"slug": payload.slug}):
        raise HTTPException(status_code=409, detail="Campaign slug already exists")
    return db.insert("campaigns", {"workspace_id": workspace_id, "raised_amount": 0, "status": "active", **payload.model_dump()})


@router.get("", response_model=list[schemas.CampaignOut])
def list_campaigns(workspace_id: int, db: MongoStore = Depends(get_db)):
    return db.find_many("campaigns", {"workspace_id": workspace_id}, sort=[("created_at", DESC)])


@router.get("/{campaign_id}", response_model=schemas.CampaignDetailOut)
def get_campaign(workspace_id: int, campaign_id: int, db: MongoStore = Depends(get_db)):
    return _campaign_detail(db, _campaign_or_404(db, workspace_id, campaign_id))


@router.post("/{campaign_id}/streams", response_model=schemas.FundingStreamOut)
def create_funding_stream(
    workspace_id: int,
    campaign_id: int,
    payload: schemas.FundingStreamCreate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("campaigns.manage")),
):
    _campaign_or_404(db, workspace_id, campaign_id)
    stream = db.insert("funding_streams", {"workspace_id": workspace_id, "campaign_id": campaign_id, **payload.model_dump()})
    return _stream_out(db, stream)


@router.get("/{campaign_id}/contributions", response_model=list[schemas.ContributionOut])
def list_contributions(workspace_id: int, campaign_id: int, db: MongoStore = Depends(get_db)):
    _campaign_or_404(db, workspace_id, campaign_id)
    contributions = db.find_many("contributions", {"workspace_id": workspace_id, "campaign_id": campaign_id}, sort=[("created_at", DESC)])
    return [_contribution_out(db, contribution) for contribution in contributions]


@router.post("/{campaign_id}/contributions/manual", response_model=schemas.ContributionOut)
def create_manual_contribution(
    workspace_id: int,
    campaign_id: int,
    payload: schemas.ContributionCreate,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("campaigns.confirm_contribution")),
):
    campaign = _campaign_or_404(db, workspace_id, campaign_id)
    _validate_stream(db, workspace_id, campaign_id, payload.stream_id)
    if payload.gateway_ref and db.find_one("contributions", {"gateway_ref": payload.gateway_ref}):
        raise HTTPException(status_code=409, detail="Contribution reference already exists")

    contribution = db.insert(
        "contributions",
        {
            "workspace_id": workspace_id,
            "campaign_id": campaign_id,
            "stream_id": payload.stream_id,
            "contributor_name": payload.contributor_name,
            "contributor_email": payload.contributor_email,
            "amount": payload.amount,
            "method": payload.method,
            "gateway_ref": payload.gateway_ref,
            "receipt_url": payload.receipt_url,
            "is_anonymous": payload.is_anonymous,
            "status": "confirmed",
            "confirmed_by_user_id": membership.user_id,
            "confirmed_at": datetime.utcnow(),
        },
    )
    db.increment("campaigns", {"id": campaign.id}, "raised_amount", payload.amount)
    return _contribution_out(db, contribution)


@router.post("/{campaign_id}/contributions/{contribution_id}/confirm", response_model=schemas.ContributionOut)
def confirm_contribution(
    workspace_id: int,
    campaign_id: int,
    contribution_id: int,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("campaigns.confirm_contribution")),
):
    campaign = _campaign_or_404(db, workspace_id, campaign_id)
    contribution = db.find_one("contributions", {"id": contribution_id, "workspace_id": workspace_id, "campaign_id": campaign_id})
    if not contribution:
        raise HTTPException(status_code=404, detail="Contribution not found")
    if contribution.status != "confirmed":
        contribution["status"] = "confirmed"
        contribution["confirmed_by_user_id"] = membership.user_id
        contribution["confirmed_at"] = datetime.utcnow()
        db.save("contributions", contribution)
        db.increment("campaigns", {"id": campaign.id}, "raised_amount", contribution.amount)
    return _contribution_out(db, contribution)
