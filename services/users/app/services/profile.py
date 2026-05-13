from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository


async def get_profile(session: AsyncSession, user_id: uuid.UUID) -> dict:
    profile = await repository.get_profile(session, user_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return profile


async def complete_onboarding(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    display_name: str,
    email: str | None,
) -> datetime:
    await repository.update_onboarding(session, user_id=user_id, display_name=display_name, email=email)
    return datetime.now(timezone.utc)
