from __future__ import annotations

import asyncio
from pathlib import Path
from functools import lru_cache
from typing import Any

import yaml
from v2.nacos import ClientConfigBuilder, ConfigParam, NacosConfigService

from app.core.config import get_settings


class NacosConfigError(RuntimeError):
    pass


class NacosConfigClient:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._loop = asyncio.new_event_loop()
        nacos_runtime_dir = Path(".nacos_runtime").resolve()
        cache_dir = nacos_runtime_dir / "cache"
        log_dir = nacos_runtime_dir / "log"
        cache_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        client_config = (
            ClientConfigBuilder()
            .server_address(f"{self._settings.nacos_host}:{self._settings.nacos_port}")
            .username(self._settings.nacos_username)
            .password(self._settings.nacos_password)
            .namespace_id(self._settings.nacos_namespace)
            .cache_dir(str(cache_dir))
            .log_dir(str(log_dir))
            .build()
        )
        self._service = self._loop.run_until_complete(NacosConfigService.create_config_service(client_config))

    def get_config_content(self, *, data_id: str, group: str, namespace_id: str | None = None) -> str:
        # namespace is already carried by the client config; method keeps the arg for a stable call shape.
        _ = namespace_id
        try:
            return self._loop.run_until_complete(self._service.get_config(ConfigParam(data_id=data_id, group=group)))
        except Exception as exc:  # pragma: no cover
            raise NacosConfigError(f"nacos config fetch failed: {exc}") from exc

    def get_yaml_config(self, *, data_id: str, group: str, namespace_id: str | None = None) -> dict[str, Any]:
        raw = self.get_config_content(data_id=data_id, group=group, namespace_id=namespace_id)
        if not raw.strip():
            return {}
        loaded = yaml.safe_load(raw)
        if isinstance(loaded, dict):
            return loaded
        raise NacosConfigError("nacos yaml content is not a mapping")


@lru_cache
def get_nacos_client() -> NacosConfigClient:
    return NacosConfigClient()
