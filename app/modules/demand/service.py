from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from app.modules.notifications import service as notifications


async def create_demand_request(
    session: AsyncSession,
    *,
    buyer_id: uuid.UUID,
    stone_id: uuid.UUID,
    requested_discount_pct,
    requested_price_inr,
    message: str | None,
) -> dict[str, Any]:
    stone = (
        await session.execute(
            text(
                """
                SELECT sm.id AS stone_id, sm.stone_id AS stone_code, sm.supplier_id,
                       s.display_name AS supplier_display_name
                FROM supplier_master sm
                JOIN suppliers s ON s.supplier_id = sm.supplier_id
                WHERE sm.id = :stone_id
                  AND sm.deleted_at IS NULL
                  AND s.deleted_at IS NULL
                """
            ),
            {"stone_id": str(stone_id)},
        )
    ).mappings().first()
    if stone is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stone not found")

    demand = (
        await session.execute(
            text(
                """
                INSERT INTO demand_requests (
                  buyer_id, stone_id, supplier_id,
                  requested_discount_pct, requested_price_inr, message
                ) VALUES (
                  :buyer_id, :stone_id, :supplier_id,
                  :requested_discount_pct, :requested_price_inr, :message
                )
                RETURNING demand_request_id, buyer_id, stone_id, supplier_id,
                          requested_discount_pct, requested_price_inr, message,
                          status, response_note, offered_price_inr, resolved_by,
                          created_at, updated_at, resolved_at
                """
            ),
            {
                "buyer_id": str(buyer_id),
                "stone_id": str(stone_id),
                "supplier_id": str(stone["supplier_id"]),
                "requested_discount_pct": requested_discount_pct,
                "requested_price_inr": requested_price_inr,
                "message": message,
            },
        )
    ).mappings().one()
    result = {**dict(demand), "supplier_display_name": stone["supplier_display_name"], "stone_code": stone["stone_code"]}
    await notifications.notify_demand_created(session, demand=result)
    return result


async def list_demand_requests(
    session: AsyncSession,
    *,
    status_filter: str | None,
    supplier_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    where = ["dr.deleted_at IS NULL"]
    params: dict = {"limit": limit, "offset": offset}
    if status_filter:
        where.append("dr.status = :status")
        params["status"] = status_filter
    if supplier_id:
        where.append("dr.supplier_id = :supplier_id")
        params["supplier_id"] = str(supplier_id)
    rows = (
        await session.execute(
            text(
                f"""
                SELECT dr.demand_request_id, dr.buyer_id, dr.stone_id, dr.supplier_id,
                       s.display_name AS supplier_display_name,
                       sm.stone_id AS stone_code,
                       dr.requested_discount_pct, dr.requested_price_inr, dr.message,
                       dr.status, dr.response_note, dr.offered_price_inr,
                       dr.resolved_by, dr.created_at, dr.updated_at, dr.resolved_at
                FROM demand_requests dr
                JOIN suppliers s ON s.supplier_id = dr.supplier_id
                JOIN supplier_master sm ON sm.id = dr.stone_id
                WHERE {' AND '.join(where)}
                ORDER BY dr.created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def get_demand_request(session: AsyncSession, *, demand_request_id: uuid.UUID) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT dr.demand_request_id, dr.buyer_id, dr.stone_id, dr.supplier_id,
                       s.display_name AS supplier_display_name,
                       sm.stone_id AS stone_code,
                       dr.requested_discount_pct, dr.requested_price_inr, dr.message,
                       dr.status, dr.response_note, dr.offered_price_inr,
                       dr.resolved_by, dr.created_at, dr.updated_at, dr.resolved_at
                FROM demand_requests dr
                JOIN suppliers s ON s.supplier_id = dr.supplier_id
                JOIN supplier_master sm ON sm.id = dr.stone_id
                WHERE dr.demand_request_id = :demand_request_id
                  AND dr.deleted_at IS NULL
                """
            ),
            {"demand_request_id": str(demand_request_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "demand request not found")
    return dict(row)


async def update_demand_request(
    session: AsyncSession,
    *,
    demand_request_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    status_value: str,
    response_note: str | None,
    offered_price_inr,
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                UPDATE demand_requests
                SET status = :status,
                    response_note = :response_note,
                    offered_price_inr = :offered_price_inr,
                    resolved_by = :resolved_by,
                    resolved_at = CASE WHEN :status IN ('countered','accepted','rejected','cancelled')
                                       THEN now() ELSE resolved_at END,
                    updated_at = now()
                WHERE demand_request_id = :demand_request_id
                  AND deleted_at IS NULL
                RETURNING demand_request_id
                """
            ),
            {
                "demand_request_id": str(demand_request_id),
                "status": status_value,
                "response_note": response_note,
                "offered_price_inr": offered_price_inr,
                "resolved_by": str(actor_user_id),
            },
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "demand request not found")
    demand = await get_demand_request(session, demand_request_id=demand_request_id)
    await notifications.notify_demand_resolved(session, demand=demand)
    return demand

