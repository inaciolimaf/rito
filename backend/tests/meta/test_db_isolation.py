"""Regra 3 da spec 009: a migration roda uma vez (via scripts/run-tests.sh, antes dos
workers do -n auto subirem) — o banco de teste já deve estar na head quando os testes
começam, e workers concorrentes não devem tentar migrar de novo."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _alembic_head_revision() -> str:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()
    assert head is not None, "Nenhuma migration encontrada em alembic/versions/."
    return head


async def test_banco_de_teste_ja_esta_na_head_antes_do_teste_rodar(
    admin_engine: AsyncEngine,
) -> None:
    expected_head = _alembic_head_revision()

    async with admin_engine.connect() as conn:
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        current = result.scalar_one()

    assert current == expected_head, (
        f"rito_test está em {current!r}, esperado {expected_head!r} — a migration não "
        "rodou (ou não rodou até o fim) antes da suíte começar."
    )
