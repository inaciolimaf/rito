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
        # Obrigatória desde a spec 135 (regra 4): sem ela o `/metrics` responde a qualquer
        # um, e o `.env.production.example` a trazia vazia — o padrão era a rota aberta.
        "metrics_token": "b" * 32,
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


def test_metrics_token_faltando_em_producao_recusa_subir() -> None:
    """Spec 135, regra 4 — e a decisão que ela tomou.

    Havia duas saídas para "`/metrics` aberto por padrão": negar a rota quando não há token,
    ou recusar o boot. A escolha foi recusar o boot, pelo precedente da regra 6 (o
    `SECRET_KEY` de exemplo) e por um motivo prático: negar a rota transforma um problema de
    segurança em um painel de observabilidade que para de funcionar sem dizer por quê, e o
    operador descobre no dia em que precisa dele. Recusar o boot avisa no deploy, junto com
    todo o resto que falta, e ninguém precisa adivinhar.
    """
    problemas = validate(_producao(metrics_token=None))

    assert [p.variavel for p in problemas] == ["metrics_token"]
    assert "/metrics" in problemas[0].motivo


def test_metrics_token_vazio_conta_como_faltando() -> None:
    """`METRICS_TOKEN=` no arquivo é exatamente o estado que abria a rota."""
    assert [p.variavel for p in validate(_producao(metrics_token=""))] == ["metrics_token"]


def test_cors_coringa_em_producao_recusa_subir() -> None:
    """Spec 135, regra 5. `allow_origins=["*"]` com `allow_credentials=True` é a combinação
    que o navegador deveria recusar — e «deveria» não é garantia que se leva para produção.
    O checador antigo só olhava para "localhost" e deixava o coringa passar inteiro."""
    problemas = validate(_producao(cors_allowed_origins="*"))

    assert [p.variavel for p in problemas] == ["cors_allowed_origins"]
    assert "coringa" in problemas[0].motivo


def test_cors_coringa_no_meio_da_lista_tambem_recusa() -> None:
    """Uma origem legítima ao lado não desfaz o coringa — basta ele estar na lista."""
    problemas = validate(_producao(cors_allowed_origins="https://app.exemplo.com.br, *"))

    assert [p.variavel for p in problemas] == ["cors_allowed_origins"]


def test_origem_que_apenas_CONTEM_asterisco_nao_e_coringa() -> None:
    """A comparação é por origem inteira, não por substring: um subdomínio curinga escrito
    à mão (`https://*.exemplo.com.br`) é outro problema — inútil, porque o middleware não o
    expande — e não é ESTE. Confundir os dois faria a mensagem mentir sobre a causa."""
    assert validate(_producao(cors_allowed_origins="https://*.exemplo.com.br")) == []
