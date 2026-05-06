from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


@router.get("", summary="My notifications inbox")
async def list_notifications() -> dict:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "notifications — coming soon")


@router.post("/{notification_id}/read", summary="Mark notification read")
async def mark_read(notification_id: str) -> dict:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "mark-read — coming soon")
