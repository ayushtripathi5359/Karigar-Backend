from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request

from app.modules.auth.deps import CurrentUser, current_user
from app.modules.users.schemas import (
    AddressCreateBody,
    AddressListResponse,
    AddressResponse,
    OnboardingCompleteBody,
    OnboardingCompleteResponse,
    UserProfileResponse,
)
from app.modules.users.services import addresses as addr_svc
from app.modules.users.services import profile as profile_svc
from app.shared.rate_limit import limiter

router = APIRouter(prefix="/v1", tags=["users"])


# ── Profile ────────────────────────────────────────────────────────────────
@router.get("/user", response_model=UserProfileResponse, summary="Current user's profile")
@limiter.limit("60/minute")
async def get_user(
    request: Request,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> UserProfileResponse:
    p = await profile_svc.get_profile(me.session, me.user_id)
    return UserProfileResponse(**p)


@router.post(
    "/onboarding/complete",
    response_model=OnboardingCompleteResponse,
    summary="Mark onboarding complete (sets full_name, optional email)",
)
@limiter.limit("20/minute")
async def complete_onboarding(
    request: Request,
    body: OnboardingCompleteBody,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> OnboardingCompleteResponse:
    completed_at = await profile_svc.complete_onboarding(
        me.session,
        user_id=me.user_id,
        display_name=body.display_name,
        email=body.email,
    )
    return OnboardingCompleteResponse(onboarding_completed=True, completed_at=completed_at)


# ── Addresses ──────────────────────────────────────────────────────────────
@router.get(
    "/users/me/addresses",
    response_model=AddressListResponse,
    summary="List my addresses",
)
@limiter.limit("60/minute")
async def list_addresses(
    request: Request,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> AddressListResponse:
    rows = await addr_svc.list_addresses(me.session, me.user_id)
    return AddressListResponse(items=[AddressResponse(**r) for r in rows])


@router.post(
    "/users/me/addresses",
    response_model=AddressResponse,
    status_code=201,
    summary="Capture a new shipping/billing address",
)
@limiter.limit("30/minute")
async def create_address(
    request: Request,
    body: AddressCreateBody,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> AddressResponse:
    row = await addr_svc.create_address(
        me.session,
        user_id=me.user_id,
        label=body.label,
        line1=body.line1,
        line2=body.line2,
        city=body.city,
        state=body.state,
        pincode=body.pincode,
        country=body.country,
        make_default=body.make_default,
    )
    return AddressResponse(**row)


@router.post(
    "/users/me/addresses/{address_id}/set-default",
    response_model=AddressResponse,
    summary="Promote an address to default",
)
@limiter.limit("30/minute")
async def set_default_address(
    request: Request,
    address_id: Annotated[UUID, Path()],
    me: Annotated[CurrentUser, Depends(current_user)],
) -> AddressResponse:
    await addr_svc.set_default(me.session, user_id=me.user_id, address_id=address_id)
    row = await addr_svc.get_address(me.session, user_id=me.user_id, address_id=address_id)
    return AddressResponse(**row)


@router.delete(
    "/users/me/addresses/{address_id}",
    status_code=204,
    summary="Soft-delete an address",
)
@limiter.limit("30/minute")
async def delete_address(
    request: Request,
    address_id: Annotated[UUID, Path()],
    me: Annotated[CurrentUser, Depends(current_user)],
) -> None:
    await addr_svc.soft_delete(me.session, user_id=me.user_id, address_id=address_id)
