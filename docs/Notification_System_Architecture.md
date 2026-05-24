# Karigar Notification System Architecture

## Purpose

Karigar notifications are the event visibility layer for buyers, suppliers,
admins, and karigar staff. The source of truth is the in-app `notifications`
table. Push delivery is secondary and auditable through `notification_outbox`,
so a push failure must never fail checkout, upload, demand, or payment flows.

## Recipient Routing Matrix

| Event | Buyer | Supplier users | Admin / staff |
| --- | --- | --- | --- |
| Payment confirmed/cancelled | Purchased order buyer | Mapped users for the stone supplier | All admin/staff |
| Supplier upload finished | Uploader if present | Mapped users for supplier | All admin/staff |
| Supplier data updated | No | Mapped users for supplier | All admin/staff |
| Demand request created | Buyer acknowledgement | Mapped users for supplier | All admin/staff |
| Demand request resolved/countered/rejected | Buyer | No by default | All admin/staff |
| Promotion published | Targeted by role/supplier | Targeted by role/supplier | Targeted by role |

Recipient routing lives in backend services and `karigar_shared.notifications`,
not in frontend code. Frontends can hide controls by role, but backend routes
and RLS remain the enforcement layer.

## Data Ownership

- `notifications`: user inbox rows. Each row belongs to exactly one `user_id`.
- `device_push_tokens`: Expo/stub device tokens registered by the current user.
- `notification_outbox`: push delivery queue and audit history per notification.
- `notification_campaigns`: admin-created promotions with text, image URL,
  deep link, and target audience.
- `demand_requests`: buyer price/discount requests linked to a stone and supplier.

ID names are table-specific: `notification_id`, `token_id`, `outbox_id`,
`campaign_id`, and `demand_request_id`.

## Outbox Lifecycle

1. A domain service creates an inbox notification with `create_notification()`.
2. The service enqueues active device tokens into `notification_outbox`.
3. `dispatch_outbox()` reads pending rows using `FOR UPDATE SKIP LOCKED`.
4. The selected provider sends the push:
   - `StubPushProvider` is used for local/dev/tests.
   - `ExpoPushProvider` sends to Expo when configured.
5. Delivery updates the outbox to `sent`, `pending` for retry, or `failed`.

Push settings:

- `NOTIFICATIONS_PUSH_ENABLED`
- `NOTIFICATIONS_PUSH_PROVIDER`
- `NOTIFICATIONS_BATCH_SIZE`
- `NOTIFICATIONS_MAX_ATTEMPTS`
- `NOTIFICATIONS_RETRY_SECONDS`
- `NOTIFICATIONS_WORKER_ENABLED`
- `NOTIFICATIONS_WORKER_INTERVAL_SECONDS`

## Demand Request Lifecycle

1. Buyer opens product detail and submits requested discount/price plus message.
2. `POST /v1/demand-requests` validates the request and creates `open` demand.
3. Supplier mapped users and admin/staff receive `demand_request` notifications.
4. Admin or mapped supplier reviews from the demand service.
5. `PATCH /v1/demand-requests/{demand_request_id}` moves the request to
   `countered`, `accepted`, `rejected`, `cancelled`, or keeps it `open`.
6. Buyer receives an update notification after resolution/counter.

## Admin Promotion Publishing

Admins create draft campaigns from `/v1/notifications/admin/campaigns`.
Publishing creates one `promotion` notification per targeted user:

- `target_role = all | buyer | supplier | admin | karigar_staff`
- `target_supplier_id` optionally narrows supplier campaigns to mapped users.
- `image_url` is URL-only in v1. Binary uploads/storage are out of scope.

## RLS And Security Rules

- Notification read/update endpoints include explicit `user_id = current_user`
  filters. RLS is still enabled, but API handlers do not rely on RLS alone.
- Service-created notification inserts are allowed for authenticated sessions
  because domain events often notify another role during the same transaction.
- Admin/staff user IDs are readable for recipient routing only; user management
  remains behind `/v1/admin/*` role guards.
- Push tokens are writable only by their owner/admin. Delivery services can read
  active tokens for routing outbox rows.
- Demand requests are visible to the buyer, admin/staff, and mapped supplier
  users for the supplier on that demand.

## API Surface

User inbox:

- `GET /v1/notifications`
- `GET /v1/notifications/unread-count`
- `POST /v1/notifications/{notification_id}/read`
- `POST /v1/notifications/read-all`
- `POST /v1/notifications/push-tokens`
- `DELETE /v1/notifications/push-tokens/{token_id}`

Demand:

- `POST /v1/demand-requests`
- `GET /v1/demand-requests`
- `GET /v1/demand-requests/{demand_request_id}`
- `PATCH /v1/demand-requests/{demand_request_id}`

Admin/BFF:

- `GET /v1/notifications/admin/campaigns`
- `POST /v1/notifications/admin/campaigns`
- `POST /v1/notifications/admin/campaigns/{campaign_id}/publish`
- `GET /v1/notifications/admin/outbox`
- `POST /v1/notifications/admin/dispatch`
- `POST /v1/notifications/admin/test-push`

## Test Coverage

Backend coverage includes:

- Notification inbox scoping, read/read-all, and push token ownership.
- Buyer demand creation routing to supplier/admin notifications.
- Supplier demand visibility only for mapped suppliers.
- Admin demand resolution notifying the buyer.
- Existing supplier upload, admin mapping, catalog, checkout, and payment flows.

Frontend coverage includes mobile OTP and admin build/test gates. Notification
and demand UI tests should continue expanding around inbox states, demand form
validation, and campaign publishing.
