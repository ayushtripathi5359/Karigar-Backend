import secrets

import pytest

from tests.helpers import (
    auth_headers,
    create_supplier_mapping,
    create_test_supplier,
    create_test_user,
)


def supplier_csv(stone_id: str, price: int = 125000) -> bytes:
    return (
        "stone_id,shape,carat,color,clarity,cut,polish,symmetry,lab,price,rap_discount\n"
        f"{stone_id},Round,1.20,G,VS1,EX,VG,Good,GIA,{price},-25\n"
    ).encode()


@pytest.mark.asyncio
async def test_admin_can_create_and_soft_delete_supplier_mapping(client):
    _admin_id, admin_token = await create_test_user("admin")
    supplier_user_id, _supplier_token = await create_test_user("buyer")
    other_supplier_user_id, _other_supplier_token = await create_test_user("buyer")
    supplier_id = await create_test_supplier()
    other_supplier_id = await create_test_supplier("Other Mapping Supplier")

    create_response = await client.post(
        "/v1/admin/supplier-user-mappings",
        headers=auth_headers(admin_token),
        json={
            "user_id": str(supplier_user_id),
            "supplier_id": str(supplier_id),
            "role_in_supplier": "manager",
            "is_primary": True,
        },
    )

    assert create_response.status_code == 201, create_response.text
    mapping = create_response.json()
    assert mapping["user_id"] == str(supplier_user_id)
    assert mapping["supplier_id"] == str(supplier_id)
    assert mapping["role_in_supplier"] == "manager"

    delete_response = await client.delete(
        f"/v1/admin/supplier-user-mappings/{mapping['mapping_id']}",
        headers=auth_headers(admin_token),
    )
    assert delete_response.status_code == 204

    list_response = await client.get(
        f"/v1/admin/supplier-user-mappings?supplier_id={supplier_id}",
        headers=auth_headers(admin_token),
    )
    assert list_response.status_code == 200
    assert list_response.json()["items"] == []

    owner_mapping_response = await client.post(
        "/v1/admin/supplier-user-mappings",
        headers=auth_headers(admin_token),
        json={
            "user_id": str(other_supplier_user_id),
            "supplier_id": str(other_supplier_id),
            "role_in_supplier": "owner",
            "is_primary": False,
        },
    )
    assert owner_mapping_response.status_code == 201, owner_mapping_response.text

    role_filter_response = await client.get(
        "/v1/admin/supplier-user-mappings?role_in_supplier=owner",
        headers=auth_headers(admin_token),
    )
    assert role_filter_response.status_code == 200
    assert all(item["role_in_supplier"] == "owner" for item in role_filter_response.json()["items"])


@pytest.mark.asyncio
async def test_supplier_upload_scope_and_upsert_counts_are_enforced(client):
    admin_id, admin_token = await create_test_user("admin")
    supplier_user_id, supplier_token = await create_test_user("supplier")
    _buyer_id, buyer_token = await create_test_user("buyer")
    supplier_id = await create_test_supplier("Mapped Supplier")
    other_supplier_id = await create_test_supplier("Blocked Supplier")
    await create_supplier_mapping(user_id=supplier_user_id, supplier_id=supplier_id, created_by=admin_id)

    stone_id = f"IT-{secrets.token_hex(5)}"
    first_upload = await client.post(
        "/v1/suppliers/uploads",
        headers=auth_headers(admin_token),
        data={"supplier_id": str(supplier_id)},
        files={"file": ("feed.csv", supplier_csv(stone_id), "text/csv")},
    )

    assert first_upload.status_code == 200, first_upload.text
    first_upload_body = first_upload.json()["upload"]
    assert first_upload_body["status"] == "done"
    assert first_upload_body["rows_total"] == 1
    assert first_upload_body["rows_new"] == 1
    assert first_upload_body["rows_trending"] == 1

    second_upload = await client.post(
        "/v1/suppliers/uploads",
        headers=auth_headers(supplier_token),
        data={"supplier_id": str(supplier_id)},
        files={"file": ("feed.csv", supplier_csv(stone_id, price=130000), "text/csv")},
    )

    assert second_upload.status_code == 200, second_upload.text
    second_upload_body = second_upload.json()["upload"]
    assert second_upload_body["rows_updated"] == 1

    forbidden_upload = await client.post(
        "/v1/suppliers/uploads",
        headers=auth_headers(supplier_token),
        data={"supplier_id": str(other_supplier_id)},
        files={"file": ("feed.csv", supplier_csv(f"NO-{stone_id}"), "text/csv")},
    )
    assert forbidden_upload.status_code == 403

    filtered_done_uploads = await client.get(
        f"/v1/suppliers/uploads?supplier_id={supplier_id}&status=done",
        headers=auth_headers(admin_token),
    )
    assert filtered_done_uploads.status_code == 200, filtered_done_uploads.text
    assert filtered_done_uploads.json()["items"]
    assert all(item["status"] == "done" for item in filtered_done_uploads.json()["items"])

    filtered_failed_uploads = await client.get(
        f"/v1/suppliers/uploads?supplier_id={supplier_id}&status=failed",
        headers=auth_headers(admin_token),
    )
    assert filtered_failed_uploads.status_code == 200, filtered_failed_uploads.text
    assert filtered_failed_uploads.json()["items"] == []

    buyer_uploads = await client.get("/v1/suppliers/uploads", headers=auth_headers(buyer_token))
    assert buyer_uploads.status_code == 403


@pytest.mark.asyncio
async def test_admin_supplier_filters_include_inactive_tier_and_search(client):
    _admin_id, admin_token = await create_test_user("admin")
    suffix = secrets.token_hex(6)
    inactive_email = f"inactive-filter-{suffix}@example.test"

    create_active = await client.post(
        "/v1/admin/suppliers",
        headers=auth_headers(admin_token),
        json={
            "supplier_code": f"FLT_ACTIVE_{suffix}",
            "display_name": f"Filter Active Supplier {suffix}",
            "contact_email": f"active-filter-{suffix}@example.test",
            "contact_phone": "9999990001",
            "tier": "T1",
            "is_active": True,
        },
    )
    assert create_active.status_code == 201, create_active.text

    create_inactive = await client.post(
        "/v1/admin/suppliers",
        headers=auth_headers(admin_token),
        json={
            "supplier_code": f"FLT_INACTIVE_{suffix}",
            "display_name": f"Filter Inactive Supplier {suffix}",
            "contact_email": inactive_email,
            "contact_phone": "9999990002",
            "tier": "T3",
            "is_active": False,
        },
    )
    assert create_inactive.status_code == 201, create_inactive.text
    inactive_supplier = create_inactive.json()

    active_only_response = await client.get(
        f"/v1/admin/suppliers?q={suffix}&active_only=true",
        headers=auth_headers(admin_token),
    )
    assert active_only_response.status_code == 200
    assert inactive_supplier["supplier_id"] not in [item["supplier_id"] for item in active_only_response.json()["items"]]

    inactive_tier_response = await client.get(
        f"/v1/admin/suppliers?q={inactive_email}&tier=T3&active_only=false",
        headers=auth_headers(admin_token),
    )
    assert inactive_tier_response.status_code == 200
    assert [item["supplier_id"] for item in inactive_tier_response.json()["items"]] == [inactive_supplier["supplier_id"]]
