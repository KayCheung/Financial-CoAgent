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


class SessionCreate(BaseModel):
    title: str | None = None
    session_type: SessionType = "chat"


class SessionOut(BaseModel):
    id: str
    title: str
    session_type: SessionType
    status: SessionStatus
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    items: list[SessionOut]
    total: int


class ChatStreamRequest(BaseModel):
    session_id: str
    message: str


class ChatInterruptRequest(BaseModel):
    session_id: str


class ChatResumeRequest(BaseModel):
    session_id: str
    resume_token: str


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
