from pydantic import BaseModel, Field


class OtpRequestBody(BaseModel):
    phone: str = Field(pattern=r"^[6-9]\d{9}$", description="10-digit Indian mobile, starts 6-9")


class OtpRequestResponse(BaseModel):
    message: str
    expires_in: int


class OtpVerifyBody(BaseModel):
    phone: str = Field(pattern=r"^[6-9]\d{9}$")
    code: str = Field(pattern=r"^\d{6}$")


class OtpVerifyResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
