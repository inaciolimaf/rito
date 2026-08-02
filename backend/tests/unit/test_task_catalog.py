"""Integridade do catálogo padrão (spec 031 §4): fonte da seed da migration 031.

O levantamento titula "152" mas lista 149 nomes únicos — 149 + 3 sistêmicas = 152
linhas por tenant (ver catalog.py e Descobertas da spec)."""

from app.domain.task_types.catalog import (
    DEFAULT_TASK_NAMES,
    OBSERVED_REWARDS,
    SYSTEM_TASK_NAMES,
)


def test_catalogo_tem_149_nomes_unicos_e_3_sistemicas() -> None:
    assert len(DEFAULT_TASK_NAMES) == 149
    assert len(set(DEFAULT_TASK_NAMES)) == 149
    assert len(SYSTEM_TASK_NAMES) == 3
    assert set(SYSTEM_TASK_NAMES).isdisjoint(DEFAULT_TASK_NAMES)


def test_pontuacoes_observadas_cobrem_so_nomes_do_catalogo() -> None:
    # As 19 pontuações do levantamento — nenhuma inventada, todas mapeadas.
    assert len(OBSERVED_REWARDS) == 19
    assert set(OBSERVED_REWARDS) <= set(DEFAULT_TASK_NAMES)
    assert all(points > 0 for points in OBSERVED_REWARDS.values())
