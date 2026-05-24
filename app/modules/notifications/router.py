from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.sql import text

from app.modules.auth.deps import CurrentUser, current_user
from app.modules.notifications import service
from app.modules.notifications.schemas import (
    NotificationListResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
    PushTokenRegisterBody,
    PushTokenResponse,
)
from app.shared.rate_limit import limiter

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


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


@router.post("/push-tokens", response_model=PushTokenResponse, summary="Register/update current device push token")
@limiter.limit("30/minute")
async def register_push_token(
    request: Request,
    body: PushTokenRegisterBody,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> PushTokenResponse:
    row = await service.register_push_token(
        me.session,
        user_id=me.user_id,
        provider=body.provider,
        push_token=body.push_token,
        platform=body.platform,
        device_id=body.device_id,
        app_version=body.app_version,
    )
    return PushTokenResponse(**row)


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
