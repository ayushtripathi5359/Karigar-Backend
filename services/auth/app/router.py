from typing import Annotated

from fastapi import APIRouter, Depends, Request

from karigar_shared.config import Settings, get_settings
from karigar_shared.db.session import request_session
from karigar_shared.rate_limit import limiter

from app import service
from app.providers.sms_stub import StubSmsSender
from app.schemas import OtpRequestBody, OtpRequestResponse, OtpVerifyBody, OtpVerifyResponse

router = APIRouter(prefix="/v1/auth", tags=["auth"])

_sender = StubSmsSender()


@router.post("/otp/request", response_model=OtpRequestResponse, summary="Request an OTP for phone login")
@limiter.limit("5/minute")
async def otp_request(
    request: Request,
    body: OtpRequestBody,
    settings: Annotated[Settings, Depends(get_settings)],
) -> OtpRequestResponse:
    rid = getattr(request.state, "request_id", None)
    async with request_session() as session:
        expires_in = await service.request_otp(
            session, phone=body.phone, sender=_sender, settings=settings, request_id=rid
        )
    return OtpRequestResponse(message="OTP sent to your registered mobile number", expires_in=expires_in)


@router.post("/otp/verify", response_model=OtpVerifyResponse, summary="Verify OTP and receive a bearer token")
@limiter.limit("10/minute")
async def otp_verify(
    request: Request,
    body: OtpVerifyBody,
    settings: Annotated[Settings, Depends(get_settings)],
) -> OtpVerifyResponse:
    rid = getattr(request.state, "request_id", None)
    async with request_session() as session:
        token = await service.verify_otp(
            session, phone=body.phone, code=body.code, settings=settings, request_id=rid
        )
    return OtpVerifyResponse(access_token=token)
