"""
Confirm a payment.

Atomic with the order status flip and the inventory_log write — all in the
same transaction so a crash mid-way leaves the DB internally consistent.

Idempotent on (idempotency_key): a replay sees the finalized row and
returns the same outcome.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from app.modules.orders.services import order_management, tracking as order_tracking
from app.modules.notifications.service import notify_order_transaction
from app.modules.payments.providers.base import PaymentProvider


async def confirm(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    payment_id: uuid.UUID,
    idempotency_key: str,
    requested_outcome: str,
    provider: PaymentProvider,
) -> dict[str, Any]:
    # Lock the payment row so concurrent confirms collapse to one outcome.
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
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "idempotency_key does not match the original intent",
        )

    # Already finalized — return the recorded outcome (true idempotency).
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

    # Call the provider (stub honours requested_outcome; real ones ignore it).
    result = await provider.confirm(
        provider_payment_id=payment["provider_payment_id"],
        requested_outcome=requested_outcome,
    )

    # Flip payment + order in one tx
    finalized = (
        await session.execute(
            text(
                """
                UPDATE payments
                SET status = :s,
                    error_code = :ec,
                    error_message = :em,
                    finalized_at = now()
                WHERE payment_id = :p
                RETURNING finalized_at
                """
            ),
            {
                "s": result.status,
                "ec": result.error_code,
                "em": result.error_message,
                "p": str(payment_id),
            },
        )
    ).scalar_one()

    new_order_status = "confirmed" if result.status == "succeeded" else "cancelled"
    await order_management.transition(
        session,
        buyer_id=user_id,
        order_id=payment["order_id"],
        new_status=new_order_status,
    )
    await order_tracking.log_status(
        session,
        order_id=payment["order_id"],
        status=new_order_status,
        notes=(
            "payment succeeded — order confirmed"
            if result.status == "succeeded"
            else f"payment failed: {result.error_message or 'unknown'}"
        ),
        actor_user_id=user_id,
    )

    if result.status == "succeeded":
        # Inventory event — only on success per design (cancel skips this).
        stone_id = (
            await session.execute(
                text(
                    """
                    SELECT stone_id FROM order_items
                    WHERE order_id = :o
                    LIMIT 1
                    """
                ),
                {"o": str(payment["order_id"])},
            )
        ).scalar_one()
        await order_tracking.record_purchase(
            session,
            stone_id=stone_id,
            user_id=user_id,
            price_inr=payment["amount_inr"],
        )

    await notify_order_transaction(
        session,
        order_id=payment["order_id"],
        buyer_id=user_id,
        order_status=new_order_status,
    )

    return {
        "payment_id": payment_id,
        "status": result.status,
        "order_id": payment["order_id"],
        "order_status": new_order_status,
        "finalized_at": finalized,
    }
