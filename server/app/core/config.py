from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Financial-CoAgent Gateway"
    api_v1_prefix: str = "/api/v1"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"
    database_url: str = "sqlite:///./coagent.db"
    upload_dir: str = "./uploads"
    audit_wal_dir: str = "./audit_wal"
    nacos_host: str = "127.0.0.1"
    nacos_port: int = 8848
    nacos_username: str = "dev"
    nacos_password: str = "dev"
    nacos_namespace: str = "dev"
    nacos_group: str = "DEFAULT_GROUP"
    nacos_datasource_data_id: str = "agent-datasource.yml"
    remote_ocr_url: str | None = None
    remote_ocr_token: str | None = None

    # S1 dev auth: replace with OIDC / enterprise SSO in S6.
    dev_bearer_token: str = "dev-local-token"
    dev_user_id: str = "dev-user"
    dev_user_name: str = "Local Developer"
    dev_tenant_id: str = "dev-tenant"
    dev_role: str = "operator"

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
