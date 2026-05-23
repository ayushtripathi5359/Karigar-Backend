import csv
import io
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, Request, Response, UploadFile, status
from sqlalchemy.sql import text

from karigar_shared.auth.deps import CurrentUser, current_user, require_supplier_access
from karigar_shared.notifications import notify_supplier_upload_finished
from karigar_shared.rate_limit import limiter

from app import ingest
from app.normalize import parse_supplier_csv
from app.schemas import (
    SupplierUploadCreateResponse,
    SupplierUploadListResponse,
    SupplierUploadResponse,
    SupplierInventoryListResponse,
    SupplierInventoryResponse,
    SupplierInventoryUpdateBody,
)

router = APIRouter(prefix="/v1/suppliers", tags=["suppliers"])

_INVENTORY_SELECT = """
    SELECT sm.id, sm.supplier_id, s.display_name AS supplier_display_name,
           sm.stone_id, sm.cert_number, sm.lab, sm.availability,
           sm.shape, sm.carat, sm.color_scale, sm.fancy_color, sm.clarity,
           sm.cut, sm.polish, sm.symmetry, sm.price_per_carat, sm.price,
           sm.rap_price, sm.rap_discount, sm.measurements, sm.supplier_extras,
           sm.updated_at
    FROM supplier_master sm
    JOIN suppliers s ON s.supplier_id = sm.supplier_id
"""

_INVENTORY_EXPORT_COLUMNS = [
    "stone_id",
    "supplier_display_name",
    "cert_number",
    "lab",
    "availability",
    "shape",
    "carat",
    "color_scale",
    "fancy_color",
    "clarity",
    "cut",
    "polish",
    "symmetry",
    "price_per_carat",
    "price",
    "rap_price",
    "rap_discount",
    "measurements",
    "supplier_extras",
    "updated_at",
]

_INVENTORY_CASTS = {
    "shape": "CAST(:shape AS stone_shape)",
    "color_scale": "CAST(:color_scale AS stone_color_scale)",
    "clarity": "CAST(:clarity AS stone_clarity)",
    "cut": "CAST(:cut AS stone_cut)",
    "polish": "CAST(:polish AS stone_polish)",
    "symmetry": "CAST(:symmetry AS stone_symmetry)",
    "lab": "CAST(:lab AS lab_name)",
    "availability": "CAST(:availability AS stone_availability)",
    "supplier_extras": "CAST(:supplier_extras AS jsonb)",
}


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
    "/inventory",
    response_model=SupplierInventoryListResponse,
    summary="List mapped supplier inventory",
)
@limiter.limit("60/minute")
async def list_inventory(
    request: Request,
    me: Annotated[CurrentUser, Depends(current_user)],
    supplier_id: UUID | None = Query(None),
    availability: str | None = Query(None, pattern=r"^(available|on_hold|sold|memo|withdrawn)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SupplierInventoryListResponse:
    where, params = await _inventory_scope(me, supplier_id=supplier_id)
    params.update({"limit": limit, "offset": offset})
    if availability:
        where.append("sm.availability = CAST(:availability AS stone_availability)")
        params["availability"] = availability
    rows = (
        await me.session.execute(
            text(
                f"""
                {_INVENTORY_SELECT}
                WHERE {' AND '.join(where)}
                ORDER BY sm.updated_at DESC, sm.stone_id
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()
    return SupplierInventoryListResponse(items=[SupplierInventoryResponse(**dict(row)) for row in rows])


@router.get("/inventory/export", summary="Export mapped supplier inventory as CSV")
@limiter.limit("20/minute")
async def export_inventory(
    request: Request,
    me: Annotated[CurrentUser, Depends(current_user)],
    supplier_id: UUID | None = Query(None),
    availability: str | None = Query(None, pattern=r"^(available|on_hold|sold|memo|withdrawn)$"),
) -> Response:
    where, params = await _inventory_scope(me, supplier_id=supplier_id)
    if availability:
        where.append("sm.availability = CAST(:availability AS stone_availability)")
        params["availability"] = availability
    rows = (
        await me.session.execute(
            text(
                f"""
                {_INVENTORY_SELECT}
                WHERE {' AND '.join(where)}
                ORDER BY sm.updated_at DESC, sm.stone_id
                """
            ),
            params,
        )
    ).mappings().all()
    return _csv_response("supplier-inventory.csv", _INVENTORY_EXPORT_COLUMNS, rows)


@router.patch(
    "/inventory/{stone_id}",
    response_model=SupplierInventoryResponse,
    summary="Update editable supplier inventory fields",
)
@limiter.limit("30/minute")
async def update_inventory(
    request: Request,
    stone_id: Annotated[UUID, Path()],
    body: SupplierInventoryUpdateBody,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> SupplierInventoryResponse:
    current = await _get_inventory_or_404(me, stone_id)
    await require_supplier_access(me, current["supplier_id"])
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no editable fields supplied")

    params = {"stone_id": str(stone_id)}
    set_sql = []
    for field, value in updates.items():
        params[field] = json.dumps(value) if field == "supplier_extras" else value
        set_sql.append(f"{field} = {_INVENTORY_CASTS.get(field, ':' + field)}")
    set_sql.append("updated_at = now()")

    await me.session.execute(
        text(
            f"""
            UPDATE supplier_master
            SET {', '.join(set_sql)}
            WHERE id = :stone_id
              AND deleted_at IS NULL
            """
        ),
        params,
    )
    return SupplierInventoryResponse(**await _get_inventory_or_404(me, stone_id))


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


@router.get("/uploads/{upload_id}/errors/export", summary="Export supplier upload errors as CSV")
@limiter.limit("20/minute")
async def export_upload_errors(
    request: Request,
    upload_id: Annotated[UUID, Path()],
    me: Annotated[CurrentUser, Depends(current_user)],
) -> Response:
    upload = await _get_upload_or_404(me, upload_id)
    errors = upload.get("error_log") or []
    if isinstance(errors, dict):
        errors = [errors]
    rows = [
        {
            "upload_id": str(upload_id),
            "supplier_id": str(upload["supplier_id"]),
            "stone_id": error.get("stone_id"),
            "error": error.get("error") or error.get("message") or json.dumps(error),
        }
        for error in errors
    ]
    return _csv_response("supplier-upload-errors.csv", ["upload_id", "supplier_id", "stone_id", "error"], rows)


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


async def _inventory_scope(me: CurrentUser, *, supplier_id: UUID | None) -> tuple[list[str], dict]:
    where = ["sm.deleted_at IS NULL", "s.deleted_at IS NULL"]
    params: dict = {}
    if supplier_id is not None:
        await require_supplier_access(me, supplier_id)
        where.append("sm.supplier_id = :supplier_id")
        params["supplier_id"] = str(supplier_id)
    elif me.role == "supplier":
        where.append(
            """
            EXISTS (
              SELECT 1 FROM supplier_user_mappings m
              WHERE m.supplier_id = sm.supplier_id
                AND m.user_id = :current_user_id
                AND m.deleted_at IS NULL
            )
            """
        )
        params["current_user_id"] = str(me.user_id)
    elif me.role not in {"admin", "karigar_staff"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
    return where, params


async def _get_inventory_or_404(me: CurrentUser, stone_id: UUID) -> dict:
    row = (
        await me.session.execute(
            text(
                f"""
                {_INVENTORY_SELECT}
                WHERE sm.id = :stone_id
                  AND sm.deleted_at IS NULL
                """
            ),
            {"stone_id": str(stone_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "inventory stone not found")
    await require_supplier_access(me, row["supplier_id"])
    return dict(row)


def _csv_response(filename: str, columns: list[str], rows) -> Response:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        record = dict(row)
        for key, value in record.items():
            if isinstance(value, dict):
                record[key] = json.dumps(value, sort_keys=True)
        writer.writerow(record)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
