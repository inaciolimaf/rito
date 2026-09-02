"""Migrations no boot, com trava (spec 099, regras 3 e 4).

Duas garantias, e a segunda é a que importa mais:

1. **uma instância por vez** aplica migration (regra 3). Deploy rolling sobe N
   containers simultaneamente; sem trava, N processos correm `alembic upgrade head`
   contra o mesmo banco.
2. **falha de migration impede a aplicação de subir** (regra 4). Um processo que sobe
   com schema inconsistente atende requisições e grava dados errados — é pior que não
   subir, porque o estrago é silencioso e cumulativo.

## Duas travas, e o motivo de serem duas

A exclusão mútua de verdade é um **advisory lock** do Postgres. A tabela
`migration_locks` da §4 da spec existe, mas não pode ser o mecanismo primário: num banco
NOVO ela ainda não existe — é a própria migration que a cria. A primeira versão usava só
a tabela e falhava exatamente no caso que mais importa, o `docker compose up` do zero:
`relation "migration_locks" does not exist`, e a aplicação não subia.

O advisory lock não tem esse problema (não depende de schema nenhum), é liberado
automaticamente quando a conexão cai — o que resolve de graça o caso da instância que
morreu com a trava na mão — e é atômico por construção.

A tabela continua, e continua sendo escrita, pelo que ela dá e o advisory lock não:
**visibilidade**. Ler `migration_locks` durante um deploy travado diz QUEM está
aplicando e DESDE QUANDO; um lock de sessão só aparece em `pg_locks`, como um número,
para quem souber que ele existe.
"""

import asyncio
import logging
import os
import socket
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

logger = logging.getLogger("rito.migrations")

# Regra 3. Tempo que uma instância espera a outra terminar antes de desistir.
LOCK_TIMEOUT = timedelta(minutes=5)
# De quanto em quanto tempo se checa se a outra terminou.
POLL_INTERVAL_SECONDS = 1.0

# Chave do advisory lock. Qualquer número serve, desde que seja o MESMO em todas as
# instâncias e não colida com outro uso de advisory lock no mesmo banco — este é o
# único do Rito.
ADVISORY_LOCK_KEY = 20260828


def _quem_sou_eu() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


async def _anotar_dono(conn: AsyncConnection, dono: str | None) -> None:
    """Registra na tabela quem está aplicando — para quem estiver diagnosticando.

    Falha em silêncio quando a tabela ainda não existe: é o caso do banco novo, em que a
    migration que cria `migration_locks` é justamente a que está prestes a rodar. Perder
    a anotação nesse instante não custa nada; o advisory lock já garante a exclusão.
    """
    try:
        if dono is None:
            await conn.execute(
                text("UPDATE migration_locks SET locked_by = NULL, locked_at = NULL WHERE id = 1")
            )
        else:
            await conn.execute(
                text(
                    "UPDATE migration_locks SET locked_by = :dono, locked_at = now() WHERE id = 1"
                ),
                {"dono": dono},
            )
        await conn.commit()
    except Exception:
        await conn.rollback()
        logger.debug("migration_locks ainda não existe — anotação de dono ignorada")


async def _tentar_travar(engine: AsyncEngine, dono: str) -> AsyncConnection | None:
    """Toma o advisory lock. Devolve a conexão que o segura, ou `None` se outra já tem.

    A conexão é DEVOLVIDA e fica aberta de propósito: advisory lock de sessão vive
    enquanto a conexão vive, e é isso que o faz sobreviver às várias transações que uma
    migration abre e fecha — e ser liberado sozinho se o processo morrer.
    """
    conn = await engine.connect()
    tomou = await conn.scalar(
        text("SELECT pg_try_advisory_lock(:chave)"), {"chave": ADVISORY_LOCK_KEY}
    )
    if not tomou:
        await conn.close()
        return None
    await _anotar_dono(conn, dono)
    return conn


async def _destravar(conn: AsyncConnection | None) -> None:
    """Solta a anotação e o advisory lock, e fecha a conexão que o segurava."""
    if conn is None:
        return
    try:
        await _anotar_dono(conn, None)
        await conn.execute(text("SELECT pg_advisory_unlock(:chave)"), {"chave": ADVISORY_LOCK_KEY})
    finally:
        await conn.close()


async def _versao_atual(engine: AsyncEngine) -> str | None:
    async with engine.connect() as conn:
        try:
            return (await conn.scalar(text("SELECT version_num FROM alembic_version"))) or None
        except Exception:
            return None


def _aplicar_sincrono() -> None:
    """`alembic upgrade head`. Síncrono porque o Alembic é síncrono — quem chama roda
    isto numa thread para não travar o event loop.

    A URL NÃO é parâmetro: `alembic/env.py` a resolve de `Settings.migrations_database_url`
    e sobrescreve o que estiver em `alembic.ini`. Aceitar uma URL aqui seria oferecer um
    controle que não existe — foi o que aconteceu na primeira versão, e o teste que
    tentava apontar para um banco inválido migrava o banco certo em silêncio.
    """
    from alembic.config import Config

    from alembic import command

    command.upgrade(Config("alembic.ini"), "head")


async def upgrade_with_lock(engine: AsyncEngine) -> None:
    """Aplica as migrations pendentes sob trava, ou espera quem está aplicando.

    Levanta se a migration falhar (regra 4) e se a espera estourar o tempo — nos dois
    casos o processo não sobe, que é o comportamento correto.
    """
    dono = _quem_sou_eu()
    limite = datetime.now(UTC) + LOCK_TIMEOUT

    trava = await _tentar_travar(engine, dono)
    while trava is None:
        if datetime.now(UTC) > limite:
            # A mensagem citava a query a rodar (`SELECT ... FROM migration_locks`) e o
            # `S608` casava com o TEXTO, achando que era SQL montado por string. Dizer as
            # colunas em vez de escrever o comando informa o mesmo e não parece query —
            # falso positivo removido na origem, sem `noqa` (spec 115).
            raise RuntimeError(
                "outra instância está aplicando migrations há mais de "
                f"{LOCK_TIMEOUT.total_seconds():.0f}s. Quem está com a trava aparece na "
                "tabela `migration_locks`, colunas `locked_by` e `locked_at`; se aquele "
                "processo morreu, o advisory lock caiu junto com a conexão dele e uma "
                "nova tentativa passa."
            )
        antes = await _versao_atual(engine)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        depois = await _versao_atual(engine)
        if antes != depois:
            logger.info("migrations aplicadas por outra instância", extra={"version": depois})
        trava = await _tentar_travar(engine, dono)

    try:
        logger.info("aplicando migrations", extra={"lock_owner": dono})
        await asyncio.to_thread(_aplicar_sincrono)
    finally:
        # Solta a trava mesmo quando a migration falha: senão a próxima tentativa
        # esperaria cinco minutos por uma instância que já morreu.
        await _destravar(trava)
