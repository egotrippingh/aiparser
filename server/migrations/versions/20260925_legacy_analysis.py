"""Fill a column missing in databases created before managed analysis.

Revision ID: 20260925_legacy_analysis
Revises: 69338e58324c
"""

from alembic import op
import sqlalchemy as sa

revision = "20260925_legacy_analysis"
down_revision = "69338e58324c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("checks")}
    if "analysis_json" not in columns:
        op.add_column("checks", sa.Column("analysis_json", sa.Text(), nullable=True))


def downgrade() -> None:
    # Existing baseline databases had this column before this migration.
    pass
