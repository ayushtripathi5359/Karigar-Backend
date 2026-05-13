"""
Async, RLS-aware session factory.

Every authenticated request runs inside a single transaction with three
session-local GUCs set:

    SET LOCAL app.current_user_id   = '<uuid>';
    SET LOCAL app.current_user_role = 'buyer' | 'supplier' | 'admin' | 'karigar_staff';
    SET LOCAL app.encryption_key    = '<key>';

`SET LOCAL` lifetime ends with the transaction.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql import text

from karigar_shared.config import get_settings

_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

SessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def _set_rls_guc(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    role: str | None,
    encryption_key: str,
) -> None:
    await session.execute(
        text("SELECT set_config('app.current_user_id', :v, true)"),
        {"v": str(user_id) if user_id else ""},
    )
    await session.execute(
        text("SELECT set_config('app.current_user_role', :v, true)"),
        {"v": role or ""},
    )
    await session.execute(
        text("SELECT set_config('app.encryption_key', :v, true)"),
        {"v": encryption_key},
    )


@asynccontextmanager
async def request_session(
    *,
    user_id: uuid.UUID | None = None,
    role: str | None = None,
) -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession scoped to one transaction with RLS GUCs set."""
    session = SessionFactory()
    try:
        async with session.begin():
            await _set_rls_guc(
                session,
                user_id=user_id,
                role=role,
                encryption_key=_settings.pii_encryption_key,
            )
            yield session
    finally:
        await session.close()
