from fastapi import APIRouter

from app.core.config import get_settings
from app.models.schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def dev_login(_payload: LoginRequest) -> LoginResponse:
    settings = get_settings()
    return LoginResponse(access_token=settings.dev_bearer_token, expires_in=3600)
