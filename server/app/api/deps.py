from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends

from app.core.security_context import TokenContext, verify_bearer_context


@dataclass
class Principal:
    user_id: str
    name: str
    tenant_id: str
    role: str
    raw_token: str


def get_principal(token_context: TokenContext = Depends(verify_bearer_context)) -> Principal:
    return Principal(
        user_id=token_context.user_id,
        name=token_context.user_name,
        tenant_id=token_context.tenant_id,
        role=token_context.role,
        raw_token=token_context.raw_token,
    )
