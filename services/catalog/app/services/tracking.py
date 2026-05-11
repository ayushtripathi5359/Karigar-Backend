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
    await session.execute(
        text(
            """
            INSERT INTO user_flow_tracking (user_id, stone_id, event_type, session_id)
            VALUES (:u, :s, 'view', :sid)
            """
        ),
        {"u": str(user_id), "s": str(stone_id), "sid": session_id},
    )
