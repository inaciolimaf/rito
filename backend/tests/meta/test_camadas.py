"""As três regras de camada do `CLAUDE.md` §5 que dá para verificar por AST (spec 118).

**Este é um gate por proxy e a honestidade sobre isso é parte do gate.**

O que ele verifica são três propriedades sintáticas, exatas e binárias:

1. existe chamada de query dentro de um `router.py`;
2. um `router.py` importa de um módulo `repository`;
3. um `service.py` importa de `app.integrations` um módulo que faz I/O.

O que ele **não** verifica é SOLID. Não há teste para "a responsabilidade é única" ou
"esta é a abstração certa" — isso é revisão humana e continua sendo. Um service pode
passar nas três checagens e ainda ter regra de negócio no lugar errado. O que estas
checagens compram é o piso: os três sintomas mais baratos de detectar e os mais comuns,
cada um dos quais, se passar, vira dívida que a próxima refatoração paga mais caro.

AST e nunca regex, pelo mesmo motivo do `test_no_rag.py`: `select` aparece dentro de
string e de comentário, e um gate que dá falso positivo em comentário é um gate que
alguém desliga.

Duas coisas que ele deliberadamente NÃO pega, medidas na entrega da 118 para quem
vier depois não precisar redescobrir:

- `session.get(Modelo, id)`, `session.add`, `session.flush` e `session.delete` dentro de
  um router. São 9 ocorrências em `automations`, `webhooks` e `schedule`. A regra 1 do §8
  da 118 lista `select/insert/update/delete/session.execute`, e ampliar a checagem para
  `.get(` sem qualificar o objeto encheria de falso positivo (`dict.get`, `payload.get`).
- as camadas de `app/public/` — ver o comentário de `_RAIZ` logo abaixo.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
APP_DIR = BACKEND_DIR / "app"

# Escopo: `app/domain/<ctx>/`, que é onde o §5 desenha as camadas
# (`models/schemas/repository/service/router`) e onde a regra 1 do §8 da spec 118 aponta
# textualmente. `app/public/` não é um bounded context — é um adapter de entrega — e o
# `app/public/router.py` HOJE monta 9 queries e importa `CustomerRepository`. Isso não é
# uma exceção deste gate: é dívida fora do escopo desta spec, medida e registrada, que
# precisa de uma spec própria (o arquivo teria de ganhar service e repositório inteiros
# para reproduzir 22 contratos públicos sem mudar nenhum). Ampliar `_RAIZ` para `APP_DIR`
# é o que fecha essa dívida — e é assim que se confere se ela foi paga.
_RAIZ = APP_DIR / "domain"

# --------------------------------------------------------------------------------------
# Listas de exceção — versionadas aqui de propósito (spec 118, §4.E).
#
# Regra 5 da spec: na entrega elas estão VAZIAS. Uma exceção legítima entra aqui, com
# justificativa escrita, e nunca como diretiva de supressão espalhada pelo código: a
# exceção que mora no
# gate é contável e revisável; a que mora no arquivo violador some.
# Cada entrada é um caminho relativo a `backend/`.
# --------------------------------------------------------------------------------------
EXCECOES_QUERY_EM_ROUTER: frozenset[str] = frozenset()
EXCECOES_REPOSITORIO_EM_ROUTER: frozenset[str] = frozenset()
EXCECOES_INTEGRACAO_EM_SERVICE: frozenset[str] = frozenset()

# Construtores de query do SQLAlchemy. Só contam quando o próprio arquivo os importa de
# `sqlalchemy` — `update`/`delete` são palavras comuns e um `service.update(...)` dentro de
# um router é exatamente o que queremos que o router faça.
_CONSTRUTORES_SQL = frozenset(
    {"select", "insert", "update", "delete", "text", "exists", "union", "union_all"}
)

# Estes dois não precisam de import para serem denúncia: `select(` e `insert(` num router
# não são outra coisa, mesmo importados com alias ou por `sqlalchemy.select`.
_CONSTRUTORES_SQL_INEQUIVOCOS = frozenset({"select", "insert"})

# `session.execute(...)` e irmãos. Router não executa statement: nem o dele, nem o de
# ninguém.
_METODOS_DE_EXECUCAO = frozenset({"execute", "exec_driver_sql", "stream"})

# Módulos de `app.integrations` que um service PODE importar: contratos e formas de dado.
#
# `base` guarda a abstração (`FileStorage`, `MessagingChannel`, `OcrProvider`,
# `LawsuitSource`) e os erros que fazem parte do contrato dela; `types`, `parser` e
# `schemas` guardam DTO — forma de dado, sem I/O. Importar forma de dado não acopla o
# service a implementação nenhuma, e um gate que reprovasse `ParsedProcess` seria ruído.
# Ruído é como um gate morre.
#
# Todo o resto de `app.integrations` — `client`, `source`, `s3`, `tesseract`, `email`,
# `factory`, `registry`, … — faz I/O ou escolhe quem faz, e é disso que o service tem de
# depender pela abstração (DIP).
_MODULOS_DE_CONTRATO = frozenset({"base", "types", "parser", "schemas"})


def _arquivos(nome: str) -> list[Path]:
    return sorted(_RAIZ.rglob(nome))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _rel(path: Path) -> str:
    return str(path.relative_to(BACKEND_DIR))


def _nomes_vindos_de_sqlalchemy(arvore: ast.Module) -> set[str]:
    """Nomes que este arquivo ligou a algo de `sqlalchemy` (respeitando `as`)."""
    nomes: set[str] = set()
    for node in ast.walk(arvore):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "sqlalchemy":
            nomes.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "sqlalchemy":
                    nomes.add(alias.asname or alias.name.split(".")[0])
    return nomes


def encontrar_queries_em_router(path: Path) -> list[str]:
    """Regra 1 do §8: nenhum `router.py` monta ou executa statement."""
    arvore = _parse(path)
    de_sqlalchemy = _nomes_vindos_de_sqlalchemy(arvore)
    achados: list[str] = []
    for node in ast.walk(arvore):
        if isinstance(node, ast.Call):
            achados += _query_nesta_chamada(path, node, de_sqlalchemy)
    return achados


def _query_nesta_chamada(path: Path, node: ast.Call, de_sqlalchemy: set[str]) -> list[str]:
    """Uma chamada é query de duas formas: pelo NOME (`select(...)`) ou pelo ATRIBUTO
    (`session.execute(...)`, `stmt.where(...)`).

    O `de_sqlalchemy` existe porque nome sozinho não basta: um `update(...)` pode ser o do
    SQLAlchemy ou o método de um dicionário. Só os construtores INEQUÍVOCOS dispensam essa
    conferência.
    """
    alvo = node.func
    if isinstance(alvo, ast.Name):
        suspeito = alvo.id in _CONSTRUTORES_SQL and alvo.id in de_sqlalchemy
        inequivoco = alvo.id in _CONSTRUTORES_SQL_INEQUIVOCOS
        return [f"{_rel(path)}:{node.lineno} {alvo.id}(...)"] if suspeito or inequivoco else []
    if isinstance(alvo, ast.Attribute):
        executa = alvo.attr in _METODOS_DE_EXECUCAO
        constroi = alvo.attr in _CONSTRUTORES_SQL_INEQUIVOCOS and _raiz(alvo) in de_sqlalchemy
        return [f"{_rel(path)}:{node.lineno} .{alvo.attr}(...)"] if executa or constroi else []
    return []


def _raiz(node: ast.expr) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _e_modulo_de_repositorio(modulo: str) -> bool:
    partes = modulo.split(".")
    return any(parte == "repository" or parte.endswith("_repository") for parte in partes)


def encontrar_repositorio_em_router(path: Path) -> list[str]:
    """Regra 2 do §8: router fala com service; service fala com repositório.

    Pega as duas formas de furar: importar o módulo (`from ... import repository`) e
    importar um símbolo dele (`from ...repository import XRepository`). O sufixo
    `Repository` no nome importado cobre o reexport — `from app.domain.x import
    XRepository` não passa por baixo.
    """
    achados: list[str] = []
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.ImportFrom):
            achados += _furos_em_import_from(path, node)
        elif isinstance(node, ast.Import):
            achados += [
                f"{_rel(path)}:{node.lineno} import {alias.name}"
                for alias in node.names
                if _e_modulo_de_repositorio(alias.name)
            ]
    return achados


def _furos_em_import_from(path: Path, node: ast.ImportFrom) -> list[str]:
    """`from X import Y` fura de duas formas: `X` é o módulo de repositório, ou `Y` é.

    Quando o próprio módulo é o repositório, o import inteiro é o furo — não adianta
    listar símbolo por símbolo.
    """
    modulo = node.module or ""
    if _e_modulo_de_repositorio(modulo):
        importados = ", ".join(alias.name for alias in node.names)
        return [f"{_rel(path)}:{node.lineno} from {modulo} import {importados}"]
    return [
        f"{_rel(path)}:{node.lineno} from {modulo} import {alias.name}"
        for alias in node.names
        if _e_modulo_de_repositorio(alias.name) or alias.name.endswith("Repository")
    ]


def encontrar_integracao_concreta_em_service(path: Path) -> list[str]:
    """Regra 3 do §8: service depende da abstração, não do cliente.

    A checagem mira no MÓDULO, não no pacote: `app.integrations.datajud.base` passa,
    `app.integrations.datajud.client` não. Ver `_MODULOS_DE_CONTRATO`.
    """
    achados: list[str] = []
    for node in ast.walk(_parse(path)):
        # Filtrar aqui, e não dentro do helper, é o que dá a `node` um tipo com
        # `lineno`: `ast.walk` devolve `ast.AST`, e nem todo nó tem posição.
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for modulo in _modulos_importados(node):
            if _e_integracao_concreta(modulo):
                achados.append(f"{_rel(path)}:{node.lineno} {modulo}")
    return achados


def _modulos_importados(node: ast.Import | ast.ImportFrom) -> list[str]:
    """Os módulos que um nó de import traz."""
    if isinstance(node, ast.ImportFrom):
        return [node.module or ""]
    return [alias.name for alias in node.names]


def _e_integracao_concreta(modulo: str) -> bool:
    """`app.integrations.datajud.base` passa; `...datajud.client` não.

    `from app.integrations.x import y` — com três partes — também não passa: importar o
    pacote roda o `__init__`, que reexporta o client. É acoplamento igual, só mais
    discreto.
    """
    partes = modulo.split(".")
    if partes[:2] != ["app", "integrations"]:
        return False
    return len(partes) < 4 or partes[-1] not in _MODULOS_DE_CONTRATO


def _violacoes(
    nome_do_arquivo: str,
    checagem: object,
    excecoes: frozenset[str],
) -> list[str]:
    achados: list[str] = []
    for path in _arquivos(nome_do_arquivo):
        if _rel(path) in excecoes:
            continue
        achados.extend(checagem(path))  # type: ignore[operator]
    return achados


def test_nenhum_router_monta_ou_executa_query() -> None:
    """§5: «`router` só faz HTTP. […] Router com `select()` dentro é bug»."""
    achados = _violacoes("router.py", encontrar_queries_em_router, EXCECOES_QUERY_EM_ROUTER)
    assert achados == [], f"query dentro de router: {achados}"


def test_nenhum_router_importa_repositorio() -> None:
    """§5: o router que chama o repositório pula o service e leva a regra junto."""
    achados = _violacoes(
        "router.py", encontrar_repositorio_em_router, EXCECOES_REPOSITORIO_EM_ROUTER
    )
    assert achados == [], f"router importando repositório: {achados}"


def test_nenhum_service_importa_integracao_concreta() -> None:
    """§5 (DIP): «`import openrouter` dentro de service é bug»."""
    achados = _violacoes(
        "service.py",
        encontrar_integracao_concreta_em_service,
        EXCECOES_INTEGRACAO_EM_SERVICE,
    )
    assert achados == [], f"service acoplado a integração concreta: {achados}"


def test_as_listas_de_excecao_estao_vazias() -> None:
    """Regra 5 da spec 118: a entrega é sem exceção nenhuma.

    Este teste é o que impede a lista de virar gaveta. Adicionar uma exceção passa a
    exigir editar este teste também — e aí a conversa acontece na revisão, que é onde
    ela deveria acontecer.
    """
    assert sorted(EXCECOES_QUERY_EM_ROUTER) == []
    assert sorted(EXCECOES_REPOSITORIO_EM_ROUTER) == []
    assert sorted(EXCECOES_INTEGRACAO_EM_SERVICE) == []
