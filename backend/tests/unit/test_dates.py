"""Prazo processual em `app/core/dates.py` (spec 126, regras 1 a 3).

É a conta que, errada, faz advogado perder prazo — e é função pura, então o teste é
barato e é aqui que o valor está. Todas as datas são FIXAS: nenhum caso depende do dia
em que a suíte roda.

Os feriados usados são os mesmos que a migration `038_workflows` semeia (9 fixos + os 4
móveis derivados da Páscoa), reescritos aqui porque o módulo é puro e recebe o calendário
por parâmetro — testar contra o banco seria testar outra coisa.
"""

from datetime import date

import pytest

from app.core.dates import (
    add_procedural_days,
    is_court_recess,
    is_procedural_day,
    procedural_deadline,
    publication_date,
)

FERIADOS_2026 = {
    date(2026, 1, 1),  # Confraternização (quinta)
    date(2026, 2, 16),  # Carnaval (segunda)
    date(2026, 2, 17),  # Carnaval (terça)
    date(2026, 4, 3),  # Sexta-feira Santa
    date(2026, 4, 21),  # Tiradentes (terça)
    date(2026, 5, 1),  # Dia do Trabalho (sexta)
    date(2026, 6, 4),  # Corpus Christi (quinta)
    date(2026, 9, 7),  # Independência (segunda)
    date(2026, 10, 12),  # Aparecida (segunda)
    date(2026, 11, 2),  # Finados (segunda)
    date(2026, 11, 15),  # Proclamação (domingo)
    date(2026, 11, 20),  # Consciência Negra (sexta)
    date(2026, 12, 25),  # Natal (sexta)
}
FERIADOS_2027 = {
    date(2027, 1, 1),  # Confraternização (sexta)
    date(2027, 2, 8),  # Carnaval (segunda)
    date(2027, 2, 9),  # Carnaval (terça)
    date(2027, 3, 26),  # Sexta-feira Santa
    date(2027, 4, 21),  # Tiradentes (quarta)
    date(2027, 5, 1),  # Dia do Trabalho (sábado)
    date(2027, 5, 27),  # Corpus Christi (quinta)
}
FERIADOS = FERIADOS_2026 | FERIADOS_2027


# ---------------------------------------------------------------------------
# Art. 224 §2 — disponibilização não é publicação
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("disponibilizacao", "publicacao", "porque"),
    [
        (date(2026, 8, 5), date(2026, 8, 6), "quarta → quinta, semana cheia"),
        (date(2026, 8, 7), date(2026, 8, 10), "sexta → segunda, o fim de semana não conta"),
        (date(2026, 8, 8), date(2026, 8, 10), "sábado → segunda"),
        (date(2026, 4, 2), date(2026, 4, 6), "quinta antes da Sexta-feira Santa → segunda"),
        (date(2026, 12, 24), date(2026, 12, 28), "véspera de Natal numa sexta → segunda"),
        (date(2026, 12, 31), date(2027, 1, 4), "vira o ano: 01/01 é feriado numa sexta"),
    ],
)
def test_publicacao_e_o_primeiro_dia_util_seguinte(
    disponibilizacao: date, publicacao: date, porque: str
) -> None:
    """CPC art. 224 §2 / Lei 11.419 art. 4º §3º. Confundir as duas datas encurta TODO
    prazo do sistema em um dia útil, e é o erro mais fácil de cometer aqui."""
    assert publication_date(disponibilizacao, FERIADOS) == publicacao, porque


# ---------------------------------------------------------------------------
# Art. 220 — recesso forense
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("dia", "no_recesso"),
    [
        (date(2026, 12, 19), False),  # véspera: ainda corre
        (date(2026, 12, 20), True),  # primeira ponta, inclusive
        (date(2027, 1, 4), True),  # meio do recesso, dia útil de calendário
        (date(2027, 1, 20), True),  # segunda ponta, inclusive
        (date(2027, 1, 21), False),  # volta a correr
        (date(2026, 6, 15), False),  # meio do ano
    ],
)
def test_recesso_forense_pega_as_duas_pontas(dia: date, no_recesso: bool) -> None:
    """Art. 220: "entre 20 de dezembro e 20 de janeiro, **inclusive**". As duas pontas
    entram, e é justamente nelas que um `>` no lugar de `>=` passa despercebido."""
    assert is_court_recess(dia) is no_recesso


def test_dia_de_recesso_nao_e_dia_de_prazo_mesmo_sendo_dia_util() -> None:
    """04/01/2027 é uma segunda-feira sem feriado nenhum: dia útil para o workflow
    (spec 038), dia parado para o prazo processual."""
    assert is_procedural_day(date(2027, 1, 4), FERIADOS) is False
    assert is_procedural_day(date(2027, 1, 4), FERIADOS, court_recess=False) is True


def test_recesso_desligado_conta_como_dia_util_comum() -> None:
    """O recesso é parâmetro, não constante escondida — prazo administrativo não para."""
    inicio = date(2026, 12, 18)  # sexta
    assert add_procedural_days(inicio, 3, FERIADOS) == date(2027, 1, 25)
    assert add_procedural_days(inicio, 3, FERIADOS, court_recess=False) == date(2026, 12, 23)


# ---------------------------------------------------------------------------
# A cadeia inteira: arts. 224 §2 → 224 caput → 219 → 220
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("disponibilizacao", "dias", "esperado", "porque"),
    [
        # Semana cheia: publicação em 06/08 (quinta), dia 1 em 07/08 (sexta).
        (date(2026, 8, 5), 5, date(2026, 8, 13), "5 dias úteis, semana cheia"),
        (date(2026, 8, 5), 15, date(2026, 8, 27), "15 dias úteis, semana cheia"),
        (date(2026, 8, 5), 30, date(2026, 9, 18), "30 dias úteis atravessam o 7 de setembro"),
        (date(2026, 8, 5), 1, date(2026, 8, 7), "prazo de 1 dia: o dia seguinte à publicação"),
        # Disponibilização na sexta: publicação na segunda, contagem começa na terça.
        (date(2026, 8, 7), 5, date(2026, 8, 17), "disponibilizado na sexta"),
        # Véspera de feriado prolongado: quinta 02/04, Sexta-feira Santa em 03/04.
        (date(2026, 4, 2), 5, date(2026, 4, 13), "o feriado emenda o fim de semana"),
        # Feriado emendado no MEIO da contagem: Carnaval segunda (08/02) e terça
        # (09/02) de 2027 comem dois dias, e o 5º dia escorrega para a segunda seguinte.
        (date(2027, 2, 3), 5, date(2027, 2, 15), "Carnaval come dois dias da contagem"),
        # Tiradentes numa terça, no meio do prazo.
        (date(2026, 4, 15), 5, date(2026, 4, 24), "Tiradentes no meio do caminho"),
    ],
)
def test_prazo_em_dias_uteis(
    disponibilizacao: date, dias: int, esperado: date, porque: str
) -> None:
    assert procedural_deadline(disponibilizacao, dias, FERIADOS) == esperado, porque


@pytest.mark.parametrize(
    ("disponibilizacao", "dias", "esperado", "porque"),
    [
        # Publicação 24/12: o dia 1 seria 28/12, que está no recesso — a contagem só
        # começa em 21/01/2027 (quinta), e o 5º dia cai em 27/01.
        (date(2026, 12, 23), 5, date(2027, 1, 27), "prazo inteiro engolido pelo recesso"),
        # Publicação 18/12 (sexta): dia 1 em 21/12? Não — 21/12 já é recesso. Idem.
        (date(2026, 12, 17), 5, date(2027, 1, 27), "recesso começa antes do dia 1"),
        # Começa a correr ANTES do recesso e é suspenso no meio: publicação 16/12
        # (quarta), dias 1 e 2 em 17 e 18/12, os outros 3 só depois de 20/01.
        (date(2026, 12, 15), 5, date(2027, 1, 25), "suspenso no meio da contagem"),
        # Publicação em 04/01, dentro do recesso: nada corre até 21/01.
        (date(2026, 12, 31), 3, date(2027, 1, 25), "publicado dentro do recesso"),
    ],
)
def test_recesso_suspende_o_curso_do_prazo(
    disponibilizacao: date, dias: int, esperado: date, porque: str
) -> None:
    """Art. 220: o prazo não é adiado, é SUSPENSO — os dias já corridos contam, e o
    resto volta a correr em 21/01."""
    assert procedural_deadline(disponibilizacao, dias, FERIADOS) == esperado, porque


@pytest.mark.parametrize(
    ("disponibilizacao", "dias", "esperado", "porque"),
    [
        # 06/08 + 15 corridos = 21/08 (sexta), dia útil: vence nele mesmo.
        (date(2026, 8, 5), 15, date(2026, 8, 21), "vencimento em dia útil"),
        # 10/08 + 15 corridos = 25/08 (terça).
        (date(2026, 8, 7), 15, date(2026, 8, 25), "disponibilizado na sexta"),
        # 11/12 + 15 = 26/12 (sábado) → segunda 28/12, mesmo estando no recesso: dias
        # corridos não são prazo processual e o art. 220 não os alcança.
        (date(2026, 12, 10), 15, date(2026, 12, 28), "prorroga para o dia útil seguinte"),
    ],
)
def test_prazo_em_dias_corridos(
    disponibilizacao: date, dias: int, esperado: date, porque: str
) -> None:
    """Art. 219, parágrafo único: a contagem em dias úteis vale só para prazo
    processual. O único ajuste que sobra é o do art. 224 §1 — vencimento em dia sem
    expediente prorroga."""
    assert (
        procedural_deadline(disponibilizacao, dias, FERIADOS, count_in_business_days=False)
        == esperado
    ), porque


def test_calendario_vazio_conta_so_o_fim_de_semana() -> None:
    """Sem feriado cadastrado a conta não quebra — ela fica ERRADA para menos, e é por
    isso que a migration 126 semeia até 2040: prazo contra tabela vazia vence antes."""
    com_feriados = procedural_deadline(date(2026, 12, 23), 5, FERIADOS, court_recess=False)
    sem_feriados = procedural_deadline(date(2026, 12, 23), 5, set(), court_recess=False)
    assert com_feriados == date(2027, 1, 4)
    assert sem_feriados == date(2026, 12, 31)
    assert sem_feriados < com_feriados


def test_prazo_menor_que_um_dia_e_erro() -> None:
    """Zero ou negativo não é "sem prazo" — é chamada errada. Quem não tem número usa
    `None` e não chega aqui (ver `publications/deadline.py`)."""
    with pytest.raises(ValueError, match="ao menos 1"):
        procedural_deadline(date(2026, 8, 5), 0, FERIADOS)
    with pytest.raises(ValueError, match="ao menos 1"):
        procedural_deadline(date(2026, 8, 5), -3, FERIADOS)


def test_offset_negativo_em_dias_processuais_e_erro() -> None:
    with pytest.raises(ValueError, match="negativo"):
        add_procedural_days(date(2026, 8, 5), -1, FERIADOS)


def test_offset_zero_em_dias_processuais_e_o_proprio_dia() -> None:
    """Mesma regra de `add_business_days` (spec 038, regra 4): "hoje" não desliza."""
    assert add_procedural_days(date(2027, 1, 4), 0, FERIADOS) == date(2027, 1, 4)
