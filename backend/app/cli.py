"""CLI de operação (spec 099, §5).

Os comandos que alguém que não participou do desenvolvimento precisa para **operar** o
Rito: aplicar migration, provisionar escritório, conferir dependências, tirar e
restaurar backup. Nenhum deles é chamado pela aplicação — são a interface de quem está
no terminal de produção, e é por isso que a saída é texto para humano em vez de JSON.

    rito db upgrade                 aplica migrations com trava
    rito db seed                    reafirma os catálogos globais
    rito tenant create --name --slug --admin-email [--admin-password]
    rito tenant seed-defaults --slug
    rito health                     verifica Postgres, Redis e storage
    rito backup create [--output]   pg_dump comprimido
    rito backup restore --input     restaura (pede confirmação)

Usa `argparse` e não uma biblioteca de CLI: são sete comandos, a stdlib dá conta, e uma
dependência a menos na imagem de produção é uma superfície a menos para atualizar.
"""

import argparse
import asyncio
import secrets
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_settings
from app.core.db import create_engine_from_url
from app.core.migrations import upgrade_with_lock
from app.core.provisioning import provision_tenant, seed_global_catalogs
from app.core.security import hash_password


def _admin_engine(settings: Settings) -> AsyncEngine:
    url = settings.migrations_database_url
    if not url:
        raise SystemExit("MIGRATIONS_DATABASE_URL não configurada — é ela que aplica migration.")
    return create_engine_from_url(url)


def _pg_url(async_url: str) -> str:
    """`postgresql+asyncpg://...` → `postgresql://...`, que é o que o `pg_dump` entende."""
    return async_url.replace("+asyncpg", "")


async def _db_upgrade(settings: Settings) -> int:
    engine = _admin_engine(settings)
    try:
        await upgrade_with_lock(engine)
        print("migrations aplicadas")
    finally:
        await engine.dispose()
    return 0


async def _db_seed(settings: Settings) -> int:
    engine = _admin_engine(settings)
    try:
        async with engine.begin() as conn:
            resultado = await seed_global_catalogs(conn)
        print(f"catálogos globais conferidos ({resultado.total} linha(s) reposta(s))")
    finally:
        await engine.dispose()
    return 0


async def _tenant_create(settings: Settings, args: argparse.Namespace) -> int:
    engine = _admin_engine(settings)
    # Senha sorteada quando não informada: obriga o primeiro acesso a passar por
    # "esqueci minha senha", e evita que uma senha combinada por chat vire a do gestor.
    senha = args.admin_password or secrets.token_urlsafe(16)
    tenant_id = uuid.uuid4()
    try:
        async with engine.begin() as conn:
            existente = await conn.scalar(
                text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": args.slug}
            )
            if existente is not None:
                print(f"escritório '{args.slug}' já existe ({existente})", file=sys.stderr)
                return 1
            await conn.execute(
                text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, :name)"),
                {"id": tenant_id, "slug": args.slug, "name": args.name},
            )
            criados = await provision_tenant(conn, tenant_id)
            await conn.execute(
                text("""
                    INSERT INTO users (tenant_id, email, password_hash, name, role,
                                       financial_access, is_active)
                    VALUES (:tenant, :email, :hash, :nome, 'GESTOR', 'FULL', true)
                    """),
                {
                    "tenant": tenant_id,
                    "email": args.admin_email,
                    "hash": hash_password(senha),
                    "nome": "Administrador",
                },
            )
    finally:
        await engine.dispose()

    print(f"escritório criado: {args.name} ({args.slug})")
    print(f"  tenant_id: {tenant_id}")
    print(f"  gestor:    {args.admin_email}")
    if not args.admin_password:
        print(f"  senha:     {senha}   <- anote agora; não é exibida de novo")
    for catalogo, quantidade in criados.items():
        print(f"  {catalogo}: {quantidade}")
    return 0


async def _tenant_seed_defaults(settings: Settings, args: argparse.Namespace) -> int:
    engine = _admin_engine(settings)
    try:
        async with engine.begin() as conn:
            tenant_id = await conn.scalar(
                text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": args.slug}
            )
            if tenant_id is None:
                print(f"escritório '{args.slug}' não encontrado", file=sys.stderr)
                return 1
            criados = await provision_tenant(conn, tenant_id)
    finally:
        await engine.dispose()
    for catalogo, quantidade in criados.items():
        print(f"{catalogo}: {quantidade}")
    return 0


async def _health(settings: Settings) -> int:
    """Mesma sonda do `/health/ready`, do terminal — útil quando a aplicação nem sobe."""
    from redis.asyncio import Redis

    from app.core.health import _probe
    from app.integrations.storage.s3 import create_file_storage

    engine = create_engine_from_url(settings.database_url)
    redis = Redis.from_url(settings.redis_url)
    storage = create_file_storage()

    async def postgres() -> object:
        async with engine.connect() as conn:
            return await conn.execute(text("SELECT 1"))

    resultados = await asyncio.gather(
        _probe("database", postgres),
        _probe("redis", redis.ping),
        _probe("storage", storage.ping),
    )
    await redis.aclose()
    await engine.dispose()

    for nome, estado in resultados:
        print(f"{nome}: {estado}")
    return 0 if all(estado == "ok" for _nome, estado in resultados) else 1


def _backup_create(settings: Settings, args: argparse.Namespace) -> int:
    destino = Path(args.output or f"rito-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.dump")
    url = _pg_url(settings.migrations_database_url or settings.database_url)
    # `--format=custom`: comprimido e restaurável seletivamente, ao contrário do SQL puro.
    resultado = subprocess.run(
        ["pg_dump", "--format=custom", "--no-owner", "--file", str(destino), url],
        check=False,
    )
    if resultado.returncode != 0:
        return resultado.returncode
    print(f"backup: {destino} ({destino.stat().st_size / 1024 / 1024:.1f} MB)")
    print("Confira a restauração num banco descartável — backup não testado não é backup.")
    return 0


def _backup_restore(settings: Settings, args: argparse.Namespace) -> int:
    origem = Path(args.input)
    if not origem.exists():
        print(f"arquivo não encontrado: {origem}", file=sys.stderr)
        return 1
    if not args.yes:
        print(
            f"Isto SOBRESCREVE o banco em {_pg_url(settings.database_url)}.\n"
            "Repita com --yes para confirmar.",
            file=sys.stderr,
        )
        return 1
    url = _pg_url(settings.migrations_database_url or settings.database_url)
    resultado = subprocess.run(
        ["pg_restore", "--clean", "--if-exists", "--no-owner", "--dbname", url, str(origem)],
        check=False,
    )
    if resultado.returncode == 0:
        print("restauração concluída")
    return resultado.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rito", description="Operação do Rito")
    sub = parser.add_subparsers(dest="grupo", required=True)

    db = sub.add_parser("db", help="banco de dados").add_subparsers(dest="acao", required=True)
    db.add_parser("upgrade", help="aplica migrations com trava")
    db.add_parser("seed", help="reafirma os catálogos globais (idempotente)")

    tenant = sub.add_parser("tenant", help="escritórios").add_subparsers(dest="acao", required=True)
    criar = tenant.add_parser("create", help="cria escritório com taxonomia e gestor")
    criar.add_argument("--name", required=True)
    criar.add_argument("--slug", required=True)
    criar.add_argument("--admin-email", required=True)
    criar.add_argument("--admin-password", default=None)
    semear = tenant.add_parser("seed-defaults", help="repõe a taxonomia de um escritório")
    semear.add_argument("--slug", required=True)

    sub.add_parser("health", help="verifica Postgres, Redis e storage")

    backup = sub.add_parser("backup", help="backup e restauração").add_subparsers(
        dest="acao", required=True
    )
    criar_backup = backup.add_parser("create")
    criar_backup.add_argument("--output", default=None)
    restaurar = backup.add_parser("restore")
    restaurar.add_argument("--input", required=True)
    restaurar.add_argument("--yes", action="store_true", help="confirma a sobrescrita")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()

    if args.grupo == "db":
        return asyncio.run(_db_upgrade(settings) if args.acao == "upgrade" else _db_seed(settings))
    if args.grupo == "tenant":
        if args.acao == "create":
            return asyncio.run(_tenant_create(settings, args))
        return asyncio.run(_tenant_seed_defaults(settings, args))
    if args.grupo == "health":
        return asyncio.run(_health(settings))
    if args.acao == "create":
        return _backup_create(settings, args)
    return _backup_restore(settings, args)


if __name__ == "__main__":
    raise SystemExit(main())
