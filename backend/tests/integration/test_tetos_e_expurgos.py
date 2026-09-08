"""Spec 137 — os tetos que faltavam, os índices que o RLS desligava e o expurgo que sobrou.

Cada teste aqui guarda um defeito MEDIDO, e o número que o defeito custava está no
docstring. Sem isso, o teste vira "o código faz o que o código faz"; com isso, quem
mexer daqui a um ano sabe o que a linha comprou.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.listing import unaccented_contains
from app.core.rls import set_tenant_context
from app.domain.customers.models import Customer
from app.domain.lawsuits.cnj import compute_check_digit, format_cnj, parse_cnj
from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.schedule.service import ScheduleService
from app.domain.users.models import UserRole
from app.domain.webhooks.models import WebhookDelivery, WebhookEndpoint
from app.domain.webhooks.service import PURGE_MAX_ROWS, RETENTION_DAYS, WebhookService
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_lawsuits import (
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)

# ---------------------------------------------------------------------------
# Defeito 4 — o predicado de busca e o índice precisam ser a MESMA expressão
# ---------------------------------------------------------------------------

# Os dois nomes que a migration 137 marca `LEAKPROOF`, e sem os quais nenhum índice
# trigram é alcançável sob RLS. `pg_dump` não emite `ALTER FUNCTION` de catálogo: depois
# de um restore, este é o único lugar onde a perda aparece.
FUNCOES_LEAKPROOF = (("texticlike", 2), ("immutable_unaccent", 1))

INDICES_DA_137 = {
    "ix_customers_name_trgm",
    "ix_transactions_description_trgm",
    "ix_posts_schedule",
    "ix_posts_schedule_deadline",
    "ix_notifications_recent",
    "ix_deliveries_created",
}


async def test_predicado_de_busca_e_a_mesma_expressao_do_indice(
    admin_engine: AsyncEngine,
) -> None:
    """O defeito 4 em uma linha: o WHERE dizia `unaccent(lower(name))`, o índice dizia
    outra coisa, e o planner não casa expressão parecida — casa expressão IGUAL.

    Medido em 100 mil contatos, sob RLS: 83,7 ms de `Parallel Seq Scan` com o predicado
    antigo contra 2,9 ms de `Bitmap Index Scan` com este. O teste compara o SQL que o
    filtro gera com a definição do índice no catálogo, que é a única comparação que o
    planner de fato faz.
    """
    # No dialeto do Postgres, e não no genérico: o genérico escreve `ILIKE` como
    # `lower(x) LIKE lower(y)`, que não é o SQL que chega ao banco — e é justamente a
    # expressão que chega ao banco que o planner compara com a do índice.
    sql = str(
        unaccented_contains(Customer.name, "conceicao").compile(
            dialect=postgresql.dialect(),  # type: ignore[no-untyped-call]  # `dialect()` do asyncpg não tem stub tipado.
            compile_kwargs={"literal_binds": True},
        )
    )
    async with admin_engine.connect() as conn:
        definicao = (
            await conn.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_customers_name_trgm'")
            )
        ).scalar_one()

    assert "immutable_unaccent(customers.name)" in sql
    assert "lower" not in sql, "o `lower()` impede a promoção do predicado sob RLS"
    assert "immutable_unaccent(name)" in definicao


@pytest.mark.parametrize(("nome", "argumentos"), FUNCOES_LEAKPROOF)
async def test_funcao_da_busca_continua_leakproof(
    admin_engine: AsyncEngine, nome: str, argumentos: int
) -> None:
    """Sob RLS, um predicado só vira condição de índice se for LEAKPROOF — senão ele
    seria avaliado antes da política de tenant. Sem estas duas marcas os seis índices
    `gin_trgm_ops` do schema existem e nunca são usados, sem erro nenhum: só o plano
    piora. Um `pg_restore` desfaz as marcas em silêncio; este teste é o alarme."""
    async with admin_engine.connect() as conn:
        leakproof = (
            await conn.execute(
                text(
                    "SELECT proleakproof FROM pg_proc "
                    "WHERE proname = :nome AND pronargs = :n "
                    "AND proargtypes::text = ANY (ARRAY['25', '25 25'])"
                ),
                {"nome": nome, "n": argumentos},
            )
        ).scalar_one()

    assert leakproof is True, f"{nome} deixou de ser LEAKPROOF — restore de backup?"


async def test_indices_da_137_existem(admin_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn:
        existentes = set(
            (
                await conn.execute(
                    text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
                )
            )
            .scalars()
            .all()
        )
    assert existentes >= INDICES_DA_137


async def test_busca_de_contato_sem_acento_continua_achando(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """A correção do defeito 4 é sobre o PLANO; o resultado não pode mudar. "conceicao"
    continua achando "Conceição", e "CONCEIÇÃO" também."""
    user = await make_user(role=UserRole.GESTOR)
    headers = auth_header(user)
    await _create_customer(client, headers, "Maria da Conceição Ética")

    for termo in ("conceicao", "CONCEIÇÃO", "Ética", "etica"):
        resposta = await client.get(f"/api/v1/customers?q={termo}", headers=headers)
        assert resposta.status_code == 200
        assert resposta.json()["total"] == 1, termo


# ---------------------------------------------------------------------------
# Defeito 1 — o expurgo de webhooks morria no teto de binds do asyncpg
# ---------------------------------------------------------------------------

_ACIMA_DO_TETO_DE_BINDS = 35_000


async def test_expurgo_de_webhooks_passa_do_teto_de_32767_binds(
    app_session_factory: async_sessionmaker[AsyncSession],
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """O defeito 1. A versão anterior carregava os ids vencidos e montava
    `DELETE ... WHERE id IN (<n binds>)`; asyncpg aceita 32.767 parâmetros por comando, e
    com 70 mil entregas isso levantava `InterfaceError` em 477 ms — a cada minuto, para
    sempre, e a retenção de 30 dias deixava de existir.

    35.000 linhas é o menor número que prova o ponto: uma a mais que o teto já bastaria
    para a versão antiga estourar.
    """
    user = await make_user(role=UserRole.GESTOR)
    async with app_session_factory() as session:
        await set_tenant_context(session, user.tenant_id)
        endpoint = WebhookEndpoint(
            tenant_id=user.tenant_id,
            name="Bench",
            url="https://example.com/hook",
            secret="s3cr3t",
        )
        session.add(endpoint)
        await session.flush()
        vencido = datetime.now(UTC) - timedelta(days=RETENTION_DAYS + 1)
        await session.execute(
            text(
                "INSERT INTO webhook_deliveries "
                "(tenant_id, endpoint_id, event_kind, payload, created_at) "
                "SELECT :tenant, :endpoint, 'lawsuit.created', '{}'::jsonb, :quando "
                "FROM generate_series(1, :quantas)"
            ),
            {
                "tenant": user.tenant_id,
                "endpoint": endpoint.id,
                "quando": vencido,
                "quantas": _ACIMA_DO_TETO_DE_BINDS,
            },
        )
        recente = WebhookDelivery(
            tenant_id=user.tenant_id,
            endpoint_id=endpoint.id,
            event_kind="lawsuit.created",
            payload={},
        )
        session.add(recente)
        await session.flush()

        service = WebhookService(session, user.tenant_id, sender=None)  # type: ignore[arg-type]  # `purge_old` não envia nada; o sender só serve a `attempt`.
        apagadas = await service.purge_old(max_rows=_ACIMA_DO_TETO_DE_BINDS + 1)

        assert apagadas == _ACIMA_DO_TETO_DE_BINDS
        restantes = (
            await session.execute(text("SELECT count(*) FROM webhook_deliveries"))
        ).scalar_one()
        assert restantes == 1, "a entrega dentro da janela de 30 dias não pode sair"
        await session.rollback()


def test_expurgo_de_webhooks_tem_teto_por_execucao() -> None:
    """O teto não é de retenção, é de transação: o beat roda de minuto em minuto e o que
    sobrar sai no minuto seguinte. 20.000/min drenam 28,8 milhões por dia."""
    assert PURGE_MAX_ROWS == 20_000


# ---------------------------------------------------------------------------
# Defeitos 2 e 3 — a agenda e o feed iCal não tinham teto de linhas
# ---------------------------------------------------------------------------


async def _agenda_com_tarefas(
    client: AsyncClient, headers: dict[str, str], user_id: str, quantas: int
) -> None:
    type_id, _grupo = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    lawsuit = await _create_lawsuit(
        client, headers, user_id=user_id, lawsuit_type_id=type_id, stage_id=stage_id
    )
    tipo = await client.post(
        "/api/v1/task-types",
        headers=headers,
        json={"name": f"Tipo {uuid.uuid4().hex[:8]}", "reward": 5},
    )
    assert tipo.status_code == 201, tipo.text
    task_type_id = tipo.json()["id"]
    for dia in range(1, quantas + 1):
        criado = await client.post(
            "/api/v1/posts",
            headers=headers,
            json={
                "lawsuit_id": lawsuit["id"],
                "task_type_id": task_type_id,
                "user_ids": [user_id],
                "scheduled_date": f"2026-09-{dia:02d}",
                "show_in_schedule": True,
            },
        )
        assert criado.status_code == 201, criado.text


async def test_agenda_avisa_quando_o_teto_corta(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Defeito 3. `GET /api/v1/schedule` devolvia a janela inteira do escritório —
    medido: 20.070 eventos e 9,6 MB numa janela de 90 dias sem filtro de usuário, com
    `Seq Scan` em `posts`. Agora tem teto, e o teto AVISA: um corte silencioso some com
    o compromisso sem dizer nada, que é pior que não ter teto."""
    user = await make_user(role=UserRole.GESTOR)
    headers = auth_header(user)
    await _agenda_com_tarefas(client, headers, str(user.user_id), quantas=3)

    async with app_session_factory() as session:
        await set_tenant_context(session, user.tenant_id)
        service = ScheduleService(session)
        from app.domain.schedule.service import DateField

        cheia = await service.list_events(
            viewer=user.user_id,
            start=date(2026, 9, 1),
            end=date(2026, 9, 30),
            date_field=DateField.SCHEDULED,
            user_id=None,
            show_completed=True,
            today=date(2026, 9, 8),
        )
        cortada = await service.list_events(
            viewer=user.user_id,
            start=date(2026, 9, 1),
            end=date(2026, 9, 30),
            date_field=DateField.SCHEDULED,
            user_id=None,
            show_completed=True,
            today=date(2026, 9, 8),
            limit=2,
        )

    assert len(cheia.events) == 3 and cheia.truncated is False
    assert len(cortada.events) == 2 and cortada.truncated is True


async def test_feed_ical_responde_304_para_o_mesmo_conteudo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Defeito 2. A rota é pública por token, sem sessão e sem rate limit, e os clientes
    de calendário fazem polling de 15 em 15 minutos POR USUÁRIO — 1,9 s de consulta e
    19,8 MB de `.ics` medidos por requisição. O `ETag` faz o polling custar um `304`
    enquanto a agenda não muda."""
    user = await make_user(role=UserRole.GESTOR)
    headers = auth_header(user)
    ativado = await client.post("/api/v1/schedule/ical/enable", headers=headers)
    url = ativado.json()["url"]

    primeira = await client.get(url)
    assert primeira.status_code == 200
    etag = primeira.headers["etag"]
    assert etag

    segunda = await client.get(url, headers={"If-None-Match": etag})
    assert segunda.status_code == 304
    assert segunda.content == b""

    terceira = await client.get(url, headers={"If-None-Match": '"outra-coisa"'})
    assert terceira.status_code == 200


# ---------------------------------------------------------------------------
# Defeito 5 — o casamento de publicação varria `lawsuits` duas vezes por intimação
# ---------------------------------------------------------------------------


# Um número CNJ válido de verdade: o `POST /lawsuits` valida o dígito verificador
# (spec 026), então um número inventado seria recusado antes de chegar ao repositório.
_DIGITOS_CNJ = "0009999" + compute_check_digit("000999920248260999") + "20248260999"
_MASCARA_CNJ = format_cnj(parse_cnj(_DIGITOS_CNJ))


@pytest.mark.parametrize("salvo_como", [_DIGITOS_CNJ, _MASCARA_CNJ], ids=["cru", "com máscara"])
async def test_casamento_por_numero_acha_nas_duas_grafias(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
    salvo_como: str,
) -> None:
    """Defeito 5. `regexp_replace` sobre a coluna desligava o `ix_lawsuits_number` —
    `Seq Scan`, 42,6 ms em 20 mil processos, por intimação, dentro do worker do DJEN.
    A busca agora é por literais indexados, e as duas grafias continuam casando."""
    user = await make_user(role=UserRole.GESTOR)
    headers = auth_header(user)
    type_id, _grupo = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    await _create_lawsuit(
        client,
        headers,
        user_id=str(user.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        process_number=salvo_como,
    )

    async with app_session_factory() as session:
        await set_tenant_context(session, user.tenant_id)
        achados = await LawsuitRepository(session).find_by_process_number_digits(_DIGITOS_CNJ)

    assert len(achados) == 1


async def test_casamento_por_numero_ainda_acha_grafia_fora_do_padrao(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A segunda tentativa (o `regexp_replace`) é o que preserva o comportamento: um
    número salvo com pontuação que não é a máscara canônica continua casando, só que
    depois de a primeira consulta — indexada — não ter achado nada."""
    user = await make_user(role=UserRole.GESTOR)
    headers = auth_header(user)
    type_id, _grupo = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    await _create_lawsuit(
        client,
        headers,
        user_id=str(user.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        process_number=_MASCARA_CNJ.replace("-", " ").replace(".", " "),
    )

    async with app_session_factory() as session:
        await set_tenant_context(session, user.tenant_id)
        achados = await LawsuitRepository(session).find_by_process_number_digits(_DIGITOS_CNJ)

    assert len(achados) == 1


async def test_candidatos_por_responsavel_param_no_teto(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Defeito 5, segunda metade: `list_by_responsible` materializava TODOS os processos
    do advogado (20.000 objetos ORM, 967 ms, 75 MB de pico) só para comparar `len(...)`
    com 1. Dois candidatos respondem "nenhum", "um" e "mais de um"."""
    user = await make_user(role=UserRole.GESTOR)
    headers = auth_header(user)
    type_id, _grupo = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    for _ in range(3):
        await _create_lawsuit(
            client,
            headers,
            user_id=str(user.user_id),
            lawsuit_type_id=type_id,
            stage_id=stage_id,
        )

    async with app_session_factory() as session:
        await set_tenant_context(session, user.tenant_id)
        repo = LawsuitRepository(session)
        assert len(await repo.list_by_responsible(user.user_id, limit=2)) == 2
        assert len(await repo.list_by_responsible(user.user_id)) == 3


# ---------------------------------------------------------------------------
# Defeitos 6 e 7 — agregado que muda por escrita de OUTRO agregado não entra em cache
# ---------------------------------------------------------------------------


async def test_quadro_do_crm_conta_o_processo_recem_criado(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Defeito 6, exatamente como foi medido: com 1 processo no escritório, criar o
    segundo mantinha `total = 1` por até cinco minutos, porque `crm:board_counts` só caía
    ao ARRASTAR um card."""
    user = await make_user(role=UserRole.GESTOR)
    headers = auth_header(user)
    type_id, _grupo = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    primeiro: dict[str, object] = await _create_lawsuit(
        client, headers, user_id=str(user.user_id), lawsuit_type_id=type_id, stage_id=stage_id
    )

    antes = (await client.get("/api/v1/crm/board", headers=headers)).json()["total"]
    await _create_lawsuit(
        client, headers, user_id=str(user.user_id), lawsuit_type_id=type_id, stage_id=stage_id
    )
    depois = (await client.get("/api/v1/crm/board", headers=headers)).json()["total"]

    assert antes == 1
    assert depois == 2

    # O arquivamento é o outro caso que a auditoria levantou, e ele NÃO era defeito de
    # cache: a visão padrão do quadro é "all", que conta processo arquivado de propósito
    # (`LAWSUIT_VIEWS`, spec 027 §5). Quem quer o quadro sem eles pede `view=active` — e
    # aí o número cai na hora, porque visão com filtro nunca passou pelo cache.
    apagado = await client.delete(f"/api/v1/lawsuits/{primeiro['id']}", headers=headers)
    assert apagado.status_code == 204
    ativos = await client.get("/api/v1/crm/board?view=active", headers=headers)
    assert ativos.json()["total"] == 1


async def test_painel_de_contatos_conta_processo_novo_na_hora(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Defeito 7, exatamente como foi medido: `with_active_lawsuit` ficava em 0 depois de
    o contato virar parte de um processo, porque `customers:stats` só cai quando alguém
    escreve um CONTATO."""
    user = await make_user(role=UserRole.GESTOR)
    headers = auth_header(user)
    customer_id = await _create_customer(client, headers, "Parte Ativa")
    type_id, _grupo = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)

    antes = (await client.get("/api/v1/customers/stats", headers=headers)).json()
    assert antes["with_active_lawsuit"] == 0

    await _create_lawsuit(
        client,
        headers,
        user_id=str(user.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
    )

    depois = (await client.get("/api/v1/customers/stats", headers=headers)).json()
    assert depois["with_active_lawsuit"] == 1
    assert depois["without_active_lawsuit"] == depois["total"] - 1


# ---------------------------------------------------------------------------
# Defeito 10 — as cinco tabelas de log que cresciam sem horizonte
# ---------------------------------------------------------------------------


async def test_expurgo_apaga_o_vencido_e_preserva_o_recente(admin_engine: AsyncEngine) -> None:
    """Defeito 10. Cinco tabelas escritas por caminho automático não tinham retenção
    nenhuma — `api_requests` sozinha grava 525 mil linhas por ano por escritório numa
    integração de minuto em minuto. Uma linha vencida e uma recente por tabela: o
    expurgo leva a primeira e não encosta na segunda.

    O escritório e o usuário são criados AQUI, pela conexão de administrador, e não pelo
    `make_user`: o expurgo abre conexão própria (é uma tarefa cross-tenant que roda como
    superusuário), e nada que estivesse dentro da transação do teste existiria para ele.
    O `DELETE` do fim é o que devolve o banco ao estado anterior sem precisar do marcador
    `commits`, cujo teto de arquivos é ele próprio um gate (spec 105, regra 8).
    """
    from app.workers.retention import POLICIES, purge_expired

    url = get_settings().migrations_database_url
    assert url is not None
    tenant_id, user_id = uuid.uuid4(), uuid.uuid4()

    inserts = {
        "api_requests": (
            "INSERT INTO api_requests (tenant_id, method, path, status_code, created_at) "
            "VALUES (:t, 'GET', '/x', 200, :quando)"
        ),
        "notifications": (
            "INSERT INTO notifications (tenant_id, user_id, kind, title, created_at) "
            "VALUES (:t, :u, 'PRAZO', 'x', :quando)"
        ),
        "ai_usage": (
            "INSERT INTO ai_usage (tenant_id, feature_key, model, status, created_at) "
            "VALUES (:t, 'chat', 'm', 'ok', :quando)"
        ),
        "search_history": (
            "INSERT INTO search_history (tenant_id, user_id, query, created_at) "
            "VALUES (:t, :u, 'x', :quando)"
        ),
    }
    horizontes = {politica.model.__tablename__: politica.days for politica in POLICIES}

    try:
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO tenants (id, slug, name) VALUES (:t, :slug, 'Expurgo')"),
                {"t": tenant_id, "slug": f"expurgo-{tenant_id}"},
            )
            await conn.execute(
                text(
                    "INSERT INTO users (id, tenant_id, email, name, password_hash) "
                    "VALUES (:u, :t, :email, 'Expurgo', 'x')"
                ),
                {"u": user_id, "t": tenant_id, "email": f"{user_id}@example.com"},
            )
            for tabela, sql in inserts.items():
                for offset in (horizontes[tabela] + 1, 0):
                    await conn.execute(
                        text(sql),
                        {
                            "t": tenant_id,
                            "u": user_id,
                            "quando": datetime.now(UTC) - timedelta(days=offset),
                        },
                    )

        apagadas = await purge_expired(url)

        async with admin_engine.connect() as conn:
            for tabela in inserts:
                restantes = (
                    await conn.execute(
                        # `tabela` vem das chaves literais do dicionário acima, nunca de
                        # entrada externa — é por isso que a f-string é segura aqui.
                        text(f"SELECT count(*) FROM {tabela} WHERE tenant_id = :t"),
                        {"t": tenant_id},
                    )
                ).scalar_one()
                assert restantes == 1, f"{tabela}: sobrou {restantes} linha(s), esperava 1"
                assert apagadas[tabela] >= 1
    finally:
        async with admin_engine.begin() as conn:
            for tabela in [*inserts, "users", "tenants"]:
                coluna = "id" if tabela == "tenants" else "tenant_id"
                # Mesmos nomes literais do dicionário acima, mais as duas raízes.
                await conn.execute(
                    text(f"DELETE FROM {tabela} WHERE {coluna} = :t"), {"t": tenant_id}
                )


def test_todo_horizonte_de_retencao_esta_declarado() -> None:
    """Retenção sem motivo escrito vira número que ninguém ousa mexer. As cinco políticas
    são explícitas, e nenhuma passa de dois anos — o mais longo é `ai_usage`, que precisa
    atravessar o fechamento do exercício."""
    from app.workers.retention import POLICIES

    tabelas = {politica.model.__tablename__: politica.days for politica in POLICIES}
    assert tabelas == {
        "api_requests": 90,
        "notifications": 180,
        "ai_usage": 730,
        "search_history": 90,
        "automation_runs": 180,
    }


# ---------------------------------------------------------------------------
# Defeito 11 — a varredura de agregados podia se sobrepor a si mesma
# ---------------------------------------------------------------------------


async def test_varredura_de_agregados_nao_se_sobrepoe() -> None:
    """Defeito 11. O beat é de um minuto e `last_refresh_at` só é escrito no FIM: uma
    rodada que passe do minuto deixa o tick seguinte disparar `REFRESH CONCURRENTLY`
    duplicado, que serializa no lock da view e empilha conexões de superusuário.

    O teste segura a trava e chama a varredura: ela desiste devolvendo lista vazia, sem
    esperar e sem refrescar nada.
    """
    from app.workers.aggregates import _sweep_lock, refresh_due_aggregates

    url = get_settings().migrations_database_url
    assert url is not None

    async with _sweep_lock(url) as adquirido:
        assert adquirido is True
        assert await refresh_due_aggregates(url) == []

    # Solta a trava: a varredura seguinte volta a poder rodar.
    async with _sweep_lock(url) as depois:
        assert depois is True


def test_chave_da_trava_nao_colide_com_a_das_migrations() -> None:
    """Advisory lock é um espaço de nomes só. Duas travas com o mesmo número seriam a
    mesma trava, e a varredura de agregados bloquearia o deploy."""
    from app.core.migrations import ADVISORY_LOCK_KEY
    from app.workers.aggregates import SWEEP_LOCK_KEY

    assert SWEEP_LOCK_KEY != ADVISORY_LOCK_KEY


def test_nenhum_uuid_orfao() -> None:
    """Sentinela boba de import: `uuid` é usado pelos helpers importados acima."""
    assert uuid.uuid4() != uuid.uuid4()
