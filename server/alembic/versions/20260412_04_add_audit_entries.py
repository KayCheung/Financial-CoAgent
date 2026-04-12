"""add audit entries table

Revision ID: 20260412_04
Revises: 20260401_03
Create Date: 2026-04-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20260412_04"
down_revision = "20260401_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_entries",
        sa.Column("entry_id", sa.String(length=64), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("wal_path", sa.String(length=512), nullable=False),
    )
    op.create_index("ix_audit_entries_session_id", "audit_entries", ["session_id"])
    op.create_index("ix_audit_entries_run_id", "audit_entries", ["run_id"])
    op.create_index("ix_audit_entries_trace_id", "audit_entries", ["trace_id"])
    op.create_index("ix_audit_entries_event_type", "audit_entries", ["event_type"])
    op.create_index("ix_audit_entries_created_at", "audit_entries", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_entries_created_at", table_name="audit_entries")
    op.drop_index("ix_audit_entries_event_type", table_name="audit_entries")
    op.drop_index("ix_audit_entries_trace_id", table_name="audit_entries")
    op.drop_index("ix_audit_entries_run_id", table_name="audit_entries")
    op.drop_index("ix_audit_entries_session_id", table_name="audit_entries")
    op.drop_table("audit_entries")
