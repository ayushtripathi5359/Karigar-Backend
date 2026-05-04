from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AppUser
from app.schemas.onboarding import OnboardingCompleteResponse


async def complete_onboarding(
    session: AsyncSession,
    user: AppUser,
    display_name: str | None,
) -> OnboardingCompleteResponse:
    now = datetime.now(timezone.utc)
    if display_name is not None:
        user.display_name = display_name
    user.onboarding_completed_at = now
    await session.commit()
    await session.refresh(user)
    return OnboardingCompleteResponse(onboarding_completed=True, completed_at=user.onboarding_completed_at)
