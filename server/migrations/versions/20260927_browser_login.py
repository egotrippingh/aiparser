"""Short-lived links from authenticated agents to browser sessions."""
from alembic import op
import sqlalchemy as sa

revision = "20260927_browser_login"
down_revision = "20260926_control"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("oauth_attempts", sa.Column("connect_id", sa.String(32), nullable=True))
    op.create_table("browser_login_tickets",
        sa.Column("ticket_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("parent_hash", sa.String(64), nullable=False),
        sa.Column("destination", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_browser_login_tickets_user_id", "browser_login_tickets", ["user_id"])
    op.create_index("ix_browser_login_tickets_parent_hash", "browser_login_tickets", ["parent_hash"])


def downgrade():
    op.drop_table("browser_login_tickets")
    op.drop_column("oauth_attempts", "connect_id")
