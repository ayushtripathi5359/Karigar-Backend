from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── User profile ───────────────────────────────────────────────────────────
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


# ── Addresses ──────────────────────────────────────────────────────────────
PINCODE_RE = r"^[0-9]{4,10}$"


class AddressCreateBody(BaseModel):
    label: str | None = Field(default=None, max_length=64)
    line1: str = Field(min_length=1, max_length=512)
    line2: str | None = Field(default=None, max_length=512)
    city: str = Field(min_length=1, max_length=128)
    state: str = Field(min_length=1, max_length=128)
    pincode: str = Field(pattern=PINCODE_RE)
    country: str = Field(default="India", max_length=64)
    make_default: bool = False


class AddressResponse(BaseModel):
    address_id: UUID
    label: str | None
    line1: str
    line2: str | None
    city: str
    state: str
    pincode: str
    country: str
    is_default: bool
    created_at: datetime


class AddressListResponse(BaseModel):
    items: list[AddressResponse]
