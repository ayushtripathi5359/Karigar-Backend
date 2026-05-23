"""admin supplier mappings

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-13
"""
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS supplier_user_mappings (
          mapping_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id          UUID NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
          supplier_id      UUID NOT NULL REFERENCES suppliers (supplier_id) ON DELETE CASCADE,
          role_in_supplier TEXT NOT NULL CHECK (role_in_supplier IN ('owner','manager','viewer')),
          is_primary       BOOLEAN NOT NULL DEFAULT FALSE,
          created_by       UUID REFERENCES users (user_id) ON DELETE SET NULL,
          created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
          deleted_at       TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sum_user_supplier_active
          ON supplier_user_mappings (user_id, supplier_id)
          WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sum_user_primary_active
          ON supplier_user_mappings (user_id)
          WHERE is_primary = TRUE AND deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sum_supplier_active
          ON supplier_user_mappings (supplier_id)
          WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_supplier_user_mappings_updated_at
          ON supplier_user_mappings
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_supplier_user_mappings_updated_at
          BEFORE UPDATE ON supplier_user_mappings
          FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_supplier_user_mappings_updated_at ON supplier_user_mappings")
    op.execute("DROP TABLE IF EXISTS supplier_user_mappings")
