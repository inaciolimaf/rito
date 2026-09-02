"""Client da API Pública do DataJud (spec 046) — api-publica.datajud.cnj.jus.br.

Toda a resiliência (retry, rate limit, breaker) mora na camada da spec 041 —
este client só monta a query Elasticsearch, envia a `APIKey` e delega o parse.
`401` NUNCA é retentado pela camada 041 (fora de `HostPolicy.retry_on`) — o
client só precisa reconhecer o status e levantar o erro específico; quem
decide o que fazer com ele (alerta + pausa, regra 3) é o `DatajudService`.
"""

import json

from app.integrations.datajud.base import (
    DatajudApiError,
    DatajudConfigError,
    DatajudUnauthorizedError,
)
from app.integrations.datajud.parser import ParsedProcess, normalize_process_number, parse_process
from app.integrations.http.types import HttpClient

# Os três erros passaram a morar em `base.py` com o protocolo que os levanta (spec 118,
# §4.D). Ficam reexportados aqui porque quem os importava de `client` continua certo.
# A conformidade com `LawsuitSource` é estrutural — sem herança, como `S3FileStorage`
# para `FileStorage` e `DjenPublicationSource` para `PublicationSource`. Quem prova que
# ela vale é `tests/unit/test_datajud_source.py`.
__all__ = [
    "DatajudApiError",
    "DatajudClient",
    "DatajudConfigError",
    "DatajudUnauthorizedError",
]


class DatajudClient:
    def __init__(self, *, http: HttpClient, base_url: str, api_key: str) -> None:
        if not api_key.strip():
            raise DatajudConfigError(
                "DATAJUD_API_KEY não configurado. Regra 2: é a chave PÚBLICA do CNJ, não "
                "uma credencial pessoal — gere uma em "
                "https://www.cnj.jus.br/sistemas/datajud/api-publica/."
            )
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def search_by_process_number(
        self, *, alias: str, process_number: str
    ) -> list[ParsedProcess]:
        # Regra 5: número vai só com dígitos na query.
        digits = normalize_process_number(process_number)
        body = json.dumps({"query": {"match": {"numeroProcesso": digits}}}).encode()

        response = await self._http.request(
            "GET",
            f"{self._base_url}/{alias}/_search",
            headers={
                "Authorization": f"APIKey {self._api_key}",
                "Content-Type": "application/json",
            },
            content=body,
        )
        if response.status_code == 401:
            raise DatajudUnauthorizedError
        if response.status_code != 200:
            raise DatajudApiError(response.status_code)

        payload = response.json()
        hits = payload.get("hits", {}).get("hits", [])
        return [parse_process(hit["_source"]) for hit in hits if "_source" in hit]
