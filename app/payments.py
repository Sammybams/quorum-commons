from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class PaymentInitializationError(RuntimeError):
    pass


@dataclass
class PaystackInitialization:
    authorization_url: str
    access_code: str
    reference: str


def amount_to_subunit(amount: float) -> int:
    return int(round(amount * 100))


def initialize_paystack_transaction(
    *,
    email: str,
    amount: float,
    reference: str,
    callback_url: str | None = None,
    metadata: dict | None = None,
) -> PaystackInitialization | None:
    secret_key = os.getenv("PAYSTACK_SECRET_KEY")
    if not secret_key:
        return None

    payload: dict[str, object] = {
        "email": email,
        "amount": str(amount_to_subunit(amount)),
        "reference": reference,
    }
    if callback_url:
        payload["callback_url"] = callback_url
    if metadata:
        payload["metadata"] = metadata

    request = Request(
        "https://api.paystack.co/transaction/initialize",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise PaymentInitializationError(detail or str(exc)) from exc
    except URLError as exc:
        raise PaymentInitializationError(str(exc.reason)) from exc

    data = json.loads(raw)
    if not data.get("status") or not data.get("data"):
        raise PaymentInitializationError(data.get("message") or "Paystack initialization failed")

    details = data["data"]
    return PaystackInitialization(
        authorization_url=details["authorization_url"],
        access_code=details["access_code"],
        reference=details["reference"],
    )


def payment_callback_url(path: str | None = None) -> str | None:
    explicit = os.getenv("PAYSTACK_CALLBACK_URL")
    if explicit:
        return explicit

    app_url = os.getenv("PUBLIC_APP_URL") or os.getenv("NEXT_PUBLIC_APP_URL")
    if not app_url:
        return None

    suffix = path or "/payments/callback"
    return f"{app_url.rstrip('/')}/{suffix.lstrip('/')}"
