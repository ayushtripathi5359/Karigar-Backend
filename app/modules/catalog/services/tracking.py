"""Catalog-side `user_flow_tracking` writes (view, click, dwell, share)."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text


async def record_view(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    stone_id: uuid.UUID,
    session_id: str | None = None,
) -> None:
    """Log a stone view. Called from GET /v1/catalog/stones/{id}.

    The uft_system_write RLS policy permits inserts where user_id matches
    the session GUC, so this runs inside the authenticated request_session.
    """
    await session.execute(
        text(
            """
            INSERT INTO user_flow_tracking (user_id, stone_id, event_type, session_id)
            VALUES (:u, :s, 'view', :sid)
            """
        ),
        {"u": str(user_id), "s": str(stone_id), "sid": session_id},
    )
