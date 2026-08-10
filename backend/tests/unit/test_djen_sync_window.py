"""Cálculo de next_sync_at a partir do DJEN_SYNC_CRON (spec 044, §6)."""

from datetime import UTC, datetime

import pytest

from app.domain.monitored_terms.sync import next_daily_run


def test_mesmo_dia_quando_horario_ainda_nao_passou() -> None:
    now = datetime(2026, 8, 10, 1, 0, tzinfo=UTC)
    assert next_daily_run("17 3 * * *", now) == datetime(2026, 8, 10, 3, 17, tzinfo=UTC)


def test_dia_seguinte_quando_horario_ja_passou() -> None:
    now = datetime(2026, 8, 10, 4, 0, tzinfo=UTC)
    assert next_daily_run("17 3 * * *", now) == datetime(2026, 8, 11, 3, 17, tzinfo=UTC)


def test_exatamente_no_horario_conta_como_passado() -> None:
    now = datetime(2026, 8, 10, 3, 17, tzinfo=UTC)
    assert next_daily_run("17 3 * * *", now) == datetime(2026, 8, 11, 3, 17, tzinfo=UTC)


@pytest.mark.parametrize(
    "cron",
    ["17 3 * * 1", "17 3 1 * *", "17 3 * *", "17 3 * * * *", "17 3"],
)
def test_cron_nao_diario_e_rejeitado(cron: str) -> None:
    """Só a forma diária é suportada — o cálculo não sabe avançar semana/mês;
    falhar explícito é melhor que agendar errado em silêncio."""
    with pytest.raises(ValueError, match="diário"):
        next_daily_run(cron, datetime(2026, 8, 10, tzinfo=UTC))
