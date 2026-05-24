from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from app.modules.auth.deps import CurrentUser, require_roles
from tests.helpers import auth_headers, create_supplier_mapping, create_test_supplier, create_test_user


@pytest.mark.asyncio
async def test_role_guard_allows_configured_roles():
    dependency = require_roles("admin", "karigar_staff")
    me = CurrentUser(user_id=uuid4(), role="admin", session=None)  # type: ignore[arg-type]

    assert await dependency(me) is me


@pytest.mark.asyncio
async def test_role_guard_rejects_other_roles():
    dependency = require_roles("admin", "karigar_staff")
    me = CurrentUser(user_id=uuid4(), role="buyer", session=None)  # type: ignore[arg-type]

    with pytest.raises(HTTPException) as exc:
        await dependency(me)

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_admin_me_allows_supplier_workspace_and_rejects_buyer(client):
    admin_id, _admin_token = await create_test_user("admin")
    supplier_user_id, supplier_token = await create_test_user("supplier")
    _buyer_id, buyer_token = await create_test_user("buyer")
    supplier_id = await create_test_supplier()
    await create_supplier_mapping(user_id=supplier_user_id, supplier_id=supplier_id, created_by=admin_id)

    supplier_response = await client.get("/v1/admin/me", headers=auth_headers(supplier_token))
    assert supplier_response.status_code == 200, supplier_response.text
    supplier_profile = supplier_response.json()
    assert supplier_profile["role"] == "supplier"
    assert [supplier["supplier_id"] for supplier in supplier_profile["suppliers"]] == [str(supplier_id)]

    buyer_response = await client.get("/v1/admin/me", headers=auth_headers(buyer_token))
    assert buyer_response.status_code == 403
