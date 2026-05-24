# Karigar Admin Panel Architecture

## Purpose

The admin panel is an operational control surface for Karigar platform teams and supplier users. It is intentionally built as an umbrella experience, but domain ownership stays separated:

- `admin` owns admin workflow orchestration, dashboard metrics, user management, supplier CRUD, and supplier-user mappings.
- `suppliers` owns upload authorization, CSV normalization, feed ingestion, and upload status.
- `auth` owns OTP login, JWT issuing, role loading, and RLS-aware request sessions.
- `catalog` continues to read inventory from `supplier_master`; upload APIs do not duplicate catalog behavior.

## Backend Shape

The modular-monolith path exposes:

- `/v1/admin/me`
- `/v1/admin/dashboard`
- `/v1/admin/users`
- `/v1/admin/suppliers`
- `/v1/admin/supplier-user-mappings`
- `/v1/suppliers/uploads`

The microservice/gateway path mirrors the admin module under `services/admin` and routes `/v1/admin/` through nginx. Keep business behavior in one place when possible; if a service copy is needed, keep the same schemas and SQL contract.

## Authorization Rules

All protected routes use `current_user()` so database work runs in one transaction with RLS session variables set.

- `admin` and `karigar_staff` can access full admin workflows.
- `supplier` can access `/v1/admin/me` and supplier-scoped upload/status workflows.
- `buyer` is blocked from admin and supplier upload surfaces.
- Supplier-specific access is enforced through `supplier_user_mappings`, not through frontend navigation alone.

## Upload Flow

1. User logs in by OTP and receives a JWT.
2. Frontend calls `/v1/admin/me`.
3. Upload page selects a supplier from the role-authorized supplier list.
4. `POST /v1/suppliers/uploads` creates a `supplier_uploads` row in `processing`.
5. CSV rows are normalized through `app/modules/suppliers/normalize.py`.
6. Valid rows are upserted into `supplier_master`.
7. Parse/row errors are appended to the upload audit row.
8. Upload status becomes `done`, `partial`, or `failed`.

## Testing

Backend tests live in `tests/`.

Recommended checks:

```bash
.venv/bin/pytest -q tests/test_admin_authz.py tests/test_supplier_normalize.py tests/test_admin_supplier_flows.py
.venv/bin/pytest -q
```

Frontend tests live in `admin/tests/` inside the frontend repo.

Recommended checks:

```bash
npm run test
npm run build
```

## Code Quality Standards

- Use typed Pydantic request/response DTOs for API boundaries.
- Keep role checks in shared auth dependencies, not scattered across handlers.
- Keep SQL parameters bound through SQLAlchemy `text(...), params`; do not interpolate user input.
- Keep comments focused on business rules, RLS behavior, and non-obvious decisions.
- Prefer small feature folders on the frontend: `features/*`, `shared/api`, `shared/ui`, `shared/config`.
- Frontend role behavior is convenience only; backend authorization remains the source of truth.
