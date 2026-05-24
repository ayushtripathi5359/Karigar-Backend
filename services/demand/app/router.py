from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from karigar_shared.auth.deps import CurrentUser, current_user
from karigar_shared.rate_limit import limiter

from app import service
from app.schemas import (
    DemandRequestCreateBody,
    DemandRequestListResponse,
    DemandRequestResponse,
    DemandRequestUpdateBody,
)

router = APIRouter(prefix="/v1/demand-requests", tags=["demand-requests"])


@router.post("", response_model=DemandRequestResponse, status_code=201, summary="Create buyer demand/discount request")
@limiter.limit("30/minute")
async def create_demand_request(
    request: Request,
    body: DemandRequestCreateBody,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> DemandRequestResponse:
    if me.role != "buyer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only buyers can create demand requests")
    row = await service.create_demand_request(
        me.session,
        buyer_id=me.user_id,
        stone_id=body.stone_id,
        requested_discount_pct=body.requested_discount_pct,
        requested_price_inr=body.requested_price_inr,
        message=body.message,
    )
    return DemandRequestResponse(**row)


@router.get("", response_model=DemandRequestListResponse, summary="List visible demand requests")
@limiter.limit("60/minute")
async def list_demand_requests(
    request: Request,
    me: Annotated[CurrentUser, Depends(current_user)],
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> DemandRequestListResponse:
    rows = await service.list_demand_requests(
        me.session,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return DemandRequestListResponse(items=[DemandRequestResponse(**row) for row in rows])


@router.get("/{demand_request_id}", response_model=DemandRequestResponse, summary="Demand request detail")
@limiter.limit("60/minute")
async def demand_request_detail(
    request: Request,
    demand_request_id: Annotated[UUID, Path()],
    me: Annotated[CurrentUser, Depends(current_user)],
) -> DemandRequestResponse:
    row = await service.get_demand_request(me.session, demand_request_id=demand_request_id)
    return DemandRequestResponse(**row)


@router.patch("/{demand_request_id}", response_model=DemandRequestResponse, summary="Update demand request status")
@limiter.limit("30/minute")
async def update_demand_request(
    request: Request,
    demand_request_id: Annotated[UUID, Path()],
    body: DemandRequestUpdateBody,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> DemandRequestResponse:
    if me.role not in {"admin", "karigar_staff", "supplier"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
    row = await service.update_demand_request(
        me.session,
        demand_request_id=demand_request_id,
        actor_user_id=me.user_id,
        status_value=body.status,
        response_note=body.response_note,
        offered_price_inr=body.offered_price_inr,
    )
    return DemandRequestResponse(**row)
