"""Adapter do DjenClient para o contrato PublicationSource (spec 044, §6).

Mapeamento termo → query (descoberta registrada na spec):
- OAB → `numeroOab` + `ufOab` (filtro nativo da API);
- CPF/CNPJ → `texto` com os dígitos do termo — o DJEN não filtra por documento,
  mas o full-text no corpo filtra (verificado ao vivo em 2026-08-10).
"""

from datetime import date

from app.domain.monitored_terms.models import MonitoredTerm, TermKind
from app.domain.monitored_terms.sync import PublicationPage
from app.integrations.djen.client import MAX_PER_PAGE, DjenClient


class DjenPublicationSource:
    def __init__(self, client: DjenClient) -> None:
        self._client = client

    async def fetch(
        self, *, term: MonitoredTerm, start: date, end: date, page: int
    ) -> PublicationPage:
        if term.kind is TermKind.OAB:
            result = await self._client.fetch_communications(
                availability_start=start,
                availability_end=end,
                oab_number=term.value,
                oab_state=term.oab_state,
                page=page,
                per_page=MAX_PER_PAGE,
            )
        else:
            result = await self._client.fetch_communications(
                availability_start=start,
                availability_end=end,
                text_query=term.value,
                page=page,
                per_page=MAX_PER_PAGE,
            )
        return PublicationPage(count=result.count, items=result.items)
