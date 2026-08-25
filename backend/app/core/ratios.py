"""Divisão segura para indicador (refatoração 080, alvo 3).

O produto inteiro tem a mesma regra escrita em nove lugares: **denominador zero vira
`None`, que a UI mostra como "—"** — nunca 0, nunca NaN, nunca ∞. Zero e "não dá para
calcular" são coisas diferentes para quem lê um relatório: 0% de conversão é um
diagnóstico, "nenhuma oportunidade no período" é a ausência dele.

`safe_ratio` é o único lugar onde essa decisão mora. Quem tem regra extra (CAC só
existe se houve gasto de marketing, por exemplo) mantém a própria condição por fora,
mas a divisão em si passa por aqui.
"""

from decimal import Decimal

__all__ = ["safe_percentage", "safe_ratio"]


def safe_ratio(
    numerator: float | int | Decimal | None,
    denominator: float | int | Decimal | None,
    *,
    digits: int | None = 2,
) -> float | None:
    """`numerator / denominator`, ou `None` se não há como dividir.

    `digits=None` devolve o quociente sem arredondar — para quem arredonda depois (a
    agilidade da 071 formata na resposta).
    """
    if numerator is None or denominator is None or float(denominator) == 0.0:
        return None
    value = float(numerator) / float(denominator)
    return value if digits is None else round(value, digits)


def safe_percentage(
    numerator: float | int | Decimal | None,
    denominator: float | int | Decimal | None,
    *,
    digits: int | None = 1,
) -> float | None:
    """A mesma divisão em pontos percentuais — a forma mais comum nos painéis.

    Arredonda uma vez só, no fim: arredondar o quociente antes de multiplicar por 100
    moveria a casa decimal do resultado.
    """
    ratio = safe_ratio(numerator, denominator, digits=None)
    if ratio is None:
        return None
    return ratio * 100 if digits is None else round(ratio * 100, digits)
