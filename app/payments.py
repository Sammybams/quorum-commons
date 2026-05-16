from __future__ import annotations

import json
import os
import hashlib
import hmac
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class PaymentInitializationError(RuntimeError):
    pass


class PaymentSimulationError(RuntimeError):
    pass


@dataclass
class PaymentInitialization:
    provider: str
    reference: str
    checkout_url: str | None = None
    access_code: str | None = None
    virtual_account_number: str | None = None
    account_name: str | None = None
    bank_name: str | None = None
    expires_at: str | None = None
    provider_transaction_ref: str | None = None


@dataclass
class PaymentVerification:
    provider: str
    reference: str
    status: str
    amount: float | None = None
    currency: str | None = None
    provider_transaction_ref: str | None = None
    raw_data: dict | None = None


def amount_to_subunit(amount: float) -> int:
    return int(round(amount * 100))


def squad_configured() -> bool:
    return bool(os.getenv("SQUAD_SECRET_KEY"))


def squad_sandbox_mode() -> bool:
    secret = os.getenv("SQUAD_SECRET_KEY", "")
    return secret.startswith("sandbox_")


def squad_base_url() -> str:
    if squad_sandbox_mode():
        return "https://sandbox-api-d.squadco.com"
    return "https://api-d.squadco.com"


def _json_request(
    *,
    url: str,
    method: str,
    headers: dict[str, str],
    payload: dict | None = None,
) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise PaymentInitializationError(detail or str(exc)) from exc
    except URLError as exc:
        raise PaymentInitializationError(str(exc.reason)) from exc

    return json.loads(raw)


def initialize_squad_dynamic_virtual_account(
    *,
    email: str,
    amount: float,
    reference: str,
    duration_seconds: int = 3600,
) -> PaymentInitialization | None:
    secret_key = os.getenv("SQUAD_SECRET_KEY")
    if not secret_key:
        return None

    payload = {
        "amount": amount_to_subunit(amount),
        "duration": duration_seconds,
        "email": email,
        "transaction_ref": reference,
    }
    data = _json_request(
        url=f"{squad_base_url()}/virtual-account/initiate-dynamic-virtual-account",
        method="POST",
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        },
        payload=payload,
    )
    if not data.get("success") or not data.get("data"):
        raise PaymentInitializationError(data.get("message") or "Squad virtual account initialization failed")

    details = data["data"]
    return PaymentInitialization(
        provider="squad",
        reference=details.get("transaction_reference") or reference,
        virtual_account_number=details.get("account_number"),
        account_name=details.get("account_name"),
        bank_name=details.get("bank"),
        expires_at=details.get("expires_at"),
        provider_transaction_ref=details.get("transaction_reference") or reference,
    )


def create_squad_dynamic_virtual_account_pool(
    *,
    beneficiary_account: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> dict | None:
    secret_key = os.getenv("SQUAD_SECRET_KEY")
    if not secret_key:
        return None

    payload: dict[str, object] = {}
    if beneficiary_account:
        payload["beneficiary_account"] = str(beneficiary_account)
    if first_name and last_name:
        payload["first_name"] = first_name
        payload["last_name"] = last_name

    data = _json_request(
        url=f"{squad_base_url()}/virtual-account/create-dynamic-virtual-account",
        method="POST",
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        },
        payload=payload,
    )
    if not data.get("success"):
        raise PaymentInitializationError(data.get("message") or "Squad dynamic account pool setup failed")
    return data.get("data") or {}


def squad_disallows_beneficiary_account(detail: str | Exception) -> bool:
    return "not allowed to pass beneficiary account" in str(detail).strip().lower()


def ensure_squad_dynamic_virtual_account_pool(*, beneficiary_account: str | None = None) -> dict | None:
    try:
        return create_squad_dynamic_virtual_account_pool(beneficiary_account=beneficiary_account)
    except PaymentInitializationError as exc:
        if beneficiary_account and squad_disallows_beneficiary_account(exc):
            return create_squad_dynamic_virtual_account_pool()
        raise


def initialize_collection_transaction(
    *,
    email: str,
    amount: float,
    reference: str,
    callback_url: str | None = None,
    metadata: dict | None = None,
    duration_seconds: int = 3600,
) -> PaymentInitialization | None:
    _ = callback_url, metadata
    return initialize_squad_dynamic_virtual_account(
        email=email,
        amount=amount,
        reference=reference,
        duration_seconds=duration_seconds,
    )


def verify_squad_transaction(reference: str) -> PaymentVerification | None:
    secret_key = os.getenv("SQUAD_SECRET_KEY")
    if not secret_key:
        return None

    data = _json_request(
        url=f"{squad_base_url()}/transaction/verify/{reference}",
        method="GET",
        headers={"Authorization": f"Bearer {secret_key}"},
    )
    payload = data.get("data") or {}
    return PaymentVerification(
        provider="squad",
        reference=payload.get("transaction_ref") or reference,
        status=str(payload.get("transaction_status") or "unknown").lower(),
        amount=(float(payload["transaction_amount"]) / 100) if payload.get("transaction_amount") is not None else None,
        currency=payload.get("transaction_currency_id"),
        provider_transaction_ref=payload.get("gateway_transaction_ref") or payload.get("transaction_ref"),
        raw_data=payload,
    )


def squad_missing_virtual_account_pool(detail: str | Exception) -> bool:
    return "unable to retrieve a virtual account" in str(detail).strip().lower()


def verify_squad_signature(raw_body: bytes, signature: str | None) -> bool:
    secret_key = os.getenv("SQUAD_SECRET_KEY")
    if not secret_key or not signature:
        return False
    expected = hmac.new(secret_key.encode("utf-8"), raw_body, hashlib.sha512).hexdigest().upper()
    return hmac.compare_digest(expected, signature.upper())


def simulate_squad_virtual_account_payment(*, virtual_account_number: str, amount: float) -> dict | None:
    secret_key = os.getenv("SQUAD_SECRET_KEY")
    if not secret_key:
        return None
    if not squad_sandbox_mode():
        raise PaymentSimulationError("Squad payment simulation is only available with sandbox credentials.")

    payload = {
        "virtual_account_number": str(virtual_account_number),
        "amount": str(int(round(amount))),
        "dva": True,
    }
    data = _json_request(
        url=f"{squad_base_url()}/virtual-account/simulate/payment",
        method="POST",
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        },
        payload=payload,
    )
    if not data.get("success"):
        raise PaymentSimulationError(data.get("message") or "Squad sandbox payment simulation failed")
    return data


def payment_callback_url(path: str | None = None) -> str | None:
    app_url = os.getenv("PUBLIC_APP_URL") or os.getenv("NEXT_PUBLIC_APP_URL")
    if not app_url:
        return None

    suffix = path or "/payments/callback"
    return f"{app_url.rstrip('/')}/{suffix.lstrip('/')}"
