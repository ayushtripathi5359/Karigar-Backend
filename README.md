# Karigar Backend (v2)

FastAPI + Postgres modular monolith for the Karigar diamond intelligence platform.
RLS-enforced data isolation, pgcrypto-encrypted PII, OTP-phone auth.

## Layout

```
app/
├── core/              shared infra (config, logging, errors, security)
├── db/                Declarative Base + RLS-aware async session factory
├── middleware/        request_id, access log
├── shared/            rate limiter
└── modules/           one folder per domain — own models, schemas, service, router, deps
    ├── auth/          OTP + JWT + auth_events  (provider-pluggable for future Google/Apple)
    ├── users/         users + addresses (PII encrypted)
    ├── catalog/       supplier_master + stone_media + search
    ├── suppliers/     supplier_uploads + scrape_jobs + ingest
    ├── calculator/    jewellery quote calculator (diamond + gold + making + GST)
    ├── pricing/       rapaport + value_scores + price_history
    ├── orders/        orders + items + tracking + inventory_log
    ├── trends/        user_flow_tracking (stone interactions) + trend_signals
    └── notifications/ notifications + news_scraping

sql/                   v2 schema (canonical state)
├── 01_karigar_schema_v2.sql       — base (23 tables, 19 ENUMs, RLS, pgcrypto)
├── 01a_karigar_otp_addendum.sql   — phone_hash, nullable email, otp_records, auth_events
├── 02_calculator_tables.sql       — diamond_inventory, metal_rates, pricing_settings
└── 03_verify_v2.sql               — self-test

alembic/               migrations on top of the SQL baseline
tests/                 pytest (asyncio mode=auto)
```

Active modules: `auth`, `users`, `health`, `calculator`, `catalog`, `orders`, and
`payments`. The remaining domain routers are scaffolded for incremental build-out.

## Run

```bash
# 1. Create the database (one-time)
PGPASSWORD=postgres psql -h localhost -U postgres -d postgres \
  -c 'DROP DATABASE IF EXISTS karigar_app; CREATE DATABASE karigar_app;'
PGPASSWORD=postgres psql -h localhost -U postgres -d karigar_app -v ON_ERROR_STOP=1 \
  -f sql/01_karigar_schema_v2.sql
PGPASSWORD=postgres psql -h localhost -U postgres -d karigar_app -v ON_ERROR_STOP=1 \
  -f sql/01a_karigar_otp_addendum.sql
PGPASSWORD=postgres psql -h localhost -U postgres -d karigar_app -v ON_ERROR_STOP=1 \
  -f sql/02_calculator_tables.sql

# 2. Verify (every probe should print "PASS …")
PGPASSWORD=postgres psql -h localhost -U postgres -d karigar_app -f sql/03_verify_v2.sql

# 3. Stamp Alembic baseline (one-time)
.venv/bin/alembic stamp head

# 4. Boot the API
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Data imports

Calculator data comes from the Karigar price chart workbook and is stored in
`diamond_inventory`, `metal_rates`, and `pricing_settings`:

```bash
.venv/bin/python scripts/seed_inventory.py \
  --excel "/path/to/Price Chart_Karigar.xlsx"
```

Supplier inventory comes from the normalized supplier master CSV and is stored in
`suppliers` plus `supplier_master`. Prefer CSV over PDF because each stone stays
on one structured row:

```bash
.venv/bin/python scripts/import_supplier_master_csv.py \
  --csv "/path/to/schemas_suppliers_master_normalized(Master).csv"
```

## Auth flow

```
POST /v1/auth/otp/request   { "phone": "9876543210" }
   → 200 { message, expires_in }
   → backend terminal prints:
        ============================================
          [PIN STUB]  +919876543210  →  123456
        ============================================

POST /v1/auth/otp/verify    { "phone": "9876543210", "code": "123456" }
   → 200 { access_token, token_type: "bearer" }
   → on first login a `users` row is created (phone_encrypted set, email NULL)

GET  /v1/user                Authorization: Bearer <token>
   → 200 { user_id, email, phone, full_name, role, is_verified, onboarding_completed, ... }
   → phone/full_name decrypted server-side via session-local app.encryption_key

POST /v1/onboarding/complete  Authorization: Bearer <token>
                              { "display_name": "...", "email": "..." }
   → 200 { onboarding_completed: true, completed_at }
```

## How RLS works

Every authenticated request opens an async transaction with three Postgres
session GUCs set:

```sql
SELECT set_config('app.current_user_id',   '<uuid>', true);
SELECT set_config('app.current_user_role', 'buyer',  true);
SELECT set_config('app.encryption_key',    '<key>',  true);
```

The Postgres helpers `current_user_id()`, `is_admin()`, `encrypt_pii()`,
`decrypt_pii()` read these. RLS policies on `users`, `addresses`, `orders`,
`order_items`, `notifications`, `user_flow_tracking` reference them.

`SET LOCAL` / `set_config(..., true)` is **transaction-scoped** — that's why
`request_session()` opens exactly one transaction per request and never
mid-commits. Don't add intermediate commits to handler code.

The unauthenticated OTP-verify path (lookup user by phone before signing
them in) bypasses `users_self_read` via the SECURITY DEFINER function
`auth_lookup_user_by_phone_hash(text)`.

## How PII encryption works

PII columns on `users` and `addresses` are `BYTEA`, encrypted with
`pgp_sym_encrypt(plaintext, app.encryption_key)`.

- Writes wrap values in `encrypt_pii(:val)` SQL — see `app/modules/users/repository.py`.
- Reads do `SELECT decrypt_pii(col) AS col` inside a session that has the GUC set.
- `pgp_sym_encrypt` is **non-deterministic** (random IV) — you cannot equality-match
  ciphertext. For phone (the OTP identifier), we keep an HMAC-SHA256 `phone_hash`
  column alongside `phone_encrypted`. Hash is searchable; ciphertext is for display.

In production, fetch `PII_ENCRYPTION_KEY` and `PHONE_HASH_PEPPER` from
HashiCorp Vault / AWS Secrets Manager — never commit them.

## Tests

```bash
.venv/bin/pytest -q
```

Tests run against the live `karigar_app` database. Each test uses a unique
phone number to avoid cross-test state.

## Adding a new domain endpoint

1. Drop into `app/modules/<domain>/`.
2. Add SQLAlchemy mappings to `models.py`, request/response shapes to `schemas.py`.
3. Implement business logic in `service.py` (no SQL strings outside service or
   repository).
4. Wire HTTP in `router.py`, register in `app/main.py`.
5. If you touch encrypted columns, partial unique indexes, RLS, or partitioned
   tables, hand-write the Alembic migration — autogenerate doesn't model these.

## Auth-provider pluggability

`app/modules/auth/providers/` holds `OtpSender` implementations.

- `sms_stub.py` — current dev provider; prints code to terminal.
- (future) `twilio.py`, `msg91.py` — production SMS.
- (future) `google_oauth.py`, `apple_oauth.py` — drop-in for SSO.

Switch providers by editing the single instantiation in `app/modules/auth/router.py`.

## Known gaps (deferred)

- **Encryption key rotation** — `key_version SMALLINT` is stamped on every encrypted
  row, but the rotation procedure (decrypt-with-old → encrypt-with-new → bump version)
  isn't implemented.
- **Monthly cron** — `price_history` is partitioned monthly through 2026-08 with a
  default catch-all. Add pg_cron / app-level scheduler to create future partitions.
- **Domain endpoints** — `catalog`, `suppliers`, `pricing`, `orders`, `trends`,
  `notifications` ship with 501 stubs; flesh out per-feature.
- **Supplier-self-read RLS** — v2 schema has buyer-side RLS only; suppliers viewing
  their own listings is a future addition.
- **Real SMS provider** — wire Twilio/MSG91 into `providers/`.
