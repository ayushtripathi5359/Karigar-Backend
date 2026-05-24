# Karigar Backend Quality Standards

## Architecture

The backend supports two deployment shapes:

- Modular monolith under `app/modules/*`.
- Microservice shape under `services/*` with shared infrastructure in `shared/karigar_shared`.

Domain ownership should remain clear:

- `auth`: OTP, JWT, auth audit events, auth providers.
- `users`: profile and addresses.
- `catalog`: stone search, details, and tracking.
- `suppliers`: supplier uploads, normalization, and inventory ingestion.
- `admin`: BFF-style admin workflows that compose domain data.
- `orders`: order lifecycle and tracking.
- `payments`: payment intent and confirmation.
- `calculator`: jewellery quote calculations.
- `pricing`: pricing/value-score domain.
- `trends`: currently scaffolded, not production-complete.

## Naming Standards

- API modules use lowercase domain folders: `app/modules/<domain>`.
- Pydantic schemas use request/response names such as `AdminUserResponse`.
- Database IDs keep table-specific names such as `user_id`, `supplier_id`, `upload_id`.
- SQL count fields should match database names exactly, for example `rows_total`, `rows_imported`, `rows_failed`.

## Security Standards

- Protected endpoints must use `current_user()` or a dependency built on top of it.
- Role checks belong in shared auth dependencies such as `require_roles`.
- Supplier scoping must use `supplier_user_mappings`; never trust frontend-only filtering.
- Use parameterized SQL through SQLAlchemy `text(...), params`.
- PII reads/writes must use the RLS-aware request session so encryption GUCs are set.

## Testing Standards

Backend tests live in `tests/`.

Run:

```bash
.venv/bin/pytest -q
.venv/bin/python -m compileall app shared services/admin services/suppliers
.venv/bin/alembic upgrade head
```

Optional pricing workbook integration test:

```bash
cd services/pricing
PYTHONPATH=. ../../.venv/bin/pytest -q tests
```

Current coverage includes:

- OTP request/verify behavior.
- Buyer order and payment flow.
- PII roundtrip.
- Critical E2E API flow: OTP login, catalog, checkout, payment confirmation.
- Admin role authorization.
- Supplier-user mapping CRUD.
- Supplier CSV normalization.
- Supplier upload permission and upsert behavior.
- Critical E2E supplier flow: admin upload followed by scoped supplier upload.
- Pricing workbook normalizer roundtrip when `KARIGAR_PRICING_WORKBOOK_PATH`
  points at the private workbook; otherwise that test skips cleanly.

## CI

GitHub Actions workflow:

- `.github/workflows/backend-quality.yml`

It runs migrations, seeds deterministic catalog data, runs pytest, compiles
backend/service code, and runs optional pricing service tests.

## Remaining Hardening

- Add tests for notifications/trends when those endpoints move beyond scaffolded `501` responses.
- Add service-level tests for each microservice deployment image.
- Add CI to run pytest, migrations, compile checks, frontend type-check, admin tests, and admin build on every PR.
- Add browser/mobile E2E tests for critical user journeys.
