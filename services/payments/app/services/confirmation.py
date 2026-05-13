"""
Confirm a payment. Atomic with the order status flip and inventory_log write.

Inlines order transition and tracking SQL directly (shared DB) instead of
calling the orders service over HTTP.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from app.providers.base import PaymentProvider


async def confirm(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    payment_id: uuid.UUID,
    idempotency_key: str,
    requested_outcome: str,
    provider: PaymentProvider,
) -> dict[str, Any]:
    payment = (
        await session.execute(
            text(
                """
                SELECT payment_id, order_id, provider, provider_payment_id,
                       amount_inr, status, idempotency_key, finalized_at
                FROM payments
                WHERE payment_id = :p
                FOR UPDATE
                """
            ),
            {"p": str(payment_id)},
        )
    ).mappings().first()

    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "payment not found")
    if payment["idempotency_key"] != idempotency_key:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "idempotency_key does not match the original intent")

    if payment["status"] in ("succeeded", "failed", "cancelled"):
        order_status = (
            await session.execute(
                text("SELECT status FROM orders WHERE order_id = :o"),
                {"o": str(payment["order_id"])},
            )
        ).scalar_one()
        return {
            "payment_id": payment["payment_id"],
            "status": payment["status"],
            "order_id": payment["order_id"],
            "order_status": order_status,
            "finalized_at": payment["finalized_at"],
        }

    result = await provider.confirm(
        provider_payment_id=payment["provider_payment_id"],
        requested_outcome=requested_outcome,
    )

    finalized = (
        await session.execute(
            text(
                """
                UPDATE payments
                SET status = :s, error_code = :ec, error_message = :em, finalized_at = now()
                WHERE payment_id = :p
                RETURNING finalized_at
                """
            ),
            {"s": result.status, "ec": result.error_code, "em": result.error_message,
             "p": str(payment_id)},
        )
    ).scalar_one()

    new_order_status = "confirmed" if result.status == "succeeded" else "cancelled"

    # Inline: order_management.transition()
    await session.execute(
        text(
            """
            UPDATE orders SET status = CAST(:s AS order_status), updated_by = :b
            WHERE order_id = :o AND deleted_at IS NULL
            """
        ),
        {"o": str(payment["order_id"]), "s": new_order_status, "b": str(user_id)},
    )

    # Inline: order_tracking.log_status()
    notes = (
        "payment succeeded — order confirmed"
        if result.status == "succeeded"
        else f"payment failed: {result.error_message or 'unknown'}"
    )
    await session.execute(
        text(
            """
            INSERT INTO order_tracking (order_id, status, notes, created_by)
            VALUES (:o, CAST(:s AS order_status), :n, :a)
            """
        ),
        {"o": str(payment["order_id"]), "s": new_order_status, "n": notes, "a": str(user_id)},
    )

    if result.status == "succeeded":
        stone_id = (
            await session.execute(
                text("SELECT stone_id FROM order_items WHERE order_id = :o LIMIT 1"),
                {"o": str(payment["order_id"])},
            )
        ).scalar_one()
        await session.execute(
            text(
                """
                INSERT INTO inventory_log (
                    stone_id, event_type, user_id, quantity_change, price_inr
                ) VALUES (
                    :s, CAST('purchased' AS inventory_event_type), :u, -1, :p
                )
                """
            ),
            {"s": str(stone_id), "u": str(user_id), "p": payment["amount_inr"]},
        )

    return {
        "payment_id": payment_id,
        "status": result.status,
        "order_id": payment["order_id"],
        "order_status": new_order_status,
        "finalized_at": finalized,
    }
