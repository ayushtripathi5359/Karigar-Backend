from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.limiter import limiter
from app.schemas.otp import OTPRequestBody, OTPRequestResponse, OTPVerifyBody, OTPVerifyResponse
from app.services import otp_service

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post(
    "/otp/request",
    response_model=OTPRequestResponse,
    summary="Request OTP for phone login",
    description=(
        "Generates a 6-digit OTP for the given Indian mobile number. "
        "In development the OTP is printed to the server console (stub). "
        "Rate limited to 5 requests per minute."
    ),
)
@limiter.limit("5/minute")
async def otp_request(
    request: Request,
    body: OTPRequestBody,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OTPRequestResponse:
    expires_in = await otp_service.request_otp(session, body.phone)
    return OTPRequestResponse(
        message="OTP sent to your registered mobile number",
        expires_in=expires_in,
    )


@router.post(
    "/otp/verify",
    response_model=OTPVerifyResponse,
    summary="Verify OTP and get access token",
    description=(
        "Verifies the submitted OTP. On success returns a bearer token valid for 30 days. "
        "Allows up to 3 incorrect attempts before the OTP is locked. "
        "Rate limited to 10 requests per minute."
    ),
)
@limiter.limit("10/minute")
async def otp_verify(
    request: Request,
    body: OTPVerifyBody,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OTPVerifyResponse:
    token = await otp_service.verify_otp(session, body.phone, body.code)
    return OTPVerifyResponse(access_token=token)
