from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, and_, create_engine, func, or_, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings

SessionType = Literal["chat", "task", "finance", "assistant", "biz"]
SessionStatus = Literal["active", "archived"]


class Base(DeclarativeBase):
    pass


class SessionModel(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(255))
    session_type: Mapped[str] = mapped_column(String(32), default="chat")
    status: Mapped[str] = mapped_column(String(32), default="active")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SessionMessageModel(Base):
    __tablename__ = "session_messages"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(String(32), default="text")
    attachments: Mapped[dict[str, Any]] = mapped_column(JSON, default=list)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class StageSnapshotModel(Base):
    __tablename__ = "stage_snapshots"
    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(128), index=True)
    run_json: Mapped[str] = mapped_column(Text)
    last_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class CheckpointModel(Base):
    __tablename__ = "session_checkpoints"
    resume_token: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    partial_assistant_text: Mapped[str] = mapped_column(Text)
    user_message_snapshot: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StreamEventModel(Base):
    __tablename__ = "stream_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    envelope_json: Mapped[str] = mapped_column(Text, nullable=False)
    server_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass
class ChatMessage:
    role: Literal["user", "assistant", "system"]
    content: str
    message_type: str = "text"
    attachments: list[dict[str, Any]] = field(default_factory=list)
    token_usage: dict[str, Any] | None = None
    run_id: str | None = None
    id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SessionRecord:
    id: str
    owner_id: str
    title: str
    session_type: SessionType
    status: SessionStatus
    pinned: bool
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessage] = field(default_factory=list)


class SessionStore:
    def __init__(self) -> None:
        settings = get_settings()
        db_url = getattr(settings, "database_url", None) or "sqlite:///./coagent.db"
        connect_args: dict = {}
        if isinstance(db_url, str) and db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self._engine = create_engine(db_url, future=True, connect_args=connect_args)
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False, class_=Session)
        self._seq_cursor: dict[str, int] = {}

    def _db(self) -> Session:
        return self._session_factory()

    @staticmethod
    def _to_record(row: SessionModel) -> SessionRecord:
        return SessionRecord(
            id=row.id,
            owner_id=row.owner_id,
            title=row.title,
            session_type=row.session_type,  # type: ignore[arg-type]
            status=row.status,  # type: ignore[arg-type]
            pinned=row.pinned,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def create(self, owner_id: str, title: str | None, session_type: SessionType) -> SessionRecord:
        now = datetime.now(timezone.utc)
        sid = str(uuid.uuid4())
        row = SessionModel(
            id=sid,
            owner_id=owner_id,
            title=title or "新会话",
            session_type=session_type,
            status="active",
            pinned=False,
            created_at=now,
            updated_at=now,
        )
        with self._db() as db:
            db.add(row)
            db.commit()
        return self._to_record(row)

    def get(self, session_id: str) -> SessionRecord | None:
        with self._db() as db:
            row = db.get(SessionModel, session_id)
            return self._to_record(row) if row else None

    def list_for_owner(
        self, owner_id: str, limit: int = 50, offset: int = 0, q: str | None = None
    ) -> tuple[list[SessionRecord], int]:
        with self._db() as db:
            base = select(SessionModel).where(SessionModel.owner_id == owner_id)
            if q:
                needle = f"%{q}%"
                matched_session_ids = (
                    select(SessionMessageModel.session_id)
                    .where(SessionMessageModel.content.like(needle))
                    .group_by(SessionMessageModel.session_id)
                )
                base = base.where(or_(SessionModel.title.like(needle), SessionModel.id.in_(matched_session_ids)))
            total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
            rows = db.scalars(
                base.order_by(SessionModel.pinned.desc(), SessionModel.updated_at.desc()).offset(offset).limit(limit)
            ).all()
            return [self._to_record(r) for r in rows], int(total)

    def update_session(self, session_id: str, *, title: str | None = None, pinned: bool | None = None) -> SessionRecord | None:
        with self._db() as db:
            row = db.get(SessionModel, session_id)
            if not row:
                return None
            if title is not None:
                row.title = title
            if pinned is not None:
                row.pinned = pinned
            row.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(row)
            return self._to_record(row)

    def delete_session(self, session_id: str) -> bool:
        with self._db() as db:
            row = db.get(SessionModel, session_id)
            if not row:
                return False
            db.query(SessionMessageModel).filter(SessionMessageModel.session_id == session_id).delete()
            db.query(StreamEventModel).filter(StreamEventModel.session_id == session_id).delete()
            db.query(StageSnapshotModel).filter(StageSnapshotModel.session_id == session_id).delete()
            db.query(CheckpointModel).filter(CheckpointModel.session_id == session_id).delete()
            db.delete(row)
            db.commit()
            return True

    def touch(self, session_id: str) -> None:
        with self._db() as db:
            row = db.get(SessionModel, session_id)
            if row:
                row.updated_at = datetime.now(timezone.utc)
                db.commit()

    def append_message(self, session_id: str, message: ChatMessage) -> ChatMessage:
        now = message.created_at or datetime.now(timezone.utc)
        mid = message.id or str(uuid.uuid4())
        row = SessionMessageModel(
            id=mid,
            session_id=session_id,
            role=message.role,
            content=message.content,
            message_type=message.message_type,
            attachments=message.attachments or [],
            token_usage=message.token_usage,
            run_id=message.run_id,
            created_at=now,
        )
        with self._db() as db:
            db.add(row)
            s = db.get(SessionModel, session_id)
            if s:
                s.updated_at = datetime.now(timezone.utc)
            db.commit()
        message.id = mid
        return message

    def list_messages(self, session_id: str, limit: int, offset: int) -> tuple[list[ChatMessage], int]:
        with self._db() as db:
            total = db.scalar(
                select(func.count()).select_from(select(SessionMessageModel).where(SessionMessageModel.session_id == session_id).subquery())
            ) or 0
            rows = db.scalars(
                select(SessionMessageModel)
                .where(SessionMessageModel.session_id == session_id)
                .order_by(SessionMessageModel.created_at.asc())
                .offset(offset)
                .limit(limit)
            ).all()
            out = [
                ChatMessage(
                    id=r.id,
                    role=r.role,  # type: ignore[arg-type]
                    content=r.content,
                    message_type=r.message_type,
                    attachments=list(r.attachments or []),
                    token_usage=r.token_usage,
                    run_id=r.run_id,
                    created_at=r.created_at,
                )
                for r in rows
            ]
            return out, int(total)

    def list_messages_before(self, session_id: str, before_id: str | None, limit: int) -> tuple[list[ChatMessage], int, str | None]:
        with self._db() as db:
            predicate = [SessionMessageModel.session_id == session_id]
            if before_id:
                anchor = db.get(SessionMessageModel, before_id)
                if anchor:
                    predicate.append(
                        or_(
                            SessionMessageModel.created_at < anchor.created_at,
                            and_(SessionMessageModel.created_at == anchor.created_at, SessionMessageModel.id < anchor.id),
                        )
                    )
            q = (
                select(SessionMessageModel)
                .where(*predicate)
                .order_by(SessionMessageModel.created_at.desc(), SessionMessageModel.id.desc())
                .limit(limit + 1)
            )
            rows = db.scalars(q).all()
            has_more = len(rows) > limit
            rows = rows[:limit]
            rows.reverse()
            next_cursor = rows[0].id if rows and has_more else None
            total = db.scalar(
                select(func.count()).select_from(select(SessionMessageModel).where(SessionMessageModel.session_id == session_id).subquery())
            ) or 0
            out = [
                ChatMessage(
                    id=r.id,
                    role=r.role,  # type: ignore[arg-type]
                    content=r.content,
                    message_type=r.message_type,
                    attachments=list(r.attachments or []),
                    token_usage=r.token_usage,
                    run_id=r.run_id,
                    created_at=r.created_at,
                )
                for r in rows
            ]
            return out, int(total), next_cursor

    def set_stage_snapshot(self, session_id: str, run: dict[str, Any], last_event_id: str | None = None) -> None:
        now = datetime.now(timezone.utc)
        with self._db() as db:
            row = db.get(StageSnapshotModel, session_id)
            if not row:
                owner_id = ""
                sess = db.get(SessionModel, session_id)
                if sess:
                    owner_id = sess.owner_id
                row = StageSnapshotModel(
                    session_id=session_id,
                    owner_id=owner_id,
                    run_json=json.dumps(run, ensure_ascii=False),
                    last_event_id=last_event_id,
                    updated_at=now,
                )
                db.add(row)
            else:
                row.run_json = json.dumps(run, ensure_ascii=False)
                row.last_event_id = last_event_id
                row.updated_at = now
            db.commit()

    def get_stage_snapshot(self, session_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.get(StageSnapshotModel, session_id)
            if not row:
                return None
            return json.loads(row.run_json)

    def save_checkpoint(
        self,
        *,
        resume_token: str,
        session_id: str,
        partial_assistant_text: str,
        user_message_snapshot: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._db() as db:
            row = CheckpointModel(
                resume_token=resume_token,
                session_id=session_id,
                partial_assistant_text=partial_assistant_text,
                user_message_snapshot=user_message_snapshot,
                created_at=now,
                consumed_at=None,
            )
            db.merge(row)
            db.commit()

    def get_checkpoint(self, resume_token: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.get(CheckpointModel, resume_token)
            if not row:
                return None
            return {
                "resume_token": row.resume_token,
                "session_id": row.session_id,
                "partial_assistant_text": row.partial_assistant_text,
                "user_message_snapshot": row.user_message_snapshot,
                "created_at": row.created_at,
                "consumed_at": row.consumed_at,
            }

    def mark_checkpoint_consumed(self, resume_token: str) -> None:
        with self._db() as db:
            row = db.get(CheckpointModel, resume_token)
            if not row:
                return
            row.consumed_at = datetime.now(timezone.utc)
            db.commit()

    def max_stream_seq_for_run(self, run_id: str) -> int:
        with self._db() as db:
            m = db.scalar(select(func.coalesce(func.max(StreamEventModel.seq), 0)).where(StreamEventModel.run_id == run_id))
            return int(m or 0)

    def next_stream_seq(self, run_id: str) -> int:
        if run_id not in self._seq_cursor:
            self._seq_cursor[run_id] = self.max_stream_seq_for_run(run_id)
        self._seq_cursor[run_id] += 1
        return self._seq_cursor[run_id]

    def append_stream_event(self, envelope: dict[str, Any]) -> None:
        ts_raw = envelope.get("server_ts")
        if isinstance(ts_raw, str):
            try:
                server_ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except ValueError:
                server_ts = datetime.now(timezone.utc)
        elif isinstance(ts_raw, datetime):
            server_ts = ts_raw
        else:
            server_ts = datetime.now(timezone.utc)
        with self._db() as db:
            row = StreamEventModel(
                event_id=envelope["event_id"],
                session_id=envelope["session_id"],
                run_id=envelope["run_id"],
                seq=int(envelope["seq"]),
                event_type=envelope["event_type"],
                envelope_json=json.dumps(envelope, ensure_ascii=False),
                server_ts=server_ts,
            )
            db.add(row)
            db.commit()

    def get_stream_event_by_id(self, event_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.scalars(select(StreamEventModel).where(StreamEventModel.event_id == event_id)).first()
            if not row:
                return None
            return json.loads(row.envelope_json)

    def list_stream_events_after_seq(self, session_id: str, run_id: str, after_seq: int) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.scalars(
                select(StreamEventModel)
                .where(
                    StreamEventModel.session_id == session_id,
                    StreamEventModel.run_id == run_id,
                    StreamEventModel.seq > after_seq,
                )
                .order_by(StreamEventModel.seq.asc())
            ).all()
            return [json.loads(r.envelope_json) for r in rows]

    def get_last_stream_event_for_run(self, run_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.scalars(
                select(StreamEventModel)
                .where(StreamEventModel.run_id == run_id)
                .order_by(StreamEventModel.seq.desc())
                .limit(1)
            ).first()
            if not row:
                return None
            return json.loads(row.envelope_json)


session_store = SessionStore()
