import pytest

from app.db.session import request_session
from app.modules.notifications import service as notification_service
from tests.helpers import (
    auth_headers,
    create_supplier_mapping,
    create_test_stone,
    create_test_supplier,
    create_test_user,
)


@pytest.mark.asyncio
async def test_notification_inbox_read_all_and_push_token_scope(client):
    buyer_id, buyer_token = await create_test_user("buyer")
    other_id, other_token = await create_test_user("buyer")

    token_response = await client.post(
        "/v1/notifications/push-tokens",
        headers=auth_headers(buyer_token),
        json={
            "provider": "expo",
            "push_token": "ExponentPushToken[test-notifications]",
            "platform": "ios",
            "device_id": "test-device",
            "app_version": "1.0.0",
        },
    )
    assert token_response.status_code == 200, token_response.text
    token_id = token_response.json()["token_id"]

    async with request_session(user_id=buyer_id, role="buyer") as session:
        buyer_notification_id = await notification_service.create_notification(
            session,
            user_id=buyer_id,
            type="system",
            title="Buyer inbox message",
            body="Visible only to this buyer.",
            metadata={"test_case": "notification_scope"},
        )
        await notification_service.create_notification(
            session,
            user_id=other_id,
            type="system",
            title="Other buyer message",
            body="Hidden from the first buyer.",
            metadata={"test_case": "notification_scope"},
        )

    buyer_list = await client.get("/v1/notifications?type=system", headers=auth_headers(buyer_token))
    assert buyer_list.status_code == 200, buyer_list.text
    buyer_items = buyer_list.json()["items"]
    assert [item["title"] for item in buyer_items] == ["Buyer inbox message"]

    other_cannot_read = await client.post(
        f"/v1/notifications/{buyer_notification_id}/read",
        headers=auth_headers(other_token),
    )
    assert other_cannot_read.status_code == 404

    unread_count = await client.get("/v1/notifications/unread-count", headers=auth_headers(buyer_token))
    assert unread_count.status_code == 200
    assert unread_count.json()["unread_count"] == 1

    mark_read = await client.post(
        f"/v1/notifications/{buyer_notification_id}/read",
        headers=auth_headers(buyer_token),
    )
    assert mark_read.status_code == 200, mark_read.text
    assert mark_read.json()["is_read"] is True

    read_all = await client.post("/v1/notifications/read-all", headers=auth_headers(buyer_token))
    assert read_all.status_code == 200
    assert read_all.json()["unread_count"] == 0

    other_delete = await client.delete(
        f"/v1/notifications/push-tokens/{token_id}",
        headers=auth_headers(other_token),
    )
    assert other_delete.status_code == 404

    owner_delete = await client.delete(
        f"/v1/notifications/push-tokens/{token_id}",
        headers=auth_headers(buyer_token),
    )
    assert owner_delete.status_code == 204


@pytest.mark.asyncio
async def test_buyer_demand_request_routes_to_supplier_and_admin_notifications(client):
    admin_id, admin_token = await create_test_user("admin")
    buyer_id, buyer_token = await create_test_user("buyer")
    supplier_user_id, supplier_token = await create_test_user("supplier")
    other_supplier_id, other_supplier_token = await create_test_user("supplier")
    supplier_id = await create_test_supplier("Demand Supplier")
    other_supplier_account_id = await create_test_supplier("Other Supplier")
    await create_supplier_mapping(user_id=supplier_user_id, supplier_id=supplier_id, created_by=admin_id)
    await create_supplier_mapping(user_id=other_supplier_id, supplier_id=other_supplier_account_id, created_by=admin_id)
    stone_id = await create_test_stone(supplier_id=supplier_id)

    create_response = await client.post(
        "/v1/demand-requests",
        headers=auth_headers(buyer_token),
        json={
            "stone_id": str(stone_id),
            "requested_discount_pct": "8.50",
            "requested_price_inr": "112000",
            "message": "Can you improve the price for a fast decision?",
        },
    )
    assert create_response.status_code == 201, create_response.text
    demand = create_response.json()
    assert demand["buyer_id"] == str(buyer_id)
    assert demand["supplier_id"] == str(supplier_id)
    assert demand["status"] == "open"

    supplier_demands = await client.get("/v1/admin/demand-requests", headers=auth_headers(supplier_token))
    assert supplier_demands.status_code == 200, supplier_demands.text
    assert [item["demand_request_id"] for item in supplier_demands.json()["items"]] == [demand["demand_request_id"]]

    other_supplier_demands = await client.get("/v1/admin/demand-requests", headers=auth_headers(other_supplier_token))
    assert other_supplier_demands.status_code == 200, other_supplier_demands.text
    assert other_supplier_demands.json()["items"] == []

    admin_notifications = await client.get(
        "/v1/notifications?type=demand_request",
        headers=auth_headers(admin_token),
    )
    assert admin_notifications.status_code == 200, admin_notifications.text
    assert any(item["metadata"]["demand_request_id"] == demand["demand_request_id"] for item in admin_notifications.json()["items"])

    supplier_notifications = await client.get(
        "/v1/notifications?type=demand_request",
        headers=auth_headers(supplier_token),
    )
    assert supplier_notifications.status_code == 200, supplier_notifications.text
    assert any(item["metadata"]["demand_request_id"] == demand["demand_request_id"] for item in supplier_notifications.json()["items"])

    resolve_response = await client.patch(
        f"/v1/admin/demand-requests/{demand['demand_request_id']}",
        headers=auth_headers(admin_token),
        json={
            "status": "countered",
            "response_note": "Supplier can support this counter price.",
            "offered_price_inr": "116000",
        },
    )
    assert resolve_response.status_code == 200, resolve_response.text
    assert resolve_response.json()["status"] == "countered"

    buyer_notifications = await client.get(
        "/v1/notifications?type=demand_request",
        headers=auth_headers(buyer_token),
    )
    assert buyer_notifications.status_code == 200, buyer_notifications.text
    assert any(item["title"] == "Demand request countered" for item in buyer_notifications.json()["items"])
