"""Alias de compatibilidade (spec 040, alvo 1): a implementação migrou para
`app/core/dates.py` — módulo único de datas. Mantido porque testes de 038 importam
daqui; código novo (incluindo a 086, prazo processual) deve importar de
`app.core.dates`."""

from app.core.dates import add_business_days, is_business_day

__all__ = ["add_business_days", "is_business_day"]
