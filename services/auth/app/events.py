"""Append-only audit writer for auth_events."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text


async def record(
    session: AsyncSession,
    *,
    event_type: str,
    user_id: uuid.UUID | None = None,
    phone_hash: str | None = None,
    request_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO auth_events
                (event_type, user_id, phone_hash, request_id, ip, user_agent)
            VALUES
                (CAST(:event_type AS auth_event_type), :user_id, :phone_hash,
                 :request_id, CAST(:ip AS INET), :user_agent)
            """
        ),
        {
            "event_type": event_type,
            "user_id": str(user_id) if user_id else None,
            "phone_hash": phone_hash,
            "request_id": request_id,
            "ip": ip,
            "user_agent": user_agent,
        },
    )
