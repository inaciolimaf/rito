"""Cálculo de prazo de intimação (spec 086, regras 2, 3 e 5).

A spec exige tabela de casos: 5, 15 e 30 dias úteis, publicação na sexta-feira, véspera
de feriado prolongado e virada de ano. É o teste mais barato do projeto e cobre a conta
que, errada, faz o escritório perder prazo.
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
    ("publicacao", "dias", "esperado", "porque"),
    [
        # Quarta-feira: 5 dias úteis caem na quarta seguinte.
        (date(2026, 8, 5), 5, date(2026, 8, 12), "5 dias úteis, semana cheia"),
        (date(2026, 8, 5), 15, date(2026, 8, 26), "15 dias úteis, semana cheia"),
        (date(2026, 8, 5), 30, date(2026, 9, 17), "30 dias úteis atravessam o 7 de setembro"),
        # Sexta-feira: a contagem começa na segunda seguinte.
        (date(2026, 8, 7), 5, date(2026, 8, 14), "publicado na sexta"),
        # Véspera de feriado prolongado (quinta antes da Sexta-feira Santa).
        (date(2026, 4, 2), 5, date(2026, 4, 10), "feriado emenda o fim de semana"),
        # Natal numa sexta: o feriado não conta, mas o prazo ainda fecha em 2026.
        (date(2026, 12, 23), 5, date(2026, 12, 31), "atravessa o Natal"),
        # Virada de ano, com 1º de janeiro numa sexta: o prazo cai só em 2027.
        (date(2026, 12, 28), 5, date(2027, 1, 5), "atravessa a virada do ano"),
    ],
)
def test_prazo_em_dias_uteis(publicacao: date, dias: int, esperado: date, porque: str) -> None:
    assert (
        compute_deadline(availability_date=publicacao, days=dias, kind="uteis", holidays=FERIADOS)
        == esperado
    ), porque


def test_prazo_em_dias_corridos_prorroga_para_o_proximo_dia_util() -> None:
    """Regra 3: quando o texto indica dias corridos, conta-se em calendário — mas o
    vencimento em dia sem expediente prorroga (CPC art. 224, §1º)."""
    # 2026-08-05 + 15 corridos = 2026-08-20 (quinta), dia útil: vence nele mesmo.
    assert compute_deadline(
        availability_date=date(2026, 8, 5), days=15, kind="corridos", holidays=FERIADOS
    ) == date(2026, 8, 20)

    # 2026-08-07 + 15 corridos = 2026-08-22 (sábado) → segunda-feira.
    assert compute_deadline(
        availability_date=date(2026, 8, 7), days=15, kind="corridos", holidays=FERIADOS
    ) == date(2026, 8, 24)

    # Cai em feriado nacional (25/12, sexta) → próximo dia útil.
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


def test_confianca_baixa_nao_preenche_o_campo() -> None:
    """Regra 4: mostrar o número e não preencher é a diferença entre ajudar e decidir."""
    assert should_prefill(0.95) is True
    assert should_prefill(0.8) is True
    assert should_prefill(0.79) is False
    assert should_prefill(None) is False
