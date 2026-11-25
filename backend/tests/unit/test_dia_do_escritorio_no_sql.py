"""O «hoje» que atravessa o SQL é o do escritório, não o do servidor (spec 136).

A spec 114 tirou `date.today()` do Python e o `DTZ` do Ruff mais o meta-teste
`test_nenhum_date_today_em_app` impedem que ele volte. Nenhum dos dois alcança
`func.current_date()`: não é `date.today()`, é uma função do Postgres — e o Postgres
responde em UTC. O gate ficava verde sobre um bug da família que ele existe para pegar.

Estes testes olham a QUERY, e não o resultado dela, de propósito. A afirmação
comportamental («a tarefa que vence hoje não está atrasada») só distingue o certo do
errado nas três horas por dia em que o servidor já virou o dia e o escritório não — um
teste assim é a dívida 30 de novo, vermelho por causa da hora. A afirmação sobre o SQL
vale 24 horas por dia: se `CURRENT_DATE` voltar a decidir «hoje», isto fica vermelho na
hora, em qualquer fuso.
"""

from datetime import date
from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.dialects import postgresql

from app.domain.dunning.repository import _overdue_condition
from app.domain.financial.dashboard import overdue_conditions
from app.domain.lawsuits.listing import LAWSUIT_VIEWS
from app.domain.posts.listing import ACTIVITY_VIEW_NAMES, activity_view_predicate

# As visões cuja resposta muda com o dia — as únicas em que «hoje» aparece. As de
# movimentação (`moved_30d`, `idle_90d`) comparam um instante com «agora menos N dias»,
# que é uma duração e não um dia: `func.now()` ali está certo e continua.
_VISOES_DE_PROCESSO_COM_DIA = (
    "moved_today",
    "closed_this_month",
    "filed_this_month",
    "archived_this_month",
)


def _sql(expressao: ColumnElement[bool] | None) -> str:
    """O SQL que a expressão emite, com os valores ligados escritos por extenso.

    `ClauseElement.compile` e `postgresql.dialect` não são tipadas nos stubs do SQLAlchemy
    2.0, e o `mypy` deste projeto reprova chamada não tipada em contexto tipado. Passar
    pelas duas por um nome `Any` evita dois `# type: ignore` que não explicariam nada além
    de "a biblioteca não tem stub aqui".
    """
    assert expressao is not None
    compilador: Any = expressao.compile
    dialeto: Any = postgresql.dialect
    return str(compilador(dialect=dialeto(), compile_kwargs={"literal_binds": True}))


def test_visao_atrasadas_de_atividades_usa_o_dia_recebido_e_nao_o_do_servidor() -> None:
    """`posts/listing.py` recebia `today` (o do escritório, spec 114) para ROTULAR a linha
    e perguntava o dia ao Postgres para FILTRAR. Entre 21h e a meia-noite em Brasília a
    mesma resposta afirmava as duas coisas: a tarefa vinha dentro de «Atrasadas» e vinha
    marcada PENDENTE."""
    sql = _sql(activity_view_predicate("overdue", date(2026, 1, 15)))
    assert "2026-01-15" in sql
    assert "CURRENT_DATE" not in sql.upper()


def test_nenhuma_visao_de_atividade_pergunta_o_dia_ao_servidor() -> None:
    for nome in ACTIVITY_VIEW_NAMES:
        sql = _sql(activity_view_predicate(nome, date(2026, 1, 15))) if nome != "all" else ""
        assert "CURRENT_DATE" not in sql.upper(), nome
        assert "now()" not in sql, nome


def test_nenhuma_visao_de_processo_pergunta_o_dia_ao_servidor() -> None:
    """`current_date` some das 12 visões — inclusive das que nem usam data, para que a
    varredura não precise saber quais são quais."""
    for nome in LAWSUIT_VIEWS.names:
        sql = _sql(LAWSUIT_VIEWS.predicate(nome)) if nome != "all" else ""
        assert "CURRENT_DATE" not in sql.upper(), nome


def test_as_visoes_de_dia_e_de_mes_leem_o_fuso_da_conta() -> None:
    """O dia do escritório vem de `accounts.timezone` (spec 011) por subconsulta — o
    caminho que a listagem tem para saber o fuso sem receber o `Clock`, que não chega até
    ela."""
    for nome in _VISOES_DE_PROCESSO_COM_DIA:
        sql = _sql(LAWSUIT_VIEWS.predicate(nome))
        assert "accounts" in sql, nome
        assert "timezone" in sql, nome


def test_as_tres_visoes_deste_mes_tem_teto_e_nao_so_piso() -> None:
    """Um processo com `closure_date` em 2027 contava como «encerrado este mês» em todos
    os meses até lá. O teto é a outra metade da janela."""
    for nome in ("closed_this_month", "filed_this_month", "archived_this_month"):
        sql = _sql(LAWSUIT_VIEWS.predicate(nome))
        assert ">=" in sql, nome
        assert "<" in sql.replace("<=", ""), nome
        assert "interval" in sql.lower() or "make_interval" in sql, nome


def test_atrasado_tem_uma_definicao_so_no_produto() -> None:
    """A cobrança (spec 060) e o dashboard financeiro (059) respondiam «o que é atrasado»
    com condições diferentes: a primeira exigia `kind = RECEITA`, a segunda não filtrava
    `kind` nenhum — e uma transferência entre contas do próprio escritório entrava no
    card «Atrasados». Agora as duas telas leem a mesma função."""
    dia = date(2026, 1, 15)
    do_financeiro = [_sql(condicao) for condicao in overdue_conditions(dia)]
    da_cobranca = [_sql(condicao) for condicao in _overdue_condition(dia)]
    assert do_financeiro == da_cobranca
    assert any("kind" in condicao for condicao in do_financeiro)
    assert any("RECEITA" in condicao for condicao in do_financeiro)
