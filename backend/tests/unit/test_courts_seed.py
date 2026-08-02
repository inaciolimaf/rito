"""Unit test do plano da spec 021: confere a estrutura do seed de tribunais/sistemas
diretamente nos dados da migration, sem tocar banco (courts/court_systems são taxonomia
global — testar via HTTP contra um tenant de teste é redundante, os dados são os mesmos
para todo tenant; mesmo padrão de tests/unit/test_stages_seed.py, spec 015)."""

import re
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[2]

_DATAJUD_ALIAS_PATTERN = re.compile(r"^api_publica_[a-z0-9-]+$")


def _load_migration_module() -> object:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(config)
    revision = script.get_revision("021_courts_systems")
    assert revision is not None
    return revision.module


def test_seed_cria_exatamente_182_tribunais_e_13_sistemas() -> None:
    module = _load_migration_module()
    courts: list[tuple[str, str, str, str | None, str | None, bool]] = module._COURTS  # type: ignore[attr-defined]
    systems: list[str] = module._SYSTEMS  # type: ignore[attr-defined]

    assert len(courts) == 182
    assert len(systems) == 13


def test_seed_e_idempotente_sem_codigo_ou_sistema_duplicado() -> None:
    """ "Rodar duas vezes não duplica" (regra 5) — na prática o Alembic nunca reaplica uma
    migration já registrada, mas o dado em si também não pode ter duplicata interna, ou uma
    segunda inserção (ex.: num ambiente que recriasse o banco) violaria o UNIQUE(code)/
    UNIQUE(name) e falharia alto, nunca silenciosamente."""
    module = _load_migration_module()
    courts: list[tuple[str, str, str, str | None, str | None, bool]] = module._COURTS  # type: ignore[attr-defined]
    systems: list[str] = module._SYSTEMS  # type: ignore[attr-defined]

    codes = [code for code, *_rest in courts]
    assert len(codes) == len(set(codes)), "código de tribunal duplicado"
    assert len(systems) == len(set(systems)), "sistema duplicado"


def test_links_de_sistema_apontam_para_tribunal_e_sistema_existentes() -> None:
    module = _load_migration_module()
    courts: list[tuple[str, str, str, str | None, str | None, bool]] = module._COURTS  # type: ignore[attr-defined]
    systems: list[str] = module._SYSTEMS  # type: ignore[attr-defined]
    links: list[tuple[str, str]] = module._COURT_SYSTEM_LINKS  # type: ignore[attr-defined]

    codes = {code for code, *_rest in courts}
    system_names = set(systems)
    for court_code, system_name in links:
        assert court_code in codes, f"{court_code!r} não existe em _COURTS"
        assert system_name in system_names, f"{system_name!r} não existe em _SYSTEMS"


def test_todo_alias_datajud_tem_formato_valido() -> None:
    module = _load_migration_module()
    courts: list[tuple[str, str, str, str | None, str | None, bool]] = module._COURTS  # type: ignore[attr-defined]

    for code, _name, _segment, _state, alias, _active in courts:
        if alias is not None:
            assert _DATAJUD_ALIAS_PATTERN.match(alias), f"{code!r} tem alias inválido: {alias!r}"


def test_tribunais_superiores_nao_tem_uf() -> None:
    """Regra 4: STF, STJ, STM, TSE, TST não têm UF."""
    module = _load_migration_module()
    courts: list[tuple[str, str, str, str | None, str | None, bool]] = module._COURTS  # type: ignore[attr-defined]

    by_code = {code: state for code, _name, _segment, state, _alias, _active in courts}
    for code in ("STF", "STJ", "STM", "TSE", "TST"):
        assert by_code[code] is None
