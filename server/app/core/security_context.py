import base64
import json
from dataclasses import dataclass

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class TokenContext:
    raw_token: str
    user_id: str
    user_name: str
    tenant_id: str
    role: str


def build_dev_access_token(*, user_id: str, user_name: str, tenant_id: str, role: str) -> str:
    payload = {
        "user_id": user_id,
        "user_name": user_name,
        "tenant_id": tenant_id,
        "role": role,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    return f"devctx.{encoded}"


def _decode_dev_context(token: str) -> TokenContext | None:
    if not token.startswith("devctx."):
        return None
    encoded = token.split(".", 1)[1]
    try:
        payload_raw = base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
        payload = json.loads(payload_raw)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=401, detail=f"Invalid dev token: {exc}") from exc

    required = ("user_id", "user_name", "tenant_id", "role")
    if any(not payload.get(key) for key in required):
        raise HTTPException(status_code=401, detail="Invalid dev token payload")

    return TokenContext(
        raw_token=token,
        user_id=str(payload["user_id"]),
        user_name=str(payload["user_name"]),
        tenant_id=str(payload["tenant_id"]),
        role=str(payload["role"]),
    )


def verify_bearer_context(
    creds: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> TokenContext:
    settings = get_settings()
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing or invalid authorization")
    token = creds.credentials
    if token == settings.dev_bearer_token:
        return TokenContext(
            raw_token=token,
            user_id=settings.dev_user_id,
            user_name=settings.dev_user_name,
            tenant_id=settings.dev_tenant_id,
            role=settings.dev_role,
        )
    context = _decode_dev_context(token)
    if context:
        return context
    raise HTTPException(status_code=401, detail="Invalid token")
