"""Restore an account uniqueness rule absent in older local databases.

Revision ID: 20260925_legacy_constraints
Revises: 20260925_auth_recovery
"""

from alembic import op
import sqlalchemy as sa

revision = "20260925_legacy_constraints"
down_revision = "20260925_auth_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    constraints = sa.inspect(op.get_bind()).get_unique_constraints("oauth_identities")
    has_rule = any(set(item["column_names"]) == {"provider", "user_id"}
                   for item in constraints)
    if not has_rule:
        with op.batch_alter_table("oauth_identities") as batch:
            batch.create_unique_constraint("uq_oauth_identities_provider_user",
                                           ["provider", "user_id"])


def downgrade() -> None:
    # The baseline already has this rule; removing it would weaken fresh databases.
    pass
