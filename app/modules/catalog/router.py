from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/v1/catalog", tags=["catalog"])


@router.get("/stones", summary="List/search stones")
async def list_stones() -> dict:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "catalog search — coming soon")


@router.get("/stones/{stone_id}", summary="Stone detail")
async def stone_detail(stone_id: str) -> dict:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "stone detail — coming soon")
