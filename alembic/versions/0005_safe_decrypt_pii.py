"""safe decrypt helper for admin views

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-13
"""
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
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
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS safe_decrypt_pii(BYTEA)")
