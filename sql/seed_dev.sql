-- =============================================================================
-- DEV-ONLY SEED — five test stones + media + value scores
-- =============================================================================
-- Idempotent: ON CONFLICT DO NOTHING so re-runs are safe.
-- DO NOT run in production.
-- =============================================================================

-- One supplier
INSERT INTO suppliers (supplier_id, supplier_code, display_name, is_active)
VALUES ('11111111-1111-1111-1111-111111111111', 'karigar_test', 'Karigar Test Supplier', TRUE)
ON CONFLICT (supplier_id) DO NOTHING;

-- Five stones of varying shape / color / clarity / price
INSERT INTO supplier_master (
  id, supplier_id, stone_id, cert_number, lab,
  shape, carat, color_scale, clarity, cut, polish, symmetry,
  price_per_carat, price, rap_price, rap_discount,
  measurements, availability
)
VALUES
  -- 1 — round halo, premium
  ('a0000001-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'STONE-001', 'GIA-1234567', 'GIA',
   'round', 0.92, 'D', 'VVS1', 'Excellent', 'Excellent', 'Excellent',
   524000.00, 482000.00, 600000.00, -0.20,
   '6.20x6.22x3.90', 'available'),
  -- 2 — oval solitaire
  ('a0000002-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
   'STONE-002', 'IGI-7654321', 'IGI',
   'oval', 1.10, 'F', 'VS2', 'Very Good', 'Very Good', 'Very Good',
   568000.00, 625000.00, 800000.00, -0.219,
   '8.10x5.80x3.60', 'available'),
  -- 3 — cushion fancy
  ('a0000003-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111',
   'STONE-003', 'GIA-9999111', 'GIA',
   'cushion', 1.50, 'G', 'SI1', 'Very Good', 'Excellent', 'Very Good',
   430000.00, 645000.00, 720000.00, -0.104,
   '7.10x6.95x4.40', 'available'),
  -- 4 — emerald cut, large
  ('a0000004-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111',
   'STONE-004', 'GIA-2222333', 'GIA',
   'emerald', 2.05, 'H', 'VS1', 'Very Good', 'Excellent', 'Excellent',
   880000.00, 1804000.00, 2200000.00, -0.18,
   '8.50x6.20x4.10', 'available'),
  -- 5 — princess on offer
  ('a0000005-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111',
   'STONE-005', 'IGI-4444555', 'IGI',
   'princess', 0.70, 'I', 'VS2', 'Very Good', 'Very Good', 'Good',
   285000.00, 199500.00, 250000.00, -0.202,
   '4.60x4.55x3.30', 'available')
ON CONFLICT (id) DO NOTHING;

-- Primary image per stone (Unsplash placeholders — replace with your CDN)
INSERT INTO stone_media (media_id, stone_id, media_type, url, is_primary, sort_order) VALUES
  ('b0000001-0000-0000-0000-000000000001', 'a0000001-0000-0000-0000-000000000001', 'image',
   'https://images.unsplash.com/photo-1605100804763-247f67b3557e?w=800', TRUE, 0),
  ('b0000002-0000-0000-0000-000000000002', 'a0000002-0000-0000-0000-000000000002', 'image',
   'https://images.unsplash.com/photo-1599643477877-530eb83abc8e?w=800', TRUE, 0),
  ('b0000003-0000-0000-0000-000000000003', 'a0000003-0000-0000-0000-000000000003', 'image',
   'https://images.unsplash.com/photo-1612271207039-65cdc2b1245d?w=800', TRUE, 0),
  ('b0000004-0000-0000-0000-000000000004', 'a0000004-0000-0000-0000-000000000004', 'image',
   'https://images.unsplash.com/photo-1543295204-2ae345412549?w=800', TRUE, 0),
  ('b0000005-0000-0000-0000-000000000005', 'a0000005-0000-0000-0000-000000000005', 'image',
   'https://images.unsplash.com/photo-1573408301185-9146fe634ad0?w=800', TRUE, 0)
ON CONFLICT (media_id) DO NOTHING;

-- Value scores so search ordering "by value" works out of the box.
-- Numbers below are illustrative — recompute via the Python module any time.
INSERT INTO value_scores (
  stone_id, carat_factor, color_factor, clarity_factor, cut_factor,
  liquidity_factor, total_score, formula_version
) VALUES
  ('a0000001-0000-0000-0000-000000000001', 0.85, 1.00, 0.90, 1.00, 0.65, 0.8745, 'v1.0'),
  ('a0000002-0000-0000-0000-000000000002', 0.85, 0.92, 0.72, 0.85, 0.65, 0.8125, 'v1.0'),
  ('a0000003-0000-0000-0000-000000000003', 0.90, 0.86, 0.60, 0.85, 0.65, 0.8000, 'v1.0'),
  ('a0000004-0000-0000-0000-000000000004', 0.95, 0.78, 0.78, 0.85, 0.65, 0.8285, 'v1.0'),
  ('a0000005-0000-0000-0000-000000000005', 0.65, 0.68, 0.72, 0.85, 0.65, 0.7235, 'v1.0')
ON CONFLICT (stone_id, formula_version) DO NOTHING;
