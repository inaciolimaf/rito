"""Query é montada pelo builder, não escrita como texto (spec 127).

O `CLAUDE.md` §5 diz quem monta query (`repository`). O que ele não dizia era **com o
quê** — e até a 127 o backend tinha 62 statements escritos como string de SQL espalhados
por 14 arquivos. Nenhum deles era vulnerável: os parâmetros iam ligados, e os poucos
identificadores interpolados vinham de allowlist. O custo era outro, e era de manutenção:

- coluna renomeada numa migration não quebra uma string — ela quebra em produção, na
  primeira vez que aquele caminho roda;
- `mypy` não enxerga nada dentro de aspas, então nenhum desses statements participava da
  checagem de tipos que o resto do backend paga para ter;
- o `S608` do Bandit passava a acusar toda f-string que se parecesse com SQL, e a resposta
  virava `# noqa` com justificativa — uma exceção por vez, cada uma correta, e o conjunto
  ensinando que `S608` se silencia.

Este gate impede a volta. Ele é AST e nunca regex, pelo mesmo motivo do `test_no_rag.py`:
a palavra `text` aparece em comentário, em docstring e em `read_text`, e um gate que dá
falso positivo em comentário é um gate que alguém desliga.

## A regra, exata e binária

`text(...)` dentro de `app/` só é permitido em dois lugares:

1. como valor de `server_default=` / `server_onupdate=` — ali não é query, é o DEFAULT da
   coluna no DDL, e o SQLAlchemy não tem outra forma de escrevê-lo;
2. nas exceções nomeadas em `EXCECOES`, cada uma com a justificativa escrita ao lado.

`exec_driver_sql` e `execute("<string>")` são proibidos sem exceção — os dois passam por
cima do compilador do SQLAlchemy inteiro.

## O que este gate NÃO cobre, de propósito

- **As migrations do Alembic.** Elas são DDL (`CREATE POLICY`, `CREATE FUNCTION`,
  `CREATE MATERIALIZED VIEW`), e o query builder não monta DDL. Também não se editam
  depois de commitadas (`CLAUDE.md` §9), então nem "voltar atrás" existe ali.
- **`app/core/rls.py::enable_rls_statements`**, que devolve as strings de DDL que as
  migrations aplicam — mesma natureza do item acima.
- **O SQL que o MODELO escreve** (spec 089). Ele é o produto daquela feature; ver a
  exceção de `_run_readonly` abaixo.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
APP_DIR = BACKEND_DIR / "app"

# `text()` só pode aparecer aqui como DEFAULT de coluna — não é consulta, é DDL da tabela.
_KWARGS_DE_DDL = frozenset({"server_default", "server_onupdate"})

# --------------------------------------------------------------------------------------
# Exceções — versionadas aqui de propósito, no mesmo idioma do `test_camadas.py` (spec
# 118, §4.E): a exceção que mora no gate é contável e revisável; a que mora no arquivo
# violador some. A chave é `<caminho relativo a backend/>::<função>`, e não o número da
# linha, porque linha muda quando alguém mexe no arquivo de cima e a exceção não deve
# expirar por causa disso.
#
# São TRÊS motivos, e nenhum tem conserto dentro do query builder:
#
# 1. DDL. `REFRESH MATERIALIZED VIEW CONCURRENTLY` não é consulta e o SQLAlchemy não
#    tem construtor para ele.
# 2. Comando de SESSÃO. `SET LOCAL`, `SAVEPOINT` e `ROLLBACK TO SAVEPOINT` mudam o estado
#    da transação; não têm linhas, não têm colunas, não passam por compilador de query.
# 3. A consulta é o PRODUTO. No text-to-SQL da 089 quem escreve o SELECT é o modelo; o
#    que protege aquele caminho é o `check_sql` e a transação somente-leitura, não a
#    forma como o statement é montado.
# --------------------------------------------------------------------------------------
EXCECOES: dict[str, str] = {
    "app/core/materialized_view.py::refresh_materialized_view_concurrently": (
        "DDL: REFRESH MATERIALIZED VIEW CONCURRENTLY não tem construtor no builder."
    ),
    "app/workers/aggregates.py::_refresh_view": (
        "DDL: mesmo REFRESH da linha acima, no caminho do beat."
    ),
    "app/domain/ai/analytics.py::_run_readonly": (
        "Comando de sessão (SET LOCAL statement_timeout / transaction_read_only) e a SQL "
        "que o próprio modelo escreveu — o produto da spec 089."
    ),
    "app/domain/ai/analytics.py::_log_failed_run": (
        "Comando de sessão: ROLLBACK TO SAVEPOINT, para poder auditar a falha numa "
        "transação que o erro já abortou."
    ),
    "app/domain/ai/analytics.py::run_sql": (
        "Comando de sessão: SAVEPOINT / ROLLBACK TO SAVEPOINT, que é o que torna o modo "
        "somente-leitura reversível."
    ),
}


def _e_chamada_de_text(node: ast.Call) -> bool:
    """`text(...)`, importado direto ou por `sqlalchemy.text(...)`."""
    alvo = node.func
    if isinstance(alvo, ast.Name):
        return alvo.id == "text"
    return isinstance(alvo, ast.Attribute) and alvo.attr == "text"


def _e_execucao_de_string(node: ast.Call) -> bool:
    """`.execute("SELECT ...")` / `.exec_driver_sql(...)` — SQL crua no driver."""
    alvo = node.func
    if not isinstance(alvo, ast.Attribute):
        return False
    if alvo.attr == "exec_driver_sql":
        return True
    primeiro = node.args[0] if node.args else None
    return (
        alvo.attr in {"execute", "scalar", "scalars", "stream"}
        and isinstance(primeiro, ast.Constant)
        and isinstance(primeiro.value, str)
    )


def _defaults_de_coluna(arvore: ast.Module) -> set[int]:
    """Os `text()` que são DEFAULT de coluna, identificados pelo objeto (não pela linha)."""
    permitidos: set[int] = set()
    for node in ast.walk(arvore):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg in _KWARGS_DE_DDL and isinstance(kw.value, ast.Call):
                permitidos.add(id(kw.value))
    return permitidos


def _funcao_de_cada_linha(arvore: ast.Module) -> dict[int, str]:
    """Linha → nome da função que a contém. A mais interna ganha (aninhamento)."""
    dono: dict[int, str] = {}
    for node in ast.walk(arvore):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for linha in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                dono[linha] = node.name
    return dono


def _sql_em_string_de(caminho: Path) -> list[tuple[str, int, str]]:
    """Todo SQL escrito como string num arquivo — (chave, linha, trecho).

    Devolve TAMBÉM o que está em `EXCECOES`: quem filtra é cada teste, e é o que permite
    a `test_toda_excecao_declarada_ainda_existe` perguntar o contrário.
    """
    arvore = ast.parse(caminho.read_text())
    permitidos = _defaults_de_coluna(arvore)
    donos = _funcao_de_cada_linha(arvore)
    relativo = caminho.relative_to(BACKEND_DIR).as_posix()
    achados: list[tuple[str, int, str]] = []
    for node in ast.walk(arvore):
        if not isinstance(node, ast.Call):
            continue
        e_text = _e_chamada_de_text(node)
        if (e_text and id(node) in permitidos) or not (e_text or _e_execucao_de_string(node)):
            continue
        chave = f"{relativo}::{donos.get(node.lineno, '<módulo>')}"
        achados.append((chave, node.lineno, ast.unparse(node)[:90]))
    return achados


def _todo_sql_em_string() -> list[tuple[str, int, str]]:
    return [
        achado for caminho in sorted(APP_DIR.rglob("*.py")) for achado in _sql_em_string_de(caminho)
    ]


def test_nenhuma_query_de_app_e_escrita_como_string() -> None:
    achados = [a for a in _todo_sql_em_string() if a[0] not in EXCECOES]
    assert achados == [], (
        "SQL em string dentro de app/ — monte com o query builder (select/insert/update/"
        "delete). Se for DDL ou comando de sessão, some a chave a EXCECOES com a "
        "justificativa escrita:\n  "
        + "\n  ".join(f"{chave} (linha {linha}): {trecho}" for chave, linha, trecho in achados)
    )


def test_toda_excecao_declarada_ainda_existe() -> None:
    """Exceção que ninguém usa mais é permissão aberta sem motivo.

    É o mesmo cuidado do `test_o_registro_nao_promete_gate_que_nao_existe` (spec 120): a
    lista só serve enquanto descreve a realidade. Sem este teste, a linha do
    `_run_readonly` sobreviveria à remoção do `_run_readonly`.
    """
    usadas = {chave for chave, _linha, _trecho in _todo_sql_em_string()}
    orfas = sorted(set(EXCECOES) - usadas)
    assert orfas == [], (
        "exceção declarada em EXCECOES sem nenhum SQL em string correspondente — "
        "apague a linha:\n  " + "\n  ".join(orfas)
    )


def test_toda_excecao_tem_justificativa_escrita() -> None:
    """Uma exceção sem motivo escrito é uma exceção que ninguém consegue revisar."""
    curtas = sorted(chave for chave, motivo in EXCECOES.items() if len(motivo.strip()) < 30)
    assert curtas == [], "exceção sem justificativa em EXCECOES:\n  " + "\n  ".join(curtas)
