"""Store extra admin entry IP allowlist rows."""
from alembic import op
import sqlalchemy as sa

revision = "20261122_admin_allowed_ip"
down_revision = "20261121_yandex_avatar"
branch_labels = depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_allowed_ip",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cidr", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("admin_allowed_ip")
