"""Add explicit project sharing memberships."""
from alembic import op
import sqlalchemy as sa

revision = "20261019_project_members"
down_revision = "20261015_email_registration"
branch_labels = depends_on = None


def upgrade():
    op.create_table("project_members",
        sa.Column("project_id", sa.String(32), sa.ForeignKey("control_projects.id"), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('editor', 'viewer')", name="ck_project_member_role"))
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"])


def downgrade():
    op.drop_index("ix_project_members_user_id", table_name="project_members")
    op.drop_table("project_members")
