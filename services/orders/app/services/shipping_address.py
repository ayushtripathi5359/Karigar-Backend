"""
Resolve a shipping address for an order.

Inlines address creation SQL directly (shared DB) instead of calling the
users service over HTTP, avoiding inter-service network overhead.
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text


async def resolve(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    address_id: uuid.UUID | None,
    new_address: dict | None,
) -> uuid.UUID:
    if address_id is not None:
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
        line2 = new_address.get("line2")
        make_default = new_address.get("make_default", False)

        if make_default:
            await session.execute(
                text(
                    "UPDATE addresses SET is_default = FALSE "
                    "WHERE user_id = :u AND deleted_at IS NULL AND is_default = TRUE"
                ),
                {"u": str(user_id)},
            )

        if line2 is None:
            new_id = (
                await session.execute(
                    text(
                        """
                        INSERT INTO addresses (
                            user_id, label, line1_encrypted,
                            city, state, pincode, country, is_default
                        ) VALUES (
                            :u, :label, encrypt_pii(:line1),
                            :city, :state, :pincode, :country, :is_default
                        )
                        RETURNING address_id
                        """
                    ),
                    {
                        "u": str(user_id), "label": new_address.get("label"),
                        "line1": new_address["line1"], "city": new_address["city"],
                        "state": new_address["state"], "pincode": new_address["pincode"],
                        "country": new_address.get("country", "India"), "is_default": make_default,
                    },
                )
            ).scalar_one()
        else:
            new_id = (
                await session.execute(
                    text(
                        """
                        INSERT INTO addresses (
                            user_id, label, line1_encrypted, line2_encrypted,
                            city, state, pincode, country, is_default
                        ) VALUES (
                            :u, :label, encrypt_pii(:line1), encrypt_pii(:line2),
                            :city, :state, :pincode, :country, :is_default
                        )
                        RETURNING address_id
                        """
                    ),
                    {
                        "u": str(user_id), "label": new_address.get("label"),
                        "line1": new_address["line1"], "line2": line2,
                        "city": new_address["city"], "state": new_address["state"],
                        "pincode": new_address["pincode"],
                        "country": new_address.get("country", "India"), "is_default": make_default,
                    },
                )
            ).scalar_one()

        return new_id

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
