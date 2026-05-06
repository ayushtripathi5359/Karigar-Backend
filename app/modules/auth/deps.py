"""
Auth dependencies.

  - bearer_token  : extract Authorization: Bearer <jwt>
  - jwt_claims    : decode + verify the token (returns dict)
  - current_user  : open an RLS-aware session, load the users row, return it.
                    Use this dep on every protected endpoint — it yields
                    (user_id, role, AsyncSession) so handlers can call the DB
                    inside the same transaction with the GUCs already set.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from app.core.config import Settings, get_settings
from app.core.security import decode_access_token
from app.db.session import request_session


def bearer_token(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> str:
    if not authorization:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "malformed Authorization header")
    return parts[1]


def jwt_claims(
    token: Annotated[str, Depends(bearer_token)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    return decode_access_token(token, settings)


@dataclass
class CurrentUser:
    user_id: uuid.UUID
    role: str
    session: AsyncSession  # already in a tx with RLS GUCs set


async def current_user(
    claims: Annotated[dict, Depends(jwt_claims)],
) -> AsyncIterator[CurrentUser]:
    """
    Yield (user_id, role, session) for the authenticated request.

    The session is opened with `request_session(user_id, role)` so all queries
    inside the handler honour RLS and can decrypt PII via the session GUCs.
    """
    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token claims") from exc

    role = claims.get("role", "buyer")

    async with request_session(user_id=user_id, role=role) as session:
        # Verify the user still exists (and isn't soft-deleted).
        # RLS policy users_self_read allows this read because user_id matches GUC.
        exists = (
            await session.execute(
                text("SELECT 1 FROM users WHERE user_id = :u AND deleted_at IS NULL"),
                {"u": str(user_id)},
            )
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")

        yield CurrentUser(user_id=user_id, role=role, session=session)
