from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.sql import text

from karigar_shared.auth.deps import CurrentUser, current_user, require_roles
from karigar_shared.rate_limit import limiter

from app import service
from app.schemas import (
    AdminTestPushBody,
    NotificationCampaignCreateBody,
    NotificationCampaignListResponse,
    NotificationCampaignResponse,
    NotificationDispatchResponse,
    NotificationListResponse,
    NotificationOutboxListResponse,
    NotificationOutboxResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
    PushTokenRegisterBody,
    PushTokenResponse,
)

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])

AdminUser = Annotated[CurrentUser, Depends(require_roles("admin", "karigar_staff"))]


@router.get("", response_model=NotificationListResponse, summary="My notifications inbox")
@limiter.limit("60/minute")
async def list_notifications(
    request: Request,
    me: Annotated[CurrentUser, Depends(current_user)],
    type: str | None = Query(None),
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> NotificationListResponse:
    where = ["deleted_at IS NULL"]
    params: dict = {"user_id": str(me.user_id), "limit": limit, "offset": offset}
    if type:
        where.append("type = CAST(:type AS notification_type)")
        params["type"] = type
    if unread_only:
        where.append("is_read = FALSE")
    rows = (
        await me.session.execute(
            text(
                f"""
                SELECT notification_id, user_id, type, title, body, metadata,
                       is_read, read_at, news_id, order_id, stone_id, created_at
                FROM notifications
                WHERE user_id = :user_id
                  AND {' AND '.join(where)}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()
    return NotificationListResponse(items=[NotificationResponse(**dict(row)) for row in rows])


@router.get("/unread-count", response_model=NotificationUnreadCountResponse, summary="Unread notification count")
@limiter.limit("60/minute")
async def unread_count(
    request: Request,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> NotificationUnreadCountResponse:
    count = (
        await me.session.execute(
            text(
                """
                SELECT count(*)
                FROM notifications
                WHERE user_id = :user_id
                  AND deleted_at IS NULL
                  AND is_read = FALSE
                """
            ),
            {"user_id": str(me.user_id)},
        )
    ).scalar_one()
    return NotificationUnreadCountResponse(unread_count=count)


@router.post("/read-all", response_model=NotificationUnreadCountResponse, summary="Mark all notifications read")
@limiter.limit("30/minute")
async def mark_all_read(
    request: Request,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> NotificationUnreadCountResponse:
    await me.session.execute(
        text(
            """
            UPDATE notifications
            SET is_read = TRUE, read_at = COALESCE(read_at, now())
            WHERE user_id = :user_id
              AND deleted_at IS NULL
              AND is_read = FALSE
            """
        ),
        {"user_id": str(me.user_id)},
    )
    return NotificationUnreadCountResponse(unread_count=0)


@router.post("/push-tokens", response_model=PushTokenResponse, summary="Register/update current device push token")
@limiter.limit("30/minute")
async def register_push_token(
    request: Request,
    body: PushTokenRegisterBody,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> PushTokenResponse:
    row = (
        await me.session.execute(
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
            {"user_id": str(me.user_id), **body.model_dump()},
        )
    ).mappings().one()
    return PushTokenResponse(**dict(row))


@router.delete("/push-tokens/{token_id}", status_code=204, summary="Deactivate current user's push token")
@limiter.limit("30/minute")
async def deactivate_push_token(
    request: Request,
    token_id: Annotated[UUID, Path()],
    me: Annotated[CurrentUser, Depends(current_user)],
) -> None:
    result = await me.session.execute(
        text(
            """
            UPDATE device_push_tokens
            SET is_active = FALSE, deleted_at = now(), updated_at = now()
            WHERE token_id = :token_id
              AND user_id = :user_id
              AND deleted_at IS NULL
            RETURNING token_id
            """
        ),
        {"token_id": str(token_id), "user_id": str(me.user_id)},
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "push token not found")


@router.get(
    "/admin/campaigns",
    response_model=NotificationCampaignListResponse,
    summary="List notification campaigns",
)
@limiter.limit("60/minute")
async def list_campaigns(
    request: Request,
    me: AdminUser,
    status_filter: str | None = Query(None, alias="status"),
) -> NotificationCampaignListResponse:
    where = ["deleted_at IS NULL"]
    params: dict = {}
    if status_filter:
        where.append("status = :status")
        params["status"] = status_filter
    rows = (
        await me.session.execute(
            text(
                f"""
                SELECT campaign_id, created_by, title, body, image_url, deep_link,
                       target_role, target_supplier_id, status, published_at, created_at
                FROM notification_campaigns
                WHERE {' AND '.join(where)}
                ORDER BY created_at DESC
                """
            ),
            params,
        )
    ).mappings().all()
    return NotificationCampaignListResponse(items=[NotificationCampaignResponse(**dict(row)) for row in rows])


@router.post(
    "/admin/campaigns",
    response_model=NotificationCampaignResponse,
    status_code=201,
    summary="Create a draft notification campaign",
)
@limiter.limit("30/minute")
async def create_campaign(
    request: Request,
    body: NotificationCampaignCreateBody,
    me: AdminUser,
) -> NotificationCampaignResponse:
    row = (
        await me.session.execute(
            text(
                """
                INSERT INTO notification_campaigns (
                  created_by, title, body, image_url, deep_link,
                  target_role, target_supplier_id
                ) VALUES (
                  :created_by, :title, :body, :image_url, :deep_link,
                  :target_role, :target_supplier_id
                )
                RETURNING campaign_id, created_by, title, body, image_url, deep_link,
                          target_role, target_supplier_id, status, published_at, created_at
                """
            ),
            {**body.model_dump(), "created_by": str(me.user_id)},
        )
    ).mappings().one()
    return NotificationCampaignResponse(**dict(row))


@router.post(
    "/admin/campaigns/{campaign_id}/publish",
    response_model=NotificationCampaignResponse,
    summary="Publish a notification campaign",
)
@limiter.limit("30/minute")
async def publish_campaign(
    request: Request,
    campaign_id: Annotated[UUID, Path()],
    me: AdminUser,
) -> NotificationCampaignResponse:
    campaign = (
        await me.session.execute(
            text(
                """
                SELECT campaign_id, created_by, title, body, image_url, deep_link,
                       target_role, target_supplier_id, status, published_at, created_at
                FROM notification_campaigns
                WHERE campaign_id = :campaign_id
                  AND deleted_at IS NULL
                FOR UPDATE
                """
            ),
            {"campaign_id": str(campaign_id)},
        )
    ).mappings().first()
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    if campaign["status"] != "published":
        recipients = await service.campaign_recipients(
            me.session,
            target_role=campaign["target_role"],
            target_supplier_id=campaign["target_supplier_id"],
        )
        await service.create_for_users(
            me.session,
            user_ids=recipients,
            type="promotion",
            title=campaign["title"],
            body=campaign["body"],
            metadata={
                "campaign_id": str(campaign["campaign_id"]),
                "image_url": campaign["image_url"],
                "deep_link": campaign["deep_link"],
                "target_role": campaign["target_role"],
                "target_supplier_id": str(campaign["target_supplier_id"]) if campaign["target_supplier_id"] else None,
            },
        )
        campaign = (
            await me.session.execute(
                text(
                    """
                    UPDATE notification_campaigns
                    SET status = 'published', published_at = COALESCE(published_at, now()), updated_at = now()
                    WHERE campaign_id = :campaign_id
                    RETURNING campaign_id, created_by, title, body, image_url, deep_link,
                              target_role, target_supplier_id, status, published_at, created_at
                    """
                ),
                {"campaign_id": str(campaign_id)},
            )
        ).mappings().one()
    return NotificationCampaignResponse(**dict(campaign))


@router.get(
    "/admin/outbox",
    response_model=NotificationOutboxListResponse,
    summary="List push delivery health",
)
@limiter.limit("60/minute")
async def list_notification_outbox(
    request: Request,
    me: AdminUser,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
) -> NotificationOutboxListResponse:
    where = []
    params: dict = {"limit": limit}
    if status_filter:
        where.append("status = :status")
        params["status"] = status_filter
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = (
        await me.session.execute(
            text(
                f"""
                SELECT outbox_id, notification_id, channel, status, attempt_count,
                       last_error, provider_message_id, created_at, delivered_at
                FROM notification_outbox
                {where_sql}
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            params,
        )
    ).mappings().all()
    return NotificationOutboxListResponse(items=[NotificationOutboxResponse(**dict(row)) for row in rows])


@router.post("/admin/dispatch", response_model=NotificationDispatchResponse, summary="Dispatch pending push notifications")
@limiter.limit("10/minute")
async def dispatch_pending(
    request: Request,
    me: AdminUser,
) -> NotificationDispatchResponse:
    result = await service.dispatch_outbox(me.session)
    return NotificationDispatchResponse(**result)


@router.post("/admin/test-push", summary="Create and dispatch a test push for the current admin")
@limiter.limit("10/minute")
async def test_push(
    request: Request,
    body: AdminTestPushBody,
    me: AdminUser,
) -> dict:
    notification_id = await service.create_notification(
        me.session,
        user_id=me.user_id,
        type="system",
        title=body.title,
        body=body.body,
        metadata={"source": "notifications_service_admin_test_push"},
    )
    result = await service.dispatch_outbox(me.session)
    return {"notification_id": notification_id, **result}


@router.post("/{notification_id}/read", response_model=NotificationResponse, summary="Mark notification read")
@limiter.limit("60/minute")
async def mark_read(
    request: Request,
    notification_id: Annotated[UUID, Path()],
    me: Annotated[CurrentUser, Depends(current_user)],
) -> NotificationResponse:
    row = (
        await me.session.execute(
            text(
                """
                UPDATE notifications
                SET is_read = TRUE, read_at = COALESCE(read_at, now())
                WHERE notification_id = :notification_id
                  AND user_id = :user_id
                  AND deleted_at IS NULL
                RETURNING notification_id, user_id, type, title, body, metadata,
                          is_read, read_at, news_id, order_id, stone_id, created_at
                """
            ),
            {"notification_id": str(notification_id), "user_id": str(me.user_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "notification not found")
    return NotificationResponse(**dict(row))
