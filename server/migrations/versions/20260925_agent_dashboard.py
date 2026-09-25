"""Add shared scan preferences, agent presence and cloud report rows.

Revision ID: 20260925_agent_dashboard
Revises: 20260925_legacy_constraints
"""

from alembic import op
import sqlalchemy as sa

revision = "20260925_agent_dashboard"
down_revision = "20260925_legacy_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scan_preferences",
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("local_time", sa.String(5), nullable=False),
        sa.Column("month_days_json", sa.Text(), nullable=False),
        sa.Column("browser_mode", sa.String(12), nullable=False),
        sa.Column("services_json", sa.Text(), nullable=False),
        sa.Column("speed_profile", sa.String(12), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "agent_devices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("local_time_zone", sa.String(80), nullable=False),
        sa.Column("active_scan", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("user_id", "device_id"),
    )
    op.create_index("ix_agent_devices_user_id", "agent_devices", ["user_id"])
    op.create_table(
        "cloud_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("local_result_id", sa.Integer(), nullable=False),
        sa.Column("local_project_id", sa.Integer(), nullable=False),
        sa.Column("project_name", sa.String(120), nullable=False),
        sa.Column("brand_name", sa.String(120), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("group_tag", sa.String(120)),
        sa.Column("service", sa.String(40), nullable=False),
        sa.Column("scan_date", sa.String(10), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("mention_types_json", sa.Text(), nullable=False),
        sa.Column("evidence_quote", sa.Text()),
        sa.Column("answer_text", sa.Text()),
        sa.Column("sources_json", sa.Text(), nullable=False),
        sa.Column("check_id", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "device_id", "local_result_id"),
    )
    op.create_index("ix_cloud_results_user_id", "cloud_results", ["user_id"])
    op.create_index("ix_cloud_results_scan_date", "cloud_results", ["scan_date"])


def downgrade() -> None:
    op.drop_index("ix_cloud_results_scan_date", table_name="cloud_results")
    op.drop_index("ix_cloud_results_user_id", table_name="cloud_results")
    op.drop_table("cloud_results")
    op.drop_index("ix_agent_devices_user_id", table_name="agent_devices")
    op.drop_table("agent_devices")
    op.drop_table("scan_preferences")
