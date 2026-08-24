"""BI: Tempo e Honorários (spec 076) — a definição canônica dos 4 ciclos
(`compute_cycle_days`), sem banco. O SQL da matview `bi_lawsuit_cycles`
(migration 076) espelha exatamente esta aritmética. Casos sobre datas FIXAS."""

from datetime import date

from app.domain.bi.service import compute_cycle_days


def test_quatro_ciclos_com_datas_completas() -> None:
    """Regra 1: prospecção (criação → fechamento), produção (fechamento → trânsito),
    execução (trânsito → arquivamento), rotação completa (criação → arquivamento)."""
    cycles = compute_cycle_days(
        created=date(2024, 1, 1),
        closure=date(2024, 1, 31),
        transit=date(2024, 5, 31),
        archived=date(2024, 9, 30),
    )
    assert cycles.prospecting_days == 30
    assert cycles.production_days == 121
    assert cycles.execution_days == 122
    assert cycles.full_cycle_days == 273


def test_ciclo_com_data_faltando_e_nulo_nao_zero() -> None:
    """Regra 2: data faltando → ciclo NULO ("não sei"), nunca zero. Zero só existe
    quando as duas datas coincidem ("no mesmo dia") — são coisas diferentes."""
    sem_transito = compute_cycle_days(
        created=date(2024, 1, 1),
        closure=date(2024, 1, 31),
        transit=None,
        archived=date(2024, 9, 30),
    )
    # Produção e execução dependem do trânsito: nulos. Prospecção e rotação não.
    assert sem_transito.prospecting_days == 30
    assert sem_transito.production_days is None
    assert sem_transito.execution_days is None
    assert sem_transito.full_cycle_days == 273

    sem_arquivamento = compute_cycle_days(
        created=date(2024, 1, 1),
        closure=date(2024, 1, 31),
        transit=date(2024, 5, 31),
        archived=None,
    )
    assert sem_arquivamento.prospecting_days == 30
    assert sem_arquivamento.production_days == 121
    assert sem_arquivamento.execution_days is None
    assert sem_arquivamento.full_cycle_days is None

    sem_fechamento = compute_cycle_days(
        created=date(2024, 1, 1),
        closure=None,
        transit=None,
        archived=None,
    )
    assert sem_fechamento.prospecting_days is None
    assert sem_fechamento.production_days is None
    assert sem_fechamento.execution_days is None
    assert sem_fechamento.full_cycle_days is None

    # Contraste: todas as datas no mesmo dia → zero em todos os ciclos, não nulo.
    mesmo_dia = compute_cycle_days(
        created=date(2024, 3, 1),
        closure=date(2024, 3, 1),
        transit=date(2024, 3, 1),
        archived=date(2024, 3, 1),
    )
    assert mesmo_dia.prospecting_days == 0
    assert mesmo_dia.production_days == 0
    assert mesmo_dia.execution_days == 0
    assert mesmo_dia.full_cycle_days == 0
