"""Application configuration via environment variables (12-factor)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="", env_file=(".env", "../.env"), extra="ignore"
    )

    app_name: str = "CPC Lab API"
    env: str = "development"

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    log_level: str = "info"

    database_url: str = "sqlite:///./data/cpc.db"

    # Auth
    jwt_secret: str = "dev-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 720
    admin_email: str = "admin@cpc.lab"
    admin_password: str = "change-me-admin"

    # Storage
    storage_backend: str = "local"  # local | s3
    data_dir: str = "./data"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "cpc-lab"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "us-east-1"

    # Jobs
    job_backend: str = "thread"  # thread | celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Engines
    engine_torch: bool = False
    hf_offline: bool = False

    # Assistant
    assistant_provider: str = ""
    assistant_base_url: str = ""
    assistant_model: str = ""
    assistant_api_key_env: str = ""

    # Scholarly APIs
    scholar_contact_email: str = ""
    scholar_rate_limit_per_min: int = 20

    # Security
    rate_limit_per_minute: int = 120
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    upload_max_mb: int = 25
    allow_public_registration: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def resolved_data_dir(self) -> Path:
        return Path(self.data_dir).resolve()

    def ensure_dirs(self) -> None:
        self.resolved_data_dir().mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
