"""
User repository.

Encryption is explicit: writes wrap PII fields in `encrypt_pii(:val)` SQL,
reads select `decrypt_pii(col) AS col`. We do NOT use a transparent ORM type
because pgcrypto round-trip is non-deterministic and SQLAlchemy can't model
the GUC-dependent decryption cleanly.

Every call must run inside a `request_session()` so the encryption key GUC
is set; otherwise decrypt_pii() raises.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text


async def get_profile(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT
                    user_id,
                    email,
                    decrypt_pii(phone_encrypted)     AS phone,
                    decrypt_pii(full_name_encrypted) AS full_name,
                    role,
                    is_verified,
                    full_name_encrypted IS NOT NULL  AS onboarding_completed,
                    last_login_at,
                    created_at
                FROM users
                WHERE user_id = :u AND deleted_at IS NULL
                """
            ),
            {"u": str(user_id)},
        )
    ).mappings().first()
    return dict(row) if row else None


async def update_onboarding(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    display_name: str,
    email: str | None,
) -> None:
    if email is None:
        await session.execute(
            text(
                """
                UPDATE users
                SET full_name_encrypted = encrypt_pii(:name),
                    is_verified = TRUE
                WHERE user_id = :u
                """
            ),
            {"name": display_name, "u": str(user_id)},
        )
    else:
        await session.execute(
            text(
                """
                UPDATE users
                SET full_name_encrypted = encrypt_pii(:name),
                    email = :email,
                    is_verified = TRUE
                WHERE user_id = :u
                """
            ),
            {"name": display_name, "email": email, "u": str(user_id)},
        )
