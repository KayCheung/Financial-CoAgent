"""init persistence tables

Revision ID: 20260401_01
Revises: None
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa


revision = "20260401_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("session_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_owner_id", "sessions", ["owner_id"])
    op.create_index("ix_sessions_updated_at", "sessions", ["updated_at"])
    op.create_table(
        "session_messages",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.Column("token_usage", sa.JSON(), nullable=True),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_session_messages_session_id", "session_messages", ["session_id"])
    op.create_index("ix_session_messages_created_at", "session_messages", ["created_at"])
    op.create_table(
        "stage_snapshots",
        sa.Column("session_id", sa.String(length=64), primary_key=True),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("run_json", sa.Text(), nullable=False),
        sa.Column("last_event_id", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_stage_snapshots_owner_id", "stage_snapshots", ["owner_id"])
    op.create_table(
        "usage_metrics",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
    )
    op.create_index("ix_usage_metrics_user_id", "usage_metrics", ["user_id"])
    op.create_index("ix_usage_metrics_recorded_at", "usage_metrics", ["recorded_at"])


def downgrade() -> None:
    op.drop_table("usage_metrics")
    op.drop_table("stage_snapshots")
    op.drop_table("session_messages")
    op.drop_table("sessions")
