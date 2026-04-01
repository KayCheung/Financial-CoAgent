from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

_bearer = HTTPBearer(auto_error=False)


def verify_bearer(
    creds: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> str:
    """Validate Bearer token; S1 uses static dev token from settings."""
    settings = get_settings()
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing or invalid authorization")
    if creds.credentials != settings.dev_bearer_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    return creds.credentials
