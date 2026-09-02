"""LSP para `LawsuitSource` (spec 118, §9): o client real e o duplo são intercambiáveis.

O `CLAUDE.md` §5 põe assim — «implementações de uma interface são intercambiáveis nos
testes (o mock é uma implementação real da interface)». Sem este teste a abstração vira
decoração: bastaria o duplo divergir na assinatura para o service passar em todo teste e
quebrar em produção, porque `Protocol` estrutural não é conferido em tempo de execução.

A conformidade é checada duas vezes, porque cada checagem pega o que a outra não pega:
por tipo (a anotação `fonte: LawsuitSource = ...`, que o mypy do `make lint` avalia) e
por forma da assinatura em tempo de execução.
"""

import inspect

from app.integrations.datajud.base import (
    DatajudApiError,
    DatajudUnauthorizedError,
    LawsuitSource,
)
from app.integrations.datajud.client import DatajudClient
from app.integrations.datajud.parser import ParsedProcess
from app.integrations.http.types import HttpResponse


class HttpInerte:
    """`HttpClient` que falha o teste se for chamado — nenhuma rede aqui (CLAUDE.md §3)."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> HttpResponse:
        raise AssertionError("teste de LSP não faz I/O")


class FakeLawsuitSource:
    """O duplo que um teste usaria no lugar do DataJud."""

    def __init__(self, resultados: list[ParsedProcess]) -> None:
        self._resultados = resultados

    async def search_by_process_number(
        self, *, alias: str, process_number: str
    ) -> list[ParsedProcess]:
        return self._resultados


def _assinatura_bate(candidato: object) -> bool:
    esperada = inspect.signature(LawsuitSource.search_by_process_number)
    obtida = inspect.signature(candidato.search_by_process_number)  # type: ignore[attr-defined]
    return list(esperada.parameters) == list(obtida.parameters)


def test_datajud_client_satisfaz_lawsuit_source() -> None:
    fonte: LawsuitSource = DatajudClient(
        http=HttpInerte(), base_url="https://exemplo.invalido", api_key="chave-de-teste"
    )
    assert _assinatura_bate(DatajudClient)
    assert inspect.iscoroutinefunction(fonte.search_by_process_number)


def test_duplo_de_teste_satisfaz_lawsuit_source() -> None:
    fonte: LawsuitSource = FakeLawsuitSource([])
    assert _assinatura_bate(FakeLawsuitSource)
    assert inspect.iscoroutinefunction(fonte.search_by_process_number)


def test_erros_do_contrato_moram_na_interface() -> None:
    """`DatajudUnauthorizedError` é caminho de contrato, não detalhe do client.

    O service trata 401 com alerta e pausa (regra 3 da 046); se o erro só existisse na
    implementação, outra `LawsuitSource` não teria como sinalizar a mesma condição.
    """
    assert issubclass(DatajudUnauthorizedError, DatajudApiError)
    assert DatajudUnauthorizedError().status_code == 401
