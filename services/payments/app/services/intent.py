"""Create a payment intent. Idempotent on (idempotency_key)."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from app.providers.base import PaymentProvider


async def create_intent(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    order_id: uuid.UUID,
    idempotency_key: str,
    provider: PaymentProvider,
) -> dict[str, Any]:
    existing = (
        await session.execute(
            text(
                """
                SELECT payment_id, order_id, provider, provider_payment_id,
                       amount_inr, status, created_at, finalized_at
                FROM payments
                WHERE idempotency_key = :k
                """
            ),
            {"k": idempotency_key},
        )
    ).mappings().first()
    if existing is not None:
        return dict(existing)

    order = (
        await session.execute(
            text(
                """
                SELECT total_inr, status
                FROM orders
                WHERE order_id = :o AND deleted_at IS NULL
                """
            ),
            {"o": str(order_id)},
        )
    ).first()
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")
    if order.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"order is '{order.status}' — only 'draft' orders accept payment")
    if order.total_inr is None or order.total_inr <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "order has no positive total")

    intent = await provider.create_intent(
        order_id=str(order_id),
        amount_inr=order.total_inr,
        idempotency_key=idempotency_key,
    )

    row = (
        await session.execute(
            text(
                """
                INSERT INTO payments (
                    order_id, provider, provider_payment_id,
                    amount_inr, status, idempotency_key
                ) VALUES (
                    :o, :p, :pref, :amt, 'initiated', :k
                )
                RETURNING payment_id, order_id, provider, provider_payment_id,
                          amount_inr, status, created_at, finalized_at
                """
            ),
            {
                "o": str(order_id), "p": provider.name,
                "pref": intent.provider_payment_id,
                "amt": order.total_inr, "k": idempotency_key,
            },
        )
    ).mappings().first()
    assert row is not None
    return dict(row)
