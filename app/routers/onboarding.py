from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import current_user
from app.limiter import limiter
from app.models.user import AppUser
from app.schemas.onboarding import OnboardingCompleteBody, OnboardingCompleteResponse
from app.services.onboarding_service import complete_onboarding

router = APIRouter(prefix="/v1/onboarding", tags=["onboarding"])


@router.post("/complete", response_model=OnboardingCompleteResponse)
@limiter.limit("20/minute")
async def onboarding_complete(
    request: Request,
    body: OnboardingCompleteBody,
    user: Annotated[AppUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OnboardingCompleteResponse:
    return await complete_onboarding(session, user, body.display_name)
