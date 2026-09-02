"""As travas do isolamento transacional (spec 105).

A spec entrega três coisas que só continuam valendo se alguém as cobrar: o banco de
cada worker sai do template, o teste roda dentro de uma transação que é desfeita, e a
lista de exceções (`@pytest.mark.commits`) não cresce sem justificativa.

O terceiro é o que mais importa. Uma exceção por teste é barata de escrever e cara de
perceber: sem um teto, daqui a vinte specs metade da suíte estaria comitando de novo e
o `rito_test` voltaria aos 9.317 tenants — que é exatamente como a dívida original
nasceu. Mesmo espírito do teto de `slow` da 009.
"""

import ast
import os
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.models import Tenant

TESTS_DIR = Path(__file__).resolve().parents[1]

# Medido ao fechar a 105, arquivo a arquivo. A spec previa 4 arquivos; a realidade são
# 19, e a diferença não é desleixo: quase todos observam o que SÓ existe depois do
# commit — visão materializada (BI, taskscore, dashboard financeiro), plano de execução
# com dado real (inbox), cache que compara ida ao banco, semântica de transação (RLS,
# runtime de IA) e `now()`, que no Postgres é o instante da TRANSAÇÃO e por isso
# congela dentro de um teste transacional.
TETO_DE_ARQUIVOS_COM_COMMITS = 19
TETO_DE_TESTES_COM_COMMITS = 69


def _arquivos_de_teste() -> list[Path]:
    return sorted(p for p in TESTS_DIR.rglob("test_*.py") if p.name != Path(__file__).name)


def _marcas_commits(caminho: Path) -> int:
    """Quantos `@pytest.mark.commits` o arquivo declara — por AST, não por regex: um
    `commits` dentro de string ou comentário não é um marcador."""
    total = 0
    for node in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Attribute) and node.attr == "commits":
            valor = node.value
            if isinstance(valor, ast.Attribute) and valor.attr == "mark":
                total += 1
    return total


def test_o_marcador_commits_nao_cresce_sem_spec() -> None:
    """Regra 8 da 105. O teto é o valor medido: subir é decisão, não acidente."""
    por_arquivo = {p: _marcas_commits(p) for p in _arquivos_de_teste()}
    com_marca = {p.relative_to(TESTS_DIR).as_posix(): n for p, n in por_arquivo.items() if n}

    assert len(com_marca) <= TETO_DE_ARQUIVOS_COM_COMMITS, (
        f"{len(com_marca)} arquivos usam @pytest.mark.commits, o teto é "
        f"{TETO_DE_ARQUIVOS_COM_COMMITS} (spec 105, regra 8). Comitar de verdade devolve "
        f"o acúmulo que a 105 eliminou — se o teste novo precisa mesmo, suba o teto numa "
        f"spec e diga por quê.\n{com_marca}"
    )
    assert sum(com_marca.values()) <= TETO_DE_TESTES_COM_COMMITS, (
        f"{sum(com_marca.values())} testes usam @pytest.mark.commits, o teto é "
        f"{TETO_DE_TESTES_COM_COMMITS} (spec 105, regra 8)."
    )


# Os dois engines próprios que continuam legítimos, cada um pelo seu motivo — e a lista
# é curta de propósito: é ela que impede o teste de virar carimbo.
_ENGINE_PROPRIO_JUSTIFICADO = {
    # Plano de execução com dado real: o teste é @pytest.mark.commits e precisa de uma
    # conexão de superusuário para o EXPLAIN, que a fábrica da aplicação não dá.
    "test_inbox_perf.py",
    # Engine apontando para uma porta morta, de propósito: o que se testa é o que o
    # sistema faz quando o banco NÃO responde.
    "test_observability.py",
}


def test_nenhuma_fixture_de_teste_comita_por_fora() -> None:
    """A porta dos fundos: uma fixture que abre engine própria e comita reintroduz o
    acúmulo sem nunca escrever `@pytest.mark.commits`.

    `tests/conftest.py` é a exceção óbvia — é ele quem define as duas fábricas.
    """
    ofensores: list[str] = []
    padrao = re.compile(r"create_engine_from_url|create_async_engine")
    for caminho in _arquivos_de_teste() + [TESTS_DIR / "integration" / "conftest.py"]:
        if not caminho.exists() or caminho.name in _ENGINE_PROPRIO_JUSTIFICADO:
            continue
        for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
            if padrao.search(linha):
                ofensores.append(f"{caminho.relative_to(TESTS_DIR)}:{numero}: {linha.strip()}")
    assert not ofensores, (
        "engine próprio fora de tests/conftest.py — a sessão do teste tem que sair de "
        "`app_session_factory` (spec 105, regras 3 e 4):\n" + "\n".join(ofensores)
    )


async def test_o_que_o_teste_escreve_nao_sobrevive_ao_teardown(
    app_engine: AsyncEngine,
) -> None:
    """Regra 3: o que a fixture escreve existe durante o teste e não existe depois.

    Monta aqui a MESMA mecânica da `app_session_factory` — conexão, transação,
    savepoints, `ROLLBACK` — em vez de espalhar a prova por dois testes acoplados por
    variável de módulo: sob `-n 3` o xdist manda cada teste para um worker (e cada
    worker tem banco próprio), e a prova viraria um `skip` silencioso.

    As duas metades importam. Sem a primeira, uma fixture que nunca escrevesse nada
    passaria; sem a segunda, a de hoje, sem rollback, também.
    """
    tenant_id = uuid.uuid4()

    async with app_engine.connect() as connection:
        transaction = await connection.begin()
        factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with factory() as session, session.begin():
            session.add(Tenant(id=tenant_id, slug=f"rollback-{tenant_id}", name="Sonda da 105"))

        # Outra sessão, mesmo teste: o `commit` acima foi um RELEASE SAVEPOINT, então o
        # dado está lá — é isto que faz o teste enxergar o que ele mesmo escreveu.
        async with factory() as session, session.begin():
            assert await session.get(Tenant, tenant_id) is not None

        await transaction.rollback()

    # Conexão nova, depois do teardown: nada sobrou para o próximo teste encontrar.
    async with app_engine.connect() as connection:
        sobrou = await connection.execute(select(Tenant.id).where(Tenant.id == tenant_id))
        assert sobrou.first() is None


async def test_o_template_esta_na_head_e_nao_tem_tenant() -> None:
    """Regra 1: o template é criado uma vez, pelas migrations, e mais nada escreve nele.

    As duas metades importam. "Na head" é o que a 009 já cobrava (o banco migrado antes
    do primeiro teste); "sem tenant" é o que a 105 acrescenta — um tenant no template
    seria copiado para o banco de todo worker, em toda execução, para sempre. Foi assim
    que o `rito_test` chegou a 9.317 tenants e 1,16 milhão de `task_types`.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    url = os.environ.get("RITO_TEST_TEMPLATE_URL")
    assert url, "RITO_TEST_TEMPLATE_URL não publicada por pytest_configure"

    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            versao = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
            tenants = (await conn.execute(text("SELECT count(*) FROM tenants"))).scalar()
    finally:
        await engine.dispose()

    assert versao == _head_do_alembic(), (
        f"template em {versao!r}, esperado {_head_do_alembic()!r} — a migration não "
        "rodou até o fim antes da suíte."
    )
    assert tenants == 0, (
        f"o template tem {tenants} tenant(s). Ele é copiado para o banco de cada worker: "
        "sujeira aqui vira sujeira em toda execução, para sempre."
    )


def _head_do_alembic() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(
        Config(str(TESTS_DIR.parent / "alembic.ini"))
    ).get_current_head()
    assert head is not None
    return head


# ---------------------------------------------------------------- spec 110, dívida 35
#
# A 105 isolou o Postgres (um banco por worker + ROLLBACK por teste) e deixou o Redis de
# fora. O que mora no Redis é justamente estado que atravessa requisições — token bucket
# do rate limit por host, circuito do breaker — e a chave é o HOST, não o tenant, então
# nem o RLS nem a transação ajudam.


def test_cada_worker_do_xdist_usa_um_banco_de_redis_proprio() -> None:
    """Dois workers nunca compartilham banco (spec 110).

    O mapeamento é testado como função pura porque, dentro de uma execução, cada processo
    só enxerga o próprio worker — não dá para observar a colisão de dentro dela. O que se
    pode afirmar é que a regra que atribui os bancos é injetora, e é isso que o teste faz.
    """
    from tests.conftest import _worker_redis_url

    original = os.environ.pop("TEST_REDIS_URL", None)
    anterior = os.environ.get("PYTEST_XDIST_WORKER")
    try:
        urls = []
        for i in range(16):
            os.environ["PYTEST_XDIST_WORKER"] = f"gw{i}"
            urls.append(_worker_redis_url())
        assert len(set(urls)) == 16, f"workers compartilhando banco de Redis: {urls}"

        # E acima de 16 a regra RECUSA, em vez de voltar a compartilhar em silêncio —
        # que é o modo de falhar que criou a dívida 35.
        os.environ["PYTEST_XDIST_WORKER"] = "gw16"
        with pytest.raises(RuntimeError, match="16 bancos"):
            _worker_redis_url()
    finally:
        if original is not None:
            os.environ["TEST_REDIS_URL"] = original
        if anterior is None:
            os.environ.pop("PYTEST_XDIST_WORKER", None)
        else:
            os.environ["PYTEST_XDIST_WORKER"] = anterior


def test_o_redis_em_uso_nao_e_o_banco_zero() -> None:
    """Banco 0 é o padrão de quem esqueceu de configurar.

    Se a suíte cair nele, o sinal é que `pytest_configure` não rodou ou que alguém
    exportou `REDIS_URL` por fora — e aí os testes estariam mexendo no Redis de
    desenvolvimento, que é pior que compartilhar entre workers.
    """
    assert not os.environ["REDIS_URL"].endswith("/0")
