from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import Principal, get_principal
from app.models.schemas import ChatInterruptRequest, ChatResumeRequest, ChatStreamRequest
from app.services.chat_runtime import chat_runtime
from app.services.session_store import session_store

router = APIRouter(prefix="/chat", tags=["chat"])


def _ensure_session(principal: Principal, session_id: str) -> None:
    s = session_store.get(session_id)
    if not s or s.owner_id != principal.user_id:
        raise HTTPException(status_code=404, detail="session_not_found")


@router.post("/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    principal: Principal = Depends(get_principal),
):
    _ensure_session(principal, payload.session_id)
    gen = chat_runtime.stream_chat(
        user_id=principal.user_id,
        session_id=payload.session_id,
        user_message=payload.message,
        attachments=payload.attachments,
        resume_token=None,
        last_event_id=payload.last_event_id,
    )

    async def sse():
        async for line in gen:
            yield line

    return StreamingResponse(sse(), media_type="text/event-stream")


@router.post("/resume")
async def chat_resume(
    payload: ChatResumeRequest,
    principal: Principal = Depends(get_principal),
):
    _ensure_session(principal, payload.session_id)
    gen = chat_runtime.stream_chat(
        user_id=principal.user_id,
        session_id=payload.session_id,
        user_message="",
        attachments=[],
        resume_token=payload.resume_token,
        last_event_id=payload.last_event_id,
    )

    async def sse():
        async for line in gen:
            yield line

    return StreamingResponse(sse(), media_type="text/event-stream")


@router.post("/interrupt")
async def chat_interrupt(
    payload: ChatInterruptRequest,
    principal: Principal = Depends(get_principal),
):
    _ensure_session(principal, payload.session_id)
    ok = await chat_runtime.interrupt(payload.session_id)
    return {"ok": ok}
