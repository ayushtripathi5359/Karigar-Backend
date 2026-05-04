from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MeResponse(BaseModel):
    id: UUID
    stack_user_id: str
    email: str | None
    display_name: str | None
    role: str
    onboarding_completed: bool
    created_at: datetime
