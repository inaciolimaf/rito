"""Financeiro: divisão de parcelas (spec 057, regra 2) — puro, sem banco."""

from datetime import date
from decimal import Decimal

from app.domain.financial.service import _installment_due_dates, _split_amount


def test_soma_das_parcelas_bate_com_o_total_com_resto_na_ultima() -> None:
    shares = _split_amount(Decimal("999.97"), 4)
    assert sum(shares) == Decimal("999.97")
    assert shares[:-1] == [Decimal("249.99")] * 3
    assert shares[-1] == Decimal("249.99") + (Decimal("999.97") - Decimal("249.99") * 4)


def test_100_dividido_por_3_da_33_33_33_33_e_33_34() -> None:
    shares = _split_amount(Decimal("100.00"), 3)
    assert shares == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
    assert sum(shares) == Decimal("100.00")


def test_dia_31_em_fevereiro_vai_para_o_ultimo_dia() -> None:
    dates = _installment_due_dates(date(2026, 1, 31), 3)
    assert dates == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]


def test_soma_fecha_com_o_total_para_todo_n_de_2_a_100() -> None:
    """Auditoria numérica (refatoração 060, Alvo 1) — o invariante "soma das parcelas
    == total" vale no intervalo INTEIRO aceito (2 a 100, regra `InstallmentRequest`),
    não só nos poucos N já cobertos acima. Alguns totais propositalmente "feios" pra
    testar arredondamento em várias direções (primo, com dízima, redondo)."""
    for total in (Decimal("999.97"), Decimal("100.00"), Decimal("0.01"), Decimal("123456.78")):
        for count in range(2, 101):
            shares = _split_amount(total, count)
            assert len(shares) == count
            assert sum(shares) == total, (total, count)
