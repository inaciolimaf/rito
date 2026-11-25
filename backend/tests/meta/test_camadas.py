"""As três regras de camada do `CLAUDE.md` §5 que dá para verificar por AST (spec 118).

**Este é um gate por proxy e a honestidade sobre isso é parte do gate.**

O que ele verifica são três propriedades sintáticas, exatas e binárias:

1. existe chamada de query dentro de um router;
2. um router importa de um módulo `repository`;
3. um módulo de regra importa de `app.integrations` algo que faz I/O.

O que ele **não** verifica é SOLID. Não há teste para "a responsabilidade é única" ou
"esta é a abstração certa" — isso é revisão humana e continua sendo. Um service pode
passar nas três checagens e ainda ter regra de negócio no lugar errado. O que estas
checagens compram é o piso: os três sintomas mais baratos de detectar e os mais comuns,
cada um dos quais, se passar, vira dívida que a próxima refatoração paga mais caro.

AST e nunca regex, pelo mesmo motivo do `test_no_rag.py`: `select` aparece dentro de
string e de comentário, e um gate que dá falso positivo em comentário é um gate que
alguém desliga.

## O que a spec 139 consertou: o gate só abria `router.py` e `service.py`

Até a 139 o universo do gate era `rglob("router.py")` + `rglob("service.py")`. Em
`app/domain/` isso são 39 + 39 arquivos vistos e **16 invisíveis**: os cinco routers da
IA, `documents/extraction_router.py`, `publications/analysis_router.py`, nove
`*_service.py`, mais `automations/engine.py`, `templates/generate.py`, `ai/copilot.py`,
`posts/listing.py` e `financial/dashboard.py`, que são camada sem o nome.

Medido: um `vazamento_router.py` com `select()`, `session.execute()` e
`CustomerRepository` importado deixava os quatro testes VERDES; o mesmo arquivo
renomeado para `router.py` reprovava três deles. O que decidia entre verde e vermelho
era o nome do arquivo, não o código. E não era hipótese — havia duas violações vivas
escondidas ali (`documents/extraction_router.py:19` e `automations/engine.py:130`).

Hoje o universo é o PAPEL, não o nome:

- **router** = arquivo que se chama `router.py`/`*_router.py` **ou** que instancia um
  `APIRouter`. As duas leituras coincidem hoje (46 arquivos, sem diferença nenhuma
  entre elas) — e é justamente por coincidirem que valem as duas: quem renomear o
  arquivo continua pego pelo `APIRouter`, quem trocar o framework continua pego pelo
  nome.
- **camada de regra** (o escopo da regra 3) = todo módulo de `app/domain/` que não é
  router nem infraestrutura de dado (`models`, `schemas`, `repository`, `exceptions` e
  seus sufixados). É mais largo que "arquivo chamado service" de propósito: o §5 cobra
  DIP de quem carrega regra, e regra mora em `engine.py`, `listing.py`, `dashboard.py`
  e `generate.py` tanto quanto em `service.py`.

Duas coisas que ele deliberadamente NÃO pega, medidas na entrega da 118 para quem
vier depois não precisar redescobrir:

- `session.get(Modelo, id)`, `session.add`, `session.flush` e `session.delete` dentro de
  um router. São 9 ocorrências em `automations`, `webhooks` e `schedule`. A regra 1 do §8
  da 118 lista `select/insert/update/delete/session.execute`, e ampliar a checagem para
  `.get(` sem qualificar o objeto encheria de falso positivo (`dict.get`, `payload.get`).
- as camadas de `app/public/` — ver o comentário de `_RAIZ` logo abaixo.
"""

import ast
import functools
from collections.abc import Callable
from pathlib import Path

import pytest

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
# Regra 5 da spec 118: na entrega elas estão VAZIAS. Uma exceção legítima entra aqui, com
# justificativa escrita, e nunca como diretiva de supressão espalhada pelo código: a
# exceção que mora no gate é contável e revisável; a que mora no arquivo violador some.
# Cada entrada é um caminho relativo a `backend/`.
#
# Spec 139: a primeira exceção da história do gate, e o motivo está escrito no
# `docs/DIVIDA-TECNICA.md`. `AutomationEngine.ai_runner` monta o provider sob demanda
# (`app.integrations.openrouter.factory`) porque o motor é chamado de dentro de use cases
# do domínio, que não têm — e não devem ter — acesso ao `app.state`. Tirar o import de lá
# exige injetar o runner nos OITO pontos que constroem o motor (`lawsuits/service.py`,
# `lawsuits/board_service.py`, `posts/completion.py`, `publications/service.py`,
# `automations/sweep.py` ×2, `automations/router.py` ×2) e nas duas raízes de composição
# (`app/main.py` e o worker) — refatoração de nove arquivos, que não cabe numa spec de
# correção de gate e que mudaria comportamento se feita pela metade (sem o fallback, toda
# decisão por IA disparada por evento de domínio cairia no ramo padrão, em silêncio).
# O `test_toda_excecao_ainda_viola_o_gate` abaixo faz esta entrada se apagar sozinha no
# dia em que a injeção chegar.
# --------------------------------------------------------------------------------------
EXCECOES_QUERY_EM_ROUTER: frozenset[str] = frozenset()
EXCECOES_REPOSITORIO_EM_ROUTER: frozenset[str] = frozenset()
EXCECOES_INTEGRACAO_EM_SERVICE: frozenset[str] = frozenset({"app/domain/automations/engine.py"})

# Construtores de query do SQLAlchemy. Só contam quando o próprio arquivo os importa de
# `sqlalchemy` — `update`/`delete` são palavras comuns e um `service.update(...)` dentro de
# um router é exatamente o que queremos que o router faça.
_CONSTRUTORES_SQL = frozenset(
    {"select", "insert", "update", "delete", "text", "exists", "union", "union_all"}
)

# Estes dois não precisam de import para serem denúncia: `select(` e `insert(` num router
# não são outra coisa, mesmo importados com alias ou por `sqlalchemy.select`.
_CONSTRUTORES_SQL_INEQUIVOCOS = frozenset({"select", "insert"})

# `session.execute(...)` e irmão. Router não executa statement: nem o dele, nem o de
# ninguém. Os dois nomes são inequívocos — nenhum service do projeto chama um método
# `execute` ou `exec_driver_sql`.
_METODOS_DE_EXECUCAO = frozenset({"execute", "exec_driver_sql"})

# `stream` é o terceiro método de execução do SQLAlchemy, e o único cujo NOME colide com
# vocabulário de domínio: `ai/threads_router.py:333` faz `async for ... in service.stream(...)`
# sobre um gerador assíncrono do service, que é exatamente o que um router deve fazer.
# Medido na spec 139: ampliar o universo do gate transformava esse `stream` no único
# achado da regra 1, um falso positivo — e falso positivo mata gate tão rápido quanto
# falso negativo. Por isso `stream` só denuncia quando o receptor é uma sessão/conexão,
# que é o único objeto sobre o qual ele significa "execute isto no banco".
_METODOS_DE_STREAM = frozenset({"stream", "stream_scalars"})
_RECEPTORES_DE_SESSAO = frozenset({"session", "conn", "connection", "db", "bind", "engine"})

# Módulos de `app.integrations` que uma camada de regra PODE importar: contratos e formas
# de dado.
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

# Arquivos de `app/domain/` que são forma de dado, não regra: ficam fora da regra 3. A
# lista é por PAPEL (o que o arquivo guarda), não por conveniência — `models.py` declara
# tabela, `schemas.py` declara DTO, `repository.py` é a camada que PODE falar com o banco
# e `exceptions.py` é vocabulário de erro.
_INFRA_DE_DADO = frozenset({"models", "schemas", "repository", "exceptions"})
_SUFIXOS_DE_INFRA = ("_models", "_schemas", "_repository")


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _rel(path: Path) -> str:
    """Caminho relativo a `backend/`, ou absoluto quando o arquivo mora fora dele.

    Os casos plantados dos testes deste arquivo moram em `tmp_path`, e um gate que
    estoura ao analisar um arquivo de fora não consegue ser provado mordendo.
    """
    try:
        return str(path.relative_to(BACKEND_DIR))
    except ValueError:
        return str(path)


@functools.cache
def _modulos() -> tuple[tuple[Path, ast.Module], ...]:
    """Todo `.py` de `app/domain/`, já parseado. O cache existe porque os quatro testes
    varrem o mesmo universo."""
    return tuple(
        (path, _parse(path))
        for path in sorted(_RAIZ.rglob("*.py"))
        if "__pycache__" not in path.parts and path.name != "__init__.py"
    )


def _declara_apirouter(arvore: ast.Module) -> bool:
    return any(
        isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "APIRouter"
        for no in ast.walk(arvore)
    )


def e_router(path: Path, arvore: ast.Module) -> bool:
    """Router pelo nome OU pelo papel — as duas leituras, de propósito (ver o módulo)."""
    return path.stem == "router" or path.stem.endswith("_router") or _declara_apirouter(arvore)


def e_camada_de_regra(path: Path, arvore: ast.Module) -> bool:
    """O escopo da regra 3: quem carrega regra de negócio, tenha "service" no nome ou não."""
    if e_router(path, arvore):
        return False
    return path.stem not in _INFRA_DE_DADO and not path.stem.endswith(_SUFIXOS_DE_INFRA)


@functools.cache
def _classificados() -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    """(routers, camadas de regra). Cacheado: a classificação varre a AST de 200 arquivos
    e os testes parametrizados do universo a consultam 17 vezes — sem cache, o gate custa
    1,4 s a mais no orçamento do CLAUDE.md §3."""
    modulos = _modulos()
    achados = [(path, e_router(path, arvore)) for path, arvore in modulos]
    encontrados_routers = tuple(path for path, roteia in achados if roteia)
    regras = tuple(
        path
        for (path, roteia), (_, arvore) in zip(achados, modulos, strict=True)
        if not roteia and e_camada_de_regra(path, arvore)
    )
    return encontrados_routers, regras


def routers() -> list[Path]:
    return list(_classificados()[0])


def camadas_de_regra() -> list[Path]:
    return list(_classificados()[1])


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
    """Regra 1 do §8: nenhum router monta ou executa statement."""
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
        constroi = alvo.attr in _CONSTRUTORES_SQL_INEQUIVOCOS and _raiz(alvo) in de_sqlalchemy
        if _executa_statement(alvo) or constroi:
            return [f"{_rel(path)}:{node.lineno} .{alvo.attr}(...)"]
    return []


def _executa_statement(alvo: ast.Attribute) -> bool:
    """`.execute(` sempre; `.stream(` só sobre sessão/conexão (ver `_METODOS_DE_STREAM`)."""
    if alvo.attr in _METODOS_DE_EXECUCAO:
        return True
    return alvo.attr in _METODOS_DE_STREAM and _receptor(alvo) in _RECEPTORES_DE_SESSAO


def _receptor(alvo: ast.Attribute) -> str | None:
    """O objeto IMEDIATO da chamada: `self.session.stream(...)` → `session`.

    O receptor imediato, e não a raiz da cadeia, é o que distingue a sessão do resto:
    a raiz de `self.session.stream(...)` é `self`, que não diz nada.
    """
    if isinstance(alvo.value, ast.Name):
        return alvo.value.id
    if isinstance(alvo.value, ast.Attribute):
        return alvo.value.attr
    return None


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


@functools.cache
def _protocolos_de(modulo: str) -> frozenset[str]:
    """As classes `Protocol` declaradas num módulo de `app.integrations`.

    Um `Protocol` É a abstração que o DIP manda depender — importá-lo não acopla a
    implementação nenhuma, mesmo que ele more num arquivo cujo nome não está em
    `_MODULOS_DE_CONTRATO`. É o caso do `DocumentMailer`, que a spec 067 pôs em
    `messaging/document_email.py` ao lado do `SmtpDocumentMailer` concreto: sem esta
    leitura, ampliar o universo do gate transformava `templates/generate.py` num falso
    positivo, e a alternativa (liberar o módulo inteiro) liberaria junto o mailer real.
    """
    caminho = BACKEND_DIR / Path(*modulo.split(".")).with_suffix(".py")
    if not caminho.is_file():
        return frozenset()
    return frozenset(
        no.name
        for no in ast.walk(_parse(caminho))
        if isinstance(no, ast.ClassDef) and any(_nome_da_base(b) == "Protocol" for b in no.bases)
    )


def _nome_da_base(base: ast.expr) -> str | None:
    if isinstance(base, ast.Name):
        return base.id
    return base.attr if isinstance(base, ast.Attribute) else None


def encontrar_integracao_concreta_em_service(path: Path) -> list[str]:
    """Regra 3 do §8: a camada de regra depende da abstração, não do cliente.

    A checagem mira no MÓDULO, não no pacote: `app.integrations.datajud.base` passa,
    `app.integrations.datajud.client` não. Ver `_MODULOS_DE_CONTRATO` — e
    `_protocolos_de`, para o símbolo que é contrato num módulo que não é.
    """
    achados: list[str] = []
    for node in ast.walk(_parse(path)):
        # Filtrar aqui, e não dentro do helper, é o que dá a `node` um tipo com
        # `lineno`: `ast.walk` devolve `ast.AST`, e nem todo nó tem posição.
        if isinstance(node, ast.ImportFrom):
            achados += _integracoes_em_import_from(path, node)
        elif isinstance(node, ast.Import):
            achados += [
                f"{_rel(path)}:{node.lineno} {alias.name}"
                for alias in node.names
                if _e_integracao_concreta(alias.name)
            ]
    return achados


def _integracoes_em_import_from(path: Path, node: ast.ImportFrom) -> list[str]:
    modulo = node.module or ""
    if not _e_integracao_concreta(modulo):
        return []
    contratos = _protocolos_de(modulo)
    return [
        f"{_rel(path)}:{node.lineno} {modulo}.{alias.name}"
        for alias in node.names
        if alias.name not in contratos
    ]


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
    arquivos: list[Path],
    checagem: Callable[[Path], list[str]],
    excecoes: frozenset[str],
) -> list[str]:
    achados: list[str] = []
    for path in arquivos:
        if _rel(path) in excecoes:
            continue
        achados.extend(checagem(path))
    return achados


# --------------------------------------------------------------------------------------
# Os três gates
# --------------------------------------------------------------------------------------


def test_nenhum_router_monta_ou_executa_query() -> None:
    """§5: «`router` só faz HTTP. […] Router com `select()` dentro é bug»."""
    achados = _violacoes(routers(), encontrar_queries_em_router, EXCECOES_QUERY_EM_ROUTER)
    assert achados == [], f"query dentro de router: {achados}"


def test_nenhum_router_importa_repositorio() -> None:
    """§5: o router que chama o repositório pula o service e leva a regra junto."""
    achados = _violacoes(routers(), encontrar_repositorio_em_router, EXCECOES_REPOSITORIO_EM_ROUTER)
    assert achados == [], f"router importando repositório: {achados}"


def test_nenhuma_camada_de_regra_importa_integracao_concreta() -> None:
    """§5 (DIP): «`import openrouter` dentro de service é bug»."""
    achados = _violacoes(
        camadas_de_regra(),
        encontrar_integracao_concreta_em_service,
        EXCECOES_INTEGRACAO_EM_SERVICE,
    )
    assert achados == [], f"camada de regra acoplada a integração concreta: {achados}"


# --------------------------------------------------------------------------------------
# O universo do gate — o que a spec 139 existe para impedir de encolher de novo
# --------------------------------------------------------------------------------------

# Os 16 arquivos que o gate NÃO abria até a spec 139, um a um. A lista é literal de
# propósito: um universo medido por `len()` volta a encolher sem ninguém notar, porque o
# número continua parecendo grande. Estes nomes são o "conferido contra o universo" da
# lição da dívida 40.
_ROUTERS_SEM_O_NOME = (
    "ai/actions_router.py",
    "ai/analytics_router.py",
    "ai/copilot_router.py",
    "ai/editor_router.py",
    "ai/threads_router.py",
    "documents/extraction_router.py",
    "publications/analysis_router.py",
)
_CAMADAS_SEM_O_NOME = (
    "ai/copilot.py",
    "automations/engine.py",
    "datajud/movement_sync_service.py",
    "financial/dashboard.py",
    "lawsuits/board_service.py",
    "lawsuits/stagnation_service.py",
    "posts/listing.py",
    "posts/recurrence_service.py",
    "reports/tabular_service.py",
    "templates/generate.py",
)


def _relativos(arquivos: list[Path]) -> set[str]:
    return {str(path.relative_to(_RAIZ)) for path in arquivos}


@pytest.mark.parametrize("arquivo", _ROUTERS_SEM_O_NOME)
def test_o_gate_abre_os_routers_que_nao_se_chamam_router_py(arquivo: str) -> None:
    """Regra 1 da spec 139: o universo é o papel, não o nome do arquivo."""
    assert arquivo in _relativos(routers())


@pytest.mark.parametrize("arquivo", _CAMADAS_SEM_O_NOME)
def test_o_gate_abre_as_camadas_de_regra_que_nao_se_chamam_service_py(arquivo: str) -> None:
    """Regra 2 da spec 139: regra de negócio mora em `engine.py` e `dashboard.py` também."""
    assert arquivo in _relativos(camadas_de_regra())


def test_o_universo_nao_encolheu() -> None:
    """O contra-controle dos dois de cima: `models.py` e `repository.py` continuam FORA.

    Um gate que passasse a abrir tudo também estaria errado — a regra 3 cobra DIP de quem
    carrega regra, e `models.py` é forma de dado. Sem este teste, "ampliar o universo"
    e "desligar a classificação" seriam indistinguíveis.
    """
    camadas = _relativos(camadas_de_regra())
    assert "customers/models.py" not in camadas
    assert "customers/repository.py" not in camadas
    assert "customers/schemas.py" not in camadas
    assert "customers/exceptions.py" not in camadas
    # E o router continua fora da regra 3: quem cobra o router são as regras 1 e 2.
    assert "customers/router.py" not in camadas
    assert "customers/service.py" in camadas


# --------------------------------------------------------------------------------------
# Casos plantados — o gate provado MORDENDO, nos dois lados
#
# Versionados aqui, como fez a spec 131: um caso plantado que não fica no repositório
# prova o gate no dia em que foi escrito e nada depois disso.
# --------------------------------------------------------------------------------------

_ROUTER_QUE_VAZA = '''\
"""Caso plantado (spec 139): router com os três sintomas, e sem `router` no nome."""

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.customers.repository import CustomerRepository

router = APIRouter()


@router.get("/vazamento")
async def vazar(session: AsyncSession) -> None:
    stmt = select(1)
    repo = CustomerRepository(session)
    await session.execute(stmt)
    return repo
'''

_ROUTER_LIMPO = '''\
"""Controle (spec 139): router que só faz HTTP — não pode reprovar."""

from fastapi import APIRouter, Depends

from app.domain.customers.service import CustomerService

router = APIRouter()


@router.get("/limpo")
async def listar(service: CustomerService = Depends()) -> None:
    async for item in service.stream(None):
        print(item)
    await service.update({"a": 1})
'''

_CAMADA_QUE_VAZA = '''\
"""Caso plantado (spec 139): regra acoplada ao cliente, e sem `service` no nome."""

from app.integrations.datajud.client import DataJudClient


class Motor:
    def rodar(self) -> None:
        from app.integrations.openrouter.factory import create_llm_provider

        create_llm_provider()
        DataJudClient()
'''

_CAMADA_LIMPA = '''\
"""Controle (spec 139): regra que depende só de contrato — não pode reprovar."""

from app.integrations.messaging.document_email import DocumentMailer
from app.integrations.openrouter.types import LLMProvider
from app.integrations.storage.base import FileStorage


class Servico:
    def __init__(self, mailer: DocumentMailer, llm: LLMProvider, storage: FileStorage) -> None:
        self.mailer = mailer
'''


def _plantar(tmp_path: Path, nome: str, fonte: str) -> Path:
    caminho = tmp_path / nome
    caminho.write_text(fonte, encoding="utf-8")
    return caminho


def test_router_plantado_com_outro_nome_reprova_as_duas_regras(tmp_path: Path) -> None:
    """A prova do achado: este arquivo dava `4 passed` antes da spec 139."""
    plantado = _plantar(tmp_path, "vazamento_router.py", _ROUTER_QUE_VAZA)

    assert e_router(plantado, _parse(plantado))
    assert encontrar_queries_em_router(plantado) != []
    assert encontrar_repositorio_em_router(plantado) != []


def test_router_plantado_sem_router_no_nome_ainda_e_router(tmp_path: Path) -> None:
    """O `APIRouter` denuncia mesmo quando o nome não ajuda — `copilot.py`, `sse.py`."""
    plantado = _plantar(tmp_path, "atalho.py", _ROUTER_QUE_VAZA)

    assert e_router(plantado, _parse(plantado))
    # E, sendo router, sai do escopo da regra 3: quem o cobra são as regras 1 e 2.
    assert not e_camada_de_regra(plantado, _parse(plantado))


def test_router_limpo_nao_reprova(tmp_path: Path) -> None:
    """O outro lado. `service.stream(...)` e `service.update(...)` são o que um router
    DEVE fazer — e os dois casam com nomes que a regra 1 conhece."""
    plantado = _plantar(tmp_path, "limpo_router.py", _ROUTER_LIMPO)

    assert e_router(plantado, _parse(plantado))
    assert encontrar_queries_em_router(plantado) == []
    assert encontrar_repositorio_em_router(plantado) == []


def test_stream_de_sessao_reprova_e_stream_de_service_nao(tmp_path: Path) -> None:
    """A borda exata do falso positivo medido em `ai/threads_router.py:333`."""
    fonte = (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "async def rota(session, service):\n"
        "    async for x in service.stream(1):\n"
        "        print(x)\n"
    )
    assert encontrar_queries_em_router(_plantar(tmp_path, "a_router.py", fonte)) == []

    fonte_ruim = fonte.replace("service.stream(1)", "session.stream(1)")
    achados = encontrar_queries_em_router(_plantar(tmp_path, "b_router.py", fonte_ruim))
    assert [a.split(" ")[-1] for a in achados] == [".stream(...)"]

    fonte_self = fonte.replace("service.stream(1)", "self.session.stream(1)")
    assert encontrar_queries_em_router(_plantar(tmp_path, "c_router.py", fonte_self)) != []


def test_camada_plantada_com_outro_nome_reprova_a_regra_3(tmp_path: Path) -> None:
    """A prova do segundo achado: `engine.py` e `dashboard.py` eram invisíveis."""
    plantado = _plantar(tmp_path, "engine.py", _CAMADA_QUE_VAZA)

    assert e_camada_de_regra(plantado, _parse(plantado))
    achados = encontrar_integracao_concreta_em_service(plantado)
    assert len(achados) == 2, achados
    assert any("openrouter.factory" in achado for achado in achados)
    assert any("datajud.client" in achado for achado in achados)


def test_camada_limpa_nao_reprova(tmp_path: Path) -> None:
    """O outro lado: contrato (`base`, `types`) e `Protocol` importado de módulo que não
    é de contrato — nenhum dos três pode reprovar."""
    plantado = _plantar(tmp_path, "dashboard.py", _CAMADA_LIMPA)

    assert e_camada_de_regra(plantado, _parse(plantado))
    assert encontrar_integracao_concreta_em_service(plantado) == []


def test_implementacao_concreta_do_mesmo_modulo_do_protocolo_reprova(tmp_path: Path) -> None:
    """A liberação é do SÍMBOLO, não do módulo: `SmtpDocumentMailer` mora ao lado do
    `DocumentMailer` e continua sendo acoplamento."""
    fonte = "from app.integrations.messaging.document_email import SmtpDocumentMailer\n"
    plantado = _plantar(tmp_path, "generate.py", fonte)

    assert encontrar_integracao_concreta_em_service(plantado) != []


def test_arquivo_de_dado_fica_fora_da_regra_3(tmp_path: Path) -> None:
    """Contra-controle da classificação: `models.py` não é camada de regra."""
    plantado = _plantar(tmp_path, "models.py", _CAMADA_QUE_VAZA)

    assert not e_camada_de_regra(plantado, _parse(plantado))


# --------------------------------------------------------------------------------------
# As listas de exceção
# --------------------------------------------------------------------------------------


def test_as_listas_de_excecao_sao_exatamente_as_declaradas() -> None:
    """Regra 5 da spec 118, com o número de hoje em vez de "vazias".

    Este teste é o que impede a lista de virar gaveta. Adicionar uma exceção passa a
    exigir editar este teste também — e aí a conversa acontece na revisão, que é onde
    ela deveria acontecer. Mudou de «tem que estar vazia» para «é exatamente esta lista»
    na spec 139, quando o universo ampliado revelou a primeira exceção legítima; a
    propriedade que importa (não dá para acrescentar em silêncio) é a mesma.
    """
    assert sorted(EXCECOES_QUERY_EM_ROUTER) == []
    assert sorted(EXCECOES_REPOSITORIO_EM_ROUTER) == []
    assert sorted(EXCECOES_INTEGRACAO_EM_SERVICE) == ["app/domain/automations/engine.py"]


def test_toda_excecao_ainda_viola_o_gate() -> None:
    """Exceção que deixou de ser necessária tem de sair — e sai reprovando.

    É a diferença entre uma lista de exceções e uma gaveta: aqui, o dia em que alguém
    injetar o runner no `AutomationEngine` o gate fica VERMELHO até a linha ser apagada.
    Sem isto, a exceção sobreviveria à própria causa, que é como toda lista de exceções
    do mundo cresce sem nunca diminuir.
    """
    orfas = [
        entrada
        for entrada in sorted(EXCECOES_INTEGRACAO_EM_SERVICE)
        if encontrar_integracao_concreta_em_service(BACKEND_DIR / entrada) == []
    ]
    assert orfas == [], (
        "exceção do gate de camadas que já não viola nada — apague a linha de "
        f"EXCECOES_INTEGRACAO_EM_SERVICE: {orfas}"
    )
