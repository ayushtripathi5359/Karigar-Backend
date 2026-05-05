import logging
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.otp import OTPRecord
from app.models.user import AppUser
from app.services import pin_stub
from app.services.flow_tracker import logtrack

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def request_otp(session: AsyncSession, phone: str) -> int:
    settings = get_settings()

    code = pin_stub.generate_pin()
    await logtrack(session, phone=phone, event="pin_generated_by_stub")

    expires_at = _utcnow() + timedelta(seconds=settings.otp_expiry_seconds)
    record = OTPRecord(phone=phone, code=code, expires_at=expires_at)
    session.add(record)
    await session.commit()

    await pin_stub.deliver_pin(phone, code)
    await logtrack(session, phone=phone, event="pin_delivered_by_stub")

    return settings.otp_expiry_seconds


async def verify_otp(session: AsyncSession, phone: str, code: str) -> str:
    settings = get_settings()

    result = await session.execute(
        select(OTPRecord)
        .where(OTPRecord.phone == phone, OTPRecord.verified.is_(False))
        .order_by(OTPRecord.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()

    if record is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no pending OTP found for this number")

    if record.attempts >= settings.otp_max_attempts:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many incorrect attempts — request a new OTP",
        )

    if _utcnow() > record.expires_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OTP has expired — request a new one")

    if record.code != code:
        record.attempts += 1
        await session.commit()
        await logtrack(session, phone=phone, event="verifyPIN_incorrect")
        remaining = settings.otp_max_attempts - record.attempts
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"incorrect OTP — {remaining} attempt{'s' if remaining != 1 else ''} remaining",
        )

    record.verified = True
    await session.commit()
    await logtrack(session, phone=phone, event="verifyPIN_success")

    user_result = await session.execute(
        select(AppUser).where(AppUser.phone == phone)
    )
    user = user_result.scalar_one_or_none()

    if user is None:
        user = AppUser(
            phone=phone,
            stack_user_id=f"phone:{phone}",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    now = _utcnow()
    payload = {
        "sub": str(user.id),
        "phone": phone,
        "iss": "karigar",
        "iat": now,
        "exp": now + timedelta(days=settings.otp_token_ttl_days),
    }
    token: str = jwt.encode(payload, settings.otp_secret, algorithm="HS256")
    return token
