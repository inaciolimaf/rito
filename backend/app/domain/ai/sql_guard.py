"""Guardrails do text-to-SQL (spec 089 §5).

Quatro camadas, todas obrigatórias e **independentes** — a spec é explícita: guardrail
que depende de outro para funcionar não é guardrail. Aqui ficam as três de análise
estática; a quarta (conexão somente-leitura, com timeout e tenant setado) vive no
service, porque é propriedade da conexão, não do texto.

A análise é sobre a **árvore sintática**, nunca sobre a string: procurar "DROP" com
regex é uma promessa que qualquer comentário, alias ou string literal quebra.
"""

from dataclasses import dataclass

import sqlglot
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
    nomes = []
    for table in tree.find_all(exp.Table):
        nome = table.name.lower()
        if nome:
            nomes.append(nome)
    return nomes


def check_sql(raw_sql: str, *, has_financial_access: bool) -> CheckedSql:
    """Valida e devolve o SQL pronto para execução, ou levanta `SqlRejected`."""
    texto = (raw_sql or "").strip().rstrip(";").strip()
    if not texto:
        raise SqlRejected("A IA não gerou nenhuma consulta.")

    try:
        arvores = sqlglot.parse(texto, dialect=DIALECT)
    except Exception as exc:  # sqlglot levanta várias formas de ParseError
        raise SqlRejected(f"A consulta gerada não é SQL válido: {exc}") from exc

    arvores = [arvore for arvore in arvores if arvore is not None]
    # Camada 2, primeira metade: um comando por vez. `SELECT 1; DROP TABLE x` é a forma
    # clássica de contrabandear o segundo.
    if len(arvores) != 1:
        raise SqlRejected("Só é permitida UMA consulta por pergunta.")
    tree = arvores[0]

    # Camada 2: somente SELECT — verificado no tipo do nó raiz, não no texto.
    if not isinstance(tree, exp.Select | exp.Union | exp.Subquery):
        raise SqlRejected(
            "Só consultas de leitura (SELECT) são permitidas — nada de alterar dados."
        )
    for proibido in (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.TruncateTable,
        exp.Grant,
        exp.Command,
    ):
        if tree.find(proibido) is not None:
            raise SqlRejected("A consulta tenta modificar o banco. Só leitura é permitida aqui.")

    # Camadas 1 e 3: allowlist, valendo em qualquer profundidade da árvore.
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


def _with_limit(tree: exp.Expression) -> str:
    """Regra 5: teto de linhas sempre presente — injetado se faltar, reduzido se
    exagerado. Um `LIMIT 100000` gerado sem malícia derruba a tela do mesmo jeito."""
    if not isinstance(tree, exp.Select | exp.Union | exp.Subquery):  # pragma: no cover
        # `check_sql` já garantiu o tipo antes de chegar aqui; a checagem existe para o
        # mypy e para o dia em que alguém chamar esta função de outro lugar.
        raise SqlRejected("Só consultas de leitura (SELECT) são permitidas.")
    limite = tree.args.get("limit")
    if limite is None:
        return tree.limit(MAX_ROWS).sql(dialect=DIALECT)
    try:
        valor = int(limite.expression.name)
    except (AttributeError, ValueError):
        valor = MAX_ROWS + 1
    if valor > MAX_ROWS:
        return tree.limit(MAX_ROWS).sql(dialect=DIALECT)
    return tree.sql(dialect=DIALECT)
