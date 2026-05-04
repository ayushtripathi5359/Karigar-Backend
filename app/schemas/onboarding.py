from datetime import datetime

from pydantic import BaseModel, Field


class OnboardingCompleteBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=256)


class OnboardingCompleteResponse(BaseModel):
    onboarding_completed: bool
    completed_at: datetime
