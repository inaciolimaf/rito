"""Client do DJEN (spec 042) — comunicaapi.pje.jus.br/api/v1/comunicacao.

Sem autenticação, mas exige User-Agent de browser (regra 1: sem ele, 403). Toda
a resiliência (retry, rate limit, breaker) mora na camada da spec 041 — este
client só monta a query, envia o User-Agent e delega o parse.
"""

from datetime import date

from pydantic import BaseModel

from app.integrations.djen.parser import ParsedCommunication, parse_communication
from app.integrations.http.types import HttpClient

MAX_PER_PAGE = 100  # regra 9: teto da API, protege o rate limit


class DjenConfigError(Exception):
    """User-Agent ausente — a API responde 403 sem ele, então falhamos antes."""


class DjenApiError(Exception):
    """Resposta não-200 que sobreviveu às retentativas da camada 041."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"DJEN respondeu status {status_code}")
        self.status_code = status_code


class DjenPage(BaseModel):
    count: int
    page: int
    items: list[ParsedCommunication]


class DjenClient:
    def __init__(self, *, http: HttpClient, base_url: str, user_agent: str) -> None:
        if not user_agent.strip():
            raise DjenConfigError(
                "DJEN_USER_AGENT não configurado — a API exige User-Agent de browser (403 sem ele)."
            )
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent

    async def fetch_communications(
        self,
        *,
        availability_start: date,
        availability_end: date,
        oab_number: str | None = None,
        oab_state: str | None = None,
        process_number: str | None = None,
        page: int = 1,
        per_page: int = MAX_PER_PAGE,
    ) -> DjenPage:
        params = {
            "dataDisponibilizacaoInicio": availability_start.isoformat(),
            "dataDisponibilizacaoFim": availability_end.isoformat(),
            "meio": "D",
            "pagina": str(page),
            "itensPorPagina": str(min(per_page, MAX_PER_PAGE)),
        }
        if oab_number:
            params["numeroOab"] = oab_number
        if oab_state:
            params["ufOab"] = oab_state
        if process_number:
            params["numeroProcesso"] = process_number

        response = await self._http.request(
            "GET",
            f"{self._base_url}/comunicacao",
            headers={"User-Agent": self._user_agent},
            params=params,
        )
        if response.status_code != 200:
            raise DjenApiError(response.status_code)

        payload = response.json()
        return DjenPage(
            count=int(payload.get("count", 0)),
            page=page,
            items=[parse_communication(item) for item in payload.get("items", [])],
        )
