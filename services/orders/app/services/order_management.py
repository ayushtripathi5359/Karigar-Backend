"""Order row + items + status transitions."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text


async def create_draft(
    session: AsyncSession,
    *,
    buyer_id: uuid.UUID,
    stone_id: uuid.UUID,
    address_id: uuid.UUID,
    quantity: int,
) -> dict[str, Any]:
    if quantity < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "quantity must be >= 1")

    row = (
        await session.execute(
            text("SELECT price FROM supplier_master WHERE id = :id AND deleted_at IS NULL"),
            {"id": str(stone_id)},
        )
    ).first()
    if row is None or row.price is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "stone has no price set")
    unit_price: Decimal = row.price

    subtotal = unit_price * quantity
    total = subtotal

    order_id = (
        await session.execute(
            text(
                """
                INSERT INTO orders (
                    buyer_id, status,
                    subtotal_inr, discount_inr, tax_inr, total_inr,
                    billing_address_id, shipping_address_id,
                    created_by
                ) VALUES (
                    :buyer_id, CAST('draft' AS order_status),
                    :subtotal, 0, 0, :total,
                    :addr, :addr,
                    :buyer_id
                )
                RETURNING order_id
                """
            ),
            {"buyer_id": str(buyer_id), "subtotal": subtotal, "total": total, "addr": str(address_id)},
        )
    ).scalar_one()

    await session.execute(
        text(
            """
            INSERT INTO order_items (order_id, stone_id, quantity, unit_price_inr)
            VALUES (:o, :s, :q, :p)
            """
        ),
        {"o": str(order_id), "s": str(stone_id), "q": quantity, "p": unit_price},
    )

    return await get_order(session, buyer_id=buyer_id, order_id=order_id)


async def transition(
    session: AsyncSession,
    *,
    buyer_id: uuid.UUID,
    order_id: uuid.UUID,
    new_status: str,
) -> None:
    res = await session.execute(
        text(
            """
            UPDATE orders SET status = CAST(:s AS order_status),
                              updated_by = :b
            WHERE order_id = :o AND deleted_at IS NULL
            """
        ),
        {"o": str(order_id), "s": new_status, "b": str(buyer_id)},
    )
    if res.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")


async def get_order(
    session: AsyncSession, *, buyer_id: uuid.UUID, order_id: uuid.UUID
) -> dict[str, Any]:
    order = (
        await session.execute(
            text(
                """
                SELECT order_id, buyer_id, status,
                       subtotal_inr, discount_inr, tax_inr, total_inr,
                       billing_address_id, shipping_address_id,
                       notes, created_at, updated_at
                FROM orders
                WHERE order_id = :o AND deleted_at IS NULL
                """
            ),
            {"o": str(order_id)},
        )
    ).mappings().first()

    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")

    items = (
        await session.execute(
            text(
                """
                SELECT order_item_id, stone_id, quantity, unit_price_inr, total_price_inr
                FROM order_items
                WHERE order_id = :o AND deleted_at IS NULL
                ORDER BY created_at ASC
                """
            ),
            {"o": str(order_id)},
        )
    ).mappings().all()

    tracking = (
        await session.execute(
            text(
                """
                SELECT status, notes, event_at
                FROM order_tracking
                WHERE order_id = :o
                ORDER BY event_at ASC
                """
            ),
            {"o": str(order_id)},
        )
    ).mappings().all()

    return {**dict(order), "items": [dict(i) for i in items], "tracking": [dict(t) for t in tracking]}


async def list_orders(
    session: AsyncSession, *, buyer_id: uuid.UUID, limit: int, offset: int
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT o.order_id, o.status, o.total_inr, o.created_at,
                       (SELECT count(*) FROM order_items oi
                          WHERE oi.order_id = o.order_id AND oi.deleted_at IS NULL) AS item_count
                FROM orders o
                WHERE o.deleted_at IS NULL
                ORDER BY o.created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": limit, "offset": offset},
        )
    ).mappings().all()
    return [dict(r) for r in rows]
