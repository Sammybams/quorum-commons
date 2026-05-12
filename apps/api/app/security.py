import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any


APP_SECRET = os.getenv("APP_SECRET", "dev-only-change-me")
TOKEN_TTL_SECONDS = int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", "86400"))
REFRESH_TOKEN_TTL_SECONDS = int(os.getenv("REFRESH_TOKEN_TTL_SECONDS", str(60 * 60 * 24 * 30)))
EMAIL_TOKEN_TTL_SECONDS = int(os.getenv("EMAIL_TOKEN_TTL_SECONDS", str(60 * 60 * 24)))
PASSWORD_RESET_TOKEN_TTL_SECONDS = int(os.getenv("PASSWORD_RESET_TOKEN_TTL_SECONDS", str(60 * 60)))
PASSWORD_ITERATIONS = 210_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False

    try:
        algorithm, iterations, salt, expected = stored_hash.split("$", 3)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations),
    ).hex()
    return hmac.compare_digest(digest, expected)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    return create_signed_token(subject, TOKEN_TTL_SECONDS, {"type": "access", **(extra or {})})


def create_refresh_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    return create_signed_token(subject, REFRESH_TOKEN_TTL_SECONDS, {"type": "refresh", **(extra or {})})


def create_email_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    return create_signed_token(subject, EMAIL_TOKEN_TTL_SECONDS, {"type": "email_verification", **(extra or {})})


def create_reset_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    return create_signed_token(subject, PASSWORD_RESET_TOKEN_TTL_SECONDS, {"type": "password_reset", **(extra or {})})


def create_signed_token(subject: str, ttl_seconds: int, extra: dict[str, Any] | None = None) -> str:
    now = int(time.time())
    payload = {"sub": subject, "iat": now, "exp": now + ttl_seconds, "jti": secrets.token_urlsafe(18), **(extra or {})}
    encoded_payload = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(encoded_payload)
    return f"{encoded_payload}.{signature}"


def decode_access_token(token: str) -> dict[str, Any] | None:
    return decode_signed_token(token, expected_type="access")


def decode_signed_token(token: str, expected_type: str | None = None) -> dict[str, Any] | None:
    try:
        encoded_payload, signature = token.split(".", 1)
    except ValueError:
        return None

    expected_signature = _sign(encoded_payload)
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(_b64decode(encoded_payload))
    except (json.JSONDecodeError, ValueError):
        return None

    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    if expected_type and payload.get("type") != expected_type:
        return None

    return payload


def _sign(value: str) -> str:
    digest = hmac.new(APP_SECRET.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _b64decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}").decode("utf-8")
