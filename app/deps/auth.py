from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stack import decode_stack_access_token
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.user import AppUser
from app.services import user_service

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
    try:
        return await user_service.sync_user_from_claims(session, claims)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing sub") from None
