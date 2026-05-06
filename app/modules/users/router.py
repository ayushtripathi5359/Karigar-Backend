from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.modules.auth.deps import CurrentUser, current_user
from app.modules.users import service
from app.modules.users.schemas import (
    OnboardingCompleteBody,
    OnboardingCompleteResponse,
    UserProfileResponse,
)
from app.shared.rate_limit import limiter

router = APIRouter(prefix="/v1", tags=["users"])


@router.get(
    "/user",
    response_model=UserProfileResponse,
    summary="Current authenticated user's profile",
)
@limiter.limit("60/minute")
async def get_user(
    request: Request,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> UserProfileResponse:
    profile = await service.get_profile(me.session, me.user_id)
    return UserProfileResponse(**profile)


@router.post(
    "/onboarding/complete",
    response_model=OnboardingCompleteResponse,
    summary="Mark onboarding complete (sets full_name, optional email)",
)
@limiter.limit("20/minute")
async def complete_onboarding(
    request: Request,
    body: OnboardingCompleteBody,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> OnboardingCompleteResponse:
    completed_at = await service.complete_onboarding(
        me.session,
        user_id=me.user_id,
        display_name=body.display_name,
        email=body.email,
    )
    return OnboardingCompleteResponse(
        onboarding_completed=True,
        completed_at=completed_at,
    )
