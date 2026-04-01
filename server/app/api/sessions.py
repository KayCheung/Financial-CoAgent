from fastapi import APIRouter, Depends, Query

from app.api.deps import Principal, get_principal
from app.models.schemas import SessionCreate, SessionListResponse, SessionOut
from app.services.session_store import session_store

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _to_out(rec) -> SessionOut:
    return SessionOut(
        id=rec.id,
        title=rec.title,
        session_type=rec.session_type,
        status=rec.status,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


@router.post("", response_model=SessionOut)
def create_session(payload: SessionCreate, principal: Principal = Depends(get_principal)) -> SessionOut:
    rec = session_store.create(
        owner_id=principal.user_id,
        title=payload.title,
        session_type=payload.session_type,
    )
    return _to_out(rec)


@router.get("", response_model=SessionListResponse)
def list_sessions(
    principal: Principal = Depends(get_principal),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> SessionListResponse:
    rows, total = session_store.list_for_owner(principal.user_id, limit=limit, offset=offset)
    return SessionListResponse(items=[_to_out(r) for r in rows], total=total)
