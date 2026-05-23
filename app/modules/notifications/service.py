from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from app.core.config import Settings, get_settings
from app.modules.notifications.providers import ExpoPushProvider, PushMessage, PushProvider, StubPushProvider


def _provider(settings: Settings | None = None) -> PushProvider:
    active_settings = settings or get_settings()
    if active_settings.notifications_push_provider == "expo":
        return ExpoPushProvider()
    return StubPushProvider()


async def create_notification(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    type: str,
    title: str,
    body: str | None = None,
    metadata: dict[str, Any] | None = None,
    order_id: uuid.UUID | None = None,
    stone_id: uuid.UUID | None = None,
    news_id: uuid.UUID | None = None,
    enqueue: bool = True,
) -> uuid.UUID:
    notification_id = (
        await session.execute(
            text(
                """
                INSERT INTO notifications (
                  user_id, type, title, body, metadata, order_id, stone_id, news_id
                ) VALUES (
                  :user_id, CAST(:type AS notification_type), :title, :body,
                  CAST(:metadata AS jsonb), :order_id, :stone_id, :news_id
                )
                RETURNING notification_id
                """
            ),
            {
                "user_id": str(user_id),
                "type": type,
                "title": title,
                "body": body,
                "metadata": _json_param(metadata),
                "order_id": str(order_id) if order_id else None,
                "stone_id": str(stone_id) if stone_id else None,
                "news_id": str(news_id) if news_id else None,
            },
        )
    ).scalar_one()
    if enqueue:
        await enqueue_push(session, notification_id=notification_id)
    return notification_id


async def create_for_users(
    session: AsyncSession,
    *,
    user_ids: Iterable[uuid.UUID],
    type: str,
    title: str,
    body: str | None = None,
    metadata: dict[str, Any] | None = None,
    order_id: uuid.UUID | None = None,
    stone_id: uuid.UUID | None = None,
    news_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    notification_ids = []
    for user_id in _dedupe(user_ids):
        notification_ids.append(
            await create_notification(
                session,
                user_id=user_id,
                type=type,
                title=title,
                body=body,
                metadata=metadata,
                order_id=order_id,
                stone_id=stone_id,
                news_id=news_id,
            )
        )
    return notification_ids


async def enqueue_push(session: AsyncSession, *, notification_id: uuid.UUID) -> None:
    # The inbox row is the source of truth; the outbox is an auditable delivery
    # attempt queue that can be dispatched later when push delivery is enabled.
    await session.execute(
        text(
            """
            INSERT INTO notification_outbox (notification_id, token_id)
            SELECT :notification_id, dpt.token_id
            FROM notifications n
            JOIN device_push_tokens dpt ON dpt.user_id = n.user_id
            WHERE n.notification_id = :notification_id
              AND dpt.is_active = TRUE
              AND dpt.deleted_at IS NULL
            """
        ),
        {"notification_id": str(notification_id)},
    )


async def dispatch_outbox(
    session: AsyncSession,
    *,
    provider: PushProvider | None = None,
    settings: Settings | None = None,
) -> dict[str, int]:
    active_settings = settings or get_settings()
    active_provider = provider or _provider(active_settings)
    rows = (
        await session.execute(
            text(
                """
                SELECT o.outbox_id, o.attempt_count, dpt.push_token,
                       n.title, n.body, n.metadata
                FROM notification_outbox o
                JOIN notifications n ON n.notification_id = o.notification_id
                JOIN device_push_tokens dpt ON dpt.token_id = o.token_id
                WHERE o.status = 'pending'
                  AND o.next_attempt_at <= now()
                  AND o.attempt_count < :max_attempts
                  AND dpt.is_active = TRUE
                  AND dpt.deleted_at IS NULL
                ORDER BY o.created_at
                LIMIT :batch_size
                FOR UPDATE SKIP LOCKED
                """
            ),
            {
                "max_attempts": active_settings.notifications_max_attempts,
                "batch_size": active_settings.notifications_batch_size,
            },
        )
    ).mappings().all()

    counts = {"sent": 0, "failed": 0}
    for row in rows:
        result = await active_provider.send(
            PushMessage(
                outbox_id=row["outbox_id"],
                push_token=row["push_token"],
                title=row["title"],
                body=row["body"],
                data=row["metadata"],
            )
        )
        if result.ok:
            counts["sent"] += 1
            await session.execute(
                text(
                    """
                    UPDATE notification_outbox
                    SET status = 'sent',
                        attempt_count = attempt_count + 1,
                        provider_message_id = :provider_message_id,
                        delivered_at = now(),
                        updated_at = now()
                    WHERE outbox_id = :outbox_id
                    """
                ),
                {
                    "outbox_id": str(row["outbox_id"]),
                    "provider_message_id": result.provider_message_id,
                },
            )
            continue

        counts["failed"] += 1
        next_status = "failed" if row["attempt_count"] + 1 >= active_settings.notifications_max_attempts else "pending"
        await session.execute(
            text(
                """
                UPDATE notification_outbox
                SET status = :status,
                    attempt_count = attempt_count + 1,
                    next_attempt_at = now() + (:retry_seconds * interval '1 second'),
                    last_error = :last_error,
                    updated_at = now()
                WHERE outbox_id = :outbox_id
                """
            ),
            {
                "outbox_id": str(row["outbox_id"]),
                "status": next_status,
                "retry_seconds": active_settings.notifications_retry_seconds,
                "last_error": result.error,
            },
        )
    return counts


async def register_push_token(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    provider: str,
    push_token: str,
    platform: str | None,
    device_id: str | None,
    app_version: str | None,
) -> dict:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO device_push_tokens (
                  user_id, provider, push_token, platform, device_id, app_version,
                  is_active, last_seen_at
                ) VALUES (
                  :user_id, :provider, :push_token, :platform, :device_id, :app_version,
                  TRUE, now()
                )
                ON CONFLICT (provider, push_token) WHERE deleted_at IS NULL
                DO UPDATE SET
                  user_id = EXCLUDED.user_id,
                  platform = EXCLUDED.platform,
                  device_id = EXCLUDED.device_id,
                  app_version = EXCLUDED.app_version,
                  is_active = TRUE,
                  last_seen_at = now(),
                  updated_at = now()
                RETURNING token_id, provider, push_token, platform, device_id, app_version,
                          is_active, last_seen_at
                """
            ),
            {
                "user_id": str(user_id),
                "provider": provider,
                "push_token": push_token,
                "platform": platform,
                "device_id": device_id,
                "app_version": app_version,
            },
        )
    ).mappings().one()
    return dict(row)


async def notify_supplier_upload_finished(session: AsyncSession, *, upload: dict) -> None:
    supplier_id = upload["supplier_id"]
    recipients = await supplier_recipients(session, supplier_id=supplier_id, include_admins=True)
    if upload.get("uploaded_by"):
        recipients.append(upload["uploaded_by"])
    title = f"Supplier upload {upload['status']}"
    body = (
        f"{upload.get('supplier_display_name') or 'Supplier'} feed: "
        f"{upload.get('rows_imported') or 0} imported, {upload.get('rows_failed') or 0} failed."
    )
    metadata = {
        "upload_id": str(upload["upload_id"]),
        "supplier_id": str(supplier_id),
        "status": upload["status"],
    }
    await create_for_users(
        session,
        user_ids=recipients,
        type="supplier_upload",
        title=title,
        body=body,
        metadata=metadata,
    )


async def notify_order_transaction(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    buyer_id: uuid.UUID,
    order_status: str,
) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT oi.stone_id, sm.supplier_id, s.display_name AS supplier_display_name
                FROM order_items oi
                JOIN supplier_master sm ON sm.id = oi.stone_id
                JOIN suppliers s ON s.supplier_id = sm.supplier_id
                WHERE oi.order_id = :order_id
                LIMIT 1
                """
            ),
            {"order_id": str(order_id)},
        )
    ).mappings().first()
    supplier_recipients_list = await supplier_recipients(
        session,
        supplier_id=row["supplier_id"] if row else None,
        include_admins=True,
    )
    title = f"Order {order_status}"
    body = f"Order #{str(order_id)[:8]} is now {order_status}."
    metadata = {
        "order_id": str(order_id),
        "supplier_id": str(row["supplier_id"]) if row else None,
        "stone_id": str(row["stone_id"]) if row else None,
        "status": order_status,
    }
    await create_for_users(
        session,
        user_ids=[buyer_id, *supplier_recipients_list],
        type="transaction",
        title=title,
        body=body,
        metadata=metadata,
        order_id=order_id,
        stone_id=row["stone_id"] if row else None,
    )


async def notify_demand_created(session: AsyncSession, *, demand: dict) -> None:
    recipients = await supplier_recipients(session, supplier_id=demand["supplier_id"], include_admins=True)
    await create_for_users(
        session,
        user_ids=recipients,
        type="demand_request",
        title="New demand request",
        body="A buyer requested a better price for a diamond.",
        metadata=_demand_metadata(demand),
        stone_id=demand["stone_id"],
    )
    await create_notification(
        session,
        user_id=demand["buyer_id"],
        type="demand_request",
        title="Demand request sent",
        body="Your price request is now visible to Karigar and the supplier.",
        metadata=_demand_metadata(demand),
        stone_id=demand["stone_id"],
    )


async def notify_demand_resolved(session: AsyncSession, *, demand: dict) -> None:
    admins = await admin_user_ids(session)
    title = f"Demand request {demand['status']}"
    body = demand.get("response_note") or "Your demand request has been updated."
    await create_for_users(
        session,
        user_ids=[demand["buyer_id"], *admins],
        type="demand_request",
        title=title,
        body=body,
        metadata=_demand_metadata(demand),
        stone_id=demand["stone_id"],
    )


async def supplier_recipients(
    session: AsyncSession,
    *,
    supplier_id: uuid.UUID | None,
    include_admins: bool,
) -> list[uuid.UUID]:
    recipients: list[uuid.UUID] = []
    if supplier_id:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT user_id
                    FROM supplier_user_mappings
                    WHERE supplier_id = :supplier_id
                      AND deleted_at IS NULL
                    """
                ),
                {"supplier_id": str(supplier_id)},
            )
        ).scalars().all()
        recipients.extend(rows)
    if include_admins:
        recipients.extend(await admin_user_ids(session))
    return _dedupe(recipients)


async def admin_user_ids(session: AsyncSession) -> list[uuid.UUID]:
    rows = (
        await session.execute(
            text(
                """
                SELECT user_id
                FROM users
                WHERE role IN ('admin','karigar_staff')
                  AND deleted_at IS NULL
                """
            )
        )
    ).scalars().all()
    return list(rows)


def _demand_metadata(demand: dict) -> dict[str, str | None]:
    return {
        "demand_request_id": str(demand["demand_request_id"]),
        "supplier_id": str(demand["supplier_id"]),
        "stone_id": str(demand["stone_id"]),
        "status": demand["status"],
    }


def _dedupe(user_ids: Iterable[uuid.UUID | str | None]) -> list[uuid.UUID]:
    seen = set()
    result = []
    for user_id in user_ids:
        if not user_id:
            continue
        normalized = uuid.UUID(str(user_id))
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _json_param(value: dict[str, Any] | None) -> str:
    import json

    return json.dumps(value or {})
