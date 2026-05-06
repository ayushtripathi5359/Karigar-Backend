"""
FastAPI dependencies for DB sessions.

Two flavours:
  - get_db_anonymous : no user context (signup, public reads, OTP request)
  - get_db_for_user  : sets RLS GUCs for the authenticated user

The auth module's `current_user` dependency layers on top of these.
"""
from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import request_session


async def get_db_anonymous() -> AsyncIterator[AsyncSession]:
    async with request_session() as session:
        yield session


# get_db_for_user is wired in app/modules/auth/deps.py to avoid a circular
# import (it depends on current_user, which is defined there).
__all__ = ["get_db_anonymous", "Depends"]
