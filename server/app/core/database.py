from __future__ import annotations

from urllib.parse import quote_plus
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.core.config import get_settings
from app.core.nacos_config import NacosConfigError, get_nacos_client


def get_database_url() -> str:
    settings = get_settings()
    configured = getattr(settings, "database_url", None)
    if configured and configured != "sqlite:///./coagent.db":
        return configured

    try:
        payload = get_nacos_client().get_yaml_config(
            data_id=settings.nacos_datasource_data_id,
            group=settings.nacos_group,
            namespace_id=settings.nacos_namespace,
        )
        datasource = (((payload.get("spring") or {}).get("datasource") or {}))
        url = datasource.get("url")
        username = datasource.get("username")
        password = datasource.get("password")
        if url and username is not None and password is not None:
            return _to_sqlalchemy_postgres_url(str(url), str(username), str(password))
    except NacosConfigError:
        pass

    return configured or "sqlite:///./coagent.db"


def _to_sqlalchemy_postgres_url(jdbc_url: str, username: str, password: str) -> str:
    prefix = "jdbc:postgresql://"
    if not jdbc_url.startswith(prefix):
        return jdbc_url
    safe_username = quote_plus(username)
    safe_password = quote_plus(password)
    return f"postgresql+psycopg2://{safe_username}:{safe_password}@{jdbc_url[len(prefix):]}"


def build_engine() -> Engine:
    db_url = get_database_url()
    connect_args: dict[str, Any] = {}
    if isinstance(db_url, str) and db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(db_url, future=True, connect_args=connect_args)


def should_auto_create_schema() -> bool:
    db_url = get_database_url()
    return isinstance(db_url, str) and db_url.startswith("sqlite")
