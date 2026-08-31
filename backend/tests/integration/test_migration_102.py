"""Spec 102, regra 14: o desempate de nomes duplicados da migration 102.

A migration cria um índice único normalizado sobre `squads`. Duplicatas que hoje são
VÁLIDAS (a constraint antiga comparava bytes) violariam esse índice, e a migration
falharia no meio de um deploy — por isso ela renomeia antes de indexar. Esta é a parte
arriscada, e é a que este teste cobre.

O SQL testado é **importado da migration**, não copiado: um teste que reescreve a query
prova que a cópia funciona, não que o deploy funciona.

Método: o cenário exige duplicatas, que o índice novo impede de inserir. Postgres tem
DDL transacional, então o teste derruba o índice, cria as duplicatas, roda o desempate,
confere e dá ROLLBACK — o índice volta ao fim, e nada disso é visível fora da transação.
"""

import importlib.util
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


def _carrega_migration() -> Any:
    """Carrega 102_squads_unaccent.py por caminho — o nome do módulo começa com dígito,
    então `import` normal não funciona."""
    caminho = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "102_squads_unaccent_unique.py"
    )
    spec = importlib.util.spec_from_file_location("migration_102", caminho)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


async def test_desempate_renomeia_duplicados_e_preserva_o_mais_antigo(
    admin_engine: AsyncEngine,
) -> None:
    desempate = _carrega_migration()._DESEMPATE
    tenant_id = uuid.uuid4()
    ids = [uuid.uuid4() for _ in range(3)]

    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            # O índice único normalizado impede inserir o cenário que a migration existe
            # para consertar. DDL é transacional no Postgres: o DROP volta no rollback.
            await conn.execute(text("DROP INDEX uq_squads_tenant_name"))
            await conn.execute(
                text("INSERT INTO tenants (id, name, slug) VALUES (:id, 'T 102', :slug)"),
                {"id": tenant_id, "slug": f"t102-{uuid.uuid4().hex[:8]}"},
            )
            # Três variações do MESMO nome para um humano, em ordem de criação conhecida.
            for posicao, (squad_id, nome) in enumerate(
                zip(ids, ["Time Ética", "TIME ETICA", "Timé Etica"], strict=True)
            ):
                await conn.execute(
                    text(
                        "INSERT INTO squads (id, tenant_id, name, is_active, created_at) "
                        "VALUES (:id, :tenant_id, :name, true, "
                        "        now() + make_interval(secs => :offset))"
                    ),
                    {
                        "id": squad_id,
                        "tenant_id": tenant_id,
                        "name": nome,
                        "offset": posicao,
                    },
                )
            # Um membro, para provar que o desempate não encosta em squad_members.
            user_id = (
                await conn.execute(
                    text(
                        "INSERT INTO users (id, tenant_id, name, email, password_hash, role) "
                        "VALUES (gen_random_uuid(), :tenant_id, 'U', :email, 'x', 'GESTOR') "
                        "RETURNING id"
                    ),
                    {"tenant_id": tenant_id, "email": f"u{uuid.uuid4().hex[:8]}@e.com"},
                )
            ).scalar_one()
            await conn.execute(
                text(
                    "INSERT INTO squad_members (id, tenant_id, squad_id, user_id) "
                    "VALUES (gen_random_uuid(), :tenant_id, :squad_id, :user_id)"
                ),
                {"tenant_id": tenant_id, "squad_id": ids[2], "user_id": user_id},
            )

            await conn.execute(text(desempate))

            linhas = (
                await conn.execute(
                    text("SELECT id, name FROM squads WHERE tenant_id = :t"),
                    {"t": tenant_id},
                )
            ).all()
            nomes: dict[uuid.UUID, str] = {row[0]: row[1] for row in linhas}

            # Nenhum time perdido.
            assert len(nomes) == 3
            # O mais antigo mantém o nome intacto.
            assert nomes[ids[0]] == "Time Ética"
            # Os demais ganham sufixo determinístico, na ordem de criação.
            assert nomes[ids[1]] == "TIME ETICA (2)"
            assert nomes[ids[2]] == "Timé Etica (3)"

            # E agora os três cabem no índice que a migration cria em seguida.
            await conn.execute(
                text(
                    "CREATE UNIQUE INDEX uq_squads_tenant_name ON squads "
                    "(tenant_id, immutable_unaccent(lower(name)))"
                )
            )

            # squad_members intacto — o desempate renomeia, nunca apaga.
            membros = (
                await conn.execute(
                    text("SELECT count(*) FROM squad_members WHERE squad_id = :s"),
                    {"s": ids[2]},
                )
            ).scalar_one()
            assert membros == 1
        finally:
            await trans.rollback()


async def test_nome_sem_duplicata_nao_e_renomeado(admin_engine: AsyncEngine) -> None:
    """O desempate só toca em quem colide: `row_number() > 1`. Um tenant sem duplicata
    sai da migration exatamente como entrou."""
    desempate = _carrega_migration()._DESEMPATE
    tenant_id = uuid.uuid4()
    squad_id = uuid.uuid4()

    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(
                text("INSERT INTO tenants (id, name, slug) VALUES (:id, 'T 102b', :slug)"),
                {"id": tenant_id, "slug": f"t102b-{uuid.uuid4().hex[:8]}"},
            )
            await conn.execute(
                text(
                    "INSERT INTO squads (id, tenant_id, name, is_active) "
                    "VALUES (:id, :tenant_id, 'Time Único', true)"
                ),
                {"id": squad_id, "tenant_id": tenant_id},
            )

            await conn.execute(text(desempate))

            nome = (
                await conn.execute(text("SELECT name FROM squads WHERE id = :id"), {"id": squad_id})
            ).scalar_one()
            assert nome == "Time Único"
        finally:
            await trans.rollback()
