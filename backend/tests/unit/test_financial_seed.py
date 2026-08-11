"""Unit test do plano da spec 054: confere o seed da migration sem tocar banco (mesma
limitação de 011/012/014/015 — a migration só semeia tenants que já existiam quando ela
rodou; um tenant criado em teste via `make_user` nunca ganha o seed, ver Descobertas)."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_migration_module() -> object:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(config)
    revision = script.get_revision("054_chart_of_accounts")
    assert revision is not None
    return revision.module


def test_seed_10_grupos_61_categorias_1_centro() -> None:
    module = _load_migration_module()
    groups: list[tuple[int, str, str]] = module._DRE_GROUPS  # type: ignore[attr-defined]
    categories: list[tuple[str, str, int]] = module._CATEGORIES  # type: ignore[attr-defined]

    assert len(groups) == 10
    assert {id_ for id_, _name, _nature in groups} == set(range(10))

    assert len(categories) == 61
    receita = [item for item in categories if item[1] == "RECEITA"]
    despesa = [item for item in categories if item[1] == "DESPESA"]
    assert len(receita) == 14
    assert len(despesa) == 47

    # Nome único (regra 5) — o próprio índice único da migration depende disso.
    names = [name for name, _type, _group in categories]
    assert len(names) == len(set(names))

    # Toda categoria aponta pra um grupo que de fato existe entre os 10 semeados.
    group_ids = {id_ for id_, _name, _nature in groups}
    for name, _type, group_id in categories:
        assert group_id in group_ids, f"{name!r} aponta para grupo inexistente {group_id!r}"

    # Regra 2 (Descobertas): as 2 exceções reais do ADVBOX — tipo RECEITA num grupo de
    # natureza DESPESA — continuam no seed, não é erro de digitação.
    by_name = {name: (type_, group_id) for name, type_, group_id in categories}
    assert by_name["PAGAMENTO DE FATURA"] == ("RECEITA", 5)
    assert by_name["REEMBOLSO DE CUSTO POR CLIENTES"] == ("RECEITA", 6)

    # Grupo 1 (Receitas) é o único de natureza RECEITA — os outros 9 são DESPESA.
    natures_by_id = {id_: nature for id_, _name, nature in groups}
    assert natures_by_id[1] == "RECEITA"
    assert all(nature == "DESPESA" for id_, nature in natures_by_id.items() if id_ != 1)
