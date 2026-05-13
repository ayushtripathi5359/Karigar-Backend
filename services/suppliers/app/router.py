from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/v1/suppliers", tags=["suppliers"])


@router.post("/uploads", summary="Trigger a supplier feed upload")
async def trigger_upload() -> dict:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "supplier uploads — coming soon")


@router.get("/uploads/{upload_id}", summary="Upload status + counts")
async def upload_status(upload_id: str) -> dict:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "upload status — coming soon")
