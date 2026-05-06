"""
Supplier upload (delta-sync) — the 120/80/40/20 flow.

For each row in the supplier feed:
    - if (supplier_id, stone_id) exists active → UPDATE  (rows_updated)
    - else                                       → INSERT  (rows_new)
    - market signals (price drop, demand spike) → flag rows_trending

Ported from /Users/mainadmin/Desktop/Karigar_Implementation/app/supplier_ingest.py — sync→async.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text


async def start_upload(
    db: AsyncSession,
    *,
    supplier_id: UUID,
    file_url: str,
    file_type: str,
    uploaded_by: UUID | None,
) -> UUID:
    """Create the upload audit row; returns upload_id."""
    return (
        await db.execute(
            text(
                """
                INSERT INTO supplier_uploads
                    (supplier_id, file_url, file_type, status, uploaded_by)
                VALUES
                    (:supplier_id, :file_url, :file_type, 'processing', :uploaded_by)
                RETURNING upload_id
                """
            ),
            {
                "supplier_id": str(supplier_id),
                "file_url": file_url,
                "file_type": file_type,
                "uploaded_by": str(uploaded_by) if uploaded_by else None,
            },
        )
    ).scalar_one()


_UPSERT = text(
    """
    INSERT INTO supplier_master (
        supplier_id, stone_id, upload_id,
        shape, carat, color_scale, fancy_color, clarity, cut, polish, symmetry,
        cert_number, lab, price_per_carat, price, rap_price, rap_discount,
        measurements, raw_payload
    ) VALUES (
        :supplier_id, :stone_id, :upload_id,
        :shape, :carat, :color_scale, :fancy_color, :clarity, :cut, :polish, :symmetry,
        :cert_number, :lab, :price_per_carat, :price, :rap_price, :rap_discount,
        :measurements, CAST(:raw_payload AS jsonb)
    )
    ON CONFLICT (supplier_id, stone_id) WHERE deleted_at IS NULL
    DO UPDATE SET
        shape           = EXCLUDED.shape,
        carat           = EXCLUDED.carat,
        color_scale     = EXCLUDED.color_scale,
        fancy_color     = EXCLUDED.fancy_color,
        clarity         = EXCLUDED.clarity,
        cut             = EXCLUDED.cut,
        polish          = EXCLUDED.polish,
        symmetry        = EXCLUDED.symmetry,
        cert_number     = EXCLUDED.cert_number,
        lab             = EXCLUDED.lab,
        price_per_carat = EXCLUDED.price_per_carat,
        price           = EXCLUDED.price,
        rap_price       = EXCLUDED.rap_price,
        rap_discount    = EXCLUDED.rap_discount,
        measurements    = EXCLUDED.measurements,
        raw_payload     = EXCLUDED.raw_payload,
        upload_id       = EXCLUDED.upload_id
    RETURNING (xmax = 0) AS inserted
    """
)


async def ingest_rows(
    db: AsyncSession,
    *,
    supplier_id: UUID,
    upload_id: UUID,
    rows: Iterable[dict[str, Any]],
) -> dict[str, int]:
    """Process normalized rows. Returns counts for the upload audit record."""
    counts = {"total": 0, "imported": 0, "new": 0, "updated": 0, "failed": 0, "trending": 0}
    errors: list[dict] = []

    for r in rows:
        counts["total"] += 1
        try:
            inserted = (
                await db.execute(
                    _UPSERT,
                    {
                        "supplier_id": str(supplier_id),
                        "stone_id": r["stone_id"],
                        "upload_id": str(upload_id),
                        "shape": r["shape"],
                        "carat": r["carat"],
                        "color_scale": r.get("color_scale"),
                        "fancy_color": r.get("fancy_color"),
                        "clarity": r["clarity"],
                        "cut": r.get("cut"),
                        "polish": r.get("polish"),
                        "symmetry": r.get("symmetry"),
                        "cert_number": r.get("cert_number"),
                        "lab": r.get("lab"),
                        "price_per_carat": r.get("price_per_carat"),
                        "price": r.get("price"),
                        "rap_price": r.get("rap_price"),
                        "rap_discount": r.get("rap_discount"),
                        "measurements": r.get("measurements"),
                        "raw_payload": r.get("raw_payload_json", "{}"),
                    },
                )
            ).scalar_one()
            counts["imported"] += 1
            counts["new" if inserted else "updated"] += 1
            if _is_trending(r):
                counts["trending"] += 1
        except Exception as exc:  # noqa: BLE001
            counts["failed"] += 1
            errors.append({"stone_id": r.get("stone_id"), "error": str(exc)})

    await db.execute(
        text(
            """
            UPDATE supplier_uploads SET
                status        = CASE
                                  WHEN :failed = 0 THEN 'done'::upload_status
                                  WHEN :failed < :total THEN 'partial'::upload_status
                                  ELSE 'failed'::upload_status
                                END,
                rows_total    = :total,
                rows_imported = :imported,
                rows_new      = :new,
                rows_updated  = :updated,
                rows_failed   = :failed,
                rows_trending = :trending,
                error_log     = CAST(:errors AS jsonb),
                processed_at  = now()
            WHERE upload_id = :upload_id
            """
        ),
        {"upload_id": str(upload_id), **counts, "errors": json.dumps(errors)},
    )

    return counts


def _is_trending(row: dict) -> bool:
    """≥ 20% back from list = noteworthy. Replace with trend_signals lookup once aggregation runs."""
    discount = row.get("rap_discount")
    return discount is not None and float(discount) <= -0.20
