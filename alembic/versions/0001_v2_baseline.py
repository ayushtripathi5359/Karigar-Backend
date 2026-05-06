"""v2 baseline — schema applied via sql/01_karigar_schema_v2.sql + sql/01a_karigar_otp_addendum.sql

Revision ID: 0001
Revises:
Create Date: 2026-05-06

The actual schema is owned by the SQL files in `sql/`. This revision is a
no-op marker so `alembic stamp head` records that the database matches the
v2 spec. Future schema changes go in real revisions on top of this baseline.
"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Schema applied externally via psql:
    #   psql -d karigar_app -f sql/01_karigar_schema_v2.sql
    #   psql -d karigar_app -f sql/01a_karigar_otp_addendum.sql
    # Then run: alembic stamp head
    pass


def downgrade() -> None:
    # Reverting v2 baseline means dropping the database. Not provided.
    raise NotImplementedError("v2 baseline cannot be downgraded — drop the DB to reset")
