# Admin/Supplier Microservices Contracts

## Purpose

This document is the frontend contract for the initial Admin/Supplier phase.
Backend microservices own permissions, scoping, and notification routing.
Frontend screens should not expose internal primary keys as editable fields.

## Admin Dashboard

Use the admin service for dashboard metrics, supplier/user management, and
supplier-user mappings:

- `GET /v1/admin/dashboard`
- `GET /v1/admin/users`
- `GET /v1/admin/users/export`
- `GET /v1/admin/suppliers`
- `GET /v1/admin/suppliers/export`
- `GET /v1/admin/supplier-user-mappings`
- `POST /v1/admin/supplier-user-mappings`

Display user-friendly labels such as supplier display name, stone code, and
certificate number. Keep UUIDs read-only and hidden unless a debug/support view
explicitly needs them.

## Supplier Dashboard And Inventory

Use the suppliers service:

- `GET /v1/suppliers/uploads`
- `POST /v1/suppliers/uploads`
- `GET /v1/suppliers/uploads/{upload_id}`
- `GET /v1/suppliers/uploads/{upload_id}/errors/export`
- `GET /v1/suppliers/inventory`
- `PATCH /v1/suppliers/inventory/{stone_id}`
- `GET /v1/suppliers/inventory/export`

Suppliers only receive mapped supplier data. Admin/staff can pass
`supplier_id` to filter. Editable inventory fields are allowlisted by the API;
primary keys, foreign keys, `supplier_id`, `id`, and audit fields are never
editable.

## Demand Requests

Use the demand service:

- `POST /v1/demand-requests`
- `GET /v1/demand-requests`
- `GET /v1/demand-requests/{demand_request_id}`
- `PATCH /v1/demand-requests/{demand_request_id}`

Buyers create requests. Admin/staff and mapped supplier users can respond with
`open`, `countered`, `accepted`, `rejected`, or `cancelled`. Demand creation
notifies mapped supplier users and admin/staff. Demand resolution notifies the
buyer and admin/staff.

## Notifications

Use the notifications service:

- `GET /v1/notifications`
- `GET /v1/notifications/unread-count`
- `POST /v1/notifications/read-all`
- `POST /v1/notifications/{notification_id}/read`
- `POST /v1/notifications/push-tokens`
- `DELETE /v1/notifications/push-tokens/{token_id}`
- `GET /v1/notifications/admin/campaigns`
- `POST /v1/notifications/admin/campaigns`
- `POST /v1/notifications/admin/campaigns/{campaign_id}/publish`
- `GET /v1/notifications/admin/outbox`
- `POST /v1/notifications/admin/dispatch`
- `POST /v1/notifications/admin/test-push`

Campaign targeting supports `target_role = all | buyer | supplier | admin |
karigar_staff`. Use `target_supplier_id` to narrow supplier notifications to
users mapped to one supplier.

## Settings/Profile

Use the users service:

- `GET /v1/user`
- `POST /v1/onboarding/complete`
- `GET /v1/users/me/addresses`
- `POST /v1/users/me/addresses`

Profile/settings screens should consume these endpoints instead of duplicating
profile data inside admin or supplier screens.

## Export Buttons

Available now:

- Users CSV: `GET /v1/admin/users/export`
- Suppliers CSV: `GET /v1/admin/suppliers/export`
- Inventory CSV: `GET /v1/suppliers/inventory/export`
- Upload error CSV: `GET /v1/suppliers/uploads/{upload_id}/errors/export`

Future exports should follow the same pattern: role-scoped backend query,
CSV response, and no frontend-only filtering for data access.
