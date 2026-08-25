"""As três travas da camada de IA (spec 081, regras 1, 2 e 12).

São testes meta porque o que eles protegem não é um comportamento: é uma decisão de
arquitetura que só se sustenta enquanto ninguém a contraria por conveniência num
domingo. Cada um falha com o nome do arquivo ofensor.
"""

import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "app"
TESTS_DIR = Path(__file__).resolve().parents[1]

# Regra 1: OpenRouter é o único gateway. SDK de provider no `app/` reprova.
_PROVIDER_SDKS = (
    "openai",
    "anthropic",
    "google.generativeai",
    "vertexai",
    "cohere",
    "mistralai",
    "litellm",
    "langchain_openai",
    "groq",
)
_IMPORT_PATTERNS = [
    re.compile(rf"^\s*(?:import|from)\s+{re.escape(sdk)}\b", re.MULTILINE) for sdk in _PROVIDER_SDKS
]

# Regra 2: nenhum id de modelo hardcoded. O formato do OpenRouter é `fabricante/modelo`,
# e a busca é por strings com essa cara — a exceção é o padrão em `config.py`, que É a
# variável de ambiente.
_MODEL_ID_PATTERN = re.compile(
    r"""["'](?:openai|anthropic|google|meta-llama|mistralai|deepseek|qwen|x-ai|cohere)/[\w.\-:]+["']"""
)
_MODEL_ID_EXEMPT = {"app/core/config.py"}


def _app_files() -> list[Path]:
    return sorted(APP_DIR.rglob("*.py"))


def test_nenhum_sdk_de_provider_e_importado_no_app() -> None:
    """Regra 1: adicionar um provider é implementar `LLMProvider`, não importar SDK."""
    ofensores: list[str] = []
    for path in _app_files():
        conteudo = path.read_text(encoding="utf-8")
        for sdk, pattern in zip(_PROVIDER_SDKS, _IMPORT_PATTERNS, strict=True):
            if pattern.search(conteudo):
                ofensores.append(f"{path.relative_to(APP_DIR.parent)}: {sdk}")
    assert ofensores == [], (
        "SDK de provider importado — OpenRouter é o único gateway (spec 081, regra 1): "
        + ", ".join(ofensores)
    )


def test_nenhum_id_de_modelo_hardcoded_fora_da_configuracao() -> None:
    """Regra 2: modelo é dado de `ai_feature_config`; o padrão vive em variável de
    ambiente. Um literal no meio do código reintroduz o deploy para trocar de modelo."""
    ofensores: list[str] = []
    for path in _app_files():
        relativo = str(path.relative_to(APP_DIR.parent))
        if relativo in _MODEL_ID_EXEMPT:
            continue
        for match in _MODEL_ID_PATTERN.finditer(path.read_text(encoding="utf-8")):
            ofensores.append(f"{relativo}: {match.group(0)}")
    assert (
        ofensores == []
    ), "id de modelo hardcoded (spec 081, regra 2) — use ai_feature_config: " + ", ".join(ofensores)


def test_provider_de_llm_em_teste_nunca_alcanca_a_rede() -> None:
    """Regra 12: em `app_env=test` o transporte é o de fixtures, que falha explicitamente
    quando a fixture não existe — nunca cai na rede."""
    import os

    from app.core.config import get_settings
    from app.integrations.http.fixtures import FixtureTransport
    from app.integrations.openrouter.factory import create_llm_provider

    assert os.environ["APP_ENV"] == "test"
    provider = create_llm_provider()
    # Alcançar o transporte por dentro é o ponto do teste: a garantia é justamente que
    # a instância montada em produção-de-teste não fala com a rede.
    http = provider._http  # noqa: SLF001
    transport = http._client._transport  # type: ignore[attr-defined]  # noqa: SLF001
    assert isinstance(transport, FixtureTransport)
    assert Path(get_settings().llm_fixtures_dir).name == "llm"
