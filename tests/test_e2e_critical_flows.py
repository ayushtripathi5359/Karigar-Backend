import secrets

import pytest

from tests.helpers import (
    auth_headers,
    create_supplier_mapping,
    create_test_supplier,
    create_test_user,
)


async def login_by_otp(client, monkeypatch: pytest.MonkeyPatch, phone: str) -> str:
    from app.modules.auth import service as auth_service

    fixed_code = "424242"
    monkeypatch.setattr(auth_service, "generate_otp_code", lambda _length=6: fixed_code)

    request_response = await client.post("/v1/auth/otp/request", json={"phone": phone})
    assert request_response.status_code == 200, request_response.text

    verify_response = await client.post("/v1/auth/otp/verify", json={"phone": phone, "code": fixed_code})
    assert verify_response.status_code == 200, verify_response.text
    return verify_response.json()["access_token"]


def e2e_supplier_csv(stone_id: str, price: int = 125000) -> bytes:
    return (
        "stone_id,shape,carat,color,clarity,cut,polish,symmetry,lab,price,rap_discount\n"
        f"{stone_id},Round,1.20,G,VS1,EX,VG,Good,GIA,{price},-25\n"
    ).encode()


@pytest.mark.asyncio
async def test_e2e_login_catalog_checkout_and_payment(client, monkeypatch):
    token = await login_by_otp(client, monkeypatch, f"98{secrets.randbelow(10**8):08d}")
    headers = auth_headers(token)

    me_response = await client.get("/v1/user", headers=headers)
    assert me_response.status_code == 200, me_response.text

    catalog_response = await client.get("/v1/catalog/stones?limit=1")
    assert catalog_response.status_code == 200, catalog_response.text
    catalog_items = catalog_response.json()["items"]
    assert catalog_items, "seed catalog must contain at least one available stone"

    stone_id = catalog_items[0]["id"]
    detail_response = await client.get(f"/v1/catalog/stones/{stone_id}", headers=headers)
    assert detail_response.status_code == 200, detail_response.text

    order_response = await client.post(
        "/v1/orders",
        headers=headers,
        json={
            "stone_id": stone_id,
            "new_address": {
                "label": "Home",
                "line1": "E2E Tower",
                "city": "Mumbai",
                "state": "Maharashtra",
                "pincode": "400001",
                "make_default": True,
            },
        },
    )
    assert order_response.status_code == 201, order_response.text
    order = order_response.json()
    assert order["status"] == "draft"

    payment_idempotency_key = f"e2e-{secrets.token_urlsafe(8)}"
    payment_intent_response = await client.post(
        "/v1/payments/intent",
        headers=headers,
        json={"order_id": order["order_id"], "idempotency_key": payment_idempotency_key},
    )
    assert payment_intent_response.status_code == 201, payment_intent_response.text

    confirm_response = await client.post(
        "/v1/payments/confirm",
        headers=headers,
        json={
            "payment_id": payment_intent_response.json()["payment_id"],
            "idempotency_key": payment_idempotency_key,
            "outcome": "success",
        },
    )
    assert confirm_response.status_code == 200, confirm_response.text
    assert confirm_response.json()["order_status"] == "confirmed"


@pytest.mark.asyncio
async def test_e2e_admin_upload_then_supplier_upload_scope(client):
    admin_id, admin_token = await create_test_user("admin")
    supplier_user_id, supplier_token = await create_test_user("supplier")
    supplier_id = await create_test_supplier("E2E Supplier")
    await create_supplier_mapping(user_id=supplier_user_id, supplier_id=supplier_id, created_by=admin_id)

    admin_profile = await client.get("/v1/admin/me", headers=auth_headers(admin_token))
    assert admin_profile.status_code == 200, admin_profile.text

    stone_id = f"E2E-{secrets.token_hex(6)}"
    admin_upload = await client.post(
        "/v1/suppliers/uploads",
        headers=auth_headers(admin_token),
        data={"supplier_id": str(supplier_id)},
        files={"file": ("admin-feed.csv", e2e_supplier_csv(stone_id), "text/csv")},
    )
    assert admin_upload.status_code == 200, admin_upload.text
    assert admin_upload.json()["upload"]["rows_new"] == 1

    supplier_upload = await client.post(
        "/v1/suppliers/uploads",
        headers=auth_headers(supplier_token),
        data={"supplier_id": str(supplier_id)},
        files={"file": ("supplier-feed.csv", e2e_supplier_csv(stone_id, price=130000), "text/csv")},
    )
    assert supplier_upload.status_code == 200, supplier_upload.text
    assert supplier_upload.json()["upload"]["rows_updated"] == 1

    supplier_uploads = await client.get(
        f"/v1/suppliers/uploads?supplier_id={supplier_id}",
        headers=auth_headers(supplier_token),
    )
    assert supplier_uploads.status_code == 200, supplier_uploads.text
    assert supplier_uploads.json()["items"]
