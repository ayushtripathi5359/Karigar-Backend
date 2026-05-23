from __future__ import annotations

import secrets
from uuid import UUID

from sqlalchemy.sql import text

from app.core.config import get_settings
from app.core.security import issue_access_token
from app.db.session import request_session


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_test_user(role: str = "buyer", full_name: str | None = None) -> tuple[UUID, str]:
    """Create a real DB user and return `(user_id, bearer_token)`.

    Integration tests exercise FastAPI dependencies and RLS-aware sessions, so
    they need persisted users instead of mocked identities.
    """
    suffix = secrets.token_hex(8)
    email = f"test-{role}-{suffix}@example.test"
    name = full_name or f"Test {role} {suffix}"
    async with request_session() as session:
        user_id = (
            await session.execute(
                text(
                    """
                    INSERT INTO users (
                      email, full_name_encrypted, role, is_verified
                    ) VALUES (
                      :email, encrypt_pii(:full_name), CAST(:role AS user_role), TRUE
                    )
                    RETURNING user_id
                    """
                ),
                {"email": email, "full_name": name, "role": role},
            )
        ).scalar_one()

    token = issue_access_token(user_id, role, get_settings())
    return user_id, token


async def create_test_supplier(display_name: str = "Test Supplier") -> UUID:
    suffix = secrets.token_hex(6)
    async with request_session() as session:
        return (
            await session.execute(
                text(
                    """
                    INSERT INTO suppliers (
                      supplier_code, display_name, tier, is_active, onboarded_at
                    ) VALUES (
                      :supplier_code, :display_name, 'T2', TRUE, now()
                    )
                    RETURNING supplier_id
                    """
                ),
                {
                    "supplier_code": f"TST_{suffix}",
                    "display_name": f"{display_name} {suffix}",
                },
            )
        ).scalar_one()


async def create_test_stone(*, supplier_id: UUID, stone_code: str | None = None, price: int = 125000) -> UUID:
    """Insert one available supplier stone for demand/order integration tests."""
    suffix = secrets.token_hex(6)
    async with request_session() as session:
        return (
            await session.execute(
                text(
                    """
                    INSERT INTO supplier_master (
                      supplier_id, stone_id, shape, carat, color_scale, clarity,
                      cut, polish, symmetry, lab, price_per_carat, price, rap_discount
                    ) VALUES (
                      :supplier_id, :stone_id, 'round'::stone_shape, 1.20, 'G'::stone_color_scale, 'VS1'::stone_clarity,
                      'Excellent'::stone_cut, 'Very Good'::stone_polish, 'Good'::stone_symmetry,
                      'GIA'::lab_name, :price_per_carat, :price, -0.25
                    )
                    RETURNING id
                    """
                ),
                {
                    "supplier_id": str(supplier_id),
                    "stone_id": stone_code or f"TST-STONE-{suffix}",
                    "price_per_carat": price,
                    "price": price,
                },
            )
        ).scalar_one()


async def create_supplier_mapping(
    *,
    user_id: UUID,
    supplier_id: UUID,
    created_by: UUID | None = None,
    role_in_supplier: str = "manager",
    is_primary: bool = True,
) -> UUID:
    async with request_session() as session:
        return (
            await session.execute(
                text(
                    """
                    INSERT INTO supplier_user_mappings (
                      user_id, supplier_id, role_in_supplier, is_primary, created_by
                    ) VALUES (
                      :user_id, :supplier_id, :role_in_supplier, :is_primary, :created_by
                    )
                    RETURNING mapping_id
                    """
                ),
                {
                    "user_id": str(user_id),
                    "supplier_id": str(supplier_id),
                    "role_in_supplier": role_in_supplier,
                    "is_primary": is_primary,
                    "created_by": str(created_by) if created_by else None,
                },
            )
        ).scalar_one()
