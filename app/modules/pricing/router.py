from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/v1/pricing", tags=["pricing"])


@router.get("/value-score/{stone_id}", summary="Karigar Value Score for a stone")
async def get_value_score(stone_id: str) -> dict:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "value score — coming soon")


@router.get("/price-history/{stone_id}", summary="Stone price history")
async def get_price_history(stone_id: str) -> dict:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "price history — coming soon")
