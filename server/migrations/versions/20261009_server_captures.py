"""Server-owned provider captures and cloud run phase.

Revision ID: 20261009_server_captures
Revises: 20260929_result_error_message
"""

from alembic import op
import sqlalchemy as sa

revision = "20261009_server_captures"
down_revision = "20260929_result_error_message"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("control_runs") as batch:
        batch.alter_column("device_id", existing_type=sa.String(64), nullable=True)
        batch.add_column(sa.Column("phase", sa.String(16), nullable=False, server_default="agent"))
    with op.batch_alter_table("cloud_results") as batch:
        batch.alter_column("device_id", existing_type=sa.String(64), nullable=True)
        batch.alter_column("local_result_id", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("local_project_id", existing_type=sa.Integer(), nullable=True)
    op.create_index("uq_cloud_server_result", "cloud_results", ["run_id", "query_id", "service"],
                    unique=True, sqlite_where=sa.text("device_id IS NULL AND run_id IS NOT NULL"),
                    postgresql_where=sa.text("device_id IS NULL AND run_id IS NOT NULL"))
    op.create_table("server_captures",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(32), sa.ForeignKey("control_runs.id"), nullable=False),
        sa.Column("query_id", sa.String(32), nullable=False),
        sa.Column("service", sa.String(40), nullable=False),
        sa.Column("check_id", sa.String(100), nullable=False),
        sa.Column("answer_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "query_id", "service"),
        sa.UniqueConstraint("check_id"),
    )
    op.create_index("ix_server_captures_run_id", "server_captures", ["run_id"])


def downgrade():
    op.drop_index("uq_cloud_server_result", table_name="cloud_results")
    op.drop_index("ix_server_captures_run_id", table_name="server_captures")
    op.drop_table("server_captures")
    with op.batch_alter_table("cloud_results") as batch:
        batch.alter_column("device_id", existing_type=sa.String(64), nullable=False)
        batch.alter_column("local_result_id", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("local_project_id", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("control_runs") as batch:
        batch.drop_column("phase")
        batch.alter_column("device_id", existing_type=sa.String(64), nullable=False)
