from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from karigar_shared.db.session import request_session


async def get_db_anonymous() -> AsyncIterator[AsyncSession]:
    async with request_session() as session:
        yield session


__all__ = ["get_db_anonymous", "Depends"]
