import uuid
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stack import decode_stack_access_token
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.user import AppUser
from app.services import user_service

BearerDep = Annotated[str | None, Header(alias="Authorization")]


def _extract_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    return token


async def stack_claims(
    authorization: BearerDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    token = _extract_token(authorization)

    # Peek at the issuer without verifying signature first
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
        if unverified.get("iss") == "karigar":
            return jwt.decode(token, settings.otp_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token has expired")
    except jwt.InvalidTokenError:
        pass  # not a karigar token — fall through to Stack Auth

    return decode_stack_access_token(token, settings)


async def current_user(
    claims: Annotated[dict, Depends(stack_claims)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AppUser:
    if claims.get("iss") == "karigar":
        user_id_str = claims.get("sub")
        if not user_id_str:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token payload")
        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token payload") from None
        result = await session.execute(select(AppUser).where(AppUser.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
        return user

    try:
        return await user_service.sync_user_from_claims(session, claims)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing sub") from None
