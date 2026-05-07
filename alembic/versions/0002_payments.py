"""payments table — applied via sql/01b_payments.sql

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-06

The actual DDL lives in `sql/01b_payments.sql`. This revision is a marker
so the alembic_version row reflects the addendum being applied. Run:

    psql -d karigar_app -f sql/01b_payments.sql
    alembic stamp head
"""
from collections.abc import Sequence

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    raise NotImplementedError("payments addendum has no automated downgrade")
