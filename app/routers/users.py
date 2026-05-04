from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import current_user
from app.limiter import limiter
from app.models import AppUser
from app.schemas import MeResponse, OnboardingCompleteBody, OnboardingCompleteResponse

router = APIRouter(prefix="/v1", tags=["users"])


@router.get("/me", response_model=MeResponse)
@limiter.limit("60/minute")
async def me(
    request: Request,
    user: Annotated[AppUser, Depends(current_user)],
) -> MeResponse:
    return MeResponse(
        id=user.id,
        stack_user_id=user.stack_user_id,
        email=user.email,
        display_name=user.display_name,
        onboarding_completed=user.onboarding_completed_at is not None,
        created_at=user.created_at,
    )


@router.post("/onboarding/complete", response_model=OnboardingCompleteResponse)
@limiter.limit("20/minute")
async def onboarding_complete(
    request: Request,
    body: OnboardingCompleteBody,
    user: Annotated[AppUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OnboardingCompleteResponse:
    now = datetime.now(timezone.utc)
    if body.display_name is not None:
        user.display_name = body.display_name
    user.onboarding_completed_at = now
    await session.commit()
    await session.refresh(user)
    return OnboardingCompleteResponse(onboarding_completed=True, completed_at=user.onboarding_completed_at)
