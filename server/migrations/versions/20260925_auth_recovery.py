"""Add shared login throttling and one-use password reset tokens.

Revision ID: 20260925_auth_recovery
Revises: 20260925_legacy_analysis
"""

from alembic import op
import sqlalchemy as sa

revision = "20260925_auth_recovery"
down_revision = "20260925_legacy_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_failures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_failures_key_hash", "auth_failures", ["key_hash"])
    op.create_table(
        "password_resets",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_password_resets_user_id", table_name="password_resets")
    op.drop_table("password_resets")
    op.drop_index("ix_auth_failures_key_hash", table_name="auth_failures")
    op.drop_table("auth_failures")
