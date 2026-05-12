from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class TelegramServiceError(RuntimeError):
    pass


def _telegram_request(bot_token: str, endpoint: str, *, payload: dict | None = None) -> dict:
    request = Request(
        f"https://api.telegram.org/bot{bot_token}/{endpoint}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise TelegramServiceError(detail or str(exc)) from exc
    except URLError as exc:
        raise TelegramServiceError(str(exc.reason)) from exc

    data = json.loads(raw)
    if not data.get("ok"):
        raise TelegramServiceError(str(data.get("description") or "Telegram API request failed"))
    return data


def telegram_get_me(bot_token: str) -> dict:
    return _telegram_request(bot_token, "getMe")


def telegram_set_webhook(
    bot_token: str,
    *,
    webhook_url: str,
    secret_token: str | None = None,
    allowed_updates: list[str] | None = None,
) -> dict:
    payload: dict[str, object] = {"url": webhook_url}
    if secret_token:
        payload["secret_token"] = secret_token
    if allowed_updates:
        payload["allowed_updates"] = allowed_updates
    return _telegram_request(bot_token, "setWebhook", payload=payload)
