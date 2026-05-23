"""Admin BFF routes.

This module is the backend umbrella for admin workflows. It composes existing
domain tables/services, but it does not own supplier ingestion or auth logic.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.sql import text

from app.modules.admin.schemas import (
    AdminDemandRequestListResponse,
    AdminDemandRequestResponse,
    AdminDemandRequestUpdateBody,
    AdminDashboardResponse,
    AdminMeResponse,
    AdminTestPushBody,
    AdminSupplierCreateBody,
    AdminSupplierListResponse,
    AdminSupplierSummary,
    AdminSupplierUpdateBody,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserUpdateBody,
    NotificationCampaignCreateBody,
    NotificationCampaignListResponse,
    NotificationCampaignResponse,
    NotificationOutboxListResponse,
    NotificationOutboxResponse,
    SupplierUserMappingCreateBody,
    SupplierUserMappingListResponse,
    SupplierUserMappingResponse,
)
from app.modules.demand import service as demand_service
from app.modules.auth.deps import CurrentUser, require_roles
from app.modules.notifications import service as notification_service
from app.shared.rate_limit import limiter

router = APIRouter(prefix="/v1/admin", tags=["admin"])

AdminUser = Annotated[CurrentUser, Depends(require_roles("admin", "karigar_staff"))]
AdminPortalUser = Annotated[CurrentUser, Depends(require_roles("admin", "karigar_staff", "supplier"))]


@router.get("/me", response_model=AdminMeResponse, summary="Current admin identity")
@limiter.limit("60/minute")
async def admin_me(request: Request, me: AdminPortalUser) -> AdminMeResponse:
    suppliers = await _mapped_suppliers(me)
    return AdminMeResponse(
        user_id=me.user_id,
        role=me.role,
        permissions=_permissions_for_role(me.role),
        suppliers=[AdminSupplierSummary(**row) for row in suppliers],
    )


@router.get("/dashboard", response_model=AdminDashboardResponse, summary="Admin dashboard metrics")
@limiter.limit("60/minute")
async def dashboard(request: Request, me: AdminUser) -> AdminDashboardResponse:
    row = (
        await me.session.execute(
            text(
                """
                SELECT
                  (SELECT count(*) FROM users WHERE deleted_at IS NULL) AS users_total,
                  (SELECT count(*) FROM suppliers WHERE is_active = TRUE AND deleted_at IS NULL) AS suppliers_active,
                  (SELECT count(*) FROM supplier_master WHERE availability = 'available' AND deleted_at IS NULL) AS stones_active,
                  (SELECT count(*) FROM supplier_uploads WHERE uploaded_at >= now() - interval '30 days') AS uploads_recent,
                  (SELECT COALESCE(sum(rows_failed), 0) FROM supplier_uploads WHERE uploaded_at >= now() - interval '30 days') AS upload_rows_failed_recent,
                  (SELECT count(*) FROM notifications WHERE user_id = :user_id AND is_read = FALSE AND deleted_at IS NULL) AS admin_unread_notifications,
                  (SELECT count(*) FROM demand_requests WHERE status = 'open' AND deleted_at IS NULL) AS open_demands,
                  (SELECT count(*) FROM notification_outbox WHERE status = 'failed') AS failed_push_deliveries,
                  (SELECT count(*) FROM notification_campaigns WHERE created_at >= now() - interval '30 days' AND deleted_at IS NULL) AS recent_campaigns
                """
            ),
            {"user_id": str(me.user_id)},
        )
    ).mappings().one()
    return AdminDashboardResponse(**dict(row))


@router.get("/users", response_model=AdminUserListResponse, summary="List/search users")
@limiter.limit("60/minute")
async def list_users(
    request: Request,
    me: AdminUser,
    q: str | None = Query(None, max_length=128),
    role: str | None = Query(None),
    is_verified: bool | None = Query(None),
    include_deleted: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> AdminUserListResponse:
    where = []
    params: dict = {"limit": limit, "offset": offset}
    if not include_deleted:
        where.append("deleted_at IS NULL")
    if role:
        where.append("role = :role")
        params["role"] = role
    if is_verified is not None:
        where.append("is_verified = :is_verified")
        params["is_verified"] = is_verified
    if q:
        where.append(
            """
            (
              email ILIKE :q OR
              safe_decrypt_pii(full_name_encrypted) ILIKE :q OR
              safe_decrypt_pii(phone_encrypted) ILIKE :q
            )
            """
        )
        params["q"] = f"%{q}%"
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = (
        await me.session.execute(
            text(
                f"""
                SELECT
                  user_id,
                  email,
                  safe_decrypt_pii(phone_encrypted) AS phone,
                  safe_decrypt_pii(full_name_encrypted) AS full_name,
                  role,
                  is_verified,
                  created_at,
                  last_login_at,
                  deleted_at
                FROM users
                {where_sql}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()
    return AdminUserListResponse(items=[AdminUserResponse(**dict(row)) for row in rows])


@router.patch("/users/{user_id}", response_model=AdminUserResponse, summary="Update a user")
@limiter.limit("30/minute")
async def update_user(
    request: Request,
    user_id: Annotated[UUID, Path()],
    body: AdminUserUpdateBody,
    me: AdminUser,
) -> AdminUserResponse:
    if user_id == me.user_id and body.deleted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "admin cannot delete self")
    updates = []
    params: dict = {"user_id": str(user_id)}
    if body.role is not None:
        updates.append("role = CAST(:role AS user_role)")
        params["role"] = body.role
    if body.is_verified is not None:
        updates.append("is_verified = :is_verified")
        params["is_verified"] = body.is_verified
    if body.deleted is not None:
        updates.append("deleted_at = CASE WHEN :deleted THEN now() ELSE NULL END")
        params["deleted"] = body.deleted
    if updates:
        await me.session.execute(
            text(f"UPDATE users SET {', '.join(updates)} WHERE user_id = :user_id"),
            params,
        )
    row = await _get_user_or_404(me, user_id)
    return AdminUserResponse(**row)


@router.get("/suppliers", response_model=AdminSupplierListResponse, summary="List suppliers")
@limiter.limit("60/minute")
async def list_suppliers(
    request: Request,
    me: AdminUser,
    q: str | None = Query(None, max_length=128),
    tier: str | None = Query(None, pattern=r"^(T1|T2|T3)$"),
    active_only: bool = Query(True),
) -> AdminSupplierListResponse:
    where = ["deleted_at IS NULL"]
    params: dict = {}
    if active_only:
        where.append("is_active = TRUE")
    if tier:
        where.append("tier = :tier")
        params["tier"] = tier
    if q:
        where.append(
            """
            (
              display_name ILIKE :q OR
              supplier_code ILIKE :q OR
              contact_email ILIKE :q OR
              contact_phone ILIKE :q
            )
            """
        )
        params["q"] = f"%{q}%"
    rows = (
        await me.session.execute(
            text(
                f"""
                SELECT supplier_id, supplier_code, display_name, contact_email, contact_phone, tier, is_active, NULL::text AS role_in_supplier, NULL::boolean AS is_primary
                FROM suppliers
                WHERE {' AND '.join(where)}
                ORDER BY display_name
                """
            ),
            params,
        )
    ).mappings().all()
    return AdminSupplierListResponse(items=[AdminSupplierSummary(**dict(row)) for row in rows])


@router.post("/suppliers", response_model=AdminSupplierSummary, status_code=201, summary="Create supplier")
@limiter.limit("30/minute")
async def create_supplier(
    request: Request,
    body: AdminSupplierCreateBody,
    me: AdminUser,
) -> AdminSupplierSummary:
    row = (
        await me.session.execute(
            text(
                """
                INSERT INTO suppliers (
                  supplier_code, display_name, contact_email, contact_phone,
                  tier, is_active, onboarded_at
                ) VALUES (
                  :supplier_code, :display_name, :contact_email, :contact_phone,
                  :tier, :is_active, now()
                )
                RETURNING supplier_id, supplier_code, display_name, contact_email, contact_phone, tier, is_active,
                          NULL::text AS role_in_supplier,
                          NULL::boolean AS is_primary
                """
            ),
            body.model_dump(),
        )
    ).mappings().one()
    return AdminSupplierSummary(**dict(row))


@router.patch("/suppliers/{supplier_id}", response_model=AdminSupplierSummary, summary="Update supplier")
@limiter.limit("30/minute")
async def update_supplier(
    request: Request,
    supplier_id: Annotated[UUID, Path()],
    body: AdminSupplierUpdateBody,
    me: AdminUser,
) -> AdminSupplierSummary:
    updates = []
    params = {"supplier_id": str(supplier_id)}
    for field, value in body.model_dump(exclude_unset=True).items():
        updates.append(f"{field} = :{field}")
        params[field] = value
    if updates:
        await me.session.execute(
            text(f"UPDATE suppliers SET {', '.join(updates)} WHERE supplier_id = :supplier_id"),
            params,
        )
    row = (
        await me.session.execute(
            text(
                """
                SELECT supplier_id, supplier_code, display_name, contact_email, contact_phone, tier, is_active,
                       NULL::text AS role_in_supplier,
                       NULL::boolean AS is_primary
                FROM suppliers
                WHERE supplier_id = :supplier_id
                """
            ),
            {"supplier_id": str(supplier_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "supplier not found")
    return AdminSupplierSummary(**dict(row))


@router.get(
    "/supplier-user-mappings",
    response_model=SupplierUserMappingListResponse,
    summary="List supplier-user mappings",
)
@limiter.limit("60/minute")
async def list_mappings(
    request: Request,
    me: AdminUser,
    user_id: UUID | None = Query(None),
    supplier_id: UUID | None = Query(None),
    role_in_supplier: str | None = Query(None, pattern=r"^(owner|manager|viewer)$"),
) -> SupplierUserMappingListResponse:
    where = ["deleted_at IS NULL"]
    params: dict = {}
    if user_id:
        where.append("user_id = :user_id")
        params["user_id"] = str(user_id)
    if supplier_id:
        where.append("supplier_id = :supplier_id")
        params["supplier_id"] = str(supplier_id)
    if role_in_supplier:
        where.append("role_in_supplier = :role_in_supplier")
        params["role_in_supplier"] = role_in_supplier
    rows = (
        await me.session.execute(
            text(
                f"""
                SELECT mapping_id, user_id, supplier_id, role_in_supplier, is_primary,
                       created_by, created_at, deleted_at
                FROM supplier_user_mappings
                WHERE {' AND '.join(where)}
                ORDER BY created_at DESC
                """
            ),
            params,
        )
    ).mappings().all()
    return SupplierUserMappingListResponse(items=[SupplierUserMappingResponse(**dict(row)) for row in rows])


@router.post(
    "/supplier-user-mappings",
    response_model=SupplierUserMappingResponse,
    status_code=201,
    summary="Map a user to a supplier",
)
@limiter.limit("30/minute")
async def create_mapping(
    request: Request,
    body: SupplierUserMappingCreateBody,
    me: AdminUser,
) -> SupplierUserMappingResponse:
    if body.is_primary:
        await me.session.execute(
            text(
                """
                UPDATE supplier_user_mappings
                SET is_primary = FALSE
                WHERE user_id = :user_id AND deleted_at IS NULL
                """
            ),
            {"user_id": str(body.user_id)},
        )
    row = (
        await me.session.execute(
            text(
                """
                INSERT INTO supplier_user_mappings (
                  user_id, supplier_id, role_in_supplier, is_primary, created_by
                ) VALUES (
                  :user_id, :supplier_id, :role_in_supplier, :is_primary, :created_by
                )
                ON CONFLICT (user_id, supplier_id) WHERE deleted_at IS NULL
                DO UPDATE SET
                  role_in_supplier = EXCLUDED.role_in_supplier,
                  is_primary = EXCLUDED.is_primary,
                  updated_at = now()
                RETURNING mapping_id, user_id, supplier_id, role_in_supplier,
                          is_primary, created_by, created_at, deleted_at
                """
            ),
            {
                "user_id": str(body.user_id),
                "supplier_id": str(body.supplier_id),
                "role_in_supplier": body.role_in_supplier,
                "is_primary": body.is_primary,
                "created_by": str(me.user_id),
            },
        )
    ).mappings().one()
    await me.session.execute(
        text("UPDATE users SET role = 'supplier'::user_role WHERE user_id = :user_id AND role = 'buyer'::user_role"),
        {"user_id": str(body.user_id)},
    )
    return SupplierUserMappingResponse(**dict(row))


@router.delete(
    "/supplier-user-mappings/{mapping_id}",
    status_code=204,
    summary="Soft-delete a supplier-user mapping",
)
@limiter.limit("30/minute")
async def delete_mapping(
    request: Request,
    mapping_id: Annotated[UUID, Path()],
    me: AdminUser,
) -> None:
    result = await me.session.execute(
        text(
            """
            UPDATE supplier_user_mappings
            SET deleted_at = now(), is_primary = FALSE
            WHERE mapping_id = :mapping_id AND deleted_at IS NULL
            RETURNING mapping_id
            """
        ),
        {"mapping_id": str(mapping_id)},
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "mapping not found")


@router.get(
    "/notifications/campaigns",
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
    "/notifications/campaigns",
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
    "/notifications/campaigns/{campaign_id}/publish",
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
        recipients = await _campaign_recipients(me, dict(campaign))
        await notification_service.create_for_users(
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
    "/notifications/outbox",
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


@router.post("/notifications/test-push", summary="Create and dispatch a test push for the current admin")
@limiter.limit("10/minute")
async def test_push(
    request: Request,
    body: AdminTestPushBody,
    me: AdminUser,
) -> dict:
    notification_id = await notification_service.create_notification(
        me.session,
        user_id=me.user_id,
        type="system",
        title=body.title,
        body=body.body,
        metadata={"source": "admin_test_push"},
    )
    result = await notification_service.dispatch_outbox(me.session)
    return {"notification_id": notification_id, **result}


@router.get(
    "/demand-requests",
    response_model=AdminDemandRequestListResponse,
    summary="List demand requests for admin or mapped supplier",
)
@limiter.limit("60/minute")
async def admin_list_demand_requests(
    request: Request,
    me: AdminPortalUser,
    status_filter: str | None = Query(None, alias="status"),
    supplier_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> AdminDemandRequestListResponse:
    if me.role == "supplier" and supplier_id is None:
        mapped = await _mapped_suppliers(me)
        supplier_id = mapped[0]["supplier_id"] if mapped else None
    rows = await demand_service.list_demand_requests(
        me.session,
        status_filter=status_filter,
        supplier_id=supplier_id,
        limit=limit,
        offset=offset,
    )
    return AdminDemandRequestListResponse(items=[AdminDemandRequestResponse(**row) for row in rows])


@router.patch(
    "/demand-requests/{demand_request_id}",
    response_model=AdminDemandRequestResponse,
    summary="Update demand request status",
)
@limiter.limit("30/minute")
async def admin_update_demand_request(
    request: Request,
    demand_request_id: Annotated[UUID, Path()],
    body: AdminDemandRequestUpdateBody,
    me: AdminPortalUser,
) -> AdminDemandRequestResponse:
    demand = await demand_service.update_demand_request(
        me.session,
        demand_request_id=demand_request_id,
        actor_user_id=me.user_id,
        status_value=body.status,
        response_note=body.response_note,
        offered_price_inr=body.offered_price_inr,
    )
    return AdminDemandRequestResponse(**demand)


async def _mapped_suppliers(me: CurrentUser) -> list[dict]:
    if me.role in {"admin", "karigar_staff"}:
        rows = (
            await me.session.execute(
                text(
                    """
                    SELECT supplier_id, supplier_code, display_name, contact_email, contact_phone, tier, is_active,
                           NULL::text AS role_in_supplier,
                           NULL::boolean AS is_primary
                    FROM suppliers
                    WHERE deleted_at IS NULL AND is_active = TRUE
                    ORDER BY display_name
                    """
                )
            )
        ).mappings().all()
        return [dict(row) for row in rows]
    rows = (
        await me.session.execute(
            text(
                """
                SELECT s.supplier_id, s.supplier_code, s.display_name,
                       m.role_in_supplier, m.is_primary
                FROM supplier_user_mappings m
                JOIN suppliers s ON s.supplier_id = m.supplier_id
                WHERE m.user_id = :user_id
                  AND m.deleted_at IS NULL
                  AND s.deleted_at IS NULL
                  AND s.is_active = TRUE
                ORDER BY m.is_primary DESC, s.display_name
                """
            ),
            {"user_id": str(me.user_id)},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _campaign_recipients(me: CurrentUser, campaign: dict) -> list[UUID]:
    params: dict = {}
    where = ["deleted_at IS NULL"]
    if campaign["target_role"] != "all":
        where.append("role = CAST(:target_role AS user_role)")
        params["target_role"] = campaign["target_role"]
    if campaign["target_supplier_id"]:
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
        params["target_supplier_id"] = str(campaign["target_supplier_id"])
    rows = (
        await me.session.execute(
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
    return list(rows)


async def _get_user_or_404(me: CurrentUser, user_id: UUID) -> dict:
    row = (
        await me.session.execute(
            text(
                """
                SELECT user_id, email,
                       safe_decrypt_pii(phone_encrypted) AS phone,
                       safe_decrypt_pii(full_name_encrypted) AS full_name,
                       role, is_verified, created_at, last_login_at, deleted_at
                FROM users
                WHERE user_id = :user_id
                """
            ),
            {"user_id": str(user_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return dict(row)


def _permissions_for_role(role: str) -> list[str]:
    if role == "admin":
        return ["admin:read", "admin:write", "users:write", "suppliers:write", "uploads:write"]
    if role == "karigar_staff":
        return ["admin:read", "users:write", "suppliers:write", "uploads:write"]
    if role == "supplier":
        return ["admin:read", "uploads:write"]
    return []
