-- =============================================================================
-- Karigar v2 — Self-Verification Script
-- Run this to confirm every bug fix and new feature is functioning.
-- =============================================================================

-- Set session context (in real app, set per-request from JWT)
SET app.encryption_key  = 'demo-key-replace-in-prod';
SET app.current_user_id = '00000000-0000-0000-0000-000000000000';
SET app.current_user_role = 'admin';

\echo '─── Object counts ───'
SELECT 'tables'   AS kind, count(*)::text FROM pg_tables  WHERE schemaname='public'
UNION ALL SELECT 'enums',     count(*)::text FROM pg_type WHERE typtype='e'
UNION ALL SELECT 'indexes',   count(*)::text FROM pg_indexes WHERE schemaname='public'
UNION ALL SELECT 'triggers',  count(*)::text FROM pg_trigger WHERE NOT tgisinternal
UNION ALL SELECT 'fkeys',     count(*)::text FROM pg_constraint WHERE contype='f'
UNION ALL SELECT 'CHECKs',    count(*)::text FROM pg_constraint WHERE contype='c' AND connamespace=(SELECT oid FROM pg_namespace WHERE nspname='public')
UNION ALL SELECT 'RLS pols',  count(*)::text FROM pg_policy
UNION ALL SELECT 'partitions',count(*)::text FROM pg_inherits WHERE inhparent='price_history'::regclass;

\echo ''
\echo '─── Tables present (must include 5 new ones) ───'
SELECT tablename FROM pg_tables
WHERE schemaname='public'
  AND tablename IN ('value_scores','price_history','supplier_uploads','scrape_jobs','trend_signals')
ORDER BY tablename;

\echo ''
\echo '─── Bug fix probes (each should NOTICE "PASS") ───'

-- Setup
INSERT INTO suppliers (supplier_code, display_name) VALUES ('demo_sup','Demo') ON CONFLICT (supplier_code) DO NOTHING;
WITH s AS (SELECT supplier_id FROM suppliers WHERE supplier_code='demo_sup')
INSERT INTO supplier_master (supplier_id,stone_id,shape,carat,color_scale,clarity,price)
SELECT s.supplier_id,'VERIFY1','round',1.0,'G','VS2',100000 FROM s
ON CONFLICT DO NOTHING;

DO $$ BEGIN
  BEGIN
    INSERT INTO supplier_master (supplier_id,stone_id,shape,carat,color_scale,clarity,rap_discount)
    SELECT supplier_id,'V_BAD','round',1,'G','VS2',5.0 FROM suppliers LIMIT 1;
    RAISE EXCEPTION 'BUG 2 not fixed';
  EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'PASS BUG 2: rap_discount range CHECK works';
  END;
END $$;

DO $$ BEGIN
  BEGIN
    INSERT INTO rapaport_price_mapping (shape,color_scale,clarity,carat_from,carat_to,rap_price_usd,usd_to_inr_rate,effective_date)
    VALUES ('round','G','VS2',5,1,7000,83.5,'2026-05-06');
    RAISE EXCEPTION 'BUG 3 not fixed';
  EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'PASS BUG 3: carat range CHECK works';
  END;
END $$;

-- BUG 4: generated column
INSERT INTO users (email, full_name_encrypted) VALUES ('verify@x.in', encrypt_pii('Verify')) ON CONFLICT (email) DO NOTHING;
DO $$
DECLARE u UUID; o UUID; sm UUID;
BEGIN
  SELECT user_id INTO u FROM users WHERE email='verify@x.in';
  INSERT INTO orders (buyer_id) VALUES (u) RETURNING order_id INTO o;
  SELECT id INTO sm FROM supplier_master WHERE stone_id='VERIFY1';
  INSERT INTO order_items (order_id,stone_id,quantity,unit_price_inr) VALUES (o,sm,4,250);
  IF (SELECT total_price_inr FROM order_items WHERE order_id=o)=1000 THEN
    RAISE NOTICE 'PASS BUG 4: order_items.total_price_inr generated correctly (4 × 250 = 1000)';
  ELSE
    RAISE EXCEPTION 'BUG 4 broken';
  END IF;
END $$;

-- BUG 5: one-default-address
DO $$
DECLARE u UUID;
BEGIN
  SELECT user_id INTO u FROM users WHERE email='verify@x.in';
  INSERT INTO addresses (user_id,line1_encrypted,city,state,pincode,is_default)
    VALUES (u, encrypt_pii('A1'),'Mumbai','MH','400001',TRUE) ON CONFLICT DO NOTHING;
  BEGIN
    INSERT INTO addresses (user_id,line1_encrypted,city,state,pincode,is_default)
      VALUES (u, encrypt_pii('A2'),'Delhi','DL','110001',TRUE);
    RAISE EXCEPTION 'BUG 5 not fixed';
  EXCEPTION WHEN unique_violation THEN
    RAISE NOTICE 'PASS BUG 5: only one default address per user enforced';
  END;
END $$;

-- price_history trigger
DO $$
DECLARE sm UUID; n INT;
BEGIN
  SELECT id INTO sm FROM supplier_master WHERE stone_id='VERIFY1';
  UPDATE supplier_master SET price=99000 WHERE id=sm;
  UPDATE supplier_master SET price=98000 WHERE id=sm;
  SELECT count(*) INTO n FROM price_history WHERE stone_id=sm;
  IF n >= 2 THEN
    RAISE NOTICE 'PASS price_history trigger: % rows recorded', n;
  ELSE
    RAISE EXCEPTION 'price_history trigger not firing';
  END IF;
END $$;

-- PII round-trip
DO $$
DECLARE name TEXT;
BEGIN
  SELECT decrypt_pii(full_name_encrypted) INTO name FROM users WHERE email='verify@x.in';
  IF name='Verify' THEN
    RAISE NOTICE 'PASS PII encryption: round-trip works';
  ELSE
    RAISE EXCEPTION 'PII encryption broken';
  END IF;
END $$;

\echo ''
\echo '─── Composite search index test (should be index-scan) ───'
EXPLAIN (COSTS OFF)
SELECT id FROM supplier_master
WHERE shape='round' AND color_scale='G' AND clarity='VS2'
  AND carat BETWEEN 0.9 AND 1.1
  AND availability='available' AND deleted_at IS NULL
ORDER BY price LIMIT 20;

\echo ''
\echo '─── Done. ───'
