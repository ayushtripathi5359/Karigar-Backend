from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from karigar_shared.config import get_settings
from karigar_shared.db.deps import get_db_anonymous
from karigar_shared.db.session import request_session
from karigar_shared.rate_limit import limiter
from karigar_shared.security import decode_access_token

from app.schemas import StoneDetail, StoneListResponse, StoneSummary
from app.services import detail as detail_svc
from app.services import tracking as tracking_svc
from app.services.search import SearchFilters, search_diamonds

router = APIRouter(prefix="/v1/catalog", tags=["catalog"])


@router.get("/stones", response_model=StoneListResponse, summary="List / search stones")
@limiter.limit("120/minute")
async def list_stones(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_anonymous)],
    shape: str | None = Query(None),
    color_scale: str | None = Query(None),
    clarity: str | None = Query(None),
    cut: str | None = Query(None),
    carat_min: float | None = Query(None),
    carat_max: float | None = Query(None),
    price_min: float | None = Query(None),
    price_max: float | None = Query(None),
    sort_by: str = Query("value_score"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> StoneListResponse:
    filters = SearchFilters(
        shape=shape, color_scale=color_scale, clarity=clarity, cut=cut,
        carat_min=carat_min, carat_max=carat_max,
        price_min=price_min, price_max=price_max,
        sort_by=sort_by, limit=limit, offset=offset,
    )
    items = await search_diamonds(session, filters)
    return StoneListResponse(items=[StoneSummary(**item.model_dump()) for item in items], total=len(items))


@router.get("/stones/{stone_id}", response_model=StoneDetail,
            summary="Stone detail (records a view when authenticated)")
@limiter.limit("120/minute")
async def stone_detail(
    request: Request,
    stone_id: Annotated[uuid.UUID, Path()],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> StoneDetail:
    user_id: uuid.UUID | None = None
    role: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        try:
            claims = decode_access_token(authorization.split(" ", 1)[1], get_settings())
            user_id = uuid.UUID(claims["sub"])
            role = claims.get("role", "buyer")
        except Exception:  # noqa: BLE001
            user_id = None

    async with request_session(user_id=user_id, role=role) as session:
        data = await detail_svc.get_stone(session, stone_id)
        if user_id is not None:
            await tracking_svc.record_view(session, user_id=user_id, stone_id=stone_id)
        return StoneDetail(**data)
