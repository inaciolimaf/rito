"""«Hoje» é o hoje do escritório, não o do servidor (spec 114).

O Rito vende prazo processual. `date.today()` lê o relógio do **processo**, e o processo
roda em UTC: um escritório em Rio Branco (UTC−5) vendo o dia de um servidor em UTC recebe
o dia seguinte por cinco horas, toda noite. Uma parcela que vence hoje aparece como
vencida; uma tarefa de amanhã entra na pontuação de hoje. Nada disso levanta exceção — é
por isso que passou cem specs sem ninguém ver.

A spec 011 guarda `timezone` por conta desde o começo, com oito opções BR/PT. O dado
sempre esteve lá; o que faltava era alguém lê-lo.

## De onde vem o fuso, e por que não de uma query

O caminho óbvio seria o repositório da conta, como `schedule/service.py` e
`reports/access_service.py` faziam cada um à sua maneira. Ele **quebra o gate de orçamento
de queries** do `CLAUDE.md` §11: medido em 01/09/2026, `/api/v1/customers/stats` usa 5 de
5 queries e a listagem de contatos 3 de 3 — folga zero nos dois, e `customers/repository`
é justamente quem filtra por «hoje».

Então o fuso vem de carona: `get_current_user` já carrega o usuário do token, e `accounts`
tem exatamente uma linha por tenant. Um `JOIN` na query que já existe custa zero query
nova, não tem cache para ficar velho, e amarra «hoje» ao contexto autenticado — que é
onde ele conceitualmente mora.

Worker e task do Celery não têm requisição nem usuário logado; lá o fuso é resolvido
explicitamente com `Clock.for_timezone(...)`, e o gate não os alcança porque ele mede rota
HTTP.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.domain.account.models import DEFAULT_TIMEZONE


class Clock:
    """O relógio de um tenant. Imutável, barato de construir, sem I/O.

    Não tem `date.today()` dentro por princípio: se ele caísse no relógio do processo em
    algum caminho, o bug que esta spec conserta voltaria por dentro do próprio conserto.
    """

    __slots__ = ("_tz",)

    def __init__(self, timezone_name: str | None = None) -> None:
        # Conta sem fuso configurado (ou linha de conta ainda não criada) cai no padrão —
        # nunca no fuso do servidor, que é o defeito que esta spec existe para tirar.
        self._tz = ZoneInfo(timezone_name or DEFAULT_TIMEZONE)

    @property
    def timezone(self) -> ZoneInfo:
        return self._tz

    def now(self) -> datetime:
        """Agora, com fuso — sempre aware. `datetime.now()` sem `tz` é o mesmo bug."""
        return datetime.now(tz=self._tz)

    def today(self) -> date:
        """O dia corrente no fuso do escritório."""
        return self.now().date()

    def __repr__(self) -> str:  # pragma: no cover — conveniência de depuração
        return f"Clock({str(self._tz)!r})"
