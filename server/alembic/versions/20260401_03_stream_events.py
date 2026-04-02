"""stream event log for SSE replay

Revision ID: 20260401_03
Revises: 20260401_02
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa


revision = "20260401_03"
down_revision = "20260401_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stream_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("envelope_json", sa.Text(), nullable=False),
        sa.Column("server_ts", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_stream_events_event_id"),
        sa.UniqueConstraint("run_id", "seq", name="uq_stream_events_run_seq"),
    )
    op.create_index("ix_stream_events_session_id", "stream_events", ["session_id"])
    op.create_index("ix_stream_events_run_id", "stream_events", ["run_id"])
    op.create_index("ix_stream_events_session_run_seq", "stream_events", ["session_id", "run_id", "seq"])


def downgrade() -> None:
    op.drop_index("ix_stream_events_session_run_seq", table_name="stream_events")
    op.drop_index("ix_stream_events_run_id", table_name="stream_events")
    op.drop_index("ix_stream_events_session_id", table_name="stream_events")
    op.drop_table("stream_events")
