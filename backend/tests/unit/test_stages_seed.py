"""Unit test do plano da spec 015: confere que os dados de seed da migration mapeiam cada
uma das 59 etapas para uma das 9 fases, sem tocar banco (a migration só semeia tenants que já
existiam quando ela rodou — um tenant criado em teste via `make_user` nunca ganha o seed, então
verificar via HTTP não é possível; ver spec 015, Descobertas)."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_migration_module() -> object:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(config)
    revision = script.get_revision("015_steps_stages")
    assert revision is not None
    return revision.module


def test_seed_das_59_etapas_mapeia_a_fase_certa() -> None:
    module = _load_migration_module()
    steps: list[str] = module._STEPS  # type: ignore[attr-defined]
    stages_by_step: list[tuple[str, str]] = module._STAGES_BY_STEP  # type: ignore[attr-defined]

    assert len(steps) == 9
    assert len(stages_by_step) == 59

    # Toda etapa aponta para uma fase que de fato existe entre as 9 semeadas.
    for name, step_name in stages_by_step:
        assert step_name in steps, f"{name!r} aponta para fase inexistente {step_name!r}"

    # Amostra de mapeamentos que a spec 015 (Descobertas) documenta explicitamente.
    by_name = dict(stages_by_step)
    assert by_name["AGUARDANDO AUDIÊNCIA"] == "Judicial"
    assert by_name["RPV EMITIDO"] == "Execução/cobrança"
    assert by_name["ARQUIVADO/ENCERRADO"] == "Arquivamento"
    assert by_name["PROCESSO RH PENDENTE"] == "Rh/financeiro"

    # "PLANEJAMENTO" é o único nome repetido na fonte real (docs/ADVBOX-...md §3.2) —
    # aparece em duas fases distintas, daí a unicidade ser por (tenant, fase).
    planejamento_steps = [step for name, step in stages_by_step if name == "PLANEJAMENTO"]
    assert sorted(planejamento_steps) == ["Marketing", "Negociação"]
