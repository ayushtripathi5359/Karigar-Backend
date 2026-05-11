-- Calculator tables: diamond inventory, metal rates, pricing settings
-- Apply with: psql $DATABASE_URL -f sql/02_calculator_tables.sql

-- ── Diamond Inventory (seeded from Master sheet of Price Chart_Karigar.xlsx) ──
CREATE TABLE IF NOT EXISTS diamond_inventory (
    id               BIGSERIAL    PRIMARY KEY,
    item_type        VARCHAR(50)  NOT NULL,   -- LGD_HPHT, LGD_CVD, Natural Diamond, Natural Fency Diamond
    batch            VARCHAR(30),
    colour           VARCHAR(20),
    shape            VARCHAR(30),
    mm_size          VARCHAR(30),
    sieve_size       VARCHAR(30),
    avg_weight_carat NUMERIC(10,4),
    karigar_color    VARCHAR(15),             -- EF, FG, GH, HI, IJ, JK, KL, LC, LM
    karigar_purity   VARCHAR(25),             -- VVS - VS, VS -SI, SI - I1, I1/I2
    company_grade    VARCHAR(40),
    vendor_price     INTEGER,                 -- per carat in INR, nullable
    vendor_name      VARCHAR(100),
    karigar_price    INTEGER      NOT NULL DEFAULT 0,  -- karigar selling price per carat
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_diamond_inv_lookup
    ON diamond_inventory (item_type, shape, karigar_color, karigar_purity, batch);

-- ── Metal Rates (seeded from Metal sheet) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS metal_rates (
    id                 SERIAL       PRIMARY KEY,
    metal_type         VARCHAR(20)  NOT NULL,             -- Gold, Silver
    purity_kt          INTEGER      NOT NULL,             -- 24, 22, 18, 14, 9; 995 for silver
    colour             VARCHAR(20)  NOT NULL DEFAULT 'Yellow',
    market_rate_per_kg NUMERIC(14,2),
    price_per_gram     NUMERIC(10,4) NOT NULL,
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (metal_type, purity_kt, colour)
);

-- ── Pricing Settings (labour, markup, GST) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS pricing_settings (
    key        VARCHAR(50)   PRIMARY KEY,
    value      NUMERIC(12,4) NOT NULL,
    updated_at TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

INSERT INTO pricing_settings (key, value) VALUES
    ('labour_per_gram', 1000),
    ('markup_pct',      0.15),
    ('gst_pct',         0.03)
ON CONFLICT (key) DO NOTHING;
