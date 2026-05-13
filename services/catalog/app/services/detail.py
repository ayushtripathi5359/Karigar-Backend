from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

_DETAIL_SQL = text(
    """
    SELECT
        sm.id, sm.stone_id, sm.cert_number, sm.lab,
        sm.shape, sm.carat, sm.color_scale, sm.fancy_color,
        sm.clarity, sm.cut, sm.polish, sm.symmetry,
        sm.price_per_carat, sm.price, sm.rap_price, sm.rap_discount,
        sm.measurements, sm.availability,
        s.display_name AS supplier_display_name,
        vs.total_score AS value_score,
        (
            SELECT json_agg(json_build_object(
                'media_id', m.media_id, 'media_type', m.media_type,
                'url', m.url, 'thumbnail_url', m.thumbnail_url,
                'is_primary', m.is_primary, 'sort_order', m.sort_order
            ) ORDER BY m.is_primary DESC, m.sort_order ASC)
            FROM stone_media m
            WHERE m.stone_id = sm.id AND m.deleted_at IS NULL
        ) AS media
    FROM supplier_master sm
    JOIN suppliers s ON s.supplier_id = sm.supplier_id
    LEFT JOIN value_scores vs ON vs.stone_id = sm.id AND vs.formula_version = 'v1.0'
    WHERE sm.id = :id AND sm.deleted_at IS NULL
    """
)


async def get_stone(session: AsyncSession, stone_id: uuid.UUID) -> dict[str, Any]:
    row = (await session.execute(_DETAIL_SQL, {"id": str(stone_id)})).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stone not found")
    data = dict(row)
    data["id"] = str(data["id"])
    data["media"] = data.get("media") or []
    return data
