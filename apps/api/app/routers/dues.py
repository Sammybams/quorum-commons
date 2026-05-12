from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from .. import models, schemas
from ..database import DESC, MongoStore, get_db
from ..payments import PaymentInitializationError, initialize_paystack_transaction, payment_callback_url
from ..rbac import require_workspace_permission

router = APIRouter(prefix="/workspaces/{workspace_id}/dues-cycles", tags=["dues"])


@router.post("", response_model=schemas.DuesCycleOut)
def create_dues_cycle(
    workspace_id: int,
    payload: schemas.DuesCycleCreate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("dues.manage")),
):
    if not db.find_by_id("workspaces", workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    return db.insert("dues_cycles", {"workspace_id": workspace_id, **payload.model_dump()})


@router.get("", response_model=list[schemas.DuesCycleOut])
def list_dues_cycles(workspace_id: int, db: MongoStore = Depends(get_db)):
    return db.find_many("dues_cycles", {"workspace_id": workspace_id}, sort=[("created_at", DESC)])


payments_router = APIRouter(prefix="/workspaces/{workspace_id}/dues-payments", tags=["dues"])


@payments_router.get("", response_model=list[schemas.DuesPaymentOut])
def list_dues_payments(workspace_id: int, db: MongoStore = Depends(get_db)):
    payments = db.find_many("dues_payments", {"workspace_id": workspace_id}, sort=[("created_at", DESC)])
    return [_payment_out(db, payment) for payment in payments]


@router.post("/{cycle_id}/payments/manual", response_model=schemas.DuesPaymentOut, status_code=201)
def create_manual_payment(
    workspace_id: int,
    cycle_id: int,
    payload: schemas.DuesPaymentCreate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("dues.manage")),
):
    cycle = db.find_one("dues_cycles", {"workspace_id": workspace_id, "id": cycle_id})
    if not cycle:
        raise HTTPException(status_code=404, detail="Dues cycle not found")

    payment = db.insert(
        "dues_payments",
        {
            "workspace_id": workspace_id,
            "cycle_id": cycle_id,
            "member_id": payload.member_id,
            "amount": payload.amount,
            "method": payload.method,
            "gateway_ref": payload.gateway_ref,
            "receipt_url": payload.receipt_url,
            "status": "pending" if payload.method == "manual" else "initiated",
            "confirmed_by_user_id": None,
            "confirmed_at": None,
        },
    )
    return _payment_out(db, payment)


@router.post("/{cycle_id}/payments/checkout", response_model=schemas.DuesPaymentCheckoutResponse, status_code=201)
def initialize_dues_checkout(
    workspace_id: int,
    cycle_id: int,
    payload: schemas.DuesPaymentCheckoutCreate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("dues.manage")),
):
    cycle = db.find_one("dues_cycles", {"workspace_id": workspace_id, "id": cycle_id})
    if not cycle:
        raise HTTPException(status_code=404, detail="Dues cycle not found")

    member = None
    if payload.member_id:
        member = db.find_one("workspace_members", {"workspace_id": workspace_id, "id": payload.member_id})
        if not member:
            raise HTTPException(status_code=404, detail="Member not found")

    user = db.find_by_id("users", member.user_id) if member else None
    email = payload.email or (user.email if user else None)
    amount = payload.amount or cycle.amount
    reference = f"QRM-DUES-{uuid4().hex[:14].upper()}"
    checkout = None
    if email:
        try:
            checkout = initialize_paystack_transaction(
                email=email,
                amount=amount,
                reference=reference,
                callback_url=payment_callback_url(f"/workspaces/{workspace_id}/dues"),
                metadata={"type": "dues_payment", "workspace_id": workspace_id, "cycle_id": cycle_id, "member_id": payload.member_id},
            )
        except PaymentInitializationError as exc:
            raise HTTPException(status_code=502, detail=f"Unable to initialize payment: {exc}") from exc

    payment = db.insert(
        "dues_payments",
        {
            "workspace_id": workspace_id,
            "cycle_id": cycle_id,
            "member_id": payload.member_id,
            "amount": amount,
            "method": "paystack" if checkout else "manual",
            "gateway_ref": reference,
            "receipt_url": None,
            "status": "initiated" if checkout else "pending",
            "confirmed_by_user_id": None,
            "confirmed_at": None,
        },
    )

    return schemas.DuesPaymentCheckoutResponse(
        payment=_payment_out(db, payment),
        payment_reference=reference,
        checkout_url=checkout.authorization_url if checkout else None,
        access_code=checkout.access_code if checkout else None,
    )


@payments_router.post("/{payment_id}/confirm", response_model=schemas.DuesPaymentOut)
def confirm_dues_payment(
    workspace_id: int,
    payment_id: int,
    db: MongoStore = Depends(get_db),
    membership=Depends(require_workspace_permission("dues.confirm_payment")),
):
    payment = db.find_one("dues_payments", {"workspace_id": workspace_id, "id": payment_id})
    if not payment:
        raise HTTPException(status_code=404, detail="Dues payment not found")

    payment["status"] = "paid"
    payment["confirmed_by_user_id"] = membership.user_id
    payment["confirmed_at"] = datetime.utcnow()
    db.save("dues_payments", payment)
    if payment.get("member_id"):
        db.update_one("workspace_members", {"id": payment.member_id}, {"dues_status": "paid"})
    return _payment_out(db, payment)


def _payment_out(db: MongoStore, payment: models.DuesPayment) -> schemas.DuesPaymentOut:
    member = db.find_by_id("workspace_members", payment.get("member_id"))
    user = db.find_by_id("users", member.user_id) if member else None
    return schemas.DuesPaymentOut(
        id=payment.id,
        workspace_id=payment.workspace_id,
        cycle_id=payment.cycle_id,
        member_id=payment.get("member_id"),
        member_name=user.full_name if user else None,
        amount=payment.amount,
        method=payment.method,
        gateway_ref=payment.get("gateway_ref"),
        receipt_url=payment.get("receipt_url"),
        status=payment.status,
        confirmed_by_user_id=payment.get("confirmed_by_user_id"),
        confirmed_at=payment.get("confirmed_at"),
        created_at=payment.created_at,
    )
