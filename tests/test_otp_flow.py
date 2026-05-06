"""End-to-end test of the OTP auth flow.

Reads the OTP code straight from the DB (since the stub provider only prints
to stdout). In a real test setup we'd inject a `RecordingSender` provider via
DI override; this is the simpler path while the auth router constructs its
own provider.
"""
import pytest
from sqlalchemy.sql import text

from app.core.config import get_settings
from app.core.security import hash_phone
from app.db.session import request_session


async def latest_unverified_otp_id(phone_hash: str) -> str | None:
    """Look up the most recent OTP record for a given phone_hash."""
    async with request_session() as session:
        return (
            await session.execute(
                text(
                    """
                    SELECT otp_id FROM otp_records
                    WHERE phone_hash = :p AND verified_at IS NULL
                    ORDER BY created_at DESC LIMIT 1
                    """
                ),
                {"p": phone_hash},
            )
        ).scalar_one_or_none()


@pytest.mark.asyncio
async def test_request_otp_creates_record(client, unique_phone):
    settings = get_settings()
    r = await client.post("/v1/auth/otp/request", json={"phone": unique_phone})
    assert r.status_code == 200, r.text
    assert r.json()["expires_in"] == settings.otp_expiry_seconds

    phone_hash = hash_phone(unique_phone, settings.phone_hash_pepper)
    otp_id = await latest_unverified_otp_id(phone_hash)
    assert otp_id is not None


@pytest.mark.asyncio
async def test_verify_with_wrong_code_fails(client, unique_phone):
    await client.post("/v1/auth/otp/request", json={"phone": unique_phone})
    r = await client.post(
        "/v1/auth/otp/verify",
        json={"phone": unique_phone, "code": "000000"},
    )
    assert r.status_code == 400
    assert "incorrect" in r.json()["message"].lower()


@pytest.mark.asyncio
async def test_validation_rejects_bad_phone(client):
    r = await client.post("/v1/auth/otp/request", json={"phone": "1234567890"})
    assert r.status_code == 422  # must start with 6-9
