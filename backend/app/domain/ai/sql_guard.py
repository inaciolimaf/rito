"""Guardrails do text-to-SQL (spec 089 §5).

Quatro camadas, todas obrigatórias e **independentes** — a spec é explícita: guardrail
que depende de outro para funcionar não é guardrail. Aqui ficam as três de análise
estática; a quarta (conexão somente-leitura, com timeout e tenant setado) vive no
service, porque é propriedade da conexão, não do texto.

A análise é sobre a **árvore sintática**, nunca sobre a string: procurar "DROP" com
regex é uma promessa que qualquer comentário, alias ou string literal quebra.

Spec 104: o `sqlglot` custa 32 ms de import e só o text-to-SQL da 089 o usa. Ele sai do
topo — mas `exp.Expression` aparece em **assinatura**, e sem
`from __future__ import annotations` o Python resolveria esse nome em tempo de import.
Daí a combinação padrão: futuro + `TYPE_CHECKING` para o que é só tipo, import dentro da
função para o que é execução.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlglot import exp

DIALECT = "postgres"
# Regra 5 da spec: teto de linhas, injetado quando o modelo esquece.
MAX_ROWS = 1000
# Regra 6: nenhuma consulta analítica precisa de mais que isso; acima disso é engano.
STATEMENT_TIMEOUT_MS = 5000

# Camada 1: só estas relações. São views agregadas — nenhuma tem dado pessoal, e todas
# já filtram por tenant (views barreira das specs 039/059/071/073/074-077 e a
# `ai_allowed_metrics` da migration 089).
ALLOWED_RELATIONS: frozenset[str] = frozenset(
    {
        "ai_allowed_metrics",
        "bi_pipeline_monthly_visible",
        "bi_vintage_visible",
        "bi_lawsuit_cycles_visible",
        "bi_cost_allocation_visible",
        "user_monthly_scores_visible",
        "account_daily_balances_visible",
        "agility_daily_visible",
        "timesheet_daily_visible",
    }
)

# Colunas que exigem `financial_access` do usuário (regra 5 da spec).
FINANCIAL_RELATIONS: frozenset[str] = frozenset(
    {
        "bi_cost_allocation_visible",
        "account_daily_balances_visible",
    }
)
FINANCIAL_COLUMNS: frozenset[str] = frozenset(
    {"total_case_value", "closed_fees", "avg_fees", "cost", "amount", "balance", "revenue"}
)

# Camada 1b (spec 133): as ÚNICAS funções que a consulta do modelo pode chamar.
#
# Allowlist, e nunca denylist. `set_config('app.tenant_id', <outro escritório>, true)` foi
# a primeira que alguém achou — dentro de uma subconsulta em `OFFSET` ela vira um InitPlan
# que o Postgres avalia ANTES de varrer a relação, e as views barreira filtram por
# `current_setting('app.tenant_id')`, avaliado DEPOIS. Uma lista do que é proibido teria
# fechado `set_config` e continuado aberta para a próxima; esta lista fecha tudo que não
# está escrito aqui, e cresce por spec.
#
# O critério de entrada é ser PURA no sentido que importa aqui: calcular a partir dos
# argumentos e não mexer em nada do estado da sessão (GUC, papel, arquivos, rede, tempo de
# espera). São as agregações, a aritmética, a conversão e o recorte de data que uma
# pergunta de indicador realmente precisa.
ALLOWED_FUNCTIONS: frozenset[str] = frozenset(
    {
        # agregação
        "count",
        "sum",
        "avg",
        "min",
        "max",
        "stddev",
        "variance",
        # aritmética
        "abs",
        "ceil",
        "floor",
        "round",
        "greatest",
        "least",
        "mod",
        # nulo e condicional
        "coalesce",
        "nullif",
        "case",
        "if",
        # conversão e data
        "cast",
        "extract",
        "timestamp_trunc",  # `date_trunc` — o sqlglot canoniza com este nome
        "time_to_str",  # `to_char`
        "current_date",
        "current_timestamp",
        # texto
        "lower",
        "upper",
        "trim",
        "length",
        "concat",
        "substring",
        # janela
        "row_number",
        "rank",
        "dense_rank",
    }
)


class SqlRejected(Exception):
    """Motivo em português, porque ele vai para a tela do usuário (regra 2)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class CheckedSql:
    sql: str
    relations: list[str]
    touches_financial: bool


def _relations(tree: exp.Expression) -> list[str]:
    """Todas as relações da árvore, INCLUSIVE as de subquery e CTE.

    `find_all` desce a árvore inteira — é o que faz a camada 3 (subquery em tabela
    proibida) não precisar de código próprio: uma tabela escondida três níveis abaixo
    aparece aqui do mesmo jeito.
    """
    from sqlglot import exp

    nomes = []
    for table in tree.find_all(exp.Table):
        nome = table.name.lower()
        if nome:
            nomes.append(nome)
    return nomes


def _single_statement(sqlglot: Any, raw_sql: str) -> Any:
    """Faz o parse e exige EXATAMENTE um comando.

    `SELECT 1; DROP TABLE x` é a forma clássica de contrabandear o segundo comando: o
    primeiro passa em qualquer checagem de texto que olhe só o começo. Contar os comandos
    depois do parse é o que fecha isso — e o `rstrip(";")` antes existe para o ponto e
    vírgula final legítimo não virar um segundo comando vazio.
    """
    texto = (raw_sql or "").strip().rstrip(";").strip()
    if not texto:
        raise SqlRejected("A IA não gerou nenhuma consulta.")
    try:
        arvores = sqlglot.parse(texto, dialect=DIALECT)
    except Exception as exc:  # sqlglot levanta várias formas de ParseError
        raise SqlRejected(f"A consulta gerada não é SQL válido: {exc}") from exc
    arvores = [arvore for arvore in arvores if arvore is not None]
    if len(arvores) != 1:
        raise SqlRejected("Só é permitida UMA consulta por pergunta.")
    return arvores[0]


def _read_only_tree(raw_sql: str) -> exp.Expression:
    """Camada 2: uma consulta, e só de leitura.

    O tipo do nó RAIZ é o que decide, não o texto — `SELECT` que esconde um `DROP` numa
    subconsulta é pego pela varredura dos nós proibidos logo abaixo, e `SELECT 1; DROP
    TABLE x` é pego pela contagem de comandos, que é a forma clássica de contrabandear o
    segundo.
    """
    import sqlglot
    from sqlglot import exp

    tree = _single_statement(sqlglot, raw_sql)
    if not isinstance(tree, exp.Select | exp.Union | exp.Subquery):
        raise SqlRejected(
            "Só consultas de leitura (SELECT) são permitidas — nada de alterar dados."
        )
    proibidos = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.TruncateTable,
        exp.Grant,
        exp.Command,
    )
    if any(tree.find(proibido) is not None for proibido in proibidos):
        raise SqlRejected("A consulta tenta modificar o banco. Só leitura é permitida aqui.")
    return tree


def _allowed_relations(tree: exp.Expression) -> list[str]:
    """Camadas 1 e 3: allowlist, valendo em qualquer profundidade da árvore."""
    relacoes = _relations(tree)
    if not relacoes:
        raise SqlRejected("A consulta não indica de onde ler os dados.")
    proibidas = sorted({nome for nome in relacoes if nome not in ALLOWED_RELATIONS})
    if proibidas:
        raise SqlRejected(
            "A consulta usa dados fora do catálogo analítico permitido: "
            + ", ".join(proibidas)
            + ". Só as visões de indicadores estão disponíveis."
        )
    return relacoes


def _function_name(node: Any) -> str:
    """Nome canônico da chamada de função, minúsculo.

    `Anonymous` é o nó que o sqlglot usa para toda função que ele não conhece — é onde
    caem `set_config`, `pg_sleep`, `dblink` e qualquer coisa que o Postgres tenha e o
    parser não modele. Para elas o nome está em `this`; para as conhecidas, `sql_name()`
    devolve o nome canônico (`date_trunc` vira `TIMESTAMP_TRUNC`).
    """
    from sqlglot import exp

    if isinstance(node, exp.Anonymous):
        return str(node.this).lower()
    return str(node.sql_name()).lower()


def _allowed_functions(tree: exp.Expression) -> None:
    """Camada 1b: nenhuma chamada de função fora de `ALLOWED_FUNCTIONS`, em profundidade
    nenhuma.

    `find_all` desce a árvore INTEIRA — inclusive `LIMIT`, `OFFSET`, `HAVING`, `ORDER BY`,
    CTE e subconsulta. É o que faz esta camada valer para o InitPlan de `OFFSET`, que é
    exatamente onde a fuga de tenant morava (spec 133 §2).
    """
    from sqlglot import exp

    proibidas = sorted(
        {
            nome
            for nome in (_function_name(node) for node in tree.find_all(exp.Func))
            if nome not in ALLOWED_FUNCTIONS
        }
    )
    if proibidas:
        raise SqlRejected(
            "A consulta chama funções que não são permitidas aqui: "
            + ", ".join(proibidas)
            + ". Só agregações e conversões simples são aceitas."
        )


def check_sql(raw_sql: str, *, has_financial_access: bool) -> CheckedSql:
    """Valida e devolve o SQL pronto para execução, ou levanta `SqlRejected`."""
    from sqlglot import exp

    tree = _read_only_tree(raw_sql)
    relacoes = _allowed_relations(tree)
    _allowed_functions(tree)
    _plain_offset(tree)

    financeiro = any(nome in FINANCIAL_RELATIONS for nome in relacoes) or any(
        coluna.name.lower() in FINANCIAL_COLUMNS for coluna in tree.find_all(exp.Column)
    )
    if financeiro and not has_financial_access:
        raise SqlRejected(
            "Esta pergunta envolve dados financeiros, e o seu usuário não tem acesso financeiro."
        )

    return CheckedSql(
        sql=_with_limit(tree), relations=sorted(set(relacoes)), touches_financial=financeiro
    )


def _literal_int(clausula: Any) -> int | None:
    """O valor de um `LIMIT`/`OFFSET` quando ele é um literal inteiro, e `None` no resto.

    Dívida 43: a versão anterior lia `int(clausula.expression.name)`. Sobre um nó `Add`,
    `.name` devolve o literal da ESQUERDA — `LIMIT 0+5000000` virava `int("0")`, passava no
    `valor > MAX_ROWS` e a consulta saía sem teto nenhum. Perguntar pelo TIPO do nó, e não
    pelo texto dele, é o que fecha a família inteira: `Add`, `Neg`, subconsulta, parâmetro,
    `ALL`. Tudo que não for um inteiro escrito por extenso volta `None`, e quem chama trata
    `None` como "exagerado".
    """
    from sqlglot import exp

    if clausula is None:
        return None
    expressao = clausula.expression if isinstance(clausula, exp.Limit | exp.Offset) else clausula
    if not isinstance(expressao, exp.Literal) or not expressao.is_int:
        return None
    try:
        return int(expressao.name)
    except ValueError:  # pragma: no cover — `is_int` já garante, mas o int() é o contrato
        return None


def _plain_offset(tree: exp.Expression) -> None:
    """Regra 5 da spec 133: `OFFSET` só aceita literal inteiro.

    O `OFFSET` é avaliado como InitPlan, antes da varredura da relação — foi por ele que a
    troca de tenant entrou. A camada de funções já fecha o caso conhecido; exigir literal
    fecha a forma, e não só o conteúdo. Nenhuma pergunta de indicador precisa de um `OFFSET`
    calculado: paginação de resultado analítico não existe nesta feature.
    """
    deslocamento = tree.args.get("offset") if hasattr(tree, "args") else None
    if deslocamento is not None and _literal_int(deslocamento) is None:
        raise SqlRejected(
            "O deslocamento de linhas (`offset`) precisa ser um número escrito — "
            "expressão não é aceita."
        )


def _with_limit(tree: exp.Expression) -> str:
    """Regra 5: teto de linhas sempre presente — injetado se faltar, reduzido se
    exagerado. Um `LIMIT 100000` gerado sem malícia derruba a tela do mesmo jeito."""
    from sqlglot import exp

    if not isinstance(tree, exp.Select | exp.Union | exp.Subquery):  # pragma: no cover
        # `check_sql` já garantiu o tipo antes de chegar aqui; a checagem existe para o
        # mypy e para o dia em que alguém chamar esta função de outro lugar.
        raise SqlRejected("Só consultas de leitura (SELECT) são permitidas.")
    valor = _literal_int(tree.args.get("limit"))
    if valor is None or valor > MAX_ROWS:
        return tree.limit(MAX_ROWS).sql(dialect=DIALECT)
    return tree.sql(dialect=DIALECT)
