from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings
from app.core.database import build_engine, should_auto_create_schema


class Base(DeclarativeBase):
    pass


class AuditEntryModel(Base):
    __tablename__ = "audit_entries"

    entry_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[str] = mapped_column(String(16), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    wal_path: Mapped[str] = mapped_column(String(512))


@dataclass(slots=True)
class AuditEntry:
    session_id: str
    run_id: str
    trace_id: str
    event_type: str
    payload: dict[str, Any]
    schema_version: str = "v1"
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    wal_path: str | None = None


class AuditStore:
    def __init__(self) -> None:
        settings = get_settings()
        self._engine = build_engine()
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False, class_=Session)
        self._wal_dir = Path(settings.audit_wal_dir).expanduser().resolve()
        self._wal_dir.mkdir(parents=True, exist_ok=True)
        if should_auto_create_schema():
            Base.metadata.create_all(self._engine)

    def _db(self) -> Session:
        return self._session_factory()

    def append(self, entry: AuditEntry) -> AuditEntry:
        wal_path = self._write_wal(entry)
        entry.wal_path = str(wal_path)
        row = AuditEntryModel(
            entry_id=entry.entry_id,
            session_id=entry.session_id,
            run_id=entry.run_id,
            trace_id=entry.trace_id,
            event_type=entry.event_type,
            payload_json=json.dumps(entry.payload, ensure_ascii=False),
            schema_version=entry.schema_version,
            created_at=entry.created_at,
            wal_path=entry.wal_path,
        )
        with self._db() as db:
            db.merge(row)
            db.commit()
        return entry

    def list_by_run(self, session_id: str, run_id: str) -> list[AuditEntry]:
        with self._db() as db:
            rows = db.scalars(
                select(AuditEntryModel)
                .where(AuditEntryModel.session_id == session_id, AuditEntryModel.run_id == run_id)
                .order_by(AuditEntryModel.created_at.asc())
            ).all()
            return [
                AuditEntry(
                    entry_id=row.entry_id,
                    session_id=row.session_id,
                    run_id=row.run_id,
                    trace_id=row.trace_id,
                    event_type=row.event_type,
                    payload=json.loads(row.payload_json),
                    schema_version=row.schema_version,
                    created_at=row.created_at,
                    wal_path=row.wal_path,
                )
                for row in rows
            ]

    def _write_wal(self, entry: AuditEntry) -> Path:
        wal_path = self._wal_dir / f"{entry.entry_id}.json"
        payload = {
            "entry_id": entry.entry_id,
            "session_id": entry.session_id,
            "run_id": entry.run_id,
            "trace_id": entry.trace_id,
            "event_type": entry.event_type,
            "payload": entry.payload,
            "schema_version": entry.schema_version,
            "created_at": entry.created_at.isoformat(),
        }
        with open(wal_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        return wal_path


audit_store = AuditStore()
