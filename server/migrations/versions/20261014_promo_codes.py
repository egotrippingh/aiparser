"""Add service-specific promotional scan credits, preserving existing checks."""
from alembic import op
import sqlalchemy as sa

revision = "20261014_promo_codes"
down_revision = "20261012_news_provider_pauses"
branch_labels = depends_on = None


def upgrade():
    op.create_table("promo_codes",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("scans_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("promo_redemptions",
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("code", sa.String(64), sa.ForeignKey("promo_codes.code"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("free_scan_balances",
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("service", sa.String(40), primary_key=True),
        sa.Column("remaining", sa.Integer(), nullable=False),
        sa.CheckConstraint("remaining >= 0", name="ck_free_scan_remaining"))
    op.add_column("checks", sa.Column("free_scan_service", sa.String(40)))


def downgrade():
    op.drop_column("checks", "free_scan_service")
    op.drop_table("free_scan_balances")
    op.drop_table("promo_redemptions")
    op.drop_table("promo_codes")
