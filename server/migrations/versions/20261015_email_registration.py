"""Require a one-use email code before password registration."""
from alembic import op
import sqlalchemy as sa

revision = "20261015_email_registration"
down_revision = "20261015_topup_emails"
branch_labels = depends_on = None


def upgrade():
    op.create_table("email_registrations",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(190), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_email_registrations_email", "email_registrations", ["email"])


def downgrade():
    op.drop_index("ix_email_registrations_email", table_name="email_registrations")
    op.drop_table("email_registrations")
