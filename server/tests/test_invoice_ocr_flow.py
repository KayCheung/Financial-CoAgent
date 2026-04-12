import io
import json

from fastapi.testclient import TestClient

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
                    events.append(json.loads(raw))
    return events


def test_invoice_route_runs_ocr_stage_and_injects_result_into_reply():
    client = TestClient(app)
    session = client.post("/api/v1/sessions", headers=_auth(), json={"title": "invoice-ocr", "session_type": "chat"}).json()
    upload = client.post(
        "/api/v1/files/upload",
        headers=_auth(),
        files={"file": ("invoice.txt", io.BytesIO("发票号码12345 金额88元".encode("utf-8")), "text/plain")},
    )
    assert upload.status_code == 200
    attachment = upload.json()

    response = client.post(
        "/api/v1/chat/stream",
        headers=_auth(),
        json={"session_id": session["id"], "message": "请识别这张发票", "attachments": [attachment]},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)

    assert any(
        e.get("event_type") == "stage_completed" and e.get("payload", {}).get("stage_key") == "ocr"
        for e in events
    )
    completed = next(e for e in events if e.get("event_type") == "completed")
    final_answer = completed.get("payload", {}).get("final_answer", "")
    assert "invoice.txt" in final_answer
    assert "发票号码12345" in final_answer
