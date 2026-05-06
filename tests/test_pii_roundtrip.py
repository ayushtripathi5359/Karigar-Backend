"""Verify pgcrypto encrypt/decrypt round-trips through a session GUC."""
import pytest
from sqlalchemy.sql import text

from app.db.session import request_session


@pytest.mark.asyncio
async def test_encrypt_decrypt_roundtrip():
    plaintext = "9876543210"
    async with request_session() as session:
        result = (
            await session.execute(
                text("SELECT decrypt_pii(encrypt_pii(:p))"),
                {"p": plaintext},
            )
        ).scalar_one()
    assert result == plaintext


@pytest.mark.asyncio
async def test_phone_hash_is_stable():
    """Same phone + same pepper → same hash. (Required for OTP lookup.)"""
    from app.core.config import get_settings
    from app.core.security import hash_phone

    settings = get_settings()
    a = hash_phone("9876543210", settings.phone_hash_pepper)
    b = hash_phone("9876543210", settings.phone_hash_pepper)
    assert a == b
    assert hash_phone("9876543211", settings.phone_hash_pepper) != a
