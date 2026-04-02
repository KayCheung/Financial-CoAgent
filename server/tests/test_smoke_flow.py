import json
import threading
import time
import asyncio
from collections.abc import Iterator
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agent.orchestrator import agent_orchestrator
from app.main import app


def _auth():
    return {"Authorization": "Bearer dev-local-token"}


def _parse_sse(body: str) -> list[dict]:
    events = []
    for block in (body or "").split("\n\n"):
        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                raw = line[5:].strip()
                if raw:
                    try:
                        events.append(json.loads(raw))
                    except json.JSONDecodeError:
                        pass
    return events


def _iter_sse_lines(response) -> Iterator[str]:
    for line in response.iter_lines():
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        yield line


def test_smoke_chat_interrupt_resume_switch_replay():
    client = TestClient(app)
    s1 = client.post("/api/v1/sessions", headers=_auth(), json={"title": "smoke-1", "session_type": "chat"}).json()
    s2 = client.post("/api/v1/sessions", headers=_auth(), json={"title": "smoke-2", "session_type": "chat"}).json()
    sid = s1["id"]
    stream_resp = client.post(
        "/api/v1/chat/stream",
        headers=_auth(),
        json={"session_id": sid, "message": "hello smoke"},
    )
    assert stream_resp.status_code == 200
    interrupt_resp = client.post("/api/v1/chat/interrupt", headers=_auth(), json={"session_id": sid})
    assert interrupt_resp.status_code == 200
    assert "ok" in interrupt_resp.json()
    # replay history
    replay_resp = client.get(f"/api/v1/sessions/{sid}/messages?limit=20", headers=_auth())
    assert replay_resp.status_code == 200
    assert replay_resp.json()["total"] >= 1
    # switch session then replay
    replay_resp_2 = client.get(f"/api/v1/sessions/{s2['id']}/messages?limit=20", headers=_auth())
    assert replay_resp_2.status_code == 200


def test_stream_replay_tail_no_duplicate_messages():
    client = TestClient(app)
    s = client.post("/api/v1/sessions", headers=_auth(), json={"title": "replay-tail", "session_type": "chat"}).json()
    sid = s["id"]
    r1 = client.post(
        "/api/v1/chat/stream",
        headers=_auth(),
        json={"session_id": sid, "message": "replay hello"},
    )
    assert r1.status_code == 200
    ev1 = _parse_sse(r1.text)
    token_events = [e for e in ev1 if e.get("event_type") == "token"]
    assert token_events, "expected token stream"
    mid = token_events[len(token_events) // 2]["event_id"]
    assert mid

    msgs_before = client.get(f"/api/v1/sessions/{sid}/messages?limit=50", headers=_auth()).json()["total"]

    r2 = client.post(
        "/api/v1/chat/stream",
        headers=_auth(),
        json={"session_id": sid, "message": "", "last_event_id": mid},
    )
    assert r2.status_code == 200
    ev2 = _parse_sse(r2.text)
    assert ev2
    assert ev2[-1].get("event_type") == "completed"

    msgs_after = client.get(f"/api/v1/sessions/{sid}/messages?limit=50", headers=_auth()).json()["total"]
    assert msgs_after == msgs_before


def test_resume_completes_and_persists_assistant():
    client = TestClient(app)
    s = client.post("/api/v1/sessions", headers=_auth(), json={"title": "resume-smoke", "session_type": "chat"}).json()
    sid = s["id"]

    collected: list[str] = []

    async def _slow_stream(_stream_input, cancel):
        parts = ["alpha ", "beta ", "gamma ", "done"]
        for p in parts:
            yield p
            await asyncio.sleep(0.05)

    def run_stream():
        with patch.object(agent_orchestrator, "stream", _slow_stream):
            with client.stream(
                "POST",
                "/api/v1/chat/stream",
                headers={**_auth(), "Accept": "text/event-stream"},
                json={"session_id": sid, "message": "resume smoke please"},
            ) as r:
                assert r.status_code == 200
                for line in _iter_sse_lines(r):
                    collected.append(line)

    th = threading.Thread(target=run_stream)
    th.start()
    time.sleep(0.08)
    client.post("/api/v1/chat/interrupt", headers=_auth(), json={"session_id": sid})
    th.join(timeout=30)
    assert not th.is_alive()

    body = "\n".join(collected)
    events = _parse_sse(body)
    resume_token = None
    for ev in events:
        if ev.get("event_type") == "checkpoint":
            resume_token = (ev.get("payload") or {}).get("resume_token")
            break
    assert resume_token, f"expected checkpoint in stream, got {events[-3:]}"

    msgs_mid = client.get(f"/api/v1/sessions/{sid}/messages?limit=50", headers=_auth()).json()["total"]

    r_resume = client.post(
        "/api/v1/chat/resume",
        headers=_auth(),
        json={"session_id": sid, "resume_token": resume_token},
    )
    assert r_resume.status_code == 200
    ev_resume = _parse_sse(r_resume.text)
    assert ev_resume
    assert any(e.get("event_type") == "completed" for e in ev_resume)

    msgs_final = client.get(f"/api/v1/sessions/{sid}/messages?limit=50", headers=_auth()).json()["total"]
    assert msgs_final >= msgs_mid + 1
