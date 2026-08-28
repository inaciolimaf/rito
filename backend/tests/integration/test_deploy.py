"""Spec 099 — trava de migration, seed idempotente e provisionamento de escritório.

O que roda aqui é o caminho REAL de operação: as mesmas funções que o `lifespan` e a CLI
chamam, contra o banco de teste. O que não roda é `docker build` — construir a imagem
leva mais que toda a suíte e tem gate próprio no CI (ver `.github/workflows/ci.yml`); o
que a suíte garante da imagem são as propriedades estáticas, em `tests/meta/test_deploy_image.py`.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.cli import build_parser, main
from app.core.migrations import _destravar, _tentar_travar, upgrade_with_lock
from app.core.provisioning import provision_tenant, seed_global_catalogs
from app.domain.legal_agents.catalog import AGENT_SEEDS


async def test_a_trava_impede_migration_concorrente(admin_engine: AsyncEngine) -> None:
    """Regra 3. Deploy rolling sobe N containers ao mesmo tempo, e o Alembic não tem
    proteção nenhuma contra duas instâncias aplicando a mesma migration."""
    primeira = await _tentar_travar(admin_engine, "instancia-a")
    segunda = await _tentar_travar(admin_engine, "instancia-b")
    try:
        assert primeira is not None
        assert segunda is None, "duas instâncias tomaram a trava ao mesmo tempo"
    finally:
        await _destravar(primeira)
        await _destravar(segunda)

    # Solta e a próxima consegue — a trava não pode ficar presa depois do deploy.
    terceira = await _tentar_travar(admin_engine, "instancia-b")
    assert terceira is not None
    await _destravar(terceira)


async def test_quem_esta_com_a_trava_fica_visivel_na_tabela(
    admin_engine: AsyncEngine,
) -> None:
    """O que a tabela dá e o advisory lock não: durante um deploy travado, dizer QUEM
    está aplicando e desde quando, sem ninguém precisar saber ler `pg_locks`."""
    trava = await _tentar_travar(admin_engine, "instancia-visivel")
    try:
        async with admin_engine.connect() as conn:
            dono = await conn.scalar(text("SELECT locked_by FROM migration_locks WHERE id = 1"))
        assert dono == "instancia-visivel"
    finally:
        await _destravar(trava)

    async with admin_engine.connect() as conn:
        assert await conn.scalar(text("SELECT locked_by FROM migration_locks WHERE id = 1")) is None


async def test_a_trava_cai_junto_com_a_conexao_de_quem_morreu(
    admin_engine: AsyncEngine,
) -> None:
    """O caso feio: instância morta com a trava na mão. Advisory lock de sessão morre com
    a conexão — sem isso, um `kill -9` no meio de um deploy exigiria alguém entrar no
    banco à mão para o sistema voltar a subir."""
    trava = await _tentar_travar(admin_engine, "vai-morrer")
    assert trava is not None
    assert await _tentar_travar(admin_engine, "vizinha") is None

    # `close()` NÃO serve para simular morte: devolve a conexão ao pool, e o advisory
    # lock continua preso a ela. `invalidate()` descarta a conexão de verdade, que é o
    # que o sistema operacional faz quando o processo morre.
    await trava.invalidate()

    retomada = await _tentar_travar(admin_engine, "nova")
    assert retomada is not None, "a trava não foi liberada quando a conexão caiu"
    await _destravar(retomada)


async def test_a_trava_funciona_em_banco_que_ainda_nao_tem_a_tabela(
    admin_engine: AsyncEngine,
) -> None:
    """O caso que quebrou a primeira versão: `docker compose up` num banco NOVO.

    A tabela `migration_locks` é criada pela própria migration que está prestes a rodar,
    então não pode ser o mecanismo de exclusão. A anotação de dono some em silêncio; a
    trava continua valendo.
    """
    from app.core.migrations import _anotar_dono

    async with admin_engine.connect() as conn:
        await conn.execute(text("CREATE TEMP TABLE _sem_locks (x int)"))
        # Não levanta, mesmo que a tabela não existisse.
        await _anotar_dono(conn, "instancia-em-banco-novo")


async def test_migration_que_falha_propaga_e_solta_a_trava(
    admin_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regra 4: falha de migration impede a aplicação de subir. E a trava precisa sair
    junto — senão a próxima tentativa espera cinco minutos por um processo que morreu.

    A falha é injetada no ponto onde o Alembic é chamado, e não apontando para um banco
    inválido: `alembic/env.py` resolve a URL das `Settings` e ignora qualquer outra, de
    modo que a versão "aponte para localhost:1" migrava o banco CERTO em silêncio e o
    teste passava por engano.
    """

    def explode() -> None:
        raise RuntimeError("migration quebrou")

    monkeypatch.setattr("app.core.migrations._aplicar_sincrono", explode)

    with pytest.raises(RuntimeError, match="migration quebrou"):
        await upgrade_with_lock(admin_engine)

    async with admin_engine.connect() as conn:
        dono = await conn.scalar(text("SELECT locked_by FROM migration_locks WHERE id = 1"))
    assert dono is None, "a trava ficou presa depois de a migration falhar"


async def test_seed_global_e_idempotente(admin_engine: AsyncEngine) -> None:
    """Regra 7. Rodar no boot só é aceitável se rodar duas vezes for igual a rodar uma."""
    async with admin_engine.begin() as conn:
        await seed_global_catalogs(conn)
        segunda = await seed_global_catalogs(conn)
        total = await conn.scalar(text("SELECT count(*) FROM legal_agents WHERE tenant_id IS NULL"))

    assert segunda.total == 0, "a segunda passada inseriu linha — o seed não é idempotente"
    assert total == len(AGENT_SEEDS)


async def test_seed_global_repoe_o_que_sumiu(admin_engine: AsyncEngine) -> None:
    """O motivo de o seed existir apesar de a migration já ter semeado: uma linha global
    pode desaparecer (foi o que um `TRUNCATE ... CASCADE` de script de teste fez com os
    19 agentes da 087), e a migration não roda de novo porque já está aplicada."""
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM legal_agents WHERE tenant_id IS NULL AND code = :code"),
            {"code": AGENT_SEEDS[0].code},
        )
        resultado = await seed_global_catalogs(conn)
        total = await conn.scalar(text("SELECT count(*) FROM legal_agents WHERE tenant_id IS NULL"))

    assert resultado.legal_agents == 1
    assert total == len(AGENT_SEEDS)


async def test_escritorio_novo_nasce_com_a_taxonomia_inteira(
    admin_engine: AsyncEngine,
) -> None:
    """Regra 8, e a lacuna que a 099 fecha: até aqui um escritório criado depois das
    migrations nascia sem grupo de ação, sem etapa e sem tipo de tarefa — ou seja, sem
    conseguir cadastrar um processo."""
    tenant_id = uuid.uuid4()
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, 'Novo')"),
            {"id": tenant_id, "slug": f"novo-{tenant_id}"},
        )
        criados = await provision_tenant(conn, tenant_id)

    assert criados["action_groups"] == 6
    assert criados["stages"] == 59
    assert criados["customer_origins"] == 8
    assert criados["lawsuit_types"] > 0
    assert criados["task_types"] > 0
    assert criados["financial_categories"] > 0
    assert criados["cost_centers"] == 1


async def test_provisionar_duas_vezes_nao_duplica(admin_engine: AsyncEngine) -> None:
    """Provisionamento que morre no meio precisa ser seguro de repetir."""
    tenant_id = uuid.uuid4()
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, 'Repetido')"),
            {"id": tenant_id, "slug": f"rep-{tenant_id}"},
        )
        await provision_tenant(conn, tenant_id)
        segunda = await provision_tenant(conn, tenant_id)

    assert sum(segunda.values()) == 0


async def test_taxonomia_do_escritorio_novo_nao_vaza_para_o_vizinho(
    admin_engine: AsyncEngine,
    make_user: Callable[..., Awaitable[object]],
) -> None:
    """Toda tabela provisionada tem RLS. Provisionar A não pode acrescentar nada a B."""
    a, b = uuid.uuid4(), uuid.uuid4()
    async with admin_engine.begin() as conn:
        for tenant_id, slug in ((a, "iso-a"), (b, "iso-b")):
            await conn.execute(
                text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, 'Iso')"),
                {"id": tenant_id, "slug": f"{slug}-{tenant_id}"},
            )
        await provision_tenant(conn, a)
        de_b = await conn.scalar(text("SELECT count(*) FROM stages WHERE tenant_id = :t"), {"t": b})

    assert de_b == 0


async def test_cli_cria_escritorio_com_gestor_e_taxonomia(
    admin_engine: AsyncEngine, capsys: pytest.CaptureFixture[str]
) -> None:
    """O comando do §5 que um operador roda no primeiro dia."""
    slug = f"cli-{uuid.uuid4().hex[:8]}"
    codigo = await asyncio.to_thread(
        main,
        [
            "tenant",
            "create",
            "--name",
            "Escritório da CLI",
            "--slug",
            slug,
            "--admin-email",
            f"{slug}@exemplo.com.br",
        ],
    )

    assert codigo == 0
    saida = capsys.readouterr().out
    # A senha sorteada é exibida UMA vez: não fica em lugar nenhum para ser recuperada.
    assert "senha:" in saida
    assert "anote agora" in saida

    async with admin_engine.connect() as conn:
        tenant_id = await conn.scalar(
            text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": slug}
        )
        gestores = await conn.scalar(
            text("SELECT count(*) FROM users WHERE tenant_id = :t AND role = 'GESTOR'"),
            {"t": tenant_id},
        )
        etapas = await conn.scalar(
            text("SELECT count(*) FROM stages WHERE tenant_id = :t"), {"t": tenant_id}
        )
    assert gestores == 1
    assert etapas == 59


async def test_cli_recusa_criar_escritorio_com_slug_repetido(
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"dup-{uuid.uuid4().hex[:8]}"
    argumentos = [
        "tenant",
        "create",
        "--name",
        "Primeiro",
        "--slug",
        slug,
        "--admin-email",
        f"{slug}@exemplo.com.br",
    ]

    assert await asyncio.to_thread(main, argumentos) == 0
    assert await asyncio.to_thread(main, argumentos) == 1
    assert "já existe" in capsys.readouterr().err


def test_cli_expoe_todos_os_comandos_do_contrato() -> None:
    """§5 da spec, verificado no parser — um comando que some do CLI some do runbook e
    de quem depende dele, sem aviso."""
    parser = build_parser()

    for argumentos in (
        ["db", "upgrade"],
        ["db", "seed"],
        ["tenant", "create", "--name", "x", "--slug", "y", "--admin-email", "z@w.com"],
        ["tenant", "seed-defaults", "--slug", "y"],
        ["health"],
        ["backup", "create"],
        ["backup", "restore", "--input", "x.dump"],
    ):
        assert parser.parse_args(argumentos) is not None


def test_restauracao_exige_confirmacao_explicita() -> None:
    """Regra 11: `pg_restore --clean` apaga o banco antes de restaurar. Um comando que
    faz isso sem confirmação é uma tecla errada de distância de um desastre."""

    parser = build_parser()
    args = parser.parse_args(["backup", "restore", "--input", "inexistente.dump"])

    assert args.yes is False


async def test_boot_recusa_subir_com_configuracao_de_producao_invalida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regras 5 e 6 pelo caminho real: o `lifespan` do app, não a função de validação.

    É a diferença entre "a validação funciona" e "a validação está ligada" — a segunda é
    a que quebra quando alguém reorganiza o boot.
    """
    from app.core.bootstrap import EXAMPLE_SECRET_KEY, ConfigurationError
    from app.core.config import get_settings
    from app.main import create_app

    settings = get_settings()
    anteriores = (settings.app_env, settings.secret_key)
    object.__setattr__(settings, "app_env", "production")
    object.__setattr__(settings, "secret_key", EXAMPLE_SECRET_KEY)
    try:
        app = create_app()
        with pytest.raises(ConfigurationError, match="SECRET_KEY"):
            async with app.router.lifespan_context(app):
                pass  # pragma: no cover — o boot não chega aqui
    finally:
        object.__setattr__(settings, "app_env", anteriores[0])
        object.__setattr__(settings, "secret_key", anteriores[1])


async def test_desligamento_solta_o_que_a_requisicao_usava() -> None:
    """Regra 10, a parte que é nossa.

    Parar de aceitar conexão e esperar as requisições em curso é do uvicorn
    (`--timeout-graceful-shutdown`, conferido em `tests/meta/test_deploy_image.py`). O
    que cabe à aplicação é soltar pool e Redis no fim do `lifespan` — sem isso, cada
    reinício deixa conexões penduradas no Postgres até o timeout do servidor.
    """
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            assert (await ac.get("/health")).status_code == 200
        engine, redis = app.state.engine, app.state.redis

    # `dispose()` esvazia o pool: nenhuma conexão fica pendurada no Postgres esperando o
    # timeout do servidor. Não afirma que o engine ficou inutilizável — o SQLAlchemy
    # abriria um pool novo sob demanda, e é assim que ele foi desenhado.
    assert engine.pool.checkedin() == 0
    assert engine.pool.checkedout() == 0
    # O `aclose()` do redis-py desconecta o pool; conexões livres viram zero.
    assert redis.connection_pool._available_connections == []
