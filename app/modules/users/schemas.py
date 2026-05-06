from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    user_id: UUID
    email: str | None
    phone: str | None                 # decrypted server-side, only for self
    full_name: str | None             # decrypted server-side, only for self
    role: str
    is_verified: bool
    onboarding_completed: bool
    last_login_at: datetime | None
    created_at: datetime


class OnboardingCompleteBody(BaseModel):
    display_name: str = Field(min_length=1, max_length=128)
    email: str | None = Field(default=None, max_length=512)


class OnboardingCompleteResponse(BaseModel):
    onboarding_completed: bool
    completed_at: datetime
