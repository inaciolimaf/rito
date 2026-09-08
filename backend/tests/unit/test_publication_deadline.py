"""Cálculo de prazo de intimação (spec 086, regras 2, 3 e 5; corrigido pela 126).

A spec exige tabela de casos: 5, 15 e 30 dias úteis, disponibilização na sexta-feira,
véspera de feriado prolongado e virada de ano. É o teste mais barato do projeto e cobre a
conta que, errada, faz o escritório perder prazo.

**As datas esperadas mudaram na spec 126, e a mudança é uma correção.** Até ela,
`compute_deadline` tratava a data de DISPONIBILIZAÇÃO como se fosse a data da PUBLICAÇÃO,
e pulava o art. 224 §2 do CPC ("considera-se como data da publicação o primeiro dia útil
seguinte ao da disponibilização") — todo prazo saía um dia útil mais curto do que o legal.
A 126 acrescentou esse passo e a suspensão do recesso forense (art. 220), e é por isso que
cada linha aqui andou. A mecânica agora mora em `app/core/dates.py` e tem tabela própria
em `tests/unit/test_dates.py`; o que sobra aqui é a política desta feature.
"""

from datetime import date

import pytest

from app.domain.publications.deadline import compute_deadline, should_prefill

# Feriados nacionais de referência (os que aparecem nos casos abaixo).
FERIADOS = {
    date(2026, 4, 3),  # Sexta-feira Santa
    date(2026, 4, 21),  # Tiradentes (terça)
    date(2026, 9, 7),  # Independência (segunda)
    date(2026, 12, 25),  # Natal (sexta)
    date(2027, 1, 1),  # Confraternização (sexta)
}


@pytest.mark.parametrize(
    ("disponibilizacao", "dias", "esperado", "porque"),
    [
        # Quarta 05/08: publicação na quinta 06/08, dia 1 na sexta 07/08.
        (date(2026, 8, 5), 5, date(2026, 8, 13), "5 dias úteis, semana cheia"),
        (date(2026, 8, 5), 15, date(2026, 8, 27), "15 dias úteis, semana cheia"),
        (date(2026, 8, 5), 30, date(2026, 9, 18), "30 dias úteis atravessam o 7 de setembro"),
        # Sexta-feira: publicação na segunda, a contagem começa na terça.
        (date(2026, 8, 7), 5, date(2026, 8, 17), "disponibilizado na sexta"),
        # Véspera de feriado prolongado (quinta antes da Sexta-feira Santa).
        (date(2026, 4, 2), 5, date(2026, 4, 13), "feriado emenda o fim de semana"),
    ],
)
def test_prazo_em_dias_uteis(
    disponibilizacao: date, dias: int, esperado: date, porque: str
) -> None:
    assert (
        compute_deadline(
            availability_date=disponibilizacao, days=dias, kind="uteis", holidays=FERIADOS
        )
        == esperado
    ), porque


@pytest.mark.parametrize(
    ("disponibilizacao", "dias", "esperado", "porque"),
    [
        (date(2026, 12, 23), 5, date(2027, 1, 27), "publicação em 24/12, tudo dentro do recesso"),
        (date(2026, 12, 28), 5, date(2027, 1, 27), "disponibilizado já dentro do recesso"),
    ],
)
def test_prazo_que_cai_no_recesso_forense_so_volta_a_correr_em_21_de_janeiro(
    disponibilizacao: date, dias: int, esperado: date, porque: str
) -> None:
    """Art. 220 do CPC (spec 126): entre 20/12 e 20/01 o prazo processual não corre.

    Este é o caso em que a versão anterior errava mais feio — ela devolvia uma data de
    começo de janeiro, no meio do recesso, e o advogado que confiasse nela trabalharia
    contra um prazo que a lei tinha suspendido.
    """
    assert (
        compute_deadline(
            availability_date=disponibilizacao, days=dias, kind="uteis", holidays=FERIADOS
        )
        == esperado
    ), porque


def test_prazo_em_dias_corridos_prorroga_para_o_proximo_dia_util() -> None:
    """Regra 3: quando o texto indica dias corridos, conta-se em calendário — mas o
    vencimento em dia sem expediente prorroga (CPC art. 224, §1º). O recesso do art. 220
    não alcança esses prazos (art. 219, parágrafo único)."""
    # Publicação em 06/08, + 15 corridos = 2026-08-21 (sexta), dia útil: vence nele mesmo.
    assert compute_deadline(
        availability_date=date(2026, 8, 5), days=15, kind="corridos", holidays=FERIADOS
    ) == date(2026, 8, 21)

    # Publicação em 10/08, + 15 corridos = 2026-08-25 (terça).
    assert compute_deadline(
        availability_date=date(2026, 8, 7), days=15, kind="corridos", holidays=FERIADOS
    ) == date(2026, 8, 25)

    # Publicação em 11/12, + 15 = 26/12 (sábado) → segunda 28/12, dentro do recesso e
    # ainda assim válida: dias corridos não são prazo processual.
    assert compute_deadline(
        availability_date=date(2026, 12, 10), days=15, kind="corridos", holidays=FERIADOS
    ) == date(2026, 12, 28)


def test_sem_prazo_identificado_nao_inventa_data() -> None:
    """Regra 5: devolver uma data "aproximada" seria pior do que não responder — parece
    uma resposta."""
    assert (
        compute_deadline(
            availability_date=date(2026, 8, 5), days=None, kind=None, holidays=FERIADOS
        )
        is None
    )
    assert (
        compute_deadline(
            availability_date=date(2026, 8, 5), days=0, kind="uteis", holidays=FERIADOS
        )
        is None
    )


def test_kind_ausente_conta_como_dias_uteis() -> None:
    """O modelo nem sempre diz a espécie. Dias úteis é o padrão porque é o do art. 219 —
    e é o mais conservador dos dois quando o vencimento cai perto do recesso."""
    assert compute_deadline(
        availability_date=date(2026, 8, 5), days=5, kind=None, holidays=FERIADOS
    ) == date(2026, 8, 13)


def test_confianca_baixa_nao_preenche_o_campo() -> None:
    """Regra 4: mostrar o número e não preencher é a diferença entre ajudar e decidir."""
    assert should_prefill(0.95) is True
    assert should_prefill(0.8) is True
    assert should_prefill(0.79) is False
    assert should_prefill(None) is False
