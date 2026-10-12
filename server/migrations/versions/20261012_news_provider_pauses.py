"""Add public news and manual provider admission pauses."""
from alembic import op
import sqlalchemy as sa

revision = "20261012_news_provider_pauses"
down_revision = "20261012_provider_tasks"
branch_labels = depends_on = None


def upgrade():
    op.add_column("provider_accounts", sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("provider_accounts", sa.Column("last_paused_at", sa.DateTime(timezone=True)))
    op.create_table("news_posts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_news_posts_created_at", "news_posts", ["created_at"])
    op.create_index("ix_news_posts_author_id", "news_posts", ["author_id"])


def downgrade():
    op.drop_table("news_posts")
    op.drop_column("provider_accounts", "last_paused_at")
    op.drop_column("provider_accounts", "paused")
