from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request

from karigar_shared.auth.deps import CurrentUser, current_user
from karigar_shared.rate_limit import limiter

from app.schemas import OrderCreateBody, OrderDetailResponse, OrderListResponse, OrderSummary
from app.services import inventory_check, order_management, shipping_address, tracking

router = APIRouter(prefix="/v1/orders", tags=["orders"])


@router.post("", response_model=OrderDetailResponse, status_code=201,
             summary="Place order — creates a 'draft'; payment confirm flips status")
@limiter.limit("30/minute")
async def create_order(
    request: Request,
    body: OrderCreateBody,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> OrderDetailResponse:
    await inventory_check.assert_available(me.session, body.stone_id)

    address_id = await shipping_address.resolve(
        me.session,
        user_id=me.user_id,
        address_id=body.address_id,
        new_address=body.new_address.model_dump() if body.new_address else None,
    )

    order = await order_management.create_draft(
        me.session, buyer_id=me.user_id, stone_id=body.stone_id,
        address_id=address_id, quantity=body.quantity,
    )

    await tracking.log_status(
        me.session, order_id=order["order_id"], status="draft",
        notes="order placed; awaiting payment", actor_user_id=me.user_id,
    )

    fresh = await order_management.get_order(me.session, buyer_id=me.user_id, order_id=order["order_id"])
    return OrderDetailResponse(**fresh)


@router.get("", response_model=OrderListResponse, summary="List my orders (newest first)")
@limiter.limit("60/minute")
async def list_orders(
    request: Request,
    me: Annotated[CurrentUser, Depends(current_user)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> OrderListResponse:
    rows = await order_management.list_orders(me.session, buyer_id=me.user_id, limit=limit, offset=offset)
    return OrderListResponse(items=[OrderSummary(**r) for r in rows])


@router.get("/{order_id}", response_model=OrderDetailResponse,
            summary="Order detail with line items and tracking")
@limiter.limit("60/minute")
async def order_detail(
    request: Request,
    order_id: Annotated[UUID, Path()],
    me: Annotated[CurrentUser, Depends(current_user)],
) -> OrderDetailResponse:
    data = await order_management.get_order(me.session, buyer_id=me.user_id, order_id=order_id)
    return OrderDetailResponse(**data)
