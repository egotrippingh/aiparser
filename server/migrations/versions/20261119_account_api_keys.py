"""Add revocable account API keys."""
from alembic import op
import sqlalchemy as sa

revision = "20261119_account_api_keys"
down_revision = "20261019_project_members"
branch_labels = depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_api_keys",
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("suffix", sa.String(4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("account_api_keys")
