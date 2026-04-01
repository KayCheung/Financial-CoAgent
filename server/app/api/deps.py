from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends

from app.core.config import get_settings
from app.core.security import verify_bearer


@dataclass
class Principal:
    user_id: str
    name: str


def get_principal(_token: str = Depends(verify_bearer)) -> Principal:
    settings = get_settings()
    return Principal(user_id=settings.dev_user_id, name=settings.dev_user_name)
