from fastapi.testclient import TestClient

from app.main import app


def test_dev_login_returns_context_token_and_can_access_api():
    client = TestClient(app)

    login = client.post("/api/v1/auth/login", json={"grant_type": "client_credentials", "client_id": "desktop"})
    assert login.status_code == 200
    payload = login.json()
    assert payload["access_token"].startswith("devctx.")
    assert payload["tenant_id"]
    assert payload["role"]

    token = payload["access_token"]
    session = client.post(
        "/api/v1/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "auth-context", "session_type": "chat"},
    )
    assert session.status_code == 200
