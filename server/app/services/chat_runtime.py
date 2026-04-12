from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.agent.orchestrator import OrchestratorState, StreamInput, agent_orchestrator
from app.services.session_store import ChatMessage, session_store
from app.services.token_budget import BudgetExceededError, TokenBudget, token_budget_guard
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
    state: OrchestratorState | None = None
    budget: TokenBudget | None = None


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
        cp = self._checkpoints.get(resume_token)
        if cp:
            return cp
        row = session_store.get_checkpoint(resume_token)
        if not row:
            return None
        return Checkpoint(
            resume_token=row["resume_token"],
            session_id=row["session_id"],
            partial_assistant_text=row["partial_assistant_text"],
            user_message_snapshot=row["user_message_snapshot"],
            created_at=row["created_at"],
        )

    def get_stage_snapshot(self, session_id: str) -> dict[str, Any] | None:
        return session_store.get_stage_snapshot(session_id)

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
        attachments: list[dict[str, Any]] | None,
        resume_token: str | None,
        last_event_id: str | None = None,
    ):
        session = session_store.get(session_id)
        if not session or session.owner_id != user_id:
            yield self._sse({"type": "error", "detail": "session_not_found"})
            return
        existing = session_store.get_stage_snapshot(session_id) or {}
        if (
            last_event_id
            and existing.get("last_event_id") == last_event_id
            and existing.get("status") in {"completed", "failed", "interrupted"}
        ):
            rid = existing.get("run_id") or str(uuid.uuid4())
            tid = existing.get("trace_id") or str(uuid.uuid4())
            status = existing.get("status") or "completed"
            fa = existing.get("final_answer") or ""
            yield ChatRuntime._sse(
                {
                    "event_id": last_event_id,
                    "event_type": "completed",
                    "session_id": session_id,
                    "thread_id": existing.get("thread_id") or session_id,
                    "run_id": rid,
                    "trace_id": tid,
                    "server_ts": ChatRuntime._now_iso(),
                    "payload": {"status": status, "final_answer": fa},
                    "type": "completed",
                    "status": status,
                    "final_answer": fa,
                }
            )
            return

        um = (user_message or "").strip()
        want_replay = bool(last_event_id and (resume_token is not None or not um))
        replay_terminal_stop = False
        if want_replay:
            anchor = session_store.get_stream_event_by_id(last_event_id)
            if anchor and anchor.get("session_id") == session_id:
                run_r = anchor.get("run_id")
                snap_run = existing.get("run_id")
                if run_r and (snap_run is None or run_r == snap_run):
                    after_seq = int(anchor.get("seq") or 0)
                    rows = session_store.list_stream_events_after_seq(session_id, run_r, after_seq)
                    for env in rows:
                        yield ChatRuntime._sse(env)
                        if env.get("event_type") in ("completed", "error"):
                            replay_terminal_stop = True
                    if not rows and not replay_terminal_stop:
                        tip = session_store.get_last_stream_event_for_run(run_r)
                        if (
                            tip
                            and tip.get("event_id") == last_event_id
                            and tip.get("event_type") in ("completed", "error")
                        ):
                            replay_terminal_stop = True
        if replay_terminal_stop:
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
            user_snapshot = um
            sent_prefix = ""

        if resume_token is None and not um:
            return

        if resume_token:
            snap_pre = session_store.get_stage_snapshot(session_id) or {}
            run_id = snap_pre.get("run_id") or str(uuid.uuid4())
            trace_id = snap_pre.get("trace_id") or str(uuid.uuid4())
        else:
            run_id = str(uuid.uuid4())
            trace_id = str(uuid.uuid4())
        thread_id = session_id
        cancel = asyncio.Event()
        async with self._lock:
            prev = self._active.get(session_id)
            if prev:
                prev.cancel.set()
            self._active[session_id] = ActiveRun(run_id=run_id, cancel=cancel, state=None, budget=None)

        if append_user:
            session_store.append_message(
                session_id,
                ChatMessage(
                    role="user",
                    content=um,
                    message_type="text+attachments" if attachments else "text",
                    attachments=attachments or [],
                    run_id=run_id,
                ),
            )
            session_store.touch(session_id)

        output_parts: list[str] = []
        history_rows, _, _ = session_store.list_messages_before(session_id, None, 200)
        history = [m for m in history_rows if m.role in ("user", "assistant")]
        input_toks = estimate_tokens(" ".join(m.content for m in history))

        try:
            budget = token_budget_guard.allocate(session_id=session_id, user_id=user_id, complexity="simple")
            _, emit_warning = token_budget_guard.consume_input(
                budget,
                " ".join(m.content for m in history) + " " + user_snapshot,
            )
            state = agent_orchestrator.prepare(
                StreamInput(
                    session_id=session_id,
                    user_message=user_snapshot,
                    history=history,
                    sent_prefix=sent_prefix,
                    user_id=user_id,
                )
            )
            async with self._lock:
                current = self._active.get(session_id)
                if current and current.run_id == run_id:
                    current.state = state
                    current.budget = budget

            yield self._event(
                event_type="budget_event",
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                trace_id=trace_id,
                payload={
                    "status": "allocated",
                    "complexity": budget.complexity,
                    "total_budget": budget.total_budget,
                    "consumed_tokens": budget.consumed,
                    "remaining_tokens": budget.remaining,
                },
            )
            if emit_warning:
                yield self._event(
                    event_type="budget_event",
                    session_id=session_id,
                    thread_id=thread_id,
                    run_id=run_id,
                    trace_id=trace_id,
                    payload={
                        "status": "warning",
                        "complexity": budget.complexity,
                        "total_budget": budget.total_budget,
                        "consumed_tokens": budget.consumed,
                        "remaining_tokens": budget.remaining,
                    },
                )

            yield self._event(
                event_type="stage_started",
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                trace_id=trace_id,
                payload={
                    "stage_key": "router",
                    "stage_label": "意图路由",
                    "status": "running",
                    "started_at": self._now_iso(),
                },
            )
            yield self._event(
                event_type="stage_completed",
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                trace_id=trace_id,
                payload={
                    "stage_key": "router",
                    "status": "completed",
                    "summary": state.route.summary if state.route else "完成路由判定",
                    "ended_at": self._now_iso(),
                },
            )
            yield self._event(
                event_type="stage_started",
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                trace_id=trace_id,
                payload={
                    "stage_key": "planner",
                    "stage_label": "任务规划",
                    "status": "running",
                    "started_at": self._now_iso(),
                },
            )
            yield self._event(
                event_type="stage_completed",
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                trace_id=trace_id,
                payload={
                    "stage_key": "planner",
                    "status": "completed",
                    "summary": state.plan.summary if state.plan else "完成上下文与工具策略规划",
                    "ended_at": self._now_iso(),
                },
            )
            yield self._event(
                event_type="stage_started",
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                trace_id=trace_id,
                payload={
                    "stage_key": "executor",
                    "stage_label": "执行回复",
                    "status": "running",
                    "started_at": self._now_iso(),
                },
            )
            try:
                progress_emitted = False
                async for piece in agent_orchestrator.stream(
                    StreamInput(
                        session_id=session_id,
                        user_message=user_snapshot,
                        history=history,
                        sent_prefix=sent_prefix,
                        user_id=user_id,
                    ),
                    cancel,
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
                        session_store.save_checkpoint(
                            resume_token=tok,
                            session_id=session_id,
                            partial_assistant_text=partial,
                            user_message_snapshot=user_snapshot,
                        )
                        yield self._event(
                            event_type="stage_failed",
                            session_id=session_id,
                            thread_id=thread_id,
                            run_id=run_id,
                            trace_id=trace_id,
                            payload={
                                "stage_key": "executor",
                                "status": "failed",
                                "error_code": "INTERRUPTED",
                                "error_message": "用户主动中断当前生成",
                                "retryable": True,
                            },
                        )
                        yield self._event(
                            event_type="checkpoint",
                            session_id=session_id,
                            thread_id=thread_id,
                            run_id=run_id,
                            trace_id=trace_id,
                            payload={
                                "resume_token": tok,
                                "partial_length": len(partial),
                                "reason": "interrupted",
                            },
                        )
                        yield self._event(
                            event_type="completed",
                            session_id=session_id,
                            thread_id=thread_id,
                            run_id=run_id,
                            trace_id=trace_id,
                            payload={"status": "interrupted", "final_answer": partial},
                        )
                        return
                    output_parts.append(piece)
                    if not progress_emitted:
                        progress_emitted = True
                        yield self._event(
                            event_type="stage_progress",
                            session_id=session_id,
                            thread_id=thread_id,
                            run_id=run_id,
                            trace_id=trace_id,
                            payload={
                                "stage_key": "executor",
                                "summary": "正在流式生成答案",
                                "percent": 60,
                            },
                        )
                    try:
                        _, emit_warning = token_budget_guard.consume_output(budget, piece)
                    except BudgetExceededError as exc:
                        partial = sent_prefix + "".join(output_parts)
                        yield self._event(
                            event_type="stage_failed",
                            session_id=session_id,
                            thread_id=thread_id,
                            run_id=run_id,
                            trace_id=trace_id,
                            payload={
                                "stage_key": "executor",
                                "status": "failed",
                                "error_code": "TOKEN_BUDGET_EXCEEDED",
                                "error_message": str(exc),
                                "retryable": False,
                            },
                        )
                        yield self._event(
                            event_type="budget_event",
                            session_id=session_id,
                            thread_id=thread_id,
                            run_id=run_id,
                            trace_id=trace_id,
                            payload={
                                "status": "blocked",
                                "complexity": budget.complexity,
                                "total_budget": budget.total_budget,
                                "consumed_tokens": budget.consumed,
                                "remaining_tokens": budget.remaining,
                            },
                        )
                        yield self._event(
                            event_type="completed",
                            session_id=session_id,
                            thread_id=thread_id,
                            run_id=run_id,
                            trace_id=trace_id,
                            payload={"status": "failed", "final_answer": partial},
                        )
                        return
                    if emit_warning:
                        yield self._event(
                            event_type="budget_event",
                            session_id=session_id,
                            thread_id=thread_id,
                            run_id=run_id,
                            trace_id=trace_id,
                            payload={
                                "status": "warning",
                                "complexity": budget.complexity,
                                "total_budget": budget.total_budget,
                                "consumed_tokens": budget.consumed,
                                "remaining_tokens": budget.remaining,
                            },
                        )
                    yield self._event(
                        event_type="token",
                        session_id=session_id,
                        thread_id=thread_id,
                        run_id=run_id,
                        trace_id=trace_id,
                        payload={"text": piece},
                    )
            except Exception as sdk_exc:
                yield self._event(
                    event_type="error",
                    session_id=session_id,
                    thread_id=thread_id,
                    run_id=run_id,
                    trace_id=trace_id,
                    payload={
                        "status": "failed",
                        "error_code": "LLM_UNAVAILABLE",
                        "error_message": f"llm_unavailable: {sdk_exc}",
                        "recoverable": True,
                    },
                )
                async for piece in self._stream_stub(user_snapshot, sent_prefix):
                    if cancel.is_set():
                        break
                    output_parts.append(piece)
                    yield self._event(
                        event_type="token",
                        session_id=session_id,
                        thread_id=thread_id,
                        run_id=run_id,
                        trace_id=trace_id,
                        payload={"text": piece},
                    )

            final = sent_prefix + "".join(output_parts)
            out_toks = estimate_tokens(final)
            session_store.append_message(
                session_id,
                ChatMessage(
                    role="assistant",
                    content=final,
                    message_type="text",
                    token_usage={"input_tokens": input_toks, "output_tokens": out_toks},
                    run_id=run_id,
                ),
            )
            session_store.touch(session_id)

            cost = stub_cost_usd(input_toks, out_toks)
            usage_tracker.record(
                user_id=user_id,
                session_id=session_id,
                input_tokens=input_toks,
                output_tokens=out_toks,
                cost_usd=cost,
                model="langchain-chat",
            )
            yield self._event(
                event_type="stage_completed",
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                trace_id=trace_id,
                payload={
                    "stage_key": "executor",
                    "status": "completed",
                    "summary": "回复生成完成",
                    "ended_at": self._now_iso(),
                },
            )
            yield self._event(
                event_type="cost_event",
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                trace_id=trace_id,
                payload={
                    "input_tokens": input_toks,
                    "output_tokens": out_toks,
                    "total_tokens": input_toks + out_toks,
                    "total_cost": cost,
                    "currency": "USD",
                    "cost_usd": cost,
                },
            )
            yield self._event(
                event_type="budget_event",
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                trace_id=trace_id,
                payload={
                    "status": "completed",
                    "complexity": budget.complexity,
                    "total_budget": budget.total_budget,
                    "consumed_tokens": budget.consumed,
                    "remaining_tokens": budget.remaining,
                },
            )
            yield self._event(
                event_type="completed",
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                trace_id=trace_id,
                payload={"status": "completed", "final_answer": final},
            )
            if resume_token:
                session_store.mark_checkpoint_consumed(resume_token)
        except BudgetExceededError as exc:
            yield self._event(
                event_type="error",
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                trace_id=trace_id,
                payload={
                    "status": "failed",
                    "error_code": "TOKEN_BUDGET_EXCEEDED",
                    "error_message": str(exc),
                    "recoverable": False,
                },
            )
            yield self._event(
                event_type="completed",
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                trace_id=trace_id,
                payload={"status": "failed"},
            )
        except Exception as exc:
            yield self._event(
                event_type="error",
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                trace_id=trace_id,
                payload={
                    "status": "failed",
                    "error_code": "GRAPH_RUNTIME_ERROR",
                    "error_message": str(exc),
                    "recoverable": True,
                },
            )
            yield self._event(
                event_type="completed",
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                trace_id=trace_id,
                payload={"status": "failed"},
            )
        finally:
            async with self._lock:
                cur = self._active.get(session_id)
                if cur and cur.run_id == run_id:
                    self._active.pop(session_id, None)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _event(
        self,
        *,
        event_type: str,
        session_id: str,
        thread_id: str,
        run_id: str,
        trace_id: str,
        payload: dict[str, Any],
    ) -> str:
        seq = session_store.next_stream_seq(run_id)
        event = {
            "event_id": f"evt_{uuid.uuid4().hex}",
            "seq": seq,
            "event_type": event_type,
            "session_id": session_id,
            "thread_id": thread_id,
            "run_id": run_id,
            "trace_id": trace_id,
            "server_ts": ChatRuntime._now_iso(),
            "payload": payload,
            # Backward-compatible fields for old renderer parser
            "type": event_type,
            **payload,
        }
        session_store.append_stream_event(event)
        self._update_stage_snapshot(event)
        return ChatRuntime._sse(event)

    def _update_stage_snapshot(self, event: dict[str, Any]) -> None:
        session_id = event.get("session_id")
        if not session_id:
            return

        payload = event.get("payload") or {}
        event_type = event.get("event_type")
        run = session_store.get_stage_snapshot(session_id)
        if not run:
            run = {
                "session_id": session_id,
                "thread_id": event.get("thread_id") or session_id,
                "run_id": event.get("run_id"),
                "status": "running",
                "trace_id": event.get("trace_id"),
                "stages": [],
                "last_event_id": None,
                "final_answer": "",
                "updated_at": None,
            }
            session_store.set_stage_snapshot(session_id, run, event.get("event_id"))

        run["run_id"] = event.get("run_id") or run.get("run_id")
        run["trace_id"] = event.get("trace_id") or run.get("trace_id")
        run["last_event_id"] = event.get("event_id")
        run["updated_at"] = event.get("server_ts")

        def upsert_stage(stage_patch: dict[str, Any]) -> None:
            stage_key = stage_patch.get("stage_key")
            if not stage_key:
                return
            stages = run["stages"]
            idx = next((i for i, s in enumerate(stages) if s.get("stage_key") == stage_key), -1)
            if idx < 0:
                stages.append(
                    {
                        "stage_key": stage_key,
                        "stage_label": stage_patch.get("stage_label") or stage_key,
                        "status": stage_patch.get("status") or "pending",
                        "started_at": stage_patch.get("started_at"),
                        "ended_at": stage_patch.get("ended_at"),
                        "duration_ms": stage_patch.get("duration_ms"),
                        "tool_name": stage_patch.get("tool_name"),
                        "summary": stage_patch.get("summary") or "",
                        "error": stage_patch.get("error_message") or stage_patch.get("error"),
                        "error_code": stage_patch.get("error_code"),
                        "retryable": stage_patch.get("retryable"),
                        "percent": stage_patch.get("percent"),
                        "approval_payload": stage_patch.get("approval_payload"),
                    }
                )
            else:
                cur = stages[idx]
                cur.update({k: v for k, v in stage_patch.items() if v is not None})
                if stage_patch.get("error_message") or stage_patch.get("error"):
                    cur["error"] = stage_patch.get("error_message") or stage_patch.get("error")

        if event_type == "stage_started":
            upsert_stage(
                {
                    "stage_key": payload.get("stage_key"),
                    "stage_label": payload.get("stage_label"),
                    "status": "running",
                    "started_at": payload.get("started_at") or event.get("server_ts"),
                }
            )
        elif event_type == "stage_progress":
            upsert_stage(
                {
                    "stage_key": payload.get("stage_key"),
                    "status": "running",
                    "summary": payload.get("summary"),
                    "percent": payload.get("percent"),
                }
            )
        elif event_type == "stage_waiting_human":
            upsert_stage(
                {
                    "stage_key": payload.get("stage_key"),
                    "stage_label": payload.get("stage_label"),
                    "status": "waiting_human",
                    "approval_payload": payload.get("approval_payload"),
                }
            )
            run["status"] = "waiting_human"
        elif event_type == "stage_completed":
            upsert_stage(
                {
                    "stage_key": payload.get("stage_key"),
                    "status": "completed",
                    "ended_at": payload.get("ended_at") or event.get("server_ts"),
                    "duration_ms": payload.get("duration_ms"),
                    "tool_name": payload.get("tool_name"),
                    "summary": payload.get("summary"),
                }
            )
        elif event_type == "stage_failed":
            upsert_stage(
                {
                    "stage_key": payload.get("stage_key"),
                    "status": "failed",
                    "summary": payload.get("summary"),
                    "error_message": payload.get("error_message"),
                    "error_code": payload.get("error_code"),
                    "retryable": payload.get("retryable"),
                    "error": payload.get("error"),
                }
            )
            run["status"] = "failed"
        elif event_type == "completed":
            run["status"] = payload.get("status") or "completed"
            run["final_answer"] = payload.get("final_answer") or ""
        elif event_type == "error":
            run["status"] = "failed"
        session_store.set_stage_snapshot(session_id, run, event.get("event_id"))

    @staticmethod
    def _sse(payload: dict[str, Any]) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


chat_runtime = ChatRuntime()
