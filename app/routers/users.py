from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.deps import current_user
from app.limiter import limiter
from app.models.user import AppUser
from app.schemas.user import MeResponse

router = APIRouter(prefix="/v1", tags=["users"])


@router.get("/user", response_model=MeResponse)
@limiter.limit("60/minute")
async def user_profile(
    request: Request,
    user: Annotated[AppUser, Depends(current_user)],
) -> MeResponse:
    return MeResponse(
        id=user.id,
        stack_user_id=user.stack_user_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        onboarding_completed=user.onboarding_completed_at is not None,
        created_at=user.created_at,
    )
