"""Store optional Yandex avatar IDs."""

from alembic import op
import sqlalchemy as sa

revision = "20261121_yandex_avatar"
down_revision = "20261119_account_api_keys"
branch_labels = depends_on = None


def upgrade() -> None:
    op.add_column("oauth_identities", sa.Column("avatar_id", sa.String(190), nullable=True))
    op.add_column("yandex_registrations", sa.Column("avatar_id", sa.String(190), nullable=True))


def downgrade() -> None:
    op.drop_column("yandex_registrations", "avatar_id")
    op.drop_column("oauth_identities", "avatar_id")
