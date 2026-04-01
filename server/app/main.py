from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import auth, chat, files, sessions, usage
from app.core.config import get_settings

settings = get_settings()
upload_dir = Path(settings.upload_dir).expanduser().resolve()
upload_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_prefix = settings.api_v1_prefix
app.include_router(auth.router, prefix=api_prefix)
app.include_router(sessions.router, prefix=api_prefix)
app.include_router(chat.router, prefix=api_prefix)
app.include_router(usage.router, prefix=api_prefix)
app.include_router(files.router, prefix=api_prefix)
app.mount("/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")


@app.get("/health")
def health():
    return {"status": "ok"}
