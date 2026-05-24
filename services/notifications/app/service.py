from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from karigar_shared.config import Settings, get_settings

from app.providers import ExpoPushProvider, PushMessage, PushProvider, StubPushProvider


def push_provider(settings: Settings | None = None) -> PushProvider:
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
                "metadata": json.dumps(metadata or {}),
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
    user_ids: Iterable[uuid.UUID | str | None],
    type: str,
    title: str,
    body: str | None = None,
    metadata: dict[str, Any] | None = None,
    order_id: uuid.UUID | None = None,
    stone_id: uuid.UUID | None = None,
    news_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    notification_ids = []
    for user_id in dedupe_user_ids(user_ids):
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
    if not active_settings.notifications_push_enabled:
        return {"sent": 0, "failed": 0, "skipped": len(rows)}

    active_provider = provider or push_provider(active_settings)
    counts = {"sent": 0, "failed": 0, "skipped": 0}
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


async def campaign_recipients(session: AsyncSession, *, target_role: str, target_supplier_id: uuid.UUID | None) -> list[uuid.UUID]:
    params: dict = {}
    where = ["deleted_at IS NULL"]
    if target_role != "all":
        where.append("role = CAST(:target_role AS user_role)")
        params["target_role"] = target_role
    if target_supplier_id:
        where.append(
            """
            user_id IN (
              SELECT user_id
              FROM supplier_user_mappings
              WHERE supplier_id = :target_supplier_id
                AND deleted_at IS NULL
            )
            """
        )
        params["target_supplier_id"] = str(target_supplier_id)
    rows = (
        await session.execute(
            text(
                f"""
                SELECT user_id
                FROM users
                WHERE {' AND '.join(where)}
                """
            ),
            params,
        )
    ).scalars().all()
    return dedupe_user_ids(rows)


def dedupe_user_ids(user_ids: Iterable[uuid.UUID | str | None]) -> list[uuid.UUID]:
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
