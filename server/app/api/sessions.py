from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import Principal, get_principal
from app.models.schemas import (
    SessionCreate,
    SessionListResponse,
    SessionMessageListResponse,
    SessionMessageOut,
    SessionOut,
    SessionUpdateRequest,
)
from app.services.session_store import session_store
from app.services.chat_runtime import chat_runtime

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _to_out(rec) -> SessionOut:
    return SessionOut(
        id=rec.id,
        title=rec.title,
        session_type=rec.session_type,
        status=rec.status,
        pinned=getattr(rec, "pinned", False),
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
    q: str | None = Query(None),
) -> SessionListResponse:
    rows, total = session_store.list_for_owner(principal.user_id, limit=limit, offset=offset, q=q)
    return SessionListResponse(items=[_to_out(r) for r in rows], total=total)


@router.get("/{session_id}/messages", response_model=SessionMessageListResponse)
def list_session_messages(
    session_id: str,
    principal: Principal = Depends(get_principal),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    cursor: str | None = Query(None),
) -> SessionMessageListResponse:
    rec = session_store.get(session_id)
    if not rec or rec.owner_id != principal.user_id:
        raise HTTPException(status_code=404, detail="session_not_found")

    if cursor:
        window, total, next_cursor = session_store.list_messages_before(session_id, cursor, limit)
        has_more = next_cursor is not None
    else:
        window, total = session_store.list_messages(session_id, limit=limit, offset=offset)
        next_cursor = None
        has_more = (offset + len(window)) < total
    return SessionMessageListResponse(
        items=[
            SessionMessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                message_type=getattr(m, "message_type", "text"),
                attachments=getattr(m, "attachments", []),
                token_usage=getattr(m, "token_usage", None),
                run_id=getattr(m, "run_id", None),
                created_at=m.created_at,
            )
            for m in window
        ],
        total=total,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/{session_id}/stages")
def get_session_stages(
    session_id: str,
    principal: Principal = Depends(get_principal),
):
    rec = session_store.get(session_id)
    if not rec or rec.owner_id != principal.user_id:
        raise HTTPException(status_code=404, detail="session_not_found")
    return {"run": chat_runtime.get_stage_snapshot(session_id)}


@router.patch("/{session_id}", response_model=SessionOut)
def update_session(
    session_id: str,
    payload: SessionUpdateRequest,
    principal: Principal = Depends(get_principal),
) -> SessionOut:
    rec = session_store.get(session_id)
    if not rec or rec.owner_id != principal.user_id:
        raise HTTPException(status_code=404, detail="session_not_found")
    updated = session_store.update_session(session_id, title=payload.title, pinned=payload.pinned)
    if not updated:
        raise HTTPException(status_code=404, detail="session_not_found")
    return _to_out(updated)


@router.delete("/{session_id}")
def delete_session(
    session_id: str,
    principal: Principal = Depends(get_principal),
):
    rec = session_store.get(session_id)
    if not rec or rec.owner_id != principal.user_id:
        raise HTTPException(status_code=404, detail="session_not_found")
    return {"ok": session_store.delete_session(session_id)}
