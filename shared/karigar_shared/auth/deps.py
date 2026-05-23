"""
Shared auth dependencies used by every protected service.

  bearer_token  : extract Authorization: Bearer <jwt>
  jwt_claims    : decode + verify the token
  current_user  : open an RLS-aware session, verify user exists, yield CurrentUser
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from karigar_shared.config import Settings, get_settings
from karigar_shared.db.session import request_session
from karigar_shared.security import decode_access_token


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
    """Yield CurrentUser(user_id, role, session) for the authenticated request."""
    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token claims") from exc

    role = claims.get("role", "buyer")

    async with request_session(user_id=user_id, role=role) as session:
        exists = (
            await session.execute(
                text("SELECT 1 FROM users WHERE user_id = :u AND deleted_at IS NULL"),
                {"u": str(user_id)},
            )
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")

        yield CurrentUser(user_id=user_id, role=role, session=session)


def require_roles(*roles: str):
    allowed = set(roles)

    async def dependency(
        me: Annotated[CurrentUser, Depends(current_user)],
    ) -> CurrentUser:
        if me.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return me

    return dependency


async def user_can_access_supplier(me: CurrentUser, supplier_id: uuid.UUID) -> bool:
    if me.role in {"admin", "karigar_staff"}:
        return True
    if me.role != "supplier":
        return False
    exists = (
        await me.session.execute(
            text(
                """
                SELECT 1
                FROM supplier_user_mappings
                WHERE user_id = :user_id
                  AND supplier_id = :supplier_id
                  AND deleted_at IS NULL
                """
            ),
            {"user_id": str(me.user_id), "supplier_id": str(supplier_id)},
        )
    ).scalar_one_or_none()
    return exists is not None


async def require_supplier_access(me: CurrentUser, supplier_id: uuid.UUID) -> None:
    if not await user_can_access_supplier(me, supplier_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "supplier access denied")
