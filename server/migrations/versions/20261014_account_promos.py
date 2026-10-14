"""Pending password completion and additive promo availability controls."""
from alembic import op
import sqlalchemy as sa

revision = "20261014_account_promos"
down_revision = "20261014_promo_codes"
branch_labels = depends_on = None


def upgrade():
    op.add_column("oauth_attempts", sa.Column("parent_hash", sa.String(64)))
    op.create_index("ix_promo_redemptions_code", "promo_redemptions", ["code"])
    op.create_table("yandex_registrations",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(190), nullable=False),
        sa.Column("subject", sa.String(190), nullable=False),
        sa.Column("connect_id", sa.String(32)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    with op.batch_alter_table("promo_codes") as batch:
        batch.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("max_redemptions", sa.Integer()))
        batch.add_column(sa.Column("expires_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
        batch.create_check_constraint("ck_promo_max_redemptions", "max_redemptions IS NULL OR max_redemptions > 0")


def downgrade():
    op.drop_index("ix_promo_redemptions_code", table_name="promo_redemptions")
    op.drop_column("oauth_attempts", "parent_hash")
    with op.batch_alter_table("promo_codes") as batch:
        batch.drop_constraint("ck_promo_max_redemptions", type_="check")
        for name in ("revision", "expires_at", "max_redemptions", "is_active"):
            batch.drop_column(name)
    op.drop_table("yandex_registrations")
