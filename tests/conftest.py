"""
pytest fixtures.

Tests run against the live `karigar_app` database. Each test uses a unique
phone number so state from previous tests doesn't bleed in.

To run: `pytest -q` from repo root with the venv activated.
"""
import secrets

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def unique_phone() -> str:
    """A 10-digit Indian-format mobile number nobody else has used."""
    suffix = secrets.randbelow(10**9)
    return f"9{suffix:09d}"
