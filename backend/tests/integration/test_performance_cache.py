"""Spec 098, regra 9 — cache de 5 minutos em dashboard e taxonomia, derrubado por evento.

Os dois lados da regra são testados sempre em par, porque cada um sozinho é um bug:
cache sem invalidação mostra número velho depois de uma escrita (o usuário lê como bug,
não como cache); invalidação sem cache não economiza nada.

O que se afirma não é "o cache existe" — é a consequência observável dele: a **segunda**
leitura não vai ao banco, e a leitura DEPOIS da escrita vai.
"""

import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from app.core.cache import cached_json, invalidate, tenant_key
from app.domain.users.models import UserRole
from app.main import app
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_lawsuits import _create_customer
from tests.perf import count_queries


class CacheFalso:
    """Implementação real do Protocol `Cache`, em memória (CLAUDE.md §5, LSP)."""

    def __init__(self) -> None:
        self.valores: dict[str, str] = {}
        self.leituras = 0

    async def get(self, name: str) -> str | None:
        self.leituras += 1
        return self.valores.get(name)

    async def set(self, name: str, value: str, *, ex: int) -> None:
        self.valores[name] = value

    async def delete(self, *names: str) -> None:
        for name in names:
            self.valores.pop(name, None)


class CacheQuebrado:
    async def get(self, name: str) -> str | None:
        raise ConnectionError("Redis fora")

    async def set(self, name: str, value: str, *, ex: int) -> None:
        raise ConnectionError("Redis fora")

    async def delete(self, *names: str) -> None:
        raise ConnectionError("Redis fora")


async def test_chave_de_cache_comeca_pelo_tenant() -> None:
    """Chave de cache não passa por RLS. O prefixo do escritório é o que impede um
    tenant de ler o agregado do outro — e por isso a montagem é uma função só."""
    a, b = uuid.uuid4(), uuid.uuid4()

    assert tenant_key("customers:stats", a) != tenant_key("customers:stats", b)
    assert tenant_key("customers:stats", a).startswith(f"customers:stats:{a}")


async def test_segunda_leitura_nao_recalcula() -> None:
    cache = CacheFalso()
    calculos = 0

    async def produzir() -> dict[str, int]:
        nonlocal calculos
        calculos += 1
        return {"total": 7}

    primeira = await cached_json(cache, "k", produzir, decode=dict)
    segunda = await cached_json(cache, "k", produzir, decode=dict)

    assert primeira == segunda == {"total": 7}
    assert calculos == 1


async def test_evento_derruba_o_cache() -> None:
    cache = CacheFalso()

    async def produzir() -> dict[str, int]:
        return {"total": 1}

    await cached_json(cache, "k", produzir, decode=dict)
    await invalidate(cache, "k")

    assert cache.valores == {}


async def test_cache_fora_do_ar_degrada_mas_nao_derruba() -> None:
    """Redis indisponível deve deixar o sistema lento, nunca fora do ar — o valor é
    calculado e devolvido igual, só sem economia."""
    calculos = 0

    async def produzir() -> dict[str, int]:
        nonlocal calculos
        calculos += 1
        return {"total": 3}

    valor = await cached_json(CacheQuebrado(), "k", produzir, decode=dict)
    await invalidate(CacheQuebrado(), "k")

    assert valor == {"total": 3}
    assert calculos == 1


async def test_dashboard_de_contatos_nao_vai_ao_banco_na_segunda_leitura(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    headers = auth_header(user)

    primeira = await client.get("/api/v1/customers/stats", headers=headers)
    async with count_queries(app) as log:
        segunda = await client.get("/api/v1/customers/stats", headers=headers)

    assert primeira.status_code == segunda.status_code == 200
    assert primeira.json() == segunda.json()
    # Só a query da autenticação: as seis agregações vieram do cache.
    assert log.count == 1, f"o dashboard recalculou apesar do cache:\n{log.resumo()}"


async def test_cadastrar_contato_derruba_o_dashboard(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """A metade que o TTL sozinho não resolve: sem invalidação por evento, o contato
    recém-cadastrado sumiria do dashboard por até cinco minutos."""
    user = await make_user(role=UserRole.GESTOR)
    headers = auth_header(user)
    antes = (await client.get("/api/v1/customers/stats", headers=headers)).json()["total"]

    criado_id = await _create_customer(client, headers, "Nova Pessoa")
    assert criado_id

    depois = (await client.get("/api/v1/customers/stats", headers=headers)).json()["total"]
    assert depois == antes + 1


async def test_catalogo_de_tarefas_e_cacheado_e_derrubado_ao_escrever(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    headers = auth_header(user)

    primeira = await client.get("/api/v1/task-types", headers=headers)
    async with count_queries(app) as log:
        await client.get("/api/v1/task-types", headers=headers)
    assert log.count == 1, f"o catálogo recalculou apesar do cache:\n{log.resumo()}"

    criado = await client.post(
        "/api/v1/task-types",
        headers=headers,
        json={"name": f"Tipo {uuid.uuid4().hex[:8]}", "reward": 5},
    )
    assert criado.status_code == 201, criado.text

    depois = await client.get("/api/v1/task-types", headers=headers)
    assert depois.json()["total"] == primeira.json()["total"] + 1


@pytest.mark.parametrize("filtro", ["?q=peticao", "?status=active", "?step_id=1"])
async def test_catalogo_filtrado_nao_usa_cache(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]], filtro: str
) -> None:
    """Cachear a listagem filtrada multiplicaria o espaço de chaves pelo produto dos
    filtros possíveis, com taxa de acerto perto de zero — só ocuparia Redis."""
    user = await make_user(role=UserRole.GESTOR)
    headers = auth_header(user)

    await client.get(f"/api/v1/task-types{filtro}", headers=headers)
    async with count_queries(app) as log:
        resposta = await client.get(f"/api/v1/task-types{filtro}", headers=headers)

    assert resposta.status_code == 200
    assert log.count > 1, "a listagem filtrada não deveria ser servida de cache"


async def test_cache_de_um_escritorio_nao_serve_o_outro(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """O isolamento do cache é o prefixo da chave, não o RLS — e por isso precisa de
    teste próprio."""
    a = await make_user(role=UserRole.GESTOR)
    b = await make_user(role=UserRole.GESTOR)
    await _create_customer(client, auth_header(a), "Só do A")

    stats_a = (await client.get("/api/v1/customers/stats", headers=auth_header(a))).json()
    stats_b = (await client.get("/api/v1/customers/stats", headers=auth_header(b))).json()

    assert stats_a["total"] >= 1
    assert stats_b["total"] == 0
