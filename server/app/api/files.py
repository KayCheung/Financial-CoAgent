from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import Principal, get_principal
from app.models.schemas import AttachmentOut
from app.core.config import get_settings

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload", response_model=AttachmentOut)
async def upload_file(
    file: UploadFile = File(...),
    principal: Principal = Depends(get_principal),
) -> AttachmentOut:
    settings = get_settings()
    upload_root = Path(settings.upload_dir).expanduser().resolve() / principal.user_id
    upload_root.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix
    attachment_id = str(uuid.uuid4())
    stored_name = f"{attachment_id}{suffix}"
    target = upload_root / stored_name
    payload = await file.read()
    target.write_bytes(payload)
    return AttachmentOut(
        attachment_id=attachment_id,
        file_name=file.filename or stored_name,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(payload),
        file_url=f"/uploads/{principal.user_id}/{stored_name}",
    )
