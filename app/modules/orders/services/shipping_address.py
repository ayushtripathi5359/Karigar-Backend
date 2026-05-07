"""Resolve an address_id for an order — either an existing one or capture inline."""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from app.modules.users.services import addresses as addr_svc


async def resolve(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    address_id: uuid.UUID | None,
    new_address: dict | None,
) -> uuid.UUID:
    """
    Returns the address_id to attach to the order.

    Either `address_id` (existing) or `new_address` (capture inline) must be
    provided. If neither, falls back to the user's default address.
    """
    if address_id is not None:
        # Confirm it belongs to this user (RLS would block otherwise; surface 404)
        owns = (
            await session.execute(
                text(
                    "SELECT 1 FROM addresses "
                    "WHERE address_id = :a AND user_id = :u AND deleted_at IS NULL"
                ),
                {"a": str(address_id), "u": str(user_id)},
            )
        ).scalar_one_or_none()
        if owns is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "address not found")
        return address_id

    if new_address is not None:
        created = await addr_svc.create_address(
            session,
            user_id=user_id,
            label=new_address.get("label"),
            line1=new_address["line1"],
            line2=new_address.get("line2"),
            city=new_address["city"],
            state=new_address["state"],
            pincode=new_address["pincode"],
            country=new_address.get("country", "India"),
            make_default=new_address.get("make_default", False),
        )
        return created["address_id"]

    # Fall back to default
    default_id = (
        await session.execute(
            text(
                "SELECT address_id FROM addresses "
                "WHERE user_id = :u AND deleted_at IS NULL AND is_default = TRUE "
                "LIMIT 1"
            ),
            {"u": str(user_id)},
        )
    ).scalar_one_or_none()
    if default_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "no shipping address — provide address_id or new_address",
        )
    return default_id
