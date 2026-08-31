"""Infraestrutura de teste do backend.

Spec 105: cada worker do xdist roda contra o **seu** banco, criado por cópia de um
template já migrado (`CREATE DATABASE ... TEMPLATE`, resolvido pelo Postgres com cópia
de arquivo: 0,13 s contra 2 s de `alembic upgrade head`), e cada teste roda dentro de
uma transação que sofre `ROLLBACK` no teardown.

As duas coisas juntas, e não uma só: o rollback por teste sozinho faz as transações
viverem o teste inteiro, e transações longas de workers diferentes no MESMO banco se
travam em `REFRESH MATERIALIZED VIEW` e DDL (medido — a suíte não terminava). Banco por
worker é o que devolve a independência que a transação longa tirou.
"""

import asyncio
import contextlib
import os
import subprocess
import sys
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
# Uma trava só, compartilhada por todos os workers, para o preparo do template.
_TEMPLATE_LOCK_KEY = 105_2026


def _with_database(url: str, name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{name}"))


def _database_name(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


def _dsn(url: str) -> str:
    """`postgresql+asyncpg://` → `postgresql://`, que é o que o asyncpg cru entende."""
    return url.replace("+asyncpg", "", 1)


def _psql(url: str, *statements: str) -> list[Any]:
    """SQL de manutenção (`CREATE`/`DROP DATABASE`, advisory lock) — fora de transação,
    por obrigação do Postgres.

    Vai em asyncpg cru, e não pelo engine do SQLAlchemy, por dois motivos: é
    `pytest_configure`, onde ainda não há event loop nem fixture, e `CREATE DATABASE`
    não roda dentro de transação — que é justamente o que todo caminho de sessão da
    aplicação abre.
    """
    import asyncpg

    async def _executar() -> list[Any]:
        conn = await asyncpg.connect(_dsn(url))
        try:
            return [await conn.fetch(statement) for statement in statements]
        finally:
            await conn.close()

    return asyncio.run(_executar())


def _template_esta_pronto(template_url: str, head: str) -> bool:
    """Pronto = migrado até a head E sem tenant nenhum.

    A segunda metade é a regra que mantém o template confiável: nada além das
    migrations escreve nele, então um tenant ali dentro só pode ser resíduo do
    esquema antigo (em agosto/2026 o `rito_test` tinha 9.317). Nesse caso ele é
    refeito do zero, uma vez, e a limpeza de 60 linhas do `run-tests.sh` some junto.
    """
    try:
        (versao,), (tenants,) = _psql(
            template_url,
            "SELECT version_num FROM alembic_version",
            "SELECT count(*) AS total FROM tenants",
        )
    except Exception:  # noqa: BLE001 — banco novo, sem as tabelas: não está pronto
        return False
    return bool(versao["version_num"] == head and tenants["total"] == 0)


def _preparar_template(maintenance_url: str, template_url: str) -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini"))).get_current_head()
    assert head is not None, "alembic sem head — migrations não foram encontradas"
    nome = _database_name(template_url)

    _psql(maintenance_url, f"SELECT pg_advisory_lock({_TEMPLATE_LOCK_KEY})")
    try:
        if _template_esta_pronto(template_url, head):
            return
        _psql(
            maintenance_url,
            f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)',
            f'CREATE DATABASE "{nome}"',
        )
        subprocess.run(  # noqa: S603 — argumentos fixos, nada vem de fora
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env={**os.environ, "MIGRATIONS_DATABASE_URL": template_url},
            check=True,
            capture_output=True,
        )
    finally:
        _psql(maintenance_url, f"SELECT pg_advisory_unlock({_TEMPLATE_LOCK_KEY})")


def _banco_do_worker(config: pytest.Config, template_url: str) -> str | None:
    """Nome do banco deste processo, ou `None` quando ele não roda teste.

    O controlador do xdist entra aqui como qualquer worker, mas não executa teste
    nenhum — criar um banco para ele seria trabalho puro.
    """
    worker = getattr(config, "workerinput", {}).get("workerid")
    if worker is None and config.getoption("numprocesses", None):
        return None
    return f"{_database_name(template_url)}_{worker or 'master'}"


def pytest_configure(config: pytest.Config) -> None:
    # Força (não só setdefault) — testes NUNCA podem herdar um DATABASE_URL/REDIS_URL de
    # ambiente apontando para um banco que não seja o de teste. Descoberto na spec 006: rodar
    # `make test` com DATABASE_URL exportado no shell (para o webServer do e2e, que aponta pro
    # banco "rito" de dev) fazia o pytest herdar esse valor via setdefault e testar contra o
    # banco errado — sem erro óbvio, só "relation does not exist" nas tabelas criadas só em
    # rito_test. Sempre sobrescrever com TEST_* elimina essa classe de bug inteira.
    os.environ["APP_ENV"] = "test"
    os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
    os.environ["DATABASE_URL"] = os.environ.get(
        "TEST_DATABASE_URL", "postgresql+asyncpg://rito_app:rito_app@localhost:5432/rito_test"
    )
    os.environ["MIGRATIONS_DATABASE_URL"] = os.environ.get(
        "TEST_MIGRATIONS_DATABASE_URL",
        "postgresql+asyncpg://rito:rito@localhost:5432/rito_test",
    )
    os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
    # Spec 099, regra 3: a aplicação aplica migrations no boot. Em teste, quem migra é o
    # `scripts/run-tests.sh`, UMA vez por sessão (spec 009, regra 3) — deixar cada
    # `lifespan` de teste correr `alembic upgrade head` custaria segundos por teste e
    # ainda faria os workers do xdist disputarem a trava.
    os.environ["RUN_MIGRATIONS_ON_BOOT"] = "false"
    os.environ["ARGON2_TIME_COST"] = os.environ.get("TEST_ARGON2_TIME_COST", "1")
    os.environ["ARGON2_MEMORY_COST"] = os.environ.get("TEST_ARGON2_MEMORY_COST", "8192")
    # MinIO é infra local (como Postgres/Redis) — testes de logo (spec 011) usam o serviço
    # de verdade do docker-compose, só num bucket separado do de dev, nunca um fake.
    os.environ["S3_ENDPOINT_URL"] = os.environ.get("TEST_S3_ENDPOINT_URL", "http://localhost:9000")
    os.environ["S3_ACCESS_KEY"] = os.environ.get("TEST_S3_ACCESS_KEY", "minioadmin")
    os.environ["S3_SECRET_KEY"] = os.environ.get("TEST_S3_SECRET_KEY", "minioadmin")
    os.environ["S3_BUCKET"] = os.environ.get("TEST_S3_BUCKET", "rito-test")
    os.environ["S3_REGION"] = os.environ.get("TEST_S3_REGION", "us-east-1")

    _preparar_banco_do_processo(config)


def _preparar_banco_do_processo(config: pytest.Config) -> None:
    """Spec 105, regras 1 e 2: template uma vez por sessão, banco próprio por worker.

    As duas URLs (`rito_app` sem BYPASSRLS e o superusuário das migrations) passam a
    apontar para o banco deste processo. Nenhum teste sabe disso — é a mesma
    `get_settings().database_url` de sempre, só que num banco que ninguém mais usa.
    """
    template_url = os.environ["MIGRATIONS_DATABASE_URL"]
    # `postgres` é o banco de manutenção: `CREATE DATABASE` não pode rodar a partir do
    # banco que ele copia, nem do banco que ele apaga.
    maintenance_url = _with_database(template_url, "postgres")

    banco = _banco_do_worker(config, template_url)
    if banco is None:  # controlador do xdist: não roda teste, não precisa de banco
        return

    _preparar_template(maintenance_url, template_url)
    _psql(
        maintenance_url,
        f'DROP DATABASE IF EXISTS "{banco}" WITH (FORCE)',
        f'CREATE DATABASE "{banco}" TEMPLATE "{_database_name(template_url)}"',
    )
    # Guardada antes da troca: é ela que o meta-teste da regra 1 inspeciona.
    os.environ["RITO_TEST_TEMPLATE_URL"] = template_url
    os.environ["DATABASE_URL"] = _with_database(os.environ["DATABASE_URL"], banco)
    os.environ["MIGRATIONS_DATABASE_URL"] = _with_database(template_url, banco)


@pytest.fixture
async def app_engine() -> AsyncGenerator[AsyncEngine]:
    """Engine com a role de aplicação (`rito_app`, sem BYPASSRLS) — RLS vale de verdade.

    Recebe a mesma instrumentação que o `lifespan` aplica ao engine da aplicação (spec
    097, regras 4 e 6): é este o engine que atende as requisições do teste depois da
    troca feita em `client`, e sem instrumentá-lo a contagem de queries por requisição e
    o span de banco simplesmente não existiriam — o gate do CLAUDE.md §11 passaria a
    medir zero e a passar sempre, que é pior do que falhar.
    """
    from app.core.config import get_settings
    from app.core.db import create_engine_from_url
    from app.core.observability import metrics as observability_metrics
    from app.core.observability.tracing import instrument_engine as instrument_engine_tracing

    engine = create_engine_from_url(get_settings().database_url)
    observability_metrics.instrument_engine(engine)
    instrument_engine_tracing(engine)
    yield engine
    await engine.dispose()


@pytest.fixture
async def app_session_factory(
    request: pytest.FixtureRequest, app_engine: AsyncEngine
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    """Spec 105, regras 3 e 4: **uma** conexão por teste, com uma transação aberta que
    sofre `ROLLBACK` no teardown.

    Toda sessão criada por esta fábrica entra nessa transação por `SAVEPOINT`
    (`join_transaction_mode="create_savepoint"`), então o `session.begin()`/`commit()`
    que os testes e a aplicação já fazem vira `SAVEPOINT`/`RELEASE` — nada chega ao
    banco de verdade. É por isso que quase nenhum teste precisou ser editado: o contrato
    da fábrica não mudou, só o que acontece do outro lado dele. E é por isso que o banco
    de teste parou de acumular: em agosto/2026 o `rito_test` tinha 9.317 tenants porque
    cada `make_user` comitava.

    `@pytest.mark.commits` devolve a fábrica de antes — engine própria, commit de
    verdade. É o que os testes de visão materializada, plano de execução e semântica de
    transação precisam: dentro de uma transação de teste eles não testariam nada, porque
    o que eles observam só existe depois do commit (regra 8).
    """
    from app.core.db import create_session_factory

    if request.node.get_closest_marker("commits") is not None:
        yield create_session_factory(app_engine)
        return

    async with app_engine.connect() as connection:
        transaction = await connection.begin()
        yield async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        await transaction.rollback()


@contextlib.asynccontextmanager
async def use_test_session(
    app: FastAPI, engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> AsyncIterator[None]:
    """Spec 105, regra 5: a sessão que o app usa nas requisições é **a mesma** do teste.

    A troca é no `app.state` e não em `dependency_overrides` de propósito: TODO caminho
    de sessão da aplicação passa por `app.state.session_factory` — `get_session`,
    `get_session_for_current_user`, o `get_current_user` que valida o token e o
    `create_durable_thread` da 103. Sobrescrever a dependência pegaria só os dois
    primeiros, e o dado escrito pelo teste ficaria invisível para os outros dois.

    O `engine` vai junto porque `tests/perf.py` (o gate de orçamento de queries) escuta
    `app.state.engine`: apontá-lo para o engine que de fato atende as requisições é o
    que mantém o gate medindo o que ele diz medir.
    """
    engine_original, factory_original = app.state.engine, app.state.session_factory
    app.state.engine, app.state.session_factory = engine, factory
    try:
        yield
    finally:
        app.state.engine, app.state.session_factory = engine_original, factory_original


@pytest.fixture
async def client(
    app_engine: AsyncEngine, app_session_factory: async_sessionmaker[AsyncSession]
) -> AsyncGenerator[AsyncClient]:
    from app.main import app

    async with (
        app.router.lifespan_context(app),
        use_test_session(app, app_engine, app_session_factory),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture
async def admin_engine() -> AsyncGenerator[AsyncEngine]:
    """Engine com o superusuário (MIGRATIONS_DATABASE_URL) — bypassa RLS, só para setup/
    verificação de teste (DDL, tabelas de sonda, conferir estado de migration).

    Spec 105, regra 7: continua **fora** da transação do teste. É conexão separada e
    comita de verdade — o que ela escreve some com o banco do worker, recriado a partir
    do template a cada sessão de pytest.
    """
    from app.core.config import get_settings
    from app.core.db import create_engine_from_url

    url = get_settings().migrations_database_url
    assert url is not None, "MIGRATIONS_DATABASE_URL não configurada para os testes"
    engine = create_engine_from_url(url)
    yield engine
    await engine.dispose()
