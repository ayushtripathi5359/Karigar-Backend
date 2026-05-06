from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/v1/orders", tags=["orders"])


@router.get("", summary="List my orders")
async def list_orders() -> dict:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "orders — coming soon")


@router.post("", summary="Create an order")
async def create_order() -> dict:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "create order — coming soon")


@router.get("/{order_id}", summary="Order detail")
async def order_detail(order_id: str) -> dict:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "order detail — coming soon")
