from fastapi import APIRouter

from app.core.config import get_settings
from app.core.security_context import build_dev_access_token
from app.models.schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def dev_login(_payload: LoginRequest) -> LoginResponse:
    settings = get_settings()
    access_token = build_dev_access_token(
        user_id=settings.dev_user_id,
        user_name=settings.dev_user_name,
        tenant_id=settings.dev_tenant_id,
        role=settings.dev_role,
    )
    return LoginResponse(
        access_token=access_token,
        expires_in=3600,
        user_id=settings.dev_user_id,
        user_name=settings.dev_user_name,
        tenant_id=settings.dev_tenant_id,
        role=settings.dev_role,
    )
