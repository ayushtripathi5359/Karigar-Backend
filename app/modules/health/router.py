from fastapi import APIRouter
from sqlalchemy.sql import text

from app.db.session import engine

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness + DB reachability")
async def health() -> dict[str, str]:
    db_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_status = "error"
    return {"status": "ok", "database": db_status}
