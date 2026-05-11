from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/v1/trends", tags=["trends"])


@router.get("", summary="Active trend signals (24h / 7d / 30d)")
async def list_trends() -> dict:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "trends — coming soon")


@router.post("/track", summary="Record a stone-interaction event")
async def track_event() -> dict:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "tracking — coming soon")
