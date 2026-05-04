from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_stack import decode_stack_access_token
from app.config import Settings, get_settings
from app.db import get_db
from app.models import AppUser

BearerDep = Annotated[str | None, Header(alias="Authorization")]


async def stack_claims(
    authorization: BearerDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    return decode_stack_access_token(token, settings)


async def current_user(
    claims: Annotated[dict, Depends(stack_claims)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AppUser:
    sub = claims.get("sub")
    if not sub or not isinstance(sub, str):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing sub")
    email = claims.get("email") if isinstance(claims.get("email"), str) else None
    result = await session.execute(select(AppUser).where(AppUser.stack_user_id == sub))
    row = result.scalar_one_or_none()
    if row is None:
        row = AppUser(stack_user_id=sub, email=email)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    elif email and row.email != email:
        row.email = email
        await session.commit()
        await session.refresh(row)
    return row
