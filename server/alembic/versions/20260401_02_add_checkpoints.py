"""add persistent checkpoints

Revision ID: 20260401_02
Revises: 20260401_01
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa


revision = "20260401_02"
down_revision = "20260401_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_checkpoints",
        sa.Column("resume_token", sa.String(length=128), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("partial_assistant_text", sa.Text(), nullable=False),
        sa.Column("user_message_snapshot", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_session_checkpoints_session_id", "session_checkpoints", ["session_id"])
    op.create_index("ix_session_checkpoints_created_at", "session_checkpoints", ["created_at"])


def downgrade() -> None:
    op.drop_table("session_checkpoints")
