"""Private server-side admin entitlement for free checks."""

from alembic import op
import sqlalchemy as sa

revision = "20260925_admin_entitlement"
down_revision = "20260925_server_ai_budget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "is_admin" not in existing:
        op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("users", "is_admin")
