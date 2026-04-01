"""Entrypoint for `uvicorn main:app` from the `server/` directory."""

from app.main import app

__all__ = ["app"]
