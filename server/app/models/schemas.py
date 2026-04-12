from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SessionType = Literal["chat", "task", "finance", "assistant", "biz"]
SessionStatus = Literal["active", "archived"]


class LoginRequest(BaseModel):
    grant_type: str | None = Field(default="client_credentials", description="S1 stub; OIDC later")
    client_id: str = "desktop"


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user_id: str | None = None
    user_name: str | None = None
    tenant_id: str | None = None
    role: str | None = None


class SessionCreate(BaseModel):
    title: str | None = None
    session_type: SessionType = "chat"


class SessionOut(BaseModel):
    id: str
    title: str
    session_type: SessionType
    status: SessionStatus
    pinned: bool = False
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    items: list[SessionOut]
    total: int


class SessionMessageOut(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    message_type: str = "text"
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    token_usage: dict[str, Any] | None = None
    run_id: str | None = None
    id: str | None = None
    created_at: datetime


class SessionMessageListResponse(BaseModel):
    items: list[SessionMessageOut]
    total: int
    next_cursor: str | None = None
    has_more: bool = False


class ChatStreamRequest(BaseModel):
    session_id: str
    message: str = ""
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    last_event_id: str | None = None


class ChatInterruptRequest(BaseModel):
    session_id: str


class ChatResumeRequest(BaseModel):
    session_id: str
    resume_token: str
    last_event_id: str | None = None


class SessionUpdateRequest(BaseModel):
    title: str | None = None
    pinned: bool | None = None


class AttachmentOut(BaseModel):
    attachment_id: str
    file_name: str
    mime_type: str
    size_bytes: int
    file_url: str


class UsageSummaryItem(BaseModel):
    user_id: str
    session_id: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    recorded_at: datetime
    model: str = "stub-stream"


class UsageSummaryResponse(BaseModel):
    items: list[UsageSummaryItem]
    totals: dict[str, Any]


class RunStageSnapshot(BaseModel):
    stage_key: str
    stage_label: str
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    tool_name: str | None = None
    summary: str = ""
    error: str | None = None
    error_code: str | None = None
    retryable: bool | None = None
    percent: int | None = None
    approval_payload: dict[str, Any] | None = None


class RunSnapshot(BaseModel):
    session_id: str
    thread_id: str
    run_id: str | None = None
    status: str = "running"
    trace_id: str | None = None
    stages: list[RunStageSnapshot] = Field(default_factory=list)
    last_event_id: str | None = None
    final_answer: str = ""
    updated_at: datetime | None = None
