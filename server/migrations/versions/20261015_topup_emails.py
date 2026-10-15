"""Persist balance top-up notifications with the payment credit."""
from alembic import op
import sqlalchemy as sa

revision = "20261015_topup_emails"
down_revision = "20261014_account_promos"
branch_labels = depends_on = None


def upgrade():
    op.create_table("topup_emails",
        sa.Column("order_id", sa.String(32), sa.ForeignKey("payment_orders.id"), primary_key=True),
        sa.Column("email", sa.String(190), nullable=False),
        sa.Column("amount_kopeks", sa.Integer(), nullable=False),
        sa.Column("balance_kopeks", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)))
    op.create_index("ix_topup_emails_due", "topup_emails", ["status", "next_attempt_at"])


def downgrade():
    op.drop_index("ix_topup_emails_due", table_name="topup_emails")
    op.drop_table("topup_emails")
