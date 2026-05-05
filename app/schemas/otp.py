import re

from pydantic import BaseModel, field_validator

_INDIA_PHONE_RE = re.compile(r"^[6-9]\d{9}$")


def _clean_phone(v: str) -> str:
    digits = re.sub(r"\D", "", v)
    if not _INDIA_PHONE_RE.match(digits):
        raise ValueError("enter a valid 10-digit Indian mobile number (starts with 6-9)")
    return digits


class OTPRequestBody(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _clean_phone(v)


class OTPRequestResponse(BaseModel):
    message: str
    expires_in: int


class OTPVerifyBody(BaseModel):
    phone: str
    code: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _clean_phone(v)

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        stripped = v.strip()
        if not re.match(r"^\d{6}$", stripped):
            raise ValueError("OTP must be exactly 6 digits")
        return stripped


class OTPVerifyResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
