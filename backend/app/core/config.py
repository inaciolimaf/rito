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
    datajud_rate_limit_per_minute: int = 60
    # Spec 047: agenda diária da sincronização de andamentos (5 campos, diária).
    datajud_sync_cron: str = "0 7 * * *"
    datajud_sync_batch_size: int = 50

    # Spec 042: DJEN não pede credencial, mas exige User-Agent de browser (403 sem ele).
    djen_base_url: str = "https://comunicaapi.pje.jus.br/api/v1"
    djen_user_agent: str = ""
    djen_rate_limit_per_minute: int = 30
    # Spec 044: agenda diária da varredura (5 campos, diária: "m h * * *") e TTL do
    # lock por termo — uma execução por vez, mesmo com worker duplicado (regra 10).
    djen_sync_cron: str = "17 3 * * *"
    djen_sync_lock_ttl_seconds: int = 3600

    # Spec 049: agenda diária do job de saúde das integrações (5 campos, diária).
    integration_health_cron: str = "0 6 * * *"

    # Spec 061: e-mail de cobrança — SMTP puro, sem vendor específico. Sem SMTP_HOST,
    # o canal levanta ChannelNotConfiguredError e a tentativa vira SKIPPED (regra 9).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "nao-responda@rito.app"
    smtp_use_tls: bool = True
    # Spec 061, regra 10: agenda diária da régua de cobrança (5 campos, diária).
    dunning_sync_cron: str = "0 8 * * *"

    # Spec 041: fixtures da camada HTTP — replay em app_env=test; HTTP_RECORD=1 grava.
    http_fixtures_dir: str = "tests/fixtures/http"
    http_record: bool = False

    log_level: str = "INFO"
    log_format: str = "json"

    # CSV de origens permitidas (CORS) — o frontend roda em porta diferente do backend em dev.
    cors_allowed_origins: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
