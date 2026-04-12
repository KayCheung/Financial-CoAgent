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


def test_invoice_ocr_stage_contains_structured_fields():
    client = TestClient(app)
    session = client.post("/api/v1/sessions", headers=_auth(), json={"title": "invoice-ocr-structured", "session_type": "chat"}).json()
    upload = client.post(
        "/api/v1/files/upload",
        headers=_auth(),
        files={"file": ("invoice-structured.txt", io.BytesIO("发票号码INV-9001 金额88.50元".encode("utf-8")), "text/plain")},
    )
    assert upload.status_code == 200

    response = client.post(
        "/api/v1/chat/stream",
        headers=_auth(),
        json={"session_id": session["id"], "message": "请识别发票并提取字段", "attachments": [upload.json()]},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)

    ocr_event = next(
        e for e in events if e.get("event_type") == "stage_completed" and e.get("payload", {}).get("stage_key") == "ocr"
    )
    ocr_results = ocr_event.get("payload", {}).get("ocr_results", [])
    assert ocr_results
    parsed_fields = ocr_results[0]["parsed_fields"]
    assert parsed_fields["invoice_number"] == "INV-9001"
    assert parsed_fields["amount"] == "88.50"
    assert parsed_fields["currency"] == "CNY"
    assert ocr_results[0]["status"] == "ok"
    assert ocr_results[0]["doc_uri"].startswith("/uploads/")
    conf = ocr_results[0]["confidence"]
    assert conf["invoice_number"] >= 0.8
    assert conf["amount"] >= 0.8
