"""Add durable provider submissions and database-wide collection admission."""
from alembic import op
import sqlalchemy as sa

revision = "20261012_provider_tasks"
down_revision = "20261009_server_captures"
branch_labels = depends_on = None


def upgrade():
    op.add_column("control_runs", sa.Column("retry_at", sa.DateTime(timezone=True)))
    accounts = op.create_table("provider_accounts",
        sa.Column("service", sa.String(40), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cooldown_until", sa.DateTime(timezone=True)))
    op.bulk_insert(accounts, [{"service": s, "revision": 0} for s in
        ("chatgpt", "perplexity", "gemini", "google_aio", "yandex_neuro")])
    op.create_table("provider_tasks",
        sa.Column("check_id", sa.String(100), primary_key=True),
        sa.Column("run_id", sa.String(32), sa.ForeignKey("control_runs.id"), nullable=False),
        sa.Column("query_id", sa.String(32), nullable=False),
        sa.Column("service", sa.String(40), nullable=False),
        sa.Column("submission_token", sa.String(32), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("task_id", sa.String(200)),
        sa.Column("answer_json", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("history_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    for field in ("run_id", "service", "state"):
        op.create_index(f"ix_provider_tasks_{field}", "provider_tasks", [field])


def downgrade():
    op.drop_table("provider_tasks")
    op.drop_table("provider_accounts")
    op.drop_column("control_runs", "retry_at")
