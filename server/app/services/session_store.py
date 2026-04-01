from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

SessionType = Literal["chat", "task", "finance", "assistant", "biz"]
SessionStatus = Literal["active", "archived"]


@dataclass
class ChatMessage:
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SessionRecord:
    id: str
    owner_id: str
    title: str
    session_type: SessionType
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessage] = field(default_factory=list)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}

    def create(
        self,
        owner_id: str,
        title: str | None,
        session_type: SessionType,
    ) -> SessionRecord:
        now = datetime.now(timezone.utc)
        sid = str(uuid.uuid4())
        rec = SessionRecord(
            id=sid,
            owner_id=owner_id,
            title=title or "新会话",
            session_type=session_type,
            status="active",
            created_at=now,
            updated_at=now,
            messages=[],
        )
        self._sessions[sid] = rec
        return rec

    def get(self, session_id: str) -> SessionRecord | None:
        return self._sessions.get(session_id)

    def list_for_owner(self, owner_id: str, limit: int = 50, offset: int = 0) -> tuple[list[SessionRecord], int]:
        rows = [s for s in self._sessions.values() if s.owner_id == owner_id]
        rows.sort(key=lambda s: s.updated_at, reverse=True)
        total = len(rows)
        return rows[offset : offset + limit], total

    def touch(self, session_id: str) -> None:
        rec = self._sessions.get(session_id)
        if rec:
            rec.updated_at = datetime.now(timezone.utc)

    def append_message(self, session_id: str, message: ChatMessage) -> None:
        rec = self._sessions.get(session_id)
        if not rec:
            return
        rec.messages.append(message)
        rec.updated_at = datetime.now(timezone.utc)


session_store = SessionStore()
