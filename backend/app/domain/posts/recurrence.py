"""Alias de compatibilidade (spec 040, alvo 1): a implementação migrou para
`app/core/dates.py` — módulo único de datas, puro e sem framework. Mantido porque
testes de 034/038 importam daqui; código novo deve importar de `app.core.dates`."""

from app.core.dates import iter_occurrences, next_occurrence, preview_occurrences

__all__ = ["iter_occurrences", "next_occurrence", "preview_occurrences"]
