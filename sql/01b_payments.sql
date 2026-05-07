-- =============================================================================
-- KARIGAR — Payments addendum
-- =============================================================================
-- Apply AFTER 01_karigar_schema_v2.sql + 01a_karigar_otp_addendum.sql.
--
-- Adds the `payments` table for the order checkout flow. The provider here
-- is `stub` for development; future Razorpay/Stripe integrations write
-- through the same table.
--
-- Ownership / RLS: payments inherit visibility from their parent order.
-- =============================================================================

CREATE TYPE payment_status AS ENUM (
  'initiated',
  'succeeded',
  'failed',
  'cancelled'
);

CREATE TABLE payments (
  payment_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id            UUID NOT NULL REFERENCES orders (order_id) ON DELETE CASCADE,
  provider            TEXT NOT NULL,                 -- 'stub' | 'razorpay' | ...
  provider_payment_id TEXT,                          -- gateway reference
  amount_inr          NUMERIC(14,2) NOT NULL,
  status              payment_status NOT NULL DEFAULT 'initiated',
  error_code          TEXT,
  error_message       TEXT,
  idempotency_key     TEXT NOT NULL UNIQUE,          -- client-supplied; replays return same row
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  finalized_at        TIMESTAMPTZ,
  CHECK (amount_inr > 0)
);

CREATE INDEX idx_payments_order   ON payments (order_id);
CREATE INDEX idx_payments_status  ON payments (status, created_at DESC);

-- RLS: payments are visible iff the parent order is visible.
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;

CREATE POLICY payments_via_order ON payments
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM orders o
      WHERE o.order_id = payments.order_id
        AND (o.buyer_id = current_user_id() OR is_admin())
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM orders o
      WHERE o.order_id = payments.order_id
        AND (o.buyer_id = current_user_id() OR is_admin())
    )
  );

COMMENT ON TABLE payments IS 'Payment lifecycle records, one row per provider intent. Replays via idempotency_key return the same row.';
