import hashlib
import hmac
import json
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..database import MongoStore, get_db

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/paystack")
async def paystack_webhook(
    request: Request,
    x_paystack_signature: str | None = Header(default=None),
    db: MongoStore = Depends(get_db),
):
    raw_body = await request.body()
    secret_key = os.getenv("PAYSTACK_SECRET_KEY")
    if secret_key:
        expected = hmac.new(secret_key.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
        if not x_paystack_signature or not hmac.compare_digest(expected, x_paystack_signature):
            raise HTTPException(status_code=401, detail="Invalid Paystack signature")

    payload = json.loads(raw_body.decode("utf-8"))
    event = payload.get("event")
    data = payload.get("data") or {}
    reference = data.get("reference")

    if event != "charge.success" or not reference:
        return {"status": "ignored"}

    payment = db.find_one("dues_payments", {"gateway_ref": reference})
    if payment:
        payment["status"] = "paid"
        payment["method"] = "paystack"
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
        contribution["method"] = "paystack"
        contribution["confirmed_at"] = datetime.utcnow()
        db.save("contributions", contribution)
        db.increment("campaigns", {"id": contribution.campaign_id}, "raised_amount", contribution.amount)
        if contribution.get("stream_id"):
            db.increment("funding_streams", {"id": contribution.stream_id}, "raised_amount", contribution.amount)

    return {"status": "processed", "contribution_id": contribution.id}
