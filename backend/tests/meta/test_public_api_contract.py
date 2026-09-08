"""O contrato da API pública é o produto da spec 095 (regras 11 e 12).

Meta test porque o que ele protege não é comportamento: é a PROMESSA de que a v1 não
muda. Renomear um campo num schema público, esquecer um escopo numa rota nova ou soltar
um endpoint sem autenticação são coisas que passariam em qualquer teste funcional — e
apareceriam meses depois, no script de terceiro que parou de funcionar.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from app.domain.api_tokens.scopes import ALL_SCOPES
from app.main import create_app

PUBLIC_PREFIX = "/api/public/v1"

# Os 22 endpoints declarados no §5 da spec. A lista é escrita à mão de propósito: gerar
# a expectativa a partir do código faria o teste concordar com qualquer coisa.
CONTRATO: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", f"{PUBLIC_PREFIX}/settings"),
        ("GET", f"{PUBLIC_PREFIX}/customers"),
        ("POST", f"{PUBLIC_PREFIX}/customers"),
        ("GET", f"{PUBLIC_PREFIX}/customers/{{customer_id}}"),
        ("GET", f"{PUBLIC_PREFIX}/customers/birthdays"),
        ("GET", f"{PUBLIC_PREFIX}/lawsuits"),
        ("POST", f"{PUBLIC_PREFIX}/lawsuits"),
        ("GET", f"{PUBLIC_PREFIX}/lawsuits/{{lawsuit_id}}"),
        ("PUT", f"{PUBLIC_PREFIX}/lawsuits/{{lawsuit_id}}"),
        ("GET", f"{PUBLIC_PREFIX}/lawsuits/{{lawsuit_id}}/history"),
        ("GET", f"{PUBLIC_PREFIX}/lawsuits/{{lawsuit_id}}/movements"),
        ("POST", f"{PUBLIC_PREFIX}/lawsuits/{{lawsuit_id}}/movements"),
        ("GET", f"{PUBLIC_PREFIX}/last-movements"),
        ("GET", f"{PUBLIC_PREFIX}/posts"),
        ("POST", f"{PUBLIC_PREFIX}/posts"),
        ("GET", f"{PUBLIC_PREFIX}/publications"),
        ("GET", f"{PUBLIC_PREFIX}/transactions"),
        ("POST", f"{PUBLIC_PREFIX}/transactions"),
        ("GET", f"{PUBLIC_PREFIX}/transactions/{{transaction_id}}"),
        ("PUT", f"{PUBLIC_PREFIX}/transactions/{{transaction_id}}"),
        ("GET", f"{PUBLIC_PREFIX}/documents"),
        ("GET", f"{PUBLIC_PREFIX}/documents/{{document_id}}/download"),
    }
)

APP_DIR = Path(__file__).resolve().parents[2] / "app"


@pytest.fixture(scope="module")
def openapi() -> dict[str, Any]:
    app = create_app()
    completo = app.openapi()
    return {
        rota: metodos
        for rota, metodos in completo["paths"].items()
        if rota.startswith(PUBLIC_PREFIX)
    }


def _operations(openapi: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (metodo.upper(), rota)
        for rota, operacoes in openapi.items()
        for metodo in operacoes
        if metodo.lower() in ("get", "post", "put", "patch", "delete")
    }


def test_a_v1_expoe_exatamente_os_22_endpoints_do_contrato(openapi: dict[str, Any]) -> None:
    """Regra 12: `v1` não sofre mudança quebrando contrato. Endpoint a mais também é
    mudança — é superfície que alguém vai passar a usar e que depois não pode sumir."""
    encontradas = _operations(openapi)

    faltando = sorted(CONTRATO - encontradas)
    sobrando = sorted(encontradas - CONTRATO)

    assert faltando == [], f"endpoint do contrato que sumiu: {faltando}"
    assert sobrando == [], f"endpoint fora do contrato: {sobrando}"


def test_toda_rota_publica_exige_token_e_escopo() -> None:
    """Uma rota nova sem `require_scope` seria pública de verdade — aberta a quem tiver
    qualquer token. O grep é sobre o código porque a dependência não aparece no OpenAPI."""
    fonte = (APP_DIR / "public" / "router.py").read_text(encoding="utf-8")
    decoradores = [linha for linha in fonte.splitlines() if linha.strip().startswith("@router.")]
    escopos = fonte.count("require_scope(")

    # `openapi.json` vive noutro router (`docs_router`), sem token e sem limite: exigir
    # escopo para ler a documentação impediria gerar cliente antes de ter acesso.
    assert escopos == len(decoradores), "toda rota de `router` precisa de require_scope"


def test_todo_escopo_declarado_e_usado_em_alguma_rota() -> None:
    """Escopo que ninguém confere é escopo que dá falsa sensação de limite: o integrador
    marca 'só leitura' e escreve mesmo assim."""
    fonte = (APP_DIR / "public" / "router.py").read_text(encoding="utf-8")
    nao_usados = [scope for scope in ALL_SCOPES if f'require_scope("{scope}")' not in fonte]

    assert nao_usados == [], f"escopo declarado e nunca conferido: {nao_usados}"


def test_o_documento_publico_e_json_valido_e_se_basta(openapi: dict[str, Any]) -> None:
    """Regra 11: o schema servido precisa ser utilizável por um gerador de cliente — o
    que exige que todo `$ref` aponte para algo que está no próprio documento."""
    from fastapi.testclient import TestClient

    with TestClient(create_app()) as client:
        resposta = client.get(f"{PUBLIC_PREFIX}/openapi.json")
    assert resposta.status_code == 200
    documento = json.loads(resposta.content)

    assert documento["info"]["version"] == "v1"
    assert set(documento["paths"]) == set(openapi)
    definidos = set(documento["components"]["schemas"])
    referenciados = _refs(documento["paths"]) | _refs(documento["components"]["schemas"])
    assert (
        referenciados <= definidos
    ), f"schema referenciado e não incluído: {sorted(referenciados - definidos)}"
    assert "bearerAuth" in documento["components"]["securitySchemes"]


def _refs(node: object) -> set[str]:
    encontrados: set[str] = set()
    if isinstance(node, dict):
        alvo = node.get("$ref")
        if isinstance(alvo, str) and alvo.startswith("#/components/schemas/"):
            encontrados.add(alvo.rsplit("/", 1)[1])
        for valor in node.values():
            encontrados |= _refs(valor)
    elif isinstance(node, list):
        for item in node:
            encontrados |= _refs(item)
    return encontrados


# Escrita direta no modelo, dentro do router público. A regra 10 da 095 diz que a escrita
# pública passa pelos services; até a spec 134 ela não passava, e o sintoma era exatamente
# este — `setattr` num objeto ORM seguido de `flush`.
_ESCRITA_DIRETA = ("setattr(", "session.add(", "session.flush(", "session.delete(")


def test_o_router_publico_nao_escreve_no_modelo_direto() -> None:
    """Regra 10 da 095 virada gate (spec 134).

    Era uma frase na spec e nada a conferia: a MESMA `payment_date` no MESMO lançamento
    dava 422 pela tela e 200 pela API, porque o PUT público escrevia atributo no modelo e
    o service — onde mora a regra — nunca era chamado. Um `setattr` de volta neste arquivo
    é a forma que o defeito tem de voltar, e agora ele reprova aqui.
    """
    fonte = (APP_DIR / "public" / "router.py").read_text(encoding="utf-8")

    encontrados = [trecho for trecho in _ESCRITA_DIRETA if trecho in fonte]

    assert encontrados == [], f"escrita fora do service no router público: {encontrados}"


def test_a_listagem_de_tarefas_aplica_a_visibilidade_da_tela() -> None:
    """Spec 134, regra 1: `GET /posts` devolvia tarefa privada de qualquer um.

    O predicado é o MESMO da API interna (`posts.listing.visible_to`) e não uma cópia — se
    a regra 8 da 033 mudar, ela muda nos dois lugares de uma vez. O gate confere que a
    rota pública continua importando o predicado de lá em vez de reinventá-lo.
    """
    fonte = (APP_DIR / "public" / "router.py").read_text(encoding="utf-8")

    assert "from app.domain.posts.listing import visible_to" in fonte
    assert "visible_to(caller.acting_user_id)" in fonte
