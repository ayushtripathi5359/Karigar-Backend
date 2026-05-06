"""
Async, RLS-aware session factory.

Every authenticated request runs inside a single transaction with three
session-local GUCs set:

    SET LOCAL app.current_user_id   = '<uuid>';
    SET LOCAL app.current_user_role = 'buyer' | 'supplier' | 'admin' | 'karigar_staff';
    SET LOCAL app.encryption_key    = '<key>';

The Postgres helper functions current_user_id() / is_admin() / encrypt_pii() /
decrypt_pii() read these GUCs to enforce RLS and PII encryption.

`SET LOCAL` lifetime ends with the transaction — so the request handler must
do all its DB work inside the single `async with request_session(...)` block
and avoid intermediate commits.
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

from app.core.config import get_settings

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
    # set_config(name, value, is_local) — is_local=true scopes to the txn.
    # Safer than SQL-level "SET LOCAL" because it's parameterized.
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
    """
    Yield an AsyncSession scoped to one transaction with RLS GUCs set.

    Anonymous (pre-auth) usage: omit user_id and role — RLS treats this as
    a public/system session, useful for OTP signup INSERT (allowed by
    `users_admin_insert` policy when current_user_id() IS NULL).

    Caller must do all DB work inside the `async with` block; commit happens
    on exit if no exception, rollback otherwise.
    """
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
