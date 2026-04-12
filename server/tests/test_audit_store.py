from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.audit_store import audit_store


def _auth():
    return {"Authorization": "Bearer dev-local-token"}


def test_stream_writes_audit_entries_and_local_wal():
    client = TestClient(app)
    session = client.post("/api/v1/sessions", headers=_auth(), json={"title": "audit-smoke", "session_type": "chat"}).json()
    sid = session["id"]

    response = client.post(
        "/api/v1/chat/stream",
        headers=_auth(),
        json={"session_id": sid, "message": "hello audit"},
    )
    assert response.status_code == 200

    stages = client.get(f"/api/v1/sessions/{sid}/stages", headers=_auth()).json()["run"]
    run_id = stages["run_id"]
    entries = audit_store.list_by_run(sid, run_id)

    assert entries
    assert any(entry.event_type == "stage_started" for entry in entries)
    assert any(entry.event_type == "completed" for entry in entries)
    assert all(entry.wal_path for entry in entries)
    assert all(Path(entry.wal_path).exists() for entry in entries if entry.wal_path)
