"""Cálculo do prazo de uma intimação (specs 086 e 126).

Esta é a parte que **não** pode ser deixada para o modelo: extrair "15 dias úteis" de um
texto é trabalho de linguagem; contar 15 dias úteis a partir da data certa, pulando
feriado e recesso, é aritmética — e aritmética a gente faz com código testado, não com um
modelo que às vezes acerta.

A aritmética em si mora em `app/core/dates.py` (`procedural_deadline`, spec 126): é lei
processual, não regra de intimação, e o financeiro e os workflows contam dias úteis pelo
mesmo módulo. O que sobra aqui é a política desta feature — o que fazer quando NÃO há
prazo identificado (regra 5: nada) e quando não há confiança suficiente para preencher o
campo (regra 4).

`days` chega de duas fontes, nunca de um palpite do código:

- do TEXTO da intimação, lido pelo modelo e conferido por um humano (spec 086);
- da CONFIGURAÇÃO do escritório, declarada pelo gestor (spec 126).

Não existe terceira. Não há neste projeto tabela de prazos por classe/assunto do CNJ, e a
spec 126 §3 registra por que não se inventa uma.
"""

from collections.abc import Collection
from datetime import date
from typing import Literal

from app.core.dates import procedural_deadline

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

    `availability_date` é a data de DISPONIBILIZAÇÃO no diário (o que o DJEN entrega); a
    publicação é o dia útil seguinte e o dia 1 do prazo é o dia útil depois dela —
    `procedural_deadline` faz os dois passos.

    Regra 5: sem prazo no texto, não se inventa data — devolver "hoje + 15" seria pior
    do que não responder, porque parece uma resposta.
    """
    if days is None or days <= 0:
        return None
    return procedural_deadline(
        availability_date,
        days,
        holidays,
        # Art. 219, parágrafo único: a contagem em dias úteis (e, com ela, a suspensão do
        # recesso do art. 220) vale só para prazo processual. Prazo em dias corridos aqui
        # é o administrativo, que corre no recesso.
        count_in_business_days=kind != "corridos",
        court_recess=kind != "corridos",
    )


def should_prefill(confidence: float | None) -> bool:
    """Regra 4: confiança baixa mostra o número, mas não preenche o campo — quem
    preenche assume, e o objetivo é o contrário."""
    return confidence is not None and confidence >= MIN_CONFIDENCE_TO_PREFILL
