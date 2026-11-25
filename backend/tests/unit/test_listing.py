"""`app/core/listing.py` — a infra que o CLAUDE.md §6 nomeia como âncora do contrato de
listagem, e que até a spec 139 não tinha **nenhum** arquivo de teste unitário.

Tudo o que se sabia sobre ela era subproduto de testes de integração de outros domínios:
os de `date_range` (coluna `date`) matavam suas mutações, os de `datetime_range` (coluna
`timestamp`) não. Medido em 08/09/2026, com a suíte INTEIRA (1.619 testes) como controle:

- `datetime.combine(end, time.max)` → `time.min` na linha 32 sobrevive a todos eles. Com
  o defeito, «criados de 01/09 a 08/09» devolve só o que tenha `created_at` exatamente às
  00:00:00,000000 do dia 08 — na prática, **nada do dia final** — em processos, contatos,
  atividades e financeiro. Sem erro, sem status diferente: só linhas a menos;
- os quatro defaults de `Page` (o quarteto de paginação do §6) também sobrevivem.

Este arquivo fecha o que dá para fechar sem banco. A verificação é feita sobre a SQL
compilada com `literal_binds`, e não sobre a expressão Python que a produziu: comparar
`datetime.combine(end, time.max)` com `datetime.combine(end, time.max)` seria repetir a
implementação com outras palavras, que é a família de asserção tautológica que a spec 132
foi caçar. O que se afirma aqui é o TEXTO da borda — `23:59:59.999999` —, que é a promessa
que a docstring da função faz ao usuário.

`unaccented_contains` fica de fora de propósito: a função está sendo trocada
(`unaccent` → `immutable_unaccent`) em spec paralela, e um teste que fixasse o nome da
função SQL de hoje reprovaria essa troca sem nada ter quebrado.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import Date, DateTime, column

from app.core.listing import Page, Predicate, date_range, datetime_range

_INICIO = date(2026, 9, 1)
_FIM = date(2026, 9, 8)


def _sql(predicado: Predicate) -> str:
    """A condição como o Postgres a receberia, com os valores no lugar dos binds."""
    return str(predicado.compile(compile_kwargs={"literal_binds": True}))


def _timestamps(start: date | None, end: date | None) -> list[str]:
    return [_sql(p) for p in datetime_range(column("created_at", DateTime), start, end)]


def _datas(start: date | None, end: date | None) -> list[str]:
    return [_sql(p) for p in date_range(column("due_date", Date), start, end)]


# ─────────────────────────────────────────────────────────────────────────────
# datetime_range — a borda que ninguém tinha
# ─────────────────────────────────────────────────────────────────────────────


def test_o_fim_do_intervalo_inclui_o_dia_final_inteiro() -> None:
    """A razão de ser da função: «de 00:00 do dia inicial a 23:59:59 do final».

    É o teste que faltava. Um registro criado às 23:00 do dia `end` tem de estar DENTRO
    do resultado — e com `time.min` no lugar de `time.max` ele sai, junto com o dia todo.
    """
    assert _timestamps(_INICIO, _FIM) == [
        "created_at >= '2026-09-01 00:00:00'",
        "created_at <= '2026-09-08 23:59:59.999999'",
    ]


@pytest.mark.parametrize(
    ("instante", "dentro"),
    [
        ("2026-09-08 00:00:00", True),  # a primeira batida do dia final
        ("2026-09-08 23:00:00", True),  # o caso que a mutação derrubava
        ("2026-09-08 23:59:59.999999", True),  # o último microssegundo
        ("2026-09-09 00:30:00", False),  # já é o dia seguinte
        ("2026-08-31 23:59:59", False),  # ainda é a véspera
    ],
)
def test_a_borda_do_intervalo_separa_o_dia_final_do_seguinte(instante: str, dentro: bool) -> None:
    """O mesmo fato, dito pelo lado de quem consulta: quais instantes o filtro aceita.

    Comparar as strings ISO funciona porque o formato é ordenável lexicograficamente —
    e é a forma mais direta de dizer «o dia 08 inteiro entra, o 09 não».
    """
    piso, teto = (condicao.split(" ", 2)[2].strip("'") for condicao in _timestamps(_INICIO, _FIM))

    assert (piso <= instante <= teto) is dentro


def test_intervalo_aberto_dos_dois_lados() -> None:
    """«Um lado só é válido»: `created_from` sem `created_to` filtra "a partir de"."""
    assert _timestamps(_INICIO, None) == ["created_at >= '2026-09-01 00:00:00'"]
    assert _timestamps(None, _FIM) == ["created_at <= '2026-09-08 23:59:59.999999'"]
    assert _timestamps(None, None) == []


def test_um_dia_so_nao_e_intervalo_vazio() -> None:
    """`from == to` é o filtro mais usado da tela («o que entrou hoje») e o que mais sofre
    com a borda errada: com `time.min` nos dois lados ele passaria a devolver nada."""
    piso, teto = _timestamps(_FIM, _FIM)

    assert piso == "created_at >= '2026-09-08 00:00:00'"
    assert teto == "created_at <= '2026-09-08 23:59:59.999999'"


# ─────────────────────────────────────────────────────────────────────────────
# date_range — a irmã que já tinha dono, mantida aqui como controle
# ─────────────────────────────────────────────────────────────────────────────


def test_coluna_de_data_compara_direto_sem_combine() -> None:
    """Coluna `date` não tem hora: combinar 00:00/23:59 ali só criaria um `timestamp`
    para o Postgres converter de volta a cada linha."""
    assert _datas(_INICIO, _FIM) == ["due_date >= '2026-09-01'", "due_date <= '2026-09-08'"]


def test_intervalo_de_data_tambem_e_aberto() -> None:
    assert _datas(_INICIO, None) == ["due_date >= '2026-09-01'"]
    assert _datas(None, _FIM) == ["due_date <= '2026-09-08'"]
    assert _datas(None, None) == []


# ─────────────────────────────────────────────────────────────────────────────
# Page — o quarteto de paginação do §6, que era prosa
# ─────────────────────────────────────────────────────────────────────────────


def test_os_quatro_padroes_de_paginacao_sao_os_do_contrato() -> None:
    """CLAUDE.md §6: página de 20, mais novo primeiro, primeira página sem cursor.

    Os três defaults sobreviviam à suíte inteira. O `descending` não é cosmético:
    `financial/repository.py` lista lançamentos com `Page(limit=50)` e herda este valor —
    invertido, a listagem sai do mais antigo para o mais novo e ninguém reclama.
    """
    page = Page()

    assert page.sort == "created_at"
    assert page.descending is True
    assert page.cursor is None
    assert page.limit == 20


def test_page_e_imutavel() -> None:
    """`frozen=True`: uma página que alguém muda no meio da consulta é um cursor que
    aponta para outra coisa na segunda ida ao banco."""
    page = Page(sort="name", descending=False, cursor=("Ana", uuid.uuid4()), limit=50)

    with pytest.raises(AttributeError):
        page.limit = 10  # type: ignore[misc]  # é exatamente o que o frozen impede


def test_page_aceita_o_cursor_como_par_ordenado() -> None:
    """O cursor é `(valor_da_ordenação, id)` — o par que o `paginate_keyset` compara como
    tupla, e que é o desempate estável do §6."""
    identificador = uuid.uuid4()
    page = Page(sort="name", descending=False, cursor=("Ana", identificador), limit=5)

    assert page.cursor == ("Ana", identificador)
    assert page.descending is False
