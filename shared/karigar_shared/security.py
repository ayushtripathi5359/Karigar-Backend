"""JWT issue/parse + phone-hash HMAC. Pure functions, no DB access."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status

from karigar_shared.config import Settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_phone(phone: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), phone.encode(), hashlib.sha256).hexdigest()


def hash_otp_code(code: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), code.encode(), hashlib.sha256).hexdigest()


def generate_otp_code(length: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def issue_access_token(user_id: uuid.UUID, role: str, settings: Settings) -> str:
    now = _utcnow()
    payload = {
        "sub": str(user_id),
        "role": role,
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.jwt_token_ttl_days)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> dict:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
