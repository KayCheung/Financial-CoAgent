from fastapi.testclient import TestClient

from app.main import app


def _auth():
    return {"Authorization": "Bearer dev-local-token"}


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
