from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_name: str = "Rito"
    secret_key: str
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 4

    database_url: str
    migrations_database_url: str | None = None
    redis_url: str

    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None

    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    datajud_api_key: str | None = None
    datajud_base_url: str = "https://api-publica.datajud.cnj.jus.br"

    log_level: str = "INFO"
    log_format: str = "json"

    # CSV de origens permitidas (CORS) — o frontend roda em porta diferente do backend em dev.
    cors_allowed_origins: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
