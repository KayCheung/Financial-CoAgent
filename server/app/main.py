from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, sessions, usage
from app.core.config import get_settings

settings = get_settings()

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


@app.get("/health")
def health():
    return {"status": "ok"}
