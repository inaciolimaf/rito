"""As três camadas estáticas do guardrail de text-to-SQL (spec 089 §5).

A spec é explícita: cada camada precisa de teste independente, porque guardrail que só
funciona junto com outro não é guardrail. Aqui cada teste desliga mentalmente as demais
e ataca uma só.
"""

import pytest

from app.domain.ai.sql_guard import MAX_ROWS, SqlRejected, check_sql


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
