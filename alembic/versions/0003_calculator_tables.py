"""calculator tables — diamond_inventory, metal_rates, pricing_settings

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-09
"""
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Schema applied externally via psql: sql/02_calculator_tables.sql
    pass


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pricing_settings")
    op.execute("DROP TABLE IF EXISTS metal_rates")
    op.execute("DROP TABLE IF EXISTS diamond_inventory")
