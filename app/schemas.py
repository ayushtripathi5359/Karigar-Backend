from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MeResponse(BaseModel):
    id: UUID
    stack_user_id: str
    email: str | None
    display_name: str | None
    onboarding_completed: bool
    created_at: datetime


class OnboardingCompleteBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=256)


class OnboardingCompleteResponse(BaseModel):
    onboarding_completed: bool
    completed_at: datetime
