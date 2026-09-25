"""Persist server AI usage and bound primary/arbiter attempts per check."""

from alembic import op
import sqlalchemy as sa

revision = "20260925_server_ai_budget"
down_revision = "20260925_agent_dashboard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("checks")}
    columns = (
        sa.Column("analysis_model", sa.String(100)),
        sa.Column("analysis_usage_json", sa.Text()),
        sa.Column("analysis_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("arbitration_json", sa.Text()),
        sa.Column("arbitration_model", sa.String(100)),
        sa.Column("arbitration_usage_json", sa.Text()),
        sa.Column("arbitration_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    for column in columns:
        if column.name not in existing:
            op.add_column("checks", column)


def downgrade() -> None:
    for column in ("arbitration_attempts", "arbitration_usage_json", "arbitration_model",
                   "arbitration_json", "analysis_attempts", "analysis_usage_json", "analysis_model"):
        op.drop_column("checks", column)
