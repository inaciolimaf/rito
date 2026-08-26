"""Cálculo do prazo de uma intimação (spec 086, regras 2 e 3).

Esta é a parte da spec que **não** pode ser deixada para o modelo: extrair "15 dias
úteis" de um texto é trabalho de linguagem; contar 15 dias úteis a partir da data certa,
pulando feriado, é aritmética — e aritmética a gente faz com código testado, não com um
modelo que às vezes acerta.

Contagem (regra 2, CPC art. 224): o prazo começa a correr no primeiro dia útil DEPOIS da
disponibilização, e é isso que `add_business_days(availability, dias)` já faz — o
primeiro dia contado é o dia útil seguinte.
"""

from collections.abc import Collection
from datetime import date, timedelta
from typing import Literal

from app.core.dates import add_business_days, is_business_day

DeadlineKind = Literal["uteis", "corridos"]

# Regra 4: abaixo disso a UI não pré-preenche nada.
MIN_CONFIDENCE_TO_PREFILL = 0.8


def compute_deadline(
    *,
    availability_date: date,
    days: int | None,
    kind: DeadlineKind | None,
    holidays: Collection[date],
) -> date | None:
    """Data final do prazo, ou `None` quando não há prazo identificado.

    Regra 5: sem prazo no texto, não se inventa data — devolver "hoje + 15" seria pior
    do que não responder, porque parece uma resposta.
    """
    if days is None or days <= 0:
        return None
    if kind == "corridos":
        # Dias corridos contam do dia seguinte, e o vencimento em dia sem expediente
        # prorroga para o próximo dia útil (CPC art. 224, §1º).
        alvo = availability_date + timedelta(days=days)
        while not is_business_day(alvo, holidays):
            alvo += timedelta(days=1)
        return alvo
    return add_business_days(availability_date, days, holidays)


def should_prefill(confidence: float | None) -> bool:
    """Regra 4: confiança baixa mostra o número, mas não preenche o campo — quem
    preenche assume, e o objetivo é o contrário."""
    return confidence is not None and confidence >= MIN_CONFIDENCE_TO_PREFILL
