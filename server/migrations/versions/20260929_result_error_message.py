"""cloud diagnostic message

Revision ID: 20260929_result_error_message
Revises: 20260927_browser_login
"""
from alembic import op
import sqlalchemy as sa
revision = "20260929_result_error_message"
down_revision = "20260927_browser_login"
branch_labels = depends_on = None
def upgrade():
    op.add_column("cloud_results", sa.Column("error_message", sa.Text(), nullable=True))
def downgrade():
    op.drop_column("cloud_results", "error_message")
