"""A fiação do app: ordem de middleware e ordem de registro de rotas (spec 109).

Estes quatro testes existem porque a spec 109 quebrou `create_app` — 70 statements, 61
chamadas sequenciais a `include_router` — em três funções e uma tabela. Nenhum teste do
projeto reprovaria se essa refatoração tivesse trocado a ordem de dois routers ou perdido
um pelo caminho:

- **trocar a ordem** não gera erro; gera a rota errada respondendo. `/posts/bulk/complete`
  casaria com `/posts/{post_id}` e devolveria 422 ("bulk" não é UUID) — um erro plausível,
  que o teste do módulo de posts nunca vê porque ele chama a rota certa;
- **perder um router** não gera erro nenhum: as rotas somem, e os testes daquele módulo
  passam a falhar por 404 — se alguém rodar a suíte inteira. Num PR que só roda o que
  mudou, some em silêncio.

Nenhum destes testes olha para o código de `main.py` por regex. Os três primeiros olham
para o **app construído**, que é o que de fato responde requisição.
"""

import ast
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware

from app.core.middleware import ObservabilityMiddleware
from app.main import _ROUTERS, app
from app.public.middleware import PublicApiMiddleware

BACKEND = Path(__file__).resolve().parents[2]
MAIN = BACKEND / "app" / "main.py"

# De fora para dentro. `app.user_middleware` guarda nessa ordem porque o Starlette faz
# `insert(0, ...)` a cada `add_middleware` — o último adicionado é o mais externo.
# Comparados como CLASSES, não por nome: duas classes homônimas em módulos diferentes
# passariam num teste por string, e é exatamente esse o erro que uma reorganização de
# módulos comete.
MIDDLEWARES_ESPERADOS = [
    PublicApiMiddleware,
    ObservabilityMiddleware,
    CORSMiddleware,
]

# Os únicos routers que ficam fora de `/api/v1`, cada um por decisão registrada em spec.
ROTAS_FORA_DA_API_V1 = {
    "/health",
    "/api/public/v1",
    "/docs/public",
    "/ical",
}


def _caminhos_em_ordem() -> list[str]:
    """Os 311 caminhos na ordem em que foram registrados.

    `openapi()["paths"]` é um `dict`, e dict preserva ordem de inserção — que aqui é a
    ordem de registro. É a forma pública de ler essa ordem: `app.routes` guarda os
    wrappers internos do FastAPI (`_IncludedRouter`), que mudam de forma entre versões.
    """
    return list(app.openapi()["paths"])


def test_ordem_dos_middlewares() -> None:
    """Regra 4: a pilha de middleware, de fora para dentro, é exatamente esta.

    O CORS ser o mais INTERNO é o ponto que importa. Um middleware externo que devolva
    resposta sem passar pelo CORS (um 429 do limite da API pública, por exemplo) chega ao
    navegador sem `Access-Control-Allow-Origin`, e o front mostra erro de origem em vez da
    mensagem real — o pior tipo de bug de produção, porque a resposta correta existe e o
    usuário não a vê.
    """
    instalados = [m.cls for m in app.user_middleware]
    nomes = [getattr(cls, "__name__", repr(cls)) for cls in instalados]
    esperados = [cls.__name__ for cls in MIDDLEWARES_ESPERADOS]
    # Identidade, um a um: `==` entre a lista do Starlette (tipada como factory) e uma
    # lista de classes o mypy recusa como comparação sem sobreposição, e ele está certo —
    # os tipos declarados não são o mesmo. `is` compara o que interessa: é esta classe.
    assert nomes == esperados, f"pilha de middleware mudou: {nomes}"
    for instalado, esperado in zip(instalados, MIDDLEWARES_ESPERADOS, strict=True):
        assert instalado is esperado


def test_rotas_ambiguas_registradas_na_ordem_certa() -> None:
    """Regra 3: no FastAPI a primeira rota que casa vence.

    Os dois pares abaixo são os únicos do projeto em que um caminho literal disputa com um
    parâmetro de caminho no mesmo prefixo. Os dois estão comentados em `main.py`; aqui eles
    ficam travados.
    """
    caminhos = _caminhos_em_ordem()
    pares = [
        # `bulk` não parseia como UUID: se `{post_id}` vencer, a resposta é 422.
        ("/api/v1/posts/bulk/complete", "/api/v1/posts/{post_id}"),
        ("/api/v1/posts/bulk/read", "/api/v1/posts/{post_id}"),
        ("/api/v1/posts/bulk/star", "/api/v1/posts/{post_id}"),
        ("/api/v1/posts/bulk/reassign", "/api/v1/posts/{post_id}"),
        # `analysis` idem, contra `{publication_id}`.
        ("/api/v1/publications/analysis/estimate", "/api/v1/publications/{publication_id}"),
    ]
    for literal, parametrizado in pares:
        assert literal in caminhos, f"{literal} sumiu do app"
        assert parametrizado in caminhos, f"{parametrizado} sumiu do app"
        assert caminhos.index(literal) < caminhos.index(parametrizado), (
            f"{literal} precisa ser registrado ANTES de {parametrizado} — "
            "senão o parâmetro de caminho vence e a rota literal fica inalcançável"
        )


def test_todo_router_importado_esta_registrado() -> None:
    """Regra 5: nenhum router importado em `main.py` fica de fora de `_ROUTERS`.

    Por AST, sobre o próprio `main.py`: todo nome importado que termine em `_router` tem
    que aparecer na tabela. É o teste que pega o `include_router` perdido numa refatoração
    — o defeito que não levanta exceção, só apaga rotas.
    """
    arvore = ast.parse(MAIN.read_text(), filename=str(MAIN))
    importados = {
        alias.asname or alias.name
        for node in ast.walk(arvore)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if (alias.asname or alias.name).endswith("_router")
    }
    registrados = {
        elemento.elts[0].id
        for elemento in ast.walk(arvore)
        if isinstance(elemento, ast.Tuple)
        and elemento.elts
        and isinstance(elemento.elts[0], ast.Name)
    }
    faltando = sorted(importados - registrados)
    assert faltando == [], (
        "router importado em main.py e nunca registrado — as rotas dele não existem:\n  "
        + "\n  ".join(faltando)
    )
    assert len(_ROUTERS) == len(
        importados
    ), f"_ROUTERS tem {len(_ROUTERS)} entradas para {len(importados)} routers importados"


def test_apenas_as_rotas_declaradas_ficam_fora_da_api_v1() -> None:
    """O prefixo `/api/v1` é a regra; as exceções são quatro e cada uma tem motivo.

    `/health` é sondagem de orquestrador (spec 099), `/api/public/v1` e `/docs/public` são
    a API pública com versão própria no caminho (spec 095, regra 12), e `/ical` é o feed
    público por token (spec 037 §5). Uma quinta exceção aparecendo aqui é quase sempre um
    prefixo esquecido, não uma decisão.
    """
    fora = {
        caminho
        for caminho in _caminhos_em_ordem()
        if not caminho.startswith("/api/v1/") and caminho != "/api/v1"
    }
    inesperadas = sorted(
        caminho
        for caminho in fora
        if not any(caminho.startswith(prefixo) for prefixo in ROTAS_FORA_DA_API_V1)
    )
    assert (
        inesperadas == []
    ), "rota fora de /api/v1 sem exceção declarada (prefixo esquecido?):\n  " + "\n  ".join(
        inesperadas
    )


# ---------------------------------------------------------------- spec 116
#
# A 116 trocou dezenas de query params soltos por modelos passados via `Depends()`. A troca
# tem uma armadilha que só aparece no OpenAPI, nunca num teste de rota que confere 200.

# Palavras reservadas que já foram usadas como nome de query param no projeto, ou que
# apareceriam naturalmente. `from` é o caso real: `GET /reports/tabular/{key}?from=...`
# existe desde a spec 070.
_ALIASES_RESERVADOS = {"from", "class", "import", "in", "for", "is", "not", "and", "or"}


def test_nenhum_query_param_ficou_com_sufixo_de_underscore() -> None:
    """A armadilha do alias reservado (spec 116).

    Num modelo Pydantic usado como dependência, o FastAPI monta a assinatura da rota
    dinamicamente e usa o **alias** como nome do parâmetro — o que ele não consegue fazer
    quando o alias é palavra reservada do Python. Aí ele cai, em silêncio, no nome do
    campo:

        alias="status" -> query param `status`   (funciona)
        alias="from"   -> query param `from_`    (vira o nome do campo)

    O estrago é mudo: a rota continua respondendo 200, o cliente continua mandando `from`,
    e o filtro simplesmente para de existir. Aconteceu de verdade nesta spec, com
    `GET /reports/tabular/{report_key}`, e foi o diff de query params que pegou.

    Um nome de parâmetro terminado em `_` é sempre esse acidente: ninguém batiza um query
    param assim de propósito.
    """
    ofensores = [
        f"{metodo.upper()} {caminho} -> {parametro['name']}"
        for caminho, ops in app.openapi()["paths"].items()
        for metodo, op in ops.items()
        if isinstance(op, dict)
        for parametro in op.get("parameters", [])
        if parametro["name"].endswith("_")
    ]
    assert ofensores == [], (
        "query param terminado em `_` — quase certamente um alias de palavra reservada "
        "que o FastAPI não conseguiu usar. Declare o `Query(alias=...)` numa dependência "
        "de FUNÇÃO, não como campo de modelo:\n  " + "\n  ".join(ofensores)
    )


def test_query_params_das_rotas_de_listagem() -> None:
    """As seis rotas que a spec 116 reescreveu continuam aceitando os mesmos parâmetros.

    Lista escrita à mão, no mesmo espírito do `CONTRATO` de `test_public_api_contract.py`:
    gerar a expectativa a partir do código faria o teste concordar com qualquer coisa.

    São exatamente as rotas cujos filtros deixaram de ser parâmetros soltos e passaram a
    chegar como objeto — a operação que, feita errado, renomeia ou apaga um query param
    sem quebrar nada mais.
    """
    esperado = {
        "/api/v1/customers": {
            "q",
            "type",
            "state",
            "city",
            "origin_id",
            "created_from",
            "created_to",
            "has_active_lawsuit",
            "birthdays",
            "archived",
            "sort",
            "order",
            "cursor",
            "limit",
        },
        "/api/v1/publications": {
            "interval",
            "date_from",
            "date_to",
            "user_id",
            "customer_id",
            "court_code",
            "process_number",
            "linked",
            "cancelled",
            "read",
            "cursor",
            "limit",
        },
        # Os três toggles NÃO entram aqui: nesta rota eles são o que se conta (§8 da 048).
        "/api/v1/publications/counts": {
            "interval",
            "date_from",
            "date_to",
            "user_id",
            "customer_id",
            "court_code",
            "process_number",
        },
        "/api/v1/transactions": {
            "kind",
            "customer_id",
            "lawsuit_id",
            "status",
            "due_from",
            "due_to",
            "q",
            "internal",
            "cursor",
            "limit",
        },
        "/api/v1/reports/tabular/{report_key}": {
            "report_key",
            "from",
            "to",
            "user_id",
            "action_group_id",
            "cursor",
            "limit",
        },
    }
    caminhos = app.openapi()["paths"]
    for caminho, nomes in esperado.items():
        atual = {p["name"] for p in caminhos[caminho]["get"]["parameters"]}
        assert (
            atual == nomes
        ), f"{caminho}: sumiram {sorted(nomes - atual)}, surgiram {sorted(atual - nomes)}"
