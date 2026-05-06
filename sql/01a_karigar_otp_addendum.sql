-- =============================================================================
-- KARIGAR — OTP-phone auth addendum to v2 schema
-- =============================================================================
-- Apply AFTER 01_karigar_schema_v2.sql.
--
-- Why this exists: v2 was designed for email/password identity. We use
-- phone-OTP as primary auth. This file adds:
--
--   1. phone_hash TEXT UNIQUE on users (HMAC-SHA256, searchable)
--   2. email + full_name_encrypted made NULLABLE (filled at onboarding)
--   3. key_version on encrypted tables (forward-compat for key rotation)
--   4. CHECK: row must have email OR phone_hash
--   5. otp_records + auth_events tables (auth-internal, no RLS)
--   6. auth_lookup_user_by_phone_hash(text) — SECURITY DEFINER lookup
--      that bypasses users RLS for the unauthenticated verify path.
--
-- All v2 RLS policies and PII encryption are unchanged.
-- =============================================================================

-- -------------------------------------------------------------
-- 1. USERS — relax NOT NULL + add phone_hash + key_version
-- -------------------------------------------------------------
ALTER TABLE users ALTER COLUMN email               DROP NOT NULL;
ALTER TABLE users ALTER COLUMN full_name_encrypted DROP NOT NULL;

ALTER TABLE users ADD COLUMN phone_hash  TEXT UNIQUE;
ALTER TABLE users ADD COLUMN key_version SMALLINT NOT NULL DEFAULT 1;

ALTER TABLE users ADD CONSTRAINT users_email_or_phone_hash
  CHECK (email IS NOT NULL OR phone_hash IS NOT NULL);

CREATE INDEX idx_users_phone_hash ON users (phone_hash) WHERE deleted_at IS NULL;

-- -------------------------------------------------------------
-- 2. ADDRESSES — key_version for rotation
-- -------------------------------------------------------------
ALTER TABLE addresses ADD COLUMN key_version SMALLINT NOT NULL DEFAULT 1;

-- -------------------------------------------------------------
-- 3. AUTH ENUMs
-- -------------------------------------------------------------
CREATE TYPE auth_event_type AS ENUM (
  'pin_requested',
  'pin_delivered',
  'pin_verified',
  'pin_incorrect',
  'pin_expired',
  'pin_rate_limited',
  'signup',
  'login'
);

-- -------------------------------------------------------------
-- 4. OTP_RECORDS — pending one-time codes
-- -------------------------------------------------------------
CREATE TABLE otp_records (
  otp_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone_hash  TEXT NOT NULL,                          -- HMAC of phone, indexed
  code_hash   TEXT NOT NULL,                          -- HMAC of the 6-digit code (no plaintext at rest)
  expires_at  TIMESTAMPTZ NOT NULL,
  attempts    INT NOT NULL DEFAULT 0,
  verified_at TIMESTAMPTZ,
  user_id     UUID REFERENCES users (user_id) ON DELETE SET NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_otp_attempts CHECK (attempts >= 0)
);

CREATE INDEX idx_otp_phone_hash_active
  ON otp_records (phone_hash, created_at DESC)
  WHERE verified_at IS NULL;

CREATE INDEX idx_otp_expires_at ON otp_records (expires_at);

-- -------------------------------------------------------------
-- 5. AUTH_EVENTS — audit trail for the auth surface
-- -------------------------------------------------------------
CREATE TABLE auth_events (
  event_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type  auth_event_type NOT NULL,
  user_id     UUID REFERENCES users (user_id) ON DELETE SET NULL,  -- nullable: pre-signup events
  phone_hash  TEXT,                                                 -- redundant with user_id when known
  request_id  TEXT,
  ip          INET,
  user_agent  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_auth_events_user_id    ON auth_events (user_id, created_at DESC);
CREATE INDEX idx_auth_events_phone_hash ON auth_events (phone_hash, created_at DESC);
CREATE INDEX idx_auth_events_created_at ON auth_events (created_at DESC);

-- -------------------------------------------------------------
-- 6. AUTH_LOOKUP — SECURITY DEFINER escape valve
-- -------------------------------------------------------------
-- The users_self_read RLS policy hides every row when current_user_id() is
-- NULL. The OTP verify flow needs to look up "is there a user with this phone
-- already?" BEFORE we know who's logging in. This function runs as the table
-- owner and bypasses RLS for that one read.
--
-- Returns: user_id if a (non-deleted) user exists with this phone_hash, else NULL.
CREATE OR REPLACE FUNCTION auth_lookup_user_by_phone_hash(p_phone_hash TEXT)
RETURNS UUID
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
  SELECT user_id
  FROM users
  WHERE phone_hash = p_phone_hash
    AND deleted_at IS NULL
  LIMIT 1;
$$;

-- Restrict callers — only the connecting role should be able to call this.
-- (In dev we run as `postgres`; in prod, GRANT EXECUTE to the app role only.)
REVOKE ALL ON FUNCTION auth_lookup_user_by_phone_hash(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_lookup_user_by_phone_hash(TEXT) TO postgres;

-- -------------------------------------------------------------
-- 7. COMMENTS
-- -------------------------------------------------------------
COMMENT ON COLUMN users.phone_hash IS 'HMAC-SHA256(phone, pepper). Searchable. phone_encrypted is for display.';
COMMENT ON COLUMN users.key_version IS 'Encryption-key version for the *_encrypted columns on this row. Bump on rotation.';
COMMENT ON TABLE  otp_records IS 'Pending OTPs. Keyed by phone_hash. code_hash is HMAC of the 6-digit code.';
COMMENT ON TABLE  auth_events IS 'Audit trail for auth surface. Pre-signup rows have NULL user_id.';
COMMENT ON FUNCTION auth_lookup_user_by_phone_hash(TEXT) IS 'RLS-bypass user lookup for the unauthenticated OTP verify path.';
