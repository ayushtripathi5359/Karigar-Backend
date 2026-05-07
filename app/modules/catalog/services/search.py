"""
Diamond search service.

Hits the composite index `idx_sm_search_composite` and joins value_scores
to surface "best value" results for any filter combination.

Ported from /Users/mainadmin/Desktop/Karigar_Implementation/app/search.py — sync→async.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text


class SearchFilters(BaseModel):
    shape: str | None = None
    color_scale: str | None = None       # 'D'..'Z'
    fancy_color: str | None = None       # 'pink', 'yellow', ...
    clarity: str | None = None
    cut: str | None = None
    carat_min: Decimal | None = None
    carat_max: Decimal | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    lab: str | None = None
    sort_by: str = "value_score"         # value_score | price_low | price_high | carat_high
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SearchResult(BaseModel):
    id: str
    cert_number: str | None
    shape: str
    carat: Decimal
    color_scale: str | None
    fancy_color: str | None
    clarity: str
    cut: str | None
    price: Decimal | None
    rap_discount: Decimal | None
    value_score: Decimal | None
    supplier_display_name: str


_ORDER_BY = {
    "value_score": "vs.total_score DESC NULLS LAST",
    "price_low": "sm.price ASC NULLS LAST",
    "price_high": "sm.price DESC NULLS LAST",
    "carat_high": "sm.carat DESC NULLS LAST",
}


async def search_diamonds(db: AsyncSession, f: SearchFilters) -> list[SearchResult]:
    where: list[str] = ["sm.deleted_at IS NULL", "sm.availability = 'available'"]
    params: dict = {}

    for col, val in [
        ("shape", f.shape),
        ("color_scale", f.color_scale),
        ("fancy_color", f.fancy_color),
        ("clarity", f.clarity),
        ("cut", f.cut),
        ("lab", f.lab),
    ]:
        if val:
            where.append(f"sm.{col} = :{col}")
            params[col] = val

    if f.carat_min is not None:
        where.append("sm.carat >= :carat_min")
        params["carat_min"] = f.carat_min
    if f.carat_max is not None:
        where.append("sm.carat <= :carat_max")
        params["carat_max"] = f.carat_max
    if f.price_min is not None:
        where.append("sm.price >= :price_min")
        params["price_min"] = f.price_min
    if f.price_max is not None:
        where.append("sm.price <= :price_max")
        params["price_max"] = f.price_max

    order_by = _ORDER_BY.get(f.sort_by, _ORDER_BY["value_score"])

    sql = text(
        f"""
        SELECT sm.id, sm.cert_number, sm.shape, sm.carat,
               sm.color_scale, sm.fancy_color, sm.clarity, sm.cut,
               sm.price, sm.rap_discount,
               vs.total_score AS value_score,
               s.display_name AS supplier_display_name
        FROM supplier_master sm
        JOIN suppliers s ON s.supplier_id = sm.supplier_id
        LEFT JOIN value_scores vs
               ON vs.stone_id = sm.id AND vs.formula_version = 'v1.0'
        WHERE {' AND '.join(where)}
        ORDER BY {order_by}
        LIMIT :limit OFFSET :offset
        """
    )
    params["limit"] = f.limit
    params["offset"] = f.offset

    rows = (await db.execute(sql, params)).mappings().all()
    return [SearchResult(**{**dict(row), "id": str(row["id"])}) for row in rows]


async def record_search(
    db: AsyncSession,
    *,
    user_id: str | None,
    filters: SearchFilters,
) -> None:
    """Log to user_flow_tracking so AI personalisation has signal."""
    if not user_id:
        return
    await db.execute(
        text(
            """
            INSERT INTO user_flow_tracking (user_id, event_type, search_query, filter_params)
            VALUES (:u, 'search', :q, CAST(:p AS jsonb))
            """
        ),
        {
            "u": user_id,
            "q": f"shape={filters.shape} color={filters.color_scale} clarity={filters.clarity}",
            "p": filters.model_dump_json(),
        },
    )
