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
import fcntl
import os
import subprocess
import sys
import tempfile
from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]


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
    except Exception:
        return False
    return bool(versao["version_num"] == head and tenants["total"] == 0)


@contextmanager
def _trava_do_template(template_url: str) -> Iterator[None]:
    """Exclusão mútua entre workers durante o preparo do template (dívida 29).

    ## O que estava quebrado

    A versão anterior usava `pg_advisory_lock`, que é trava de **sessão**: ela vive
    enquanto a conexão viver. Mas quem a tomava era `_psql`, que abre uma conexão e a
    FECHA no `finally` — a trava morria no instante seguinte ao ser tomada, e o
    `pg_advisory_unlock` do fim rodava numa conexão nova, sem trava nenhuma. O Postgres
    respondia `false` e emitia aviso; o retorno era descartado e ninguém lia.

    Ficou cem specs sem morder porque o `run-tests.sh` roda `alembic upgrade head` sobre o
    template ANTES do pytest: quando os workers chegam aqui, `_template_esta_pronto` já é
    `True` para todos e ninguém entra no bloco protegido. Com template novo, os N workers
    entram juntos, todos fazem `DROP`/`CREATE DATABASE` e disparam N `alembic upgrade`
    concorrentes sobre o mesmo banco — `UniqueViolationError` em migration, e a suíte cai
    antes do primeiro teste.

    ## Por que trava de arquivo, e não a do banco

    Manter a trava do Postgres viva exigiria que TODO o bloco protegido — a checagem, o
    `DROP`/`CREATE` e o `alembic` — rodasse dentro do mesmo `asyncio.run` da conexão que a
    detém. Os helpers deste arquivo (`_psql`, `_template_esta_pronto`) abrem cada um o seu
    `asyncio.run`, e aninhá-los é erro em tempo de execução; converter todos para async
    seria uma reescrita do preparo por causa de uma trava.

    `flock` faz o mesmo serviço aqui: os workers do xdist são sempre processos locais de
    UMA execução do pytest, e o bloqueio é entre eles. O limite honesto é que duas máquinas
    apontando para o mesmo Postgres não se veriam — cenário que não existe, porque o
    template é local por definição e o nome do banco vem da URL de teste da própria
    máquina.

    O arquivo leva o nome do banco: dois templates diferentes (spec exclusiva, por exemplo)
    não se bloqueiam à toa.
    """
    trava = Path(tempfile.gettempdir()) / f"rito-template-{_database_name(template_url)}.lock"
    with trava.open("w") as arquivo:
        fcntl.flock(arquivo, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(arquivo, fcntl.LOCK_UN)


def _preparar_template(maintenance_url: str, template_url: str) -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini"))).get_current_head()
    assert head is not None, "alembic sem head — migrations não foram encontradas"
    nome = _database_name(template_url)

    with _trava_do_template(template_url):
        if _template_esta_pronto(template_url, head):
            return
        _psql(
            maintenance_url,
            f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)',
            f'CREATE DATABASE "{nome}"',
        )
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env={**os.environ, "MIGRATIONS_DATABASE_URL": template_url},
            check=True,
            capture_output=True,
        )


def _banco_do_worker(config: pytest.Config, template_url: str) -> str | None:
    """Nome do banco deste processo, ou `None` quando ele não roda teste.

    O controlador do xdist entra aqui como qualquer worker, mas não executa teste
    nenhum — criar um banco para ele seria trabalho puro.
    """
    worker = getattr(config, "workerinput", {}).get("workerid")
    if worker is None and config.getoption("numprocesses", None):
        return None
    return f"{_database_name(template_url)}_{worker or 'master'}"


def _redis_url_do_worker() -> str:
    """Um banco de Redis por worker do xdist (spec 110, dívida 35).

    A spec 105 deu a cada worker uma cópia própria do Postgres, e o `ROLLBACK` por teste
    passou a garantir isolamento — mas só no Postgres. O Redis continuou sendo **um banco
    para todos**, e o que mora nele é justamente estado que atravessa requisições: o token
    bucket do rate limit por host (spec 041, regra 4) e o circuito do breaker.

    O sintoma era um teste de limite recebendo 200 onde esperava 429, porque outro worker
    tinha gastado a janela do mesmo host — e a chave é o host, não o tenant, então o RLS
    não ajuda. Passava sozinho, passava na maioria das execuções, e reprovava quando a
    distribuição entre workers calhava mal.

    Redis tem 16 bancos numerados; `gw0` fica no 15, `gw1` no 14, e assim por diante — de
    trás para a frente para não esbarrar no 0, que é o padrão de quem esquecer de
    configurar. Acima de 16 workers não há banco para todos, e aí é melhor falhar dizendo
    isso do que voltar a compartilhar em silêncio.

    `TEST_REDIS_URL` continua mandando quando alguém a exporta: quem aponta para outro
    Redis está dizendo o que quer, e essa escolha é mais específica que este cálculo.
    """
    explicito = os.environ.get("TEST_REDIS_URL")
    if explicito:
        return explicito
    worker = os.environ.get("PYTEST_XDIST_WORKER", "")
    indice = int(worker.removeprefix("gw")) if worker.startswith("gw") else 0
    if indice > 15:
        raise RuntimeError(
            f"xdist com {indice + 1} workers, mas o Redis só tem 16 bancos: os workers "
            "acima do 16 compartilhariam estado (dívida 35). Reduza PYTEST_WORKERS ou "
            "exporte TEST_REDIS_URL apontando para outra instância."
        )
    return f"redis://localhost:6379/{15 - indice}"


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
    os.environ["REDIS_URL"] = _redis_url_do_worker()
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
