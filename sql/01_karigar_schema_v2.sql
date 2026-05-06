-- =============================================================================
-- KARIGAR APP — PostgreSQL Database Schema v2 (PATCHED & EXTENDED)
-- =============================================================================
-- Engine      : PostgreSQL 15+ (tested on 16.13)
-- Currency    : INR (NUMERIC(14,2)) — explicit in column names
-- Soft delete : deleted_at TIMESTAMPTZ (NULL = active)
-- Audit       : created_at, updated_at + auto trigger
-- Security    : Row-Level Security on user-scoped tables
-- PII         : pgcrypto envelope encryption for personal data
--
-- Changes from v1:
--   1.  event_type TEXT → ENUM in inventory_log + user_flow_tracking
--   2.  CHECK on rap_discount, carat ranges, prices, quantities
--   3.  CHECK on carat_from <= carat_to
--   4.  order_items.total_price_inr is now a generated column
--   5.  One-default-address-per-user enforced via partial unique index
--   6.  One-primary-image-per-stone enforced same way
--   7.  ON DELETE CASCADE on child tables (order_items, etc.)
--   8.  supplier_code ENUM dropped — only the FK to suppliers is used
--   9.  stone_color split: color_scale (D-Z) + fancy_color (text)
--   10. Soft-delete-friendly partial unique index on (supplier_id, stone_id)
--   11. Composite search index on supplier_master
--   12. RLS policies on user-scoped tables
--   13. PII columns encrypted via pgcrypto (full_name, phone, address lines)
-- New tables added:
--   - value_scores         (the Karigar / DIAMIND crown jewel)
--   - price_history        (partitioned, time-series)
--   - supplier_uploads     (delta-sync audit)
--   - scrape_jobs          (scraper run audit)
--   - trend_signals        (aggregated demand patterns)
-- =============================================================================

-- -------------------------------------------------------------
-- EXTENSIONS
-- -------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid + symmetric encryption
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- trigram fuzzy text search

-- -------------------------------------------------------------
-- HELPER FUNCTIONS — encryption + RLS context
-- -------------------------------------------------------------
-- The encryption key MUST be set per session by the application:
--    SET app.encryption_key = '<key fetched from Vault at request time>';
-- Storing the key in postgresql.conf would defeat the purpose.

CREATE OR REPLACE FUNCTION encrypt_pii(plaintext TEXT)
RETURNS BYTEA LANGUAGE sql VOLATILE AS $$
  SELECT pgp_sym_encrypt(plaintext, current_setting('app.encryption_key'));
$$;

CREATE OR REPLACE FUNCTION decrypt_pii(ciphertext BYTEA)
RETURNS TEXT LANGUAGE sql STABLE AS $$
  SELECT pgp_sym_decrypt(ciphertext, current_setting('app.encryption_key'));
$$;

-- App must set these before issuing user-scoped queries:
--    SET app.current_user_id   = '<uuid>';
--    SET app.current_user_role = 'buyer' | 'supplier' | 'admin' | 'karigar_staff';
CREATE OR REPLACE FUNCTION current_user_id()
RETURNS UUID LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid;
$$;

CREATE OR REPLACE FUNCTION current_user_role()
RETURNS TEXT LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.current_user_role', true), '');
$$;

CREATE OR REPLACE FUNCTION is_admin()
RETURNS BOOLEAN LANGUAGE sql STABLE AS $$
  SELECT current_user_role() IN ('admin','karigar_staff');
$$;

-- Auto-update updated_at trigger
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

-- -------------------------------------------------------------
-- ENUMS
-- -------------------------------------------------------------
CREATE TYPE user_role AS ENUM ('buyer','supplier','admin','karigar_staff');

CREATE TYPE stone_shape AS ENUM (
  'round','princess','cushion','oval','emerald','pear',
  'marquise','radiant','asscher','heart','other'
);

-- v2: White-scale only. Fancy diamonds use fancy_color text column.
CREATE TYPE stone_color_scale AS ENUM (
  'D','E','F','G','H','I','J','K','L','M','N',
  'O','P','Q','R','S','T','U','V','W','X','Y','Z'
);

CREATE TYPE stone_clarity AS ENUM (
  'FL','IF','VVS1','VVS2','VS1','VS2','SI1','SI2','I1','I2','I3'
);

CREATE TYPE stone_cut       AS ENUM ('Excellent','Very Good','Good','Fair','Poor');
CREATE TYPE stone_polish    AS ENUM ('Excellent','Very Good','Good','Fair','Poor');
CREATE TYPE stone_symmetry  AS ENUM ('Excellent','Very Good','Good','Fair','Poor');

CREATE TYPE fluorescence_intensity AS ENUM ('None','Faint','Medium','Strong','Very Strong');
CREATE TYPE stone_availability     AS ENUM ('available','on_hold','sold','memo','withdrawn');

CREATE TYPE order_status AS ENUM (
  'draft','confirmed','processing','shipped','delivered','cancelled','returned'
);

CREATE TYPE notification_type AS ENUM (
  'order_update','price_alert','news','offer','system','trend_signal'
);

CREATE TYPE media_type AS ENUM ('image','video','certificate','dna_scan','three_sixty');
CREATE TYPE lab_name   AS ENUM ('GIA','IGI','HRD','AGS','GCAL','GSI','other');

-- v2: Strict event vocabularies (was loose TEXT in v1)
CREATE TYPE inventory_event_type AS ENUM (
  'listed','viewed','added_to_cart','purchased','returned','memo_out','memo_back',
  'price_changed','status_changed','withdrawn'
);
CREATE TYPE user_flow_event_type AS ENUM (
  'view','search','wishlist_add','wishlist_remove','compare','share','filter','click','dwell'
);

CREATE TYPE upload_status AS ENUM ('queued','processing','done','failed','partial');
CREATE TYPE scrape_status AS ENUM ('queued','running','done','failed');

CREATE TYPE trend_kind AS ENUM (
  'demand_spike','price_rise','price_drop','low_stock','popular_search','new_listing_burst'
);

CREATE TYPE trend_period AS ENUM ('last_24h','last_7d','last_30d');

-- -------------------------------------------------------------
-- 1. USERS — PII columns are encrypted (BYTEA via pgcrypto)
-- -------------------------------------------------------------
CREATE TABLE users (
  user_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email            TEXT NOT NULL UNIQUE,                -- email is identifier, not encrypted
  phone_encrypted  BYTEA,                               -- pgp_sym_encrypt
  full_name_encrypted BYTEA NOT NULL,                   -- pgp_sym_encrypt
  role             user_role NOT NULL DEFAULT 'buyer',
  password_hash    TEXT,                                -- argon2id when in-house auth; NULL for SSO
  avatar_url       TEXT,
  preferred_lang   TEXT DEFAULT 'en',
  is_verified      BOOLEAN NOT NULL DEFAULT FALSE,
  last_login_at    TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at       TIMESTAMPTZ
);

CREATE INDEX idx_users_email      ON users (email)      WHERE deleted_at IS NULL;
CREATE INDEX idx_users_role       ON users (role)       WHERE deleted_at IS NULL;
CREATE INDEX idx_users_deleted_at ON users (deleted_at);

CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- -------------------------------------------------------------
-- 2. ADDRESSES — line1/line2 encrypted, single default per user
-- -------------------------------------------------------------
CREATE TABLE addresses (
  address_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
  label            TEXT,
  line1_encrypted  BYTEA NOT NULL,
  line2_encrypted  BYTEA,
  city             TEXT NOT NULL,
  state            TEXT NOT NULL,
  pincode          TEXT NOT NULL,
  country          TEXT NOT NULL DEFAULT 'India',
  is_default       BOOLEAN NOT NULL DEFAULT FALSE,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at       TIMESTAMPTZ,
  CONSTRAINT chk_pincode_format CHECK (pincode ~ '^[0-9]{4,10}$')
);

CREATE INDEX idx_addresses_user_id ON addresses (user_id) WHERE deleted_at IS NULL;

-- BUG 5 FIX: only one default address per user
CREATE UNIQUE INDEX idx_addresses_one_default
  ON addresses (user_id) WHERE is_default = TRUE AND deleted_at IS NULL;

CREATE TRIGGER trg_addresses_updated_at
  BEFORE UPDATE ON addresses
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- -------------------------------------------------------------
-- 3. SUPPLIERS — supplier_code TEXT (was ENUM in v1)
-- -------------------------------------------------------------
CREATE TABLE suppliers (
  supplier_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  supplier_code   TEXT NOT NULL UNIQUE,                 -- BUG 9 FIX: TEXT, not enum
  display_name    TEXT NOT NULL,
  legal_name      TEXT,
  contact_email   TEXT,
  contact_phone   TEXT,
  website         TEXT,
  api_endpoint    TEXT,
  api_key_hint    TEXT,                                 -- last 4 chars only; full key in vault
  vault_secret_ref TEXT,                                -- e.g. 'kv/suppliers/ratnakala'
  tier            TEXT CHECK (tier IN ('T1','T2','T3')),
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  onboarded_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at      TIMESTAMPTZ
);

CREATE INDEX idx_suppliers_active ON suppliers (is_active) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_suppliers_updated_at
  BEFORE UPDATE ON suppliers
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- -------------------------------------------------------------
-- 4. SUPPLIER_MASTER — diamond inventory (the big one)
--    v2: color split, CHECK constraints, partial unique, composite index
-- -------------------------------------------------------------
CREATE TABLE supplier_master (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  supplier_id         UUID NOT NULL REFERENCES suppliers (supplier_id) ON DELETE RESTRICT,

  -- Identification
  stone_id            TEXT NOT NULL,
  cert_number         TEXT,
  lab                 lab_name,
  availability        stone_availability NOT NULL DEFAULT 'available',
  location            TEXT,

  -- 4Cs
  shape               stone_shape NOT NULL,
  carat               NUMERIC(8,3) NOT NULL,
  color_scale         stone_color_scale,                -- D-Z; NULL if fancy
  fancy_color         TEXT,                             -- BUG 10 FIX: free-text fancy
  clarity             stone_clarity NOT NULL,
  cut                 stone_cut,
  polish              stone_polish,
  symmetry            stone_symmetry,
  fluorescence        fluorescence_intensity,
  fluorescence_color  TEXT,

  -- Pricing (INR)
  rap_price           NUMERIC(14,2),
  rap_value           NUMERIC(14,2),
  rap_discount        NUMERIC(7,4),
  price_per_carat     NUMERIC(14,2),
  price               NUMERIC(14,2),

  -- Proportions
  measurements        TEXT,
  length              NUMERIC(7,3),
  width               NUMERIC(7,3),
  depth               NUMERIC(7,3),
  table_pct           NUMERIC(5,2),
  depth_pct           NUMERIC(5,2),
  crown_angle         NUMERIC(5,2),
  crown_height        NUMERIC(5,2),
  pav_angle           NUMERIC(5,2),
  pav_depth           NUMERIC(5,2),
  ratio               NUMERIC(6,3),

  -- Girdle & culet
  girdle              TEXT,
  girdle_pct          NUMERIC(5,2),
  lower_half          NUMERIC(5,2),
  culet               TEXT,

  -- Quality flags
  milky               TEXT,
  shade               TEXT,
  bgm                 TEXT,
  natts               TEXT,
  hna                 TEXT,
  eye_clean           TEXT,
  inclusion_type      TEXT,

  -- Supplier-specific extras (JSONB instead of column-per-supplier soup)
  supplier_extras     JSONB,                            -- white_table, side_black, etc.

  -- Misc
  origin              TEXT,
  comments            TEXT,
  description         TEXT,
  inscription         TEXT,
  cert_date           DATE,
  cert_comments       TEXT,
  sheet_date          DATE,

  -- Provenance
  upload_id           UUID,                             -- FK added later (forward ref)
  scrape_job_id       UUID,                             -- FK added later
  raw_payload         JSONB,

  -- Audit
  ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at          TIMESTAMPTZ,

  -- BUG 2/3 FIX: domain CHECK constraints
  CONSTRAINT chk_carat_positive       CHECK (carat > 0),
  CONSTRAINT chk_price_non_negative   CHECK (price IS NULL OR price >= 0),
  CONSTRAINT chk_ppc_non_negative     CHECK (price_per_carat IS NULL OR price_per_carat >= 0),
  CONSTRAINT chk_rap_discount_range   CHECK (rap_discount IS NULL OR rap_discount BETWEEN -1 AND 1),
  CONSTRAINT chk_color_xor_fancy      CHECK (
    (color_scale IS NOT NULL AND fancy_color IS NULL) OR
    (color_scale IS NULL AND fancy_color IS NOT NULL)
  )
);

-- BUG 11 FIX: partial unique index allows soft-deleted rows to be re-uploaded
CREATE UNIQUE INDEX idx_sm_unique_active
  ON supplier_master (supplier_id, stone_id) WHERE deleted_at IS NULL;

CREATE INDEX idx_sm_supplier_id  ON supplier_master (supplier_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_sm_availability ON supplier_master (availability) WHERE deleted_at IS NULL;
CREATE INDEX idx_sm_raw_payload  ON supplier_master USING GIN (raw_payload);
CREATE INDEX idx_sm_extras       ON supplier_master USING GIN (supplier_extras);

-- BUG 12 FIX: composite index for the dominant search query pattern
CREATE INDEX idx_sm_search_composite
  ON supplier_master (shape, color_scale, clarity, carat, price)
  WHERE deleted_at IS NULL AND availability = 'available';

CREATE TRIGGER trg_supplier_master_updated_at
  BEFORE UPDATE ON supplier_master
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- -------------------------------------------------------------
-- 5. DISTINCT_VALUES_PER_COLUMN
-- -------------------------------------------------------------
CREATE TABLE distinct_values_per_column (
  id            BIGSERIAL PRIMARY KEY,
  column_name   TEXT NOT NULL,
  value         TEXT NOT NULL,
  mapped        BOOLEAN NOT NULL DEFAULT FALSE,
  display_order INT,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (column_name, value)
);

CREATE INDEX idx_dvpc_column_name ON distinct_values_per_column (column_name);

-- -------------------------------------------------------------
-- 6. STONE_MEDIA — one primary image per stone enforced
-- -------------------------------------------------------------
CREATE TABLE stone_media (
  media_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stone_id        UUID NOT NULL REFERENCES supplier_master (id) ON DELETE CASCADE,
  media_type      media_type NOT NULL,
  url             TEXT NOT NULL,
  thumbnail_url   TEXT,
  is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
  sort_order      INT NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at      TIMESTAMPTZ
);

CREATE INDEX idx_stone_media_stone_id ON stone_media (stone_id) WHERE deleted_at IS NULL;

-- BUG 6 FIX: only one primary image per stone
CREATE UNIQUE INDEX idx_stone_media_one_primary
  ON stone_media (stone_id) WHERE is_primary = TRUE AND deleted_at IS NULL;

-- -------------------------------------------------------------
-- 7. RAPAPORT_PRICE_MAPPING — carat range CHECK
-- -------------------------------------------------------------
CREATE TABLE rapaport_price_mapping (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  shape           stone_shape NOT NULL,
  color_scale     stone_color_scale NOT NULL,
  clarity         stone_clarity NOT NULL,
  carat_from      NUMERIC(8,3) NOT NULL,
  carat_to        NUMERIC(8,3) NOT NULL,
  rap_price_usd   NUMERIC(14,2) NOT NULL,
  usd_to_inr_rate NUMERIC(10,4) NOT NULL,
  rap_price_inr   NUMERIC(14,2) GENERATED ALWAYS AS (rap_price_usd * usd_to_inr_rate) STORED,
  effective_date  DATE NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at      TIMESTAMPTZ,
  CONSTRAINT chk_carat_range CHECK (carat_from <= carat_to),               -- BUG 3
  CONSTRAINT chk_rap_usd_positive CHECK (rap_price_usd > 0),
  CONSTRAINT chk_fx_positive  CHECK (usd_to_inr_rate > 0)
);

CREATE INDEX idx_rap_lookup
  ON rapaport_price_mapping (shape, color_scale, clarity, effective_date)
  WHERE deleted_at IS NULL;

CREATE TRIGGER trg_rap_updated_at
  BEFORE UPDATE ON rapaport_price_mapping
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- -------------------------------------------------------------
-- 8. ORDERS
-- -------------------------------------------------------------
CREATE TABLE orders (
  order_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  buyer_id            UUID NOT NULL REFERENCES users (user_id) ON DELETE RESTRICT,
  status              order_status NOT NULL DEFAULT 'draft',
  subtotal_inr        NUMERIC(14,2) NOT NULL DEFAULT 0,
  discount_inr        NUMERIC(14,2) NOT NULL DEFAULT 0,
  tax_inr             NUMERIC(14,2) NOT NULL DEFAULT 0,
  total_inr           NUMERIC(14,2) NOT NULL DEFAULT 0,
  billing_address_id  UUID REFERENCES addresses (address_id),
  shipping_address_id UUID REFERENCES addresses (address_id),
  notes               TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by          UUID REFERENCES users (user_id),
  updated_by          UUID REFERENCES users (user_id),
  deleted_at          TIMESTAMPTZ,
  CONSTRAINT chk_money_non_negative CHECK (
    subtotal_inr >= 0 AND discount_inr >= 0 AND tax_inr >= 0 AND total_inr >= 0
  )
);

CREATE INDEX idx_orders_buyer_id ON orders (buyer_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_orders_status   ON orders (status)   WHERE deleted_at IS NULL;
CREATE INDEX idx_orders_created  ON orders (created_at DESC);

CREATE TRIGGER trg_orders_updated_at
  BEFORE UPDATE ON orders
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- -------------------------------------------------------------
-- 9. ORDER_ITEMS — total_price_inr is now a generated column
-- -------------------------------------------------------------
CREATE TABLE order_items (
  order_item_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id        UUID NOT NULL REFERENCES orders (order_id) ON DELETE CASCADE,
  stone_id        UUID NOT NULL REFERENCES supplier_master (id) ON DELETE RESTRICT,
  quantity        INT NOT NULL DEFAULT 1,
  unit_price_inr  NUMERIC(14,2) NOT NULL,
  -- BUG 4 FIX: cannot drift from line math
  total_price_inr NUMERIC(14,2) GENERATED ALWAYS AS (quantity * unit_price_inr) STORED,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at      TIMESTAMPTZ,
  CONSTRAINT chk_qty_positive   CHECK (quantity > 0),
  CONSTRAINT chk_unit_price_pos CHECK (unit_price_inr >= 0)
);

CREATE INDEX idx_order_items_order_id ON order_items (order_id);
CREATE INDEX idx_order_items_stone_id ON order_items (stone_id);

CREATE TRIGGER trg_order_items_updated_at
  BEFORE UPDATE ON order_items
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- -------------------------------------------------------------
-- 10. ORDER_TRACKING
-- -------------------------------------------------------------
CREATE TABLE order_tracking (
  tracking_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id        UUID NOT NULL REFERENCES orders (order_id) ON DELETE CASCADE,
  status          order_status NOT NULL,
  location        TEXT,
  carrier         TEXT,
  tracking_number TEXT,
  notes           TEXT,
  event_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by      UUID REFERENCES users (user_id)
);

CREATE INDEX idx_order_tracking_order_id ON order_tracking (order_id);
CREATE INDEX idx_order_tracking_event_at ON order_tracking (event_at DESC);

-- -------------------------------------------------------------
-- 11. INVENTORY_LOG — event_type now ENUM
-- -------------------------------------------------------------
CREATE TABLE inventory_log (
  log_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stone_id        UUID NOT NULL REFERENCES supplier_master (id) ON DELETE CASCADE,
  event_type      inventory_event_type NOT NULL,                -- BUG 1 FIX
  user_id         UUID REFERENCES users (user_id) ON DELETE SET NULL,
  event_source    TEXT CHECK (event_source IN ('user','system','scraper','supplier')),
  quantity_change INT NOT NULL DEFAULT 0,
  price_inr       NUMERIC(14,2),
  notes           TEXT,
  event_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_inv_log_stone_id   ON inventory_log (stone_id);
CREATE INDEX idx_inv_log_event_at   ON inventory_log (event_at DESC);
CREATE INDEX idx_inv_log_event_type ON inventory_log (event_type);

-- -------------------------------------------------------------
-- 12. USER_FLOW_TRACKING — event_type now ENUM
-- -------------------------------------------------------------
CREATE TABLE user_flow_tracking (
  track_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
  stone_id        UUID REFERENCES supplier_master (id) ON DELETE SET NULL,
  event_type      user_flow_event_type NOT NULL,                -- BUG 1 FIX
  session_id      TEXT,
  search_query    TEXT,
  filter_params   JSONB,
  dwell_seconds   INT,
  device_type     TEXT,
  ip_address      INET,
  event_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_uft_user_id  ON user_flow_tracking (user_id);
CREATE INDEX idx_uft_stone_id ON user_flow_tracking (stone_id);
CREATE INDEX idx_uft_event_at ON user_flow_tracking (event_at DESC);
CREATE INDEX idx_uft_filter   ON user_flow_tracking USING GIN (filter_params);

-- -------------------------------------------------------------
-- 13. NEWS_SCRAPING
-- -------------------------------------------------------------
CREATE TABLE news_scraping (
  news_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_url      TEXT NOT NULL,
  source_name     TEXT,
  title           TEXT NOT NULL,
  summary         TEXT,
  full_content    TEXT,
  category        TEXT,
  sentiment_score NUMERIC(4,3),
  published_at    TIMESTAMPTZ,
  scraped_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  is_processed    BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at      TIMESTAMPTZ,
  UNIQUE (source_url),
  CONSTRAINT chk_sentiment_range CHECK (
    sentiment_score IS NULL OR sentiment_score BETWEEN -1 AND 1
  )
);

CREATE INDEX idx_news_category     ON news_scraping (category)     WHERE deleted_at IS NULL;
CREATE INDEX idx_news_published_at ON news_scraping (published_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_news_title_trgm   ON news_scraping USING GIN (title gin_trgm_ops);

-- -------------------------------------------------------------
-- 14. NOTIFICATIONS
-- -------------------------------------------------------------
CREATE TABLE notifications (
  notification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
  type            notification_type NOT NULL,
  title           TEXT NOT NULL,
  body            TEXT,
  metadata        JSONB,
  is_read         BOOLEAN NOT NULL DEFAULT FALSE,
  read_at         TIMESTAMPTZ,
  news_id         UUID REFERENCES news_scraping (news_id) ON DELETE SET NULL,
  order_id        UUID REFERENCES orders (order_id) ON DELETE SET NULL,
  stone_id        UUID REFERENCES supplier_master (id) ON DELETE SET NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at      TIMESTAMPTZ
);

CREATE INDEX idx_notif_user_unread ON notifications (user_id, is_read, created_at DESC)
  WHERE deleted_at IS NULL;

-- ===========================================================================
-- NEW TABLES — crown jewels & operational audit
-- ===========================================================================

-- -------------------------------------------------------------
-- 15. VALUE_SCORES — the Karigar / DIAMIND moat
--     formula: 0.4·carat + 0.2·color + 0.15·clarity + 0.15·cut + 0.1·liquidity
-- -------------------------------------------------------------
CREATE TABLE value_scores (
  score_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stone_id         UUID NOT NULL REFERENCES supplier_master (id) ON DELETE CASCADE,
  carat_factor     NUMERIC(5,4) NOT NULL,
  color_factor     NUMERIC(5,4) NOT NULL,
  clarity_factor   NUMERIC(5,4) NOT NULL,
  cut_factor       NUMERIC(5,4) NOT NULL,
  liquidity_factor NUMERIC(5,4) NOT NULL,
  total_score      NUMERIC(5,4) NOT NULL,
  formula_version  TEXT NOT NULL DEFAULT 'v1.0',
  computed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (stone_id, formula_version),
  CONSTRAINT chk_factors_range CHECK (
    carat_factor     BETWEEN 0 AND 1 AND
    color_factor     BETWEEN 0 AND 1 AND
    clarity_factor   BETWEEN 0 AND 1 AND
    cut_factor       BETWEEN 0 AND 1 AND
    liquidity_factor BETWEEN 0 AND 1 AND
    total_score      BETWEEN 0 AND 1
  )
);

CREATE INDEX idx_value_scores_total
  ON value_scores (formula_version, total_score DESC);
CREATE INDEX idx_value_scores_stone
  ON value_scores (stone_id, computed_at DESC);

-- -------------------------------------------------------------
-- 16. PRICE_HISTORY — partitioned time-series
-- -------------------------------------------------------------
CREATE TABLE price_history (
  history_id      UUID DEFAULT gen_random_uuid(),
  stone_id        UUID NOT NULL,
  price_per_carat NUMERIC(14,2),
  price_inr       NUMERIC(14,2),
  rap_discount    NUMERIC(7,4),
  source          TEXT NOT NULL,                       -- 'supplier','scrape','manual','system'
  recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (history_id, recorded_at),
  FOREIGN KEY (stone_id) REFERENCES supplier_master (id) ON DELETE CASCADE
) PARTITION BY RANGE (recorded_at);

CREATE INDEX idx_price_history_stone_time
  ON price_history (stone_id, recorded_at DESC);

-- Initial partitions (extend in maintenance jobs)
CREATE TABLE price_history_2026_05 PARTITION OF price_history
  FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE price_history_2026_06 PARTITION OF price_history
  FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE price_history_2026_07 PARTITION OF price_history
  FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE price_history_default PARTITION OF price_history DEFAULT;

-- Auto-record on supplier_master price change
CREATE OR REPLACE FUNCTION record_price_change()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.price IS DISTINCT FROM OLD.price
     OR NEW.price_per_carat IS DISTINCT FROM OLD.price_per_carat
     OR NEW.rap_discount IS DISTINCT FROM OLD.rap_discount THEN
    INSERT INTO price_history (
      stone_id, price_per_carat, price_inr, rap_discount, source
    ) VALUES (
      NEW.id, NEW.price_per_carat, NEW.price, NEW.rap_discount, 'system'
    );
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_supplier_master_price_history
  AFTER UPDATE ON supplier_master
  FOR EACH ROW EXECUTE FUNCTION record_price_change();

-- -------------------------------------------------------------
-- 17. SUPPLIER_UPLOADS — delta-sync audit
-- -------------------------------------------------------------
CREATE TABLE supplier_uploads (
  upload_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  supplier_id     UUID NOT NULL REFERENCES suppliers (supplier_id) ON DELETE RESTRICT,
  file_url        TEXT,
  file_type       TEXT NOT NULL CHECK (file_type IN ('xlsx','csv','json','api','whatsapp')),
  status          upload_status NOT NULL DEFAULT 'queued',
  rows_total      INT,
  rows_imported   INT,
  rows_new        INT,
  rows_updated    INT,
  rows_failed     INT,
  rows_trending   INT,
  error_log       JSONB,
  uploaded_by     UUID REFERENCES users (user_id) ON DELETE SET NULL,
  uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at    TIMESTAMPTZ
);

CREATE INDEX idx_supplier_uploads_supplier ON supplier_uploads (supplier_id, uploaded_at DESC);
CREATE INDEX idx_supplier_uploads_status   ON supplier_uploads (status);

-- Forward FK from supplier_master.upload_id (from earlier in this script)
ALTER TABLE supplier_master
  ADD CONSTRAINT fk_supplier_master_upload
  FOREIGN KEY (upload_id) REFERENCES supplier_uploads (upload_id) ON DELETE SET NULL;

-- -------------------------------------------------------------
-- 18. SCRAPE_JOBS — marketplace scraper audit
-- -------------------------------------------------------------
CREATE TABLE scrape_jobs (
  job_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_name       TEXT NOT NULL,                     -- 'rapnet','nivoda','vdb',...
  status            scrape_status NOT NULL DEFAULT 'queued',
  started_at        TIMESTAMPTZ,
  finished_at       TIMESTAMPTZ,
  records_collected INT,
  records_new       INT,
  records_updated   INT,
  records_failed    INT,
  filters_used      JSONB,
  error_message     TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_scrape_jobs_source_time ON scrape_jobs (source_name, created_at DESC);
CREATE INDEX idx_scrape_jobs_status      ON scrape_jobs (status);

-- Forward FK from supplier_master.scrape_job_id
ALTER TABLE supplier_master
  ADD CONSTRAINT fk_supplier_master_scrape_job
  FOREIGN KEY (scrape_job_id) REFERENCES scrape_jobs (job_id) ON DELETE SET NULL;

-- -------------------------------------------------------------
-- 19. TREND_SIGNALS — aggregated demand patterns
-- -------------------------------------------------------------
CREATE TABLE trend_signals (
  signal_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  segment_key   TEXT NOT NULL,                         -- e.g. 'round_1ct_g_vs2'
  trend_type    trend_kind NOT NULL,
  score         NUMERIC(5,4) NOT NULL,                 -- 0..1 strength
  period        trend_period NOT NULL,
  evidence      JSONB,                                 -- supporting numbers
  observed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  valid_until   TIMESTAMPTZ,
  CONSTRAINT chk_trend_score_range CHECK (score BETWEEN 0 AND 1)
);

CREATE INDEX idx_trend_signals_segment ON trend_signals (segment_key, observed_at DESC);
-- WHERE clauses on indexes must be IMMUTABLE; query layer filters by valid_until at read time.
CREATE INDEX idx_trend_signals_type ON trend_signals (trend_type, observed_at DESC);
CREATE INDEX idx_trend_signals_validity ON trend_signals (valid_until)
  WHERE valid_until IS NOT NULL;

-- ===========================================================================
-- ROW-LEVEL SECURITY POLICIES
-- ===========================================================================
-- App layer must SET app.current_user_id and app.current_user_role per request.
-- Admins / karigar_staff bypass via is_admin() helper.

-- USERS: a user can read/update only their own row; admin sees all
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY users_self_read ON users
  FOR SELECT USING (user_id = current_user_id() OR is_admin());
CREATE POLICY users_self_write ON users
  FOR UPDATE USING (user_id = current_user_id() OR is_admin());
CREATE POLICY users_admin_insert ON users
  FOR INSERT WITH CHECK (is_admin() OR current_user_id() IS NULL); -- NULL = signup path
CREATE POLICY users_admin_delete ON users
  FOR DELETE USING (is_admin());

-- ADDRESSES
ALTER TABLE addresses ENABLE ROW LEVEL SECURITY;
CREATE POLICY addresses_owner ON addresses
  FOR ALL USING (user_id = current_user_id() OR is_admin())
  WITH CHECK (user_id = current_user_id() OR is_admin());

-- ORDERS — buyer sees own orders; admin sees all
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY orders_buyer ON orders
  FOR ALL USING (buyer_id = current_user_id() OR is_admin())
  WITH CHECK (buyer_id = current_user_id() OR is_admin());

-- ORDER_ITEMS — visible if parent order is visible
ALTER TABLE order_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY order_items_via_order ON order_items
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM orders o
      WHERE o.order_id = order_items.order_id
        AND (o.buyer_id = current_user_id() OR is_admin())
    )
  );

-- NOTIFICATIONS
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY notifications_owner ON notifications
  FOR ALL USING (user_id = current_user_id() OR is_admin())
  WITH CHECK (user_id = current_user_id() OR is_admin());

-- USER_FLOW_TRACKING — owner reads, system writes
ALTER TABLE user_flow_tracking ENABLE ROW LEVEL SECURITY;
CREATE POLICY uft_owner_read ON user_flow_tracking
  FOR SELECT USING (user_id = current_user_id() OR is_admin());
CREATE POLICY uft_system_write ON user_flow_tracking
  FOR INSERT WITH CHECK (user_id = current_user_id() OR is_admin());

-- supplier_master / suppliers / news / etc. are PUBLIC reads → no RLS
-- (filtered server-side as needed)

-- ===========================================================================
-- TABLE COMMENTS
-- ===========================================================================
COMMENT ON TABLE supplier_master    IS 'Diamond inventory; canonical fields from mapping_rules.xlsx. PII not present here.';
COMMENT ON TABLE value_scores       IS 'Karigar Value Score (crown jewel). 0.4·carat + 0.2·color + 0.15·clarity + 0.15·cut + 0.1·liquidity.';
COMMENT ON TABLE price_history      IS 'Time-series price snapshots; partitioned monthly; auto-populated by trigger on supplier_master price changes.';
COMMENT ON TABLE supplier_uploads   IS 'Audit log of supplier feed ingestion runs (delta sync 120/80/40/20).';
COMMENT ON TABLE scrape_jobs        IS 'Audit log of marketplace scrape runs.';
COMMENT ON TABLE trend_signals      IS 'Aggregated demand/supply trends. Feeds intelligence layer + notifications.';
COMMENT ON COLUMN users.full_name_encrypted IS 'pgp_sym_encrypt with app.encryption_key set per-session.';
COMMENT ON COLUMN orders.subtotal_inr        IS 'All monetary values in Indian Rupees.';

-- =============================================================================
-- END OF SCHEMA v2
-- =============================================================================
