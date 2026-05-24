CREATE OR REPLACE FUNCTION safe_decrypt_pii(ciphertext BYTEA)
RETURNS TEXT LANGUAGE plpgsql STABLE AS $$
BEGIN
  IF ciphertext IS NULL THEN
    RETURN NULL;
  END IF;
  RETURN pgp_sym_decrypt(ciphertext, current_setting('app.encryption_key'));
EXCEPTION WHEN OTHERS THEN
  RETURN NULL;
END;
$$;
