"""Expurgo das tabelas de log que cresciam sem horizonte (spec 137).

O beat já tinha retenção para `external_requests` (30 d), `aggregate_refresh_log` (90 d),
`ai_threads` (90 d), `access_logs` (12 m) e os `sync_runs` de termos (90 d). Cinco tabelas
ficaram de fora, todas escritas por caminho automático — e tabela que só cresce não avisa:
ela aparece como lentidão geral, meses depois, sem um culpado óbvio.

Roda como superusuário (`MIGRATIONS_DATABASE_URL`) porque a purga é cross-tenant e as
tabelas têm FORCE RLS — mesmo padrão de `workers/external_requests.py`.

Nenhum teste importa este módulo pela fila (CLAUDE.md §3); o que se testa é
`purge_expired`, chamada direto.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func
from sqlalchemy.orm import InstrumentedAttribute

from app.core.bootstrap import migrations_url
from app.core.db import create_engine_from_url
from app.core.sql import days_interval
from app.domain.ai.models import AiUsage
from app.domain.api_tokens.models import ApiRequest
from app.domain.automations.models import AutomationRun
from app.domain.notifications.models import Notification
from app.domain.search.models import SearchHistory
from app.workers.celery_app import celery_app


@dataclass(frozen=True, slots=True)
class Retention:
    """Uma tabela, a coluna que diz a idade da linha e por quantos dias ela fica."""

    model: type[Any]
    column: InstrumentedAttribute[Any]
    days: int


# Os cinco horizontes. Cada um é uma decisão, e o comentário é a decisão escrita:
# retenção sem motivo declarado vira número que ninguém ousa mexer.
POLICIES: tuple[Retention, ...] = (
    # Uma linha por chamada da API pública. Uma integração que consulta de minuto em
    # minuto grava 525 mil linhas por ano por escritório. 90 dias é o mesmo horizonte do
    # `aggregate_refresh_log` e dos `sync_runs`, e é o que o integrador precisa para
    # diagnosticar "por que a minha chamada falhou" — ninguém audita a requisição de
    # abril em novembro.
    Retention(ApiRequest, ApiRequest.created_at, 90),
    # O sino do cabeçalho é operação corrente. Notificação de seis meses atrás não é mais
    # aviso — e o fato que a originou (o prazo, a menção, a intimação) continua no
    # processo e na tarefa, que é onde alguém vai procurar. Vale para lida e não lida:
    # poupar as não lidas transformaria a tabela num crescimento sem teto de novo, bastando
    # um usuário que nunca abre o sino.
    Retention(Notification, Notification.created_at, 180),
    # Base de custo de IA. Precisa atravessar o fechamento do exercício e permitir a
    # comparação com o mesmo mês do ano anterior — 24 meses é o menor horizonte que dá as
    # duas coisas. É a retenção mais longa das cinco, e de propósito: é a única que
    # responde a pergunta financeira.
    Retention(AiUsage, AiUsage.created_at, 730),
    # Serve às buscas recentes do próprio usuário. Ninguém reabre a busca de três meses
    # atrás, e o valor da linha cai a zero em dias.
    Retention(SearchHistory, SearchHistory.created_at, 90),
    # A tela de execuções de automação existe para diagnosticar "por que isto não
    # disparou". Seis meses cobrem a sazonalidade do escritório (o ciclo de um processo
    # trabalhista, a virada de exercício) sem guardar o passo a passo de 2024.
    # `automation_run_steps` sai junto por `ON DELETE CASCADE`.
    Retention(AutomationRun, AutomationRun.started_at, 180),
)


async def purge_expired(url: str | None = None) -> dict[str, int]:
    """Apaga o que passou do horizonte de cada tabela. Devolve as linhas por tabela.

    Um `DELETE` por tabela, com o corte DENTRO do comando — nunca uma lista de ids vinda
    para o Python, que é como o expurgo de webhooks quebrava no teto de 32.767 binds do
    asyncpg (spec 137, defeito 1). Sem `LIMIT` por lote aqui de propósito: estas cinco
    rodam uma vez por dia, fora do horário de trabalho, e o `LIMIT` sem índice de data
    transformaria o expurgo numa varredura por lote.
    """
    resolvida = url or migrations_url("o expurgo cross-tenant das tabelas de log")
    engine = create_engine_from_url(resolvida)
    apagadas: dict[str, int] = {}
    try:
        async with engine.begin() as conn:
            for politica in POLICIES:
                resultado = await conn.execute(
                    delete(politica.model).where(
                        politica.column < func.now() - days_interval(politica.days)
                    )
                )
                apagadas[politica.model.__tablename__] = int(resultado.rowcount)
    finally:
        await engine.dispose()
    return apagadas


@celery_app.task(name="app.workers.retention.purge_expired")
def purge_expired_task() -> dict[str, int]:
    return asyncio.run(purge_expired())
