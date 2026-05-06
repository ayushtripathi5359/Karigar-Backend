"""
OTP service.

Two operations:
  - request_otp(phone) — generate code, persist hashed, send via provider, audit.
  - verify_otp(phone, code) — verify, signup-on-first-use, mint JWT, audit.

Both run inside a single transaction (request_session ctx) so the RLS GUCs
(`app.current_user_id`, `app.current_user_role`, `app.encryption_key`) stay
in scope. No intermediate commits — they would reset SET LOCAL.

Pre-auth `users` lookup goes through the SECURITY DEFINER function
`auth_lookup_user_by_phone_hash`, which bypasses the `users_self_read`
policy that would otherwise hide every row when current_user_id is NULL.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from app.core.config import Settings
from app.core.security import (
    generate_otp_code,
    hash_otp_code,
    hash_phone,
    issue_access_token,
)
from app.modules.auth import events
from app.modules.auth.providers.base import OtpSender


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def request_otp(
    session: AsyncSession,
    *,
    phone: str,
    sender: OtpSender,
    settings: Settings,
    request_id: str | None = None,
) -> int:
    """Generate a fresh OTP, persist the hash, deliver, audit. Returns TTL in seconds."""
    phone_hash = hash_phone(phone, settings.phone_hash_pepper)
    code = generate_otp_code(settings.otp_code_length)
    code_hash = hash_otp_code(code, settings.phone_hash_pepper)
    expires_at = _utcnow() + timedelta(seconds=settings.otp_expiry_seconds)

    # Look up an existing user (RLS-bypass via SECURITY DEFINER fn)
    result = await session.execute(
        text("SELECT auth_lookup_user_by_phone_hash(:p)"),
        {"p": phone_hash},
    )
    user_id: uuid.UUID | None = result.scalar_one_or_none()

    await session.execute(
        text(
            """
            INSERT INTO otp_records (phone_hash, code_hash, expires_at, user_id)
            VALUES (:phone_hash, :code_hash, :expires_at, :user_id)
            """
        ),
        {
            "phone_hash": phone_hash,
            "code_hash": code_hash,
            "expires_at": expires_at,
            "user_id": str(user_id) if user_id else None,
        },
    )

    await events.record(
        session,
        event_type="pin_requested",
        user_id=user_id,
        phone_hash=phone_hash,
        request_id=request_id,
    )

    # Provider call last — if it raises, the tx rolls back so we don't leave
    # orphan otp_records.
    await sender.send(phone, code)

    await events.record(
        session,
        event_type="pin_delivered",
        user_id=user_id,
        phone_hash=phone_hash,
        request_id=request_id,
    )

    return settings.otp_expiry_seconds


async def verify_otp(
    session: AsyncSession,
    *,
    phone: str,
    code: str,
    settings: Settings,
    request_id: str | None = None,
) -> str:
    """Verify the code, create user on first login, return signed JWT."""
    phone_hash = hash_phone(phone, settings.phone_hash_pepper)
    code_hash = hash_otp_code(code, settings.phone_hash_pepper)

    # Latest unverified OTP for this phone (RLS-free; otp_records has no policy)
    row = (
        await session.execute(
            text(
                """
                SELECT otp_id, code_hash, expires_at, attempts, user_id
                FROM otp_records
                WHERE phone_hash = :p AND verified_at IS NULL
                ORDER BY created_at DESC
                LIMIT 1
                FOR UPDATE
                """
            ),
            {"p": phone_hash},
        )
    ).first()

    if row is None:
        await events.record(session, event_type="pin_incorrect",
                            phone_hash=phone_hash, request_id=request_id)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no pending OTP — request a new one")

    otp_id, expected_hash, expires_at, attempts, existing_user_id = row

    if attempts >= settings.otp_max_attempts:
        await events.record(session, event_type="pin_rate_limited",
                            phone_hash=phone_hash, request_id=request_id)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many incorrect attempts — request a new OTP",
        )

    if _utcnow() > expires_at:
        await events.record(session, event_type="pin_expired",
                            phone_hash=phone_hash, request_id=request_id)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OTP has expired — request a new one")

    if code_hash != expected_hash:
        await session.execute(
            text("UPDATE otp_records SET attempts = attempts + 1 WHERE otp_id = :id"),
            {"id": otp_id},
        )
        await events.record(session, event_type="pin_incorrect",
                            phone_hash=phone_hash, request_id=request_id)
        remaining = settings.otp_max_attempts - (attempts + 1)
        plural = "s" if remaining != 1 else ""
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"incorrect OTP — {remaining} attempt{plural} remaining",
        )

    # Code is correct — mark verified
    await session.execute(
        text("UPDATE otp_records SET verified_at = now() WHERE otp_id = :id"),
        {"id": otp_id},
    )

    user_id = existing_user_id
    if user_id is None:
        # First login for this phone — create the users row.
        # Allowed by the `users_admin_insert` policy because current_user_id() is NULL here.
        new_user = (
            await session.execute(
                text(
                    """
                    INSERT INTO users (
                        email, phone_encrypted, full_name_encrypted, role,
                        phone_hash, is_verified
                    )
                    VALUES (
                        NULL, encrypt_pii(:phone), NULL, 'buyer',
                        :phone_hash, TRUE
                    )
                    RETURNING user_id
                    """
                ),
                {"phone": phone, "phone_hash": phone_hash},
            )
        ).scalar_one()
        user_id = new_user

        # Tie this OTP to the new user
        await session.execute(
            text("UPDATE otp_records SET user_id = :u WHERE otp_id = :o"),
            {"u": str(user_id), "o": otp_id},
        )

        await events.record(session, event_type="signup",
                            user_id=user_id, phone_hash=phone_hash,
                            request_id=request_id)

    # Update last_login_at
    await session.execute(
        text("UPDATE users SET last_login_at = now() WHERE user_id = :u"),
        {"u": str(user_id)},
    )

    await events.record(session, event_type="pin_verified",
                        user_id=user_id, phone_hash=phone_hash,
                        request_id=request_id)
    await events.record(session, event_type="login",
                        user_id=user_id, phone_hash=phone_hash,
                        request_id=request_id)

    # Read role for JWT claim
    role = (
        await session.execute(
            text("SELECT role FROM users WHERE user_id = :u"),
            {"u": str(user_id)},
        )
    ).scalar_one()

    return issue_access_token(user_id, role, settings)
