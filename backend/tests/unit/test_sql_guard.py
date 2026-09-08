"""As três camadas estáticas do guardrail de text-to-SQL (spec 089 §5).

A spec é explícita: cada camada precisa de teste independente, porque guardrail que só
funciona junto com outro não é guardrail. Aqui cada teste desliga mentalmente as demais
e ataca uma só.
"""

import pytest

from app.domain.ai.sql_guard import (
    ALLOWED_FUNCTIONS,
    FINANCIAL_COLUMNS,
    FINANCIAL_RELATIONS,
    MAX_ROWS,
    SqlRejected,
    check_sql,
)


def _ok(sql: str, *, financial: bool = True) -> str:
    return check_sql(sql, has_financial_access=financial).sql


def test_consulta_valida_passa_e_ganha_limite() -> None:
    resultado = check_sql(
        "SELECT month, lawsuits FROM ai_allowed_metrics", has_financial_access=False
    )

    assert resultado.sql.endswith(f"LIMIT {MAX_ROWS}")
    assert resultado.relations == ["ai_allowed_metrics"]


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE users",
        "DELETE FROM lawsuits",
        "UPDATE lawsuits SET folder = 'x'",
        "INSERT INTO lawsuits (id) VALUES (gen_random_uuid())",
        "TRUNCATE TABLE customers",
        "ALTER TABLE users ADD COLUMN x TEXT",
        "GRANT SELECT ON users TO rito_app",
    ],
)
def test_camada_2_so_select(sql: str) -> None:
    """Comando de escrita é rejeitado pelo TIPO do nó, não por procurar palavra."""
    with pytest.raises(SqlRejected):
        check_sql(sql, has_financial_access=True)


def test_camada_2_recusa_mais_de_um_comando() -> None:
    """`SELECT 1; DROP TABLE x` é a forma clássica de contrabandear o segundo."""
    with pytest.raises(SqlRejected) as exc:
        check_sql("SELECT 1 FROM ai_allowed_metrics; DROP TABLE users", has_financial_access=True)

    assert "UMA consulta" in exc.value.reason


def test_camada_2_nao_se_engana_com_palavra_em_string() -> None:
    """O contrário também importa: uma consulta legítima que contém "delete" num texto
    não pode ser barrada — é o que separa parser de regex."""
    sql = _ok("SELECT stage FROM ai_allowed_metrics WHERE stage = 'delete me'")

    assert "delete me" in sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM users",
        "SELECT name FROM customers LIMIT 10",
        "SELECT c.name FROM ai_allowed_metrics m JOIN customers c ON true",
    ],
)
def test_camada_1_allowlist_de_relacoes(sql: str) -> None:
    with pytest.raises(SqlRejected) as exc:
        check_sql(sql, has_financial_access=True)

    assert "fora do catálogo" in exc.value.reason


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT month FROM ai_allowed_metrics WHERE month IN (SELECT birthdate FROM customers)",
        "WITH escondido AS (SELECT id FROM users) SELECT month FROM ai_allowed_metrics",
        "SELECT (SELECT count(*) FROM lawsuits) AS total FROM ai_allowed_metrics",
    ],
)
def test_camada_3_subquery_e_cte_em_tabela_proibida(sql: str) -> None:
    """A tabela escondida três níveis abaixo é encontrada do mesmo jeito — a varredura
    é na árvore inteira."""
    with pytest.raises(SqlRejected) as exc:
        check_sql(sql, has_financial_access=True)

    assert "fora do catálogo" in exc.value.reason


def test_limite_exagerado_e_reduzido() -> None:
    """`LIMIT 100000` gerado sem malícia derruba a tela do mesmo jeito."""
    sql = _ok("SELECT month FROM ai_allowed_metrics LIMIT 100000")

    assert sql.endswith(f"LIMIT {MAX_ROWS}")


def test_limite_menor_e_respeitado() -> None:
    sql = _ok("SELECT month FROM ai_allowed_metrics LIMIT 5")

    assert sql.endswith("LIMIT 5")


def test_recorte_financeiro_exige_acesso_financeiro() -> None:
    """Regra 5 da spec: a coluna de dinheiro está no catálogo, mas não é para todos."""
    with pytest.raises(SqlRejected) as exc:
        check_sql(
            "SELECT sum(total_case_value) FROM ai_allowed_metrics", has_financial_access=False
        )
    assert "acesso" in exc.value.reason

    permitido = check_sql(
        "SELECT sum(total_case_value) FROM ai_allowed_metrics", has_financial_access=True
    )
    assert permitido.touches_financial is True


def test_texto_vazio_ou_ilegivel_e_rejeitado() -> None:
    with pytest.raises(SqlRejected):
        check_sql("", has_financial_access=True)
    with pytest.raises(SqlRejected):
        check_sql("isto não é sql de jeito nenhum ((", has_financial_access=True)


def test_vocabulario_financeiro_esta_escrito_duas_vezes() -> None:
    """O recorte financeiro é allowlist ao contrário: o que está aqui EXIGE acesso.

    Escrito duas vezes de propósito (spec 132). A medição de mutação mostrou que apagar seis
    dos sete nomes de coluna e os dois de relação não fazia nenhum teste falhar — só
    `total_case_value` era exercitado, e as outras oito entradas eram vocabulário sem
    guarda. Num guardrail, sumir com um nome desta lista é abrir um vazamento; a repetição
    literal é o preço de a lista não poder encolher em silêncio.

    `MAX_ROWS` entra pelo mesmo motivo: o teto de linhas da regra 5 é conferido em toda parte
    contra a própria constante (`endswith(f"LIMIT {MAX_ROWS}")`), o que passa com qualquer
    valor. Este é o único lugar onde o número está fixado.
    """
    relacoes_esperadas = {"bi_cost_allocation_visible", "account_daily_balances_visible"}
    colunas_esperadas = {
        "total_case_value",
        "closed_fees",
        "avg_fees",
        "cost",
        "amount",
        "balance",
        "revenue",
    }

    assert set(FINANCIAL_RELATIONS) == relacoes_esperadas
    assert set(FINANCIAL_COLUMNS) == colunas_esperadas
    assert MAX_ROWS == 1000


@pytest.mark.parametrize(
    "relacao", ["bi_cost_allocation_visible", "account_daily_balances_visible"]
)
def test_relacao_financeira_exige_acesso_mesmo_sem_coluna_de_dinheiro(relacao: str) -> None:
    """As duas portas do recorte financeiro são independentes: a coluna e a RELAÇÃO.

    `SELECT month FROM bi_cost_allocation_visible` não cita nenhuma coluna da lista — quem
    barra é o nome da view. Antes da 132 só o caminho da coluna tinha teste.
    """
    with pytest.raises(SqlRejected) as exc:
        check_sql(f"SELECT month FROM {relacao}", has_financial_access=False)
    assert "acesso financeiro" in exc.value.reason

    permitido = check_sql(f"SELECT month FROM {relacao}", has_financial_access=True)
    assert permitido.touches_financial is True


def test_cte_que_escreve_e_barrada_mesmo_com_select_na_raiz() -> None:
    """O nó raiz é `Select` e ainda assim a consulta escreve — `WITH x AS (DELETE …)` é SQL
    válido no Postgres e devolve linhas.

    É o caso que a varredura de nós proibidos existe para pegar, e o único em que ela decide
    sozinha: a checagem de tipo da raiz deixa passar, a contagem de comandos também.
    """
    with pytest.raises(SqlRejected) as exc:
        check_sql(
            "WITH removidos AS (DELETE FROM users RETURNING id) "
            "SELECT month FROM ai_allowed_metrics",
            has_financial_access=True,
        )

    assert str(exc.value) == "A consulta tenta modificar o banco. Só leitura é permitida aqui."


def test_limite_que_nao_da_para_ler_cai_no_teto() -> None:
    """Um `LIMIT` que não é literal inteiro trata-se como exagerado, nunca como aceitável.

    `LIMIT (SELECT 5)` passa no parser e o valor só existe em tempo de execução — é o ramo
    de exceção de `_with_limit`, que antes da 132 não tinha teste nenhum: trocar o
    `MAX_ROWS + 1` por `MAX_ROWS - 1` ali devolvia a consulta SEM teto e a suíte ficava
    verde. `LIMIT ALL` é o caso vizinho, e cai antes: o `sqlglot` descarta o nó, então o
    teto é injetado como se não houvesse limite.
    """
    ilegivel = check_sql(
        "SELECT month FROM ai_allowed_metrics LIMIT (SELECT 5)", has_financial_access=False
    )
    sem_limite = check_sql(
        "SELECT month FROM ai_allowed_metrics LIMIT ALL", has_financial_access=False
    )

    assert ilegivel.sql.endswith(f"LIMIT {MAX_ROWS}")
    assert sem_limite.sql.endswith(f"LIMIT {MAX_ROWS}")


@pytest.mark.parametrize(
    ("sql", "motivo"),
    [
        ("", "A IA não gerou nenhuma consulta."),
        (
            "DROP TABLE users",
            "Só consultas de leitura (SELECT) são permitidas — nada de alterar dados.",
        ),
        ("SELECT 1", "A consulta não indica de onde ler os dados."),
    ],
)
def test_todo_motivo_de_recusa_chega_inteiro_ao_usuario(sql: str, motivo: str) -> None:
    """Regra 2: o motivo vai para a tela, em português.

    Comparado por igualdade e lido de `str(exc)`, não de `.reason`: a medição da 132 mostrou
    que apagar a frase inteira, ou tirar o `super().__init__(reason)` da exceção, não
    derrubava nenhum teste — todos olhavam só o tipo da exceção ou um pedaço da frase.
    """
    with pytest.raises(SqlRejected) as exc:
        check_sql(sql, has_financial_access=True)

    assert str(exc.value) == motivo


def test_sql_ilegivel_diz_o_que_o_parser_reclamou() -> None:
    """A única mensagem com cauda variável: o erro do `sqlglot` entra nela, porque é o que
    permite a quem lê o log entender o que o modelo gerou."""
    with pytest.raises(SqlRejected) as exc:
        check_sql("isto não é sql de jeito nenhum ((", has_financial_access=True)

    assert str(exc.value).startswith("A consulta gerada não é SQL válido: ")


def test_a_recusa_por_allowlist_nomeia_todas_as_relacoes_barradas() -> None:
    """O motivo tem de listar o que foi barrado, e todas: quem pergunta em português não
    faz ideia de quais views existem, e uma frase que cita só a primeira manda a pessoa
    corrigir metade do problema."""
    with pytest.raises(SqlRejected) as exc:
        check_sql("SELECT c.name FROM users u JOIN customers c ON true", has_financial_access=True)

    assert str(exc.value) == (
        "A consulta usa dados fora do catálogo analítico permitido: customers, users. "
        "Só as visões de indicadores estão disponíveis."
    )


# ------------------------------------------------- camada 1b: funções (spec 133)


@pytest.mark.parametrize(
    ("sql", "onde"),
    [
        (
            "SELECT * FROM ai_allowed_metrics LIMIT 1000 OFFSET "
            "(SELECT 0 FROM (SELECT set_config('app.tenant_id','11111111-1111-1111-1111-"
            "111111111111',true)) AS z)",
            "no OFFSET — o InitPlan que a auditoria usou",
        ),
        (
            "SELECT month FROM ai_allowed_metrics GROUP BY month "
            "HAVING count(*) > length(set_config('app.tenant_id','x',true))",
            "no HAVING",
        ),
        (
            "SELECT month FROM ai_allowed_metrics ORDER BY set_config('app.tenant_id','x',true)",
            "no ORDER BY",
        ),
        (
            "SELECT month, (SELECT set_config('app.tenant_id','x',true)) FROM ai_allowed_metrics",
            "numa subconsulta escalar",
        ),
        (
            "SELECT month FROM ai_allowed_metrics WHERE month IN "
            "(SELECT month FROM ai_allowed_metrics WHERE set_config('a','b',true) IS NULL)",
            "numa subconsulta de IN",
        ),
        ("SELECT month FROM ai_allowed_metrics WHERE pg_sleep(10) IS NULL", "pg_sleep no WHERE"),
        (
            "SELECT month FROM ai_allowed_metrics WHERE dblink('x','y') IS NULL",
            "dblink no WHERE",
        ),
        (
            "SELECT pg_read_file('/etc/passwd') FROM ai_allowed_metrics",
            "leitura de arquivo na projeção",
        ),
        (
            "SELECT month FROM ai_allowed_metrics "
            "WHERE CASE WHEN true THEN set_config('a','b',true) ELSE '' END = ''",
            "escondida dentro de um CASE permitido",
        ),
    ],
)
def test_camada_1b_funcao_fora_da_allowlist_e_recusada(sql: str, onde: str) -> None:
    """O achado CRÍTICO da auditoria: o guarda filtrava por tipo de nó e por tabela, e não
    olhava chamada de função nenhuma.

    `set_config('app.tenant_id', <outro escritório>, true)` num InitPlan de `OFFSET` é
    avaliado ANTES da varredura da relação; as nove views barreira leem
    `current_setting('app.tenant_id')` DEPOIS. Medido no HEAD: a sessão do escritório A
    recebia a linha do B. O `transaction_read_only = on` não protegia — `set_config` não é
    escrita.

    A defesa é allowlist e não denylist justamente pelos casos abaixo: `set_config` foi a
    primeira que alguém achou, e `pg_sleep`, `dblink` e `pg_read_file` mostram que a lista
    do proibido nunca estaria completa. A varredura é `find_all` na árvore inteira, então a
    cláusula em que a função aparece não faz diferença — é o que os nove casos provam.
    """
    with pytest.raises(SqlRejected) as exc:
        check_sql(sql, has_financial_access=True)

    assert "funções que não são permitidas" in exc.value.reason, onde


def test_camada_1b_a_recusa_nomeia_a_funcao_barrada() -> None:
    """Regra 2: o motivo vai inteiro para a tela — e sem o nome ninguém corrige nada."""
    with pytest.raises(SqlRejected) as exc:
        check_sql(
            "SELECT pg_sleep(1), set_config('a','b',true) FROM ai_allowed_metrics",
            has_financial_access=True,
        )

    assert str(exc.value) == (
        "A consulta chama funções que não são permitidas aqui: pg_sleep, set_config. "
        "Só agregações e conversões simples são aceitas."
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*), sum(lawsuits), avg(lawsuits) FROM ai_allowed_metrics",
        "SELECT min(month), max(month), stddev(lawsuits) FROM ai_allowed_metrics",
        "SELECT round(avg(lawsuits), 2), abs(lawsuits), ceil(lawsuits) FROM ai_allowed_metrics",
        "SELECT coalesce(stage, 'sem etapa'), nullif(lawsuits, 0) FROM ai_allowed_metrics",
        "SELECT date_trunc('month', month), extract(year FROM month) FROM ai_allowed_metrics",
        "SELECT to_char(month, 'YYYY-MM'), cast(lawsuits AS numeric) FROM ai_allowed_metrics",
        "SELECT lawsuits::text, lower(stage), length(stage) FROM ai_allowed_metrics",
        "SELECT CASE WHEN won > lost THEN 'ganhando' ELSE 'perdendo' END FROM ai_allowed_metrics",
        "SELECT rank() OVER (ORDER BY lawsuits) FROM ai_allowed_metrics",
        "SELECT month FROM ai_allowed_metrics WHERE month >= current_date - 30",
    ],
)
def test_camada_1b_o_vocabulario_analitico_continua_passando(sql: str) -> None:
    """A allowlist tem de caber na pergunta real: contar, somar, agrupar por mês, comparar.

    Uma lista curta demais fecha a feature — o modelo geraria SQL correto e o usuário
    levaria "função não permitida" na tela. Estes dez casos são o piso do que a 089
    prometeu responder.
    """
    assert check_sql(sql, has_financial_access=True).sql


def test_camada_1b_o_vocabulario_de_funcoes_esta_escrito_duas_vezes() -> None:
    """Mesmo motivo do vocabulário financeiro (spec 132): apagar um nome desta lista é
    ABRIR uma porta, e nenhuma outra asserção enxergaria isso.

    O contrário também vale, e é o risco real desta spec: acrescentar `set_config` aqui
    reabriria o achado crítico inteiro, e o único teste que reprovaria seria este.
    """
    assert set(ALLOWED_FUNCTIONS) == {
        "count", "sum", "avg", "min", "max", "stddev", "variance",
        "abs", "ceil", "floor", "round", "greatest", "least", "mod",
        "coalesce", "nullif", "case", "if",
        "cast", "extract", "timestamp_trunc", "time_to_str",
        "current_date", "current_timestamp",
        "lower", "upper", "trim", "length", "concat", "substring",
        "row_number", "rank", "dense_rank",
    }  # fmt: skip


# ------------------------------------------------- teto de linhas (dívida 43)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT month FROM ai_allowed_metrics LIMIT 0+5000000",
        "SELECT month FROM ai_allowed_metrics LIMIT 5000000-1",
        "SELECT month FROM ai_allowed_metrics LIMIT 1000*1000",
        "SELECT month FROM ai_allowed_metrics LIMIT -1",
    ],
)
def test_limite_com_aritmetica_cai_no_teto(sql: str) -> None:
    """Dívida 43: `int(limite.expression.name)` sobre um nó `Add` devolvia o literal da
    ESQUERDA.

    `LIMIT 0+5000000` virava `int("0")`, passava no `valor > MAX_ROWS` e a consulta saía
    **sem teto** — medido no HEAD. A correção não é reconhecer a soma: é aceitar só literal
    inteiro e tratar todo o resto como exagerado, porque a família de formas que `.name`
    lê errado não tem fim (`Add`, `Neg`, `Mul`, parâmetro, subconsulta).
    """
    assert check_sql(sql, has_financial_access=False).sql.endswith(f"LIMIT {MAX_ROWS}")


def test_limite_literal_dentro_do_teto_continua_intacto() -> None:
    """O outro lado da dívida 43: a correção não podia virar "sempre 1000"."""
    assert _ok("SELECT month FROM ai_allowed_metrics LIMIT 5").endswith("LIMIT 5")
    assert _ok(f"SELECT month FROM ai_allowed_metrics LIMIT {MAX_ROWS}").endswith(
        f"LIMIT {MAX_ROWS}"
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT month FROM ai_allowed_metrics LIMIT 10 OFFSET (SELECT 1)",
        "SELECT month FROM ai_allowed_metrics LIMIT 10 OFFSET 5+5",
    ],
)
def test_deslocamento_precisa_ser_numero_escrito(sql: str) -> None:
    """Spec 133: o InitPlan que carregou a fuga era um `OFFSET` calculado.

    A camada de funções fecha o conteúdo conhecido; exigir literal fecha a FORMA. Nenhuma
    pergunta de indicador precisa de um deslocamento calculado — esta feature não pagina
    resultado, ela responde uma pergunta.
    """
    with pytest.raises(SqlRejected) as exc:
        check_sql(sql, has_financial_access=True)

    assert str(exc.value) == (
        "O deslocamento de linhas (`offset`) precisa ser um número escrito — "
        "expressão não é aceita."
    )


def test_deslocamento_literal_passa() -> None:
    assert "OFFSET 5" in _ok("SELECT month FROM ai_allowed_metrics LIMIT 10 OFFSET 5")
