"""O contrato da fonte de processos — `LawsuitSource` (spec 118, §4.D).

Por que esta interface existe (e por que o `djen` já tinha a dele desde a 044): o
`CLAUDE.md` §5 põe a integração atrás de uma interface para que o service dependa da
abstração (DIP), e o `datajud` era a assimetria que sobrou — `DatajudService` importava
`DatajudClient`, a classe que abre socket. Com a interface, trocar o DataJud por outra
fonte de processo (ou por um duplo de teste) não toca em `app/domain/datajud/`.

Os erros moram aqui junto do protocolo, não no client, pelo mesmo motivo do
`ChannelNotConfiguredError` em `messaging/base.py`: `raise DatajudUnauthorizedError` faz
parte do contrato — o service trata `401` com alerta e pausa (regra 3 da 046) —, e um
contrato cujo caminho de erro só existe na implementação não é um contrato. `client.py`
os reexporta para quem já os importava de lá.
"""

from typing import Protocol

from app.integrations.datajud.parser import ParsedProcess


class DatajudConfigError(Exception):
    """Chave ausente — regra 1 da 046: sempre vem de `DATAJUD_API_KEY`, nunca hardcoded."""


class DatajudApiError(Exception):
    """Resposta não-200 (exceto 401, tratado à parte) que sobreviveu às retentativas
    da camada 041."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"DataJud respondeu status {status_code}")
        self.status_code = status_code


class DatajudUnauthorizedError(DatajudApiError):
    """401 — chave pública inválida ou rotacionada (regra 3 da 046)."""

    def __init__(self) -> None:
        super().__init__(401)


class LawsuitSource(Protocol):
    """Fonte de processos judiciais. O DataJud é uma implementação (`DatajudClient`);
    trocar a fonte não toca no `DatajudService` (OCP).

    `alias` é o índice do tribunal na fonte — no DataJud, o `datajud_alias` do `Court`.
    Levanta `DatajudUnauthorizedError` quando a credencial da fonte não vale mais e
    `DatajudApiError` para as demais falhas que sobreviveram às retentativas.
    """

    async def search_by_process_number(
        self, *, alias: str, process_number: str
    ) -> list[ParsedProcess]: ...
