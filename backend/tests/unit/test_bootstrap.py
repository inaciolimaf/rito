"""Spec 099, regras 5 e 6 — configuração inválida derruba o boot, não a requisição.

O que se afirma é sempre a mesma coisa em formas diferentes: o problema aparece ANTES de
o sistema atender alguém, e a mensagem diz o que fazer.
"""

import pytest

from app.core.bootstrap import (
    EXAMPLE_SECRET_KEY,
    ConfigurationError,
    ensure_valid,
    validate,
)
from app.core.config import Settings


def _producao(**overrides: object) -> Settings:
    # `model_construct` pula a validação do Pydantic de propósito: o que se testa aqui é
    # a validação da 099, não a de tipos — e montar um `Settings` completo por variável
    # de ambiente em cada caso engessaria o teste no formato do `.env`.
    base: dict[str, object] = {
        "app_env": "production",
        "secret_key": "a" * 48,
        "database_url": "postgresql+asyncpg://rito_app:x@db/rito",
        "migrations_database_url": "postgresql+asyncpg://rito:x@db/rito",
        "redis_url": "redis://redis:6379/0",
        "s3_endpoint_url": "https://s3.exemplo",
        "s3_access_key": "k",
        "s3_secret_key": "s",
        "s3_bucket": "rito",
        "s3_region": "us-east-1",
        "cors_allowed_origins": "https://app.exemplo.com.br",
    }
    return Settings.model_construct(**(base | overrides))  # type: ignore[arg-type]  # ver comentário acima


def test_configuracao_completa_passa() -> None:
    assert validate(_producao()) == []


def test_variavel_faltando_aparece_com_o_motivo() -> None:
    problemas = validate(_producao(s3_bucket=None))

    assert [p.variavel for p in problemas] == ["s3_bucket"]
    assert "anexos" in problemas[0].motivo


def test_mensagem_lista_TODAS_as_que_faltam_de_uma_vez() -> None:
    """Descobrir uma por vez, com um deploy entre cada, transforma dez minutos de
    configuração numa tarde."""
    with pytest.raises(ConfigurationError) as erro:
        ensure_valid(_producao(s3_bucket=None, redis_url=None, s3_region=None))

    mensagem = str(erro.value)
    assert "S3_BUCKET" in mensagem
    assert "REDIS_URL" in mensagem
    assert "S3_REGION" in mensagem


def test_secret_key_de_exemplo_recusa_subir() -> None:
    """Regra 6. É o segredo que assina token de sessão, e está publicado no
    `.env.example` — quem leu o repositório sabe assinar um token de qualquer usuário."""
    problemas = validate(_producao(secret_key=EXAMPLE_SECRET_KEY))

    assert [p.variavel for p in problemas] == ["secret_key"]
    assert "público" in problemas[0].motivo


def test_secret_key_curta_demais_tambem_recusa() -> None:
    problemas = validate(_producao(secret_key="curta"))

    assert [p.variavel for p in problemas] == ["secret_key"]


def test_cors_apontando_para_localhost_em_producao_e_erro() -> None:
    """O navegador de ninguém vai chegar a localhost — e a origem real ficaria de fora,
    o que aparece como "o sistema não carrega" sem nenhum erro no servidor."""
    problemas = validate(_producao(cors_allowed_origins="http://localhost:5173"))

    assert [p.variavel for p in problemas] == ["cors_allowed_origins"]


def test_desenvolvimento_nao_e_barrado_por_nada_disso() -> None:
    """A validação é de PRODUÇÃO. Exigir S3 e segredo forte em dev tornaria o primeiro
    `make up` de alguém uma sequência de erros."""
    dev = Settings.model_construct(
        app_env="development",
        secret_key=EXAMPLE_SECRET_KEY,
        database_url="postgresql+asyncpg://x@localhost/rito",
        redis_url="redis://localhost:6379/0",
        cors_allowed_origins="http://localhost:5173",
    )

    assert validate(dev) == []
