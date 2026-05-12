import json
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..database import MongoStore, get_db
from ..payments import PaymentInitializationError, verify_squad_signature, verify_squad_transaction

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _process_confirmed_reference(
    db: MongoStore,
    *,
    reference: str,
    provider: str,
    provider_transaction_ref: str | None = None,
):
    payment = db.find_one("dues_payments", {"gateway_ref": reference})
    if payment:
        payment["status"] = "paid"
        payment["method"] = provider
        payment["provider"] = provider
        payment["provider_transaction_ref"] = provider_transaction_ref or reference
        payment["verification_status"] = "verified"
        payment["confirmed_at"] = datetime.utcnow()
        db.save("dues_payments", payment)

        if payment.get("member_id"):
            db.update_one("workspace_members", {"id": payment.member_id}, {"dues_status": "paid"})

        return {"status": "processed", "payment_id": payment.id}

    contribution = db.find_one("contributions", {"gateway_ref": reference})
    if not contribution:
        raise HTTPException(status_code=404, detail="Payment reference not found")

    if contribution.status != "confirmed":
        contribution["status"] = "confirmed"
        contribution["method"] = provider
        contribution["provider"] = provider
        contribution["provider_transaction_ref"] = provider_transaction_ref or reference
        contribution["verification_status"] = "verified"
        contribution["confirmed_at"] = datetime.utcnow()
        db.save("contributions", contribution)
        db.increment("campaigns", {"id": contribution.campaign_id}, "raised_amount", contribution.amount)
        if contribution.get("stream_id"):
            db.increment("funding_streams", {"id": contribution.stream_id}, "raised_amount", contribution.amount)

    return {"status": "processed", "contribution_id": contribution.id}

@router.post("/squad")
async def squad_webhook(
    request: Request,
    x_squad_encrypted_body: str | None = Header(default=None),
    db: MongoStore = Depends(get_db),
):
    raw_body = await request.body()
    if not verify_squad_signature(raw_body, x_squad_encrypted_body):
        raise HTTPException(status_code=401, detail="Invalid Squad signature")

    payload = json.loads(raw_body.decode("utf-8"))
    reference = (
        payload.get("merchant_reference")
        or payload.get("transaction_reference")
        or payload.get("gateway_transaction_ref")
        or payload.get("transaction_ref")
    )
    if not reference:
        return {"status": "ignored"}

    try:
        verification = verify_squad_transaction(str(reference))
    except PaymentInitializationError:
        verification = None
    if verification and verification.status not in {"success", "successful"}:
        return {"status": "ignored", "reason": verification.status}

    provider_reference = verification.provider_transaction_ref if verification else str(reference)
    return _process_confirmed_reference(
        db,
        reference=str(reference),
        provider="squad",
        provider_transaction_ref=provider_reference,
    )
