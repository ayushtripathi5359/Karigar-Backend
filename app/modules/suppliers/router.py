from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, Request, UploadFile, status
from sqlalchemy.sql import text

from app.modules.auth.deps import CurrentUser, current_user, require_supplier_access
from app.modules.notifications.service import notify_supplier_upload_finished
from app.modules.suppliers import ingest
from app.modules.suppliers.normalize import parse_supplier_csv
from app.modules.suppliers.schemas import (
    SupplierUploadCreateResponse,
    SupplierUploadListResponse,
    SupplierUploadResponse,
)
from app.shared.rate_limit import limiter

router = APIRouter(prefix="/v1/suppliers", tags=["suppliers"])


@router.post(
    "/uploads",
    response_model=SupplierUploadCreateResponse,
    summary="Upload a supplier CSV feed",
)
@limiter.limit("20/minute")
async def trigger_upload(
    request: Request,
    me: Annotated[CurrentUser, Depends(current_user)],
    supplier_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
    file_url: Annotated[str | None, Form()] = None,
) -> SupplierUploadCreateResponse:
    await require_supplier_access(me, supplier_id)
    filename = file.filename or "supplier-upload.csv"
    file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else "csv"
    if file_type != "csv":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "supplier upload v1 supports csv files")

    upload_id = await ingest.start_upload(
        me.session,
        supplier_id=supplier_id,
        file_url=file_url or filename,
        file_type=file_type,
        uploaded_by=me.user_id,
    )
    normalized_rows, parse_errors = parse_supplier_csv(await file.read())
    await ingest.ingest_rows(
        me.session,
        supplier_id=supplier_id,
        upload_id=upload_id,
        rows=normalized_rows,
    )
    await ingest.append_upload_errors(me.session, upload_id=upload_id, errors=parse_errors)
    upload = await _get_upload_or_404(me, upload_id)
    await notify_supplier_upload_finished(me.session, upload=upload)
    return SupplierUploadCreateResponse(upload=SupplierUploadResponse(**upload))


@router.get(
    "/uploads",
    response_model=SupplierUploadListResponse,
    summary="List supplier upload runs",
)
@limiter.limit("60/minute")
async def list_uploads(
    request: Request,
    me: Annotated[CurrentUser, Depends(current_user)],
    supplier_id: UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status", pattern=r"^(queued|processing|done|failed|partial)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SupplierUploadListResponse:
    where = ["su.supplier_id = s.supplier_id"]
    params: dict = {"limit": limit, "offset": offset}

    if supplier_id is not None:
        await require_supplier_access(me, supplier_id)
        where.append("su.supplier_id = :supplier_id")
        params["supplier_id"] = str(supplier_id)
    elif me.role == "supplier":
        where.append(
            """
            EXISTS (
              SELECT 1 FROM supplier_user_mappings m
              WHERE m.supplier_id = su.supplier_id
                AND m.user_id = :current_user_id
                AND m.deleted_at IS NULL
            )
            """
        )
        params["current_user_id"] = str(me.user_id)
    elif me.role not in {"admin", "karigar_staff"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")

    if status_filter:
        where.append("su.status = CAST(:status AS upload_status)")
        params["status"] = status_filter

    rows = (
        await me.session.execute(
            text(
                f"""
                SELECT su.*, s.display_name AS supplier_display_name
                FROM supplier_uploads su, suppliers s
                WHERE {' AND '.join(where)}
                ORDER BY su.uploaded_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()
    return SupplierUploadListResponse(items=[SupplierUploadResponse(**dict(row)) for row in rows])


@router.get(
    "/uploads/{upload_id}",
    response_model=SupplierUploadResponse,
    summary="Upload status + counts",
)
@limiter.limit("60/minute")
async def upload_status(
    request: Request,
    upload_id: Annotated[UUID, Path()],
    me: Annotated[CurrentUser, Depends(current_user)],
) -> SupplierUploadResponse:
    row = await _get_upload_or_404(me, upload_id)
    return SupplierUploadResponse(**row)


async def _get_upload_or_404(me: CurrentUser, upload_id: UUID) -> dict:
    row = (
        await me.session.execute(
            text(
                """
                SELECT su.*, s.display_name AS supplier_display_name
                FROM supplier_uploads su
                JOIN suppliers s ON s.supplier_id = su.supplier_id
                WHERE su.upload_id = :upload_id
                """
            ),
            {"upload_id": str(upload_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "upload not found")
    await require_supplier_access(me, row["supplier_id"])
    return dict(row)
