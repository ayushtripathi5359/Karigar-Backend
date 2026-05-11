"""Address CRUD — PII encrypted via pgcrypto SQL."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text


async def list_addresses(session: AsyncSession, user_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT address_id,
                       label,
                       decrypt_pii(line1_encrypted) AS line1,
                       decrypt_pii(line2_encrypted) AS line2,
                       city, state, pincode, country, is_default,
                       created_at
                FROM addresses
                WHERE user_id = :u AND deleted_at IS NULL
                ORDER BY is_default DESC, created_at DESC
                """
            ),
            {"u": str(user_id)},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def create_address(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    label: str | None,
    line1: str,
    line2: str | None,
    city: str,
    state: str,
    pincode: str,
    country: str,
    make_default: bool,
) -> dict[str, Any]:
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
                    "u": str(user_id), "label": label, "line1": line1,
                    "city": city, "state": state, "pincode": pincode,
                    "country": country, "is_default": make_default,
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
                    "u": str(user_id), "label": label, "line1": line1, "line2": line2,
                    "city": city, "state": state, "pincode": pincode,
                    "country": country, "is_default": make_default,
                },
            )
        ).scalar_one()

    return await get_address(session, user_id=user_id, address_id=new_id)


async def get_address(
    session: AsyncSession, *, user_id: uuid.UUID, address_id: uuid.UUID
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT address_id, label,
                       decrypt_pii(line1_encrypted) AS line1,
                       decrypt_pii(line2_encrypted) AS line2,
                       city, state, pincode, country, is_default, created_at
                FROM addresses
                WHERE address_id = :a AND user_id = :u AND deleted_at IS NULL
                """
            ),
            {"a": str(address_id), "u": str(user_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "address not found")
    return dict(row)


async def set_default(
    session: AsyncSession, *, user_id: uuid.UUID, address_id: uuid.UUID
) -> None:
    await get_address(session, user_id=user_id, address_id=address_id)
    await session.execute(
        text(
            "UPDATE addresses SET is_default = FALSE "
            "WHERE user_id = :u AND deleted_at IS NULL AND is_default = TRUE"
        ),
        {"u": str(user_id)},
    )
    await session.execute(
        text("UPDATE addresses SET is_default = TRUE WHERE address_id = :a"),
        {"a": str(address_id)},
    )


async def soft_delete(
    session: AsyncSession, *, user_id: uuid.UUID, address_id: uuid.UUID
) -> None:
    await get_address(session, user_id=user_id, address_id=address_id)
    await session.execute(
        text("UPDATE addresses SET deleted_at = now(), is_default = FALSE WHERE address_id = :a"),
        {"a": str(address_id)},
    )
