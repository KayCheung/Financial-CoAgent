from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.agent.orchestrator import StreamInput, agent_orchestrator
from app.services.session_store import ChatMessage, session_store
from app.services.usage_tracker import estimate_tokens, stub_cost_usd, usage_tracker


@dataclass
class Checkpoint:
    resume_token: str
    session_id: str
    partial_assistant_text: str
    user_message_snapshot: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ActiveRun:
    run_id: str
    cancel: asyncio.Event


class ChatRuntime:
    def __init__(self) -> None:
        self._checkpoints: dict[str, Checkpoint] = {}
        self._active: dict[str, ActiveRun] = {}
        self._lock = asyncio.Lock()

    async def interrupt(self, session_id: str) -> bool:
        async with self._lock:
            run = self._active.get(session_id)
            if not run:
                return False
            run.cancel.set()
            return True

    def get_checkpoint(self, resume_token: str) -> Checkpoint | None:
        return self._checkpoints.get(resume_token)

    @staticmethod
    def _full_stub_reply(user_text: str) -> str:
        return f"（S1 占位回复）已收到：{user_text}"

    async def _stream_stub(self, user_snapshot: str, sent_prefix: str):
        full = self._full_stub_reply(user_snapshot)
        if not full.startswith(sent_prefix):
            sent_prefix = ""
        rest = full[len(sent_prefix) :]
        chunk_size = 8
        for i in range(0, len(rest), chunk_size):
            yield rest[i : i + chunk_size]
            await asyncio.sleep(0.02)

    async def stream_chat(
        self,
        *,
        user_id: str,
        session_id: str,
        user_message: str,
        resume_token: str | None,
    ):
        session = session_store.get(session_id)
        if not session or session.owner_id != user_id:
            yield self._sse({"type": "error", "detail": "session_not_found"})
            return

        append_user = resume_token is None
        if resume_token:
            cp = self.get_checkpoint(resume_token)
            if not cp or cp.session_id != session_id:
                yield self._sse({"type": "error", "detail": "invalid_resume_token"})
                return
            user_snapshot = cp.user_message_snapshot
            sent_prefix = cp.partial_assistant_text
        else:
            user_snapshot = user_message
            sent_prefix = ""

        run_id = str(uuid.uuid4())
        cancel = asyncio.Event()
        async with self._lock:
            prev = self._active.get(session_id)
            if prev:
                prev.cancel.set()
            self._active[session_id] = ActiveRun(run_id=run_id, cancel=cancel)

        if append_user:
            session_store.append_message(session_id, ChatMessage(role="user", content=user_message))
            session_store.touch(session_id)

        output_parts: list[str] = []
        history = [m for m in session.messages if m.role in ("user", "assistant")]
        input_toks = estimate_tokens(" ".join(m.content for m in history))

        try:
            yield self._sse({"type": "run_start", "run_id": run_id, "session_id": session_id})
            try:
                async for piece in agent_orchestrator.stream(
                    StreamInput(
                        session_id=session_id,
                        user_message=user_snapshot,
                        history=history,
                        sent_prefix=sent_prefix,
                    ),
                    cancel=cancel,
                ):
                    if cancel.is_set():
                        partial = sent_prefix + "".join(output_parts)
                        tok = str(uuid.uuid4())
                        self._checkpoints[tok] = Checkpoint(
                            resume_token=tok,
                            session_id=session_id,
                            partial_assistant_text=partial,
                            user_message_snapshot=user_snapshot,
                        )
                        yield self._sse(
                            {
                                "type": "checkpoint",
                                "resume_token": tok,
                                "partial_length": len(partial),
                                "reason": "interrupted",
                            }
                        )
                        yield self._sse({"type": "done", "status": "interrupted"})
                        return
                    output_parts.append(piece)
                    yield self._sse({"type": "token", "text": piece})
            except Exception as sdk_exc:
                yield self._sse({"type": "error", "detail": f"llm_unavailable: {sdk_exc}"})
                async for piece in self._stream_stub(user_snapshot, sent_prefix):
                    if cancel.is_set():
                        break
                    output_parts.append(piece)
                    yield self._sse({"type": "token", "text": piece})

            final = sent_prefix + "".join(output_parts)
            session_store.append_message(session_id, ChatMessage(role="assistant", content=final))
            session_store.touch(session_id)

            out_toks = estimate_tokens(final)
            cost = stub_cost_usd(input_toks, out_toks)
            usage_tracker.record(
                user_id=user_id,
                session_id=session_id,
                input_tokens=input_toks,
                output_tokens=out_toks,
                cost_usd=cost,
                model="claude-agent-sdk",
            )
            yield self._sse(
                {
                    "type": "cost_event",
                    "input_tokens": input_toks,
                    "output_tokens": out_toks,
                    "cost_usd": cost,
                }
            )
            yield self._sse({"type": "done", "status": "completed"})
        except Exception as exc:
            yield self._sse({"type": "error", "detail": str(exc)})
            yield self._sse({"type": "done", "status": "failed"})
        finally:
            async with self._lock:
                cur = self._active.get(session_id)
                if cur and cur.run_id == run_id:
                    self._active.pop(session_id, None)

    @staticmethod
    def _sse(payload: dict[str, Any]) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


chat_runtime = ChatRuntime()
