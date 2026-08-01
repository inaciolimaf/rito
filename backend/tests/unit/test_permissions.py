from app.core.permissions import capabilities_for
from app.domain.users.models import FinancialAccess, UserRole


def test_gestor_has_settings_and_catalog_capabilities() -> None:
    caps = capabilities_for(UserRole.GESTOR, FinancialAccess.NONE)
    assert "settings.manage" in caps
    assert "tasks.catalog.edit" in caps


def test_colaborador_lacks_gestor_only_capabilities() -> None:
    caps = capabilities_for(UserRole.COLABORADOR, FinancialAccess.NONE)
    assert "settings.manage" not in caps
    assert "tasks.catalog.edit" not in caps


def test_financial_capabilities_are_orthogonal_to_role() -> None:
    """Colaborador com FULL tem capacidade financeira mesmo sem ser Gestor (regra 2)."""
    caps = capabilities_for(UserRole.COLABORADOR, FinancialAccess.FULL)
    assert "financial.write" in caps
    assert "financial.read" in caps


def test_gestor_with_no_financial_access_lacks_financial_capabilities() -> None:
    caps = capabilities_for(UserRole.GESTOR, FinancialAccess.NONE)
    assert "financial.read" not in caps
    assert "financial.write" not in caps


def test_role_hierarchy_is_cumulative() -> None:
    """GESTOR > ADMINISTRADOR > COLABORADOR: cada um inclui as capacidades do de baixo."""
    colaborador_caps = set(capabilities_for(UserRole.COLABORADOR, FinancialAccess.NONE))
    admin_caps = set(capabilities_for(UserRole.ADMINISTRADOR, FinancialAccess.NONE))
    gestor_caps = set(capabilities_for(UserRole.GESTOR, FinancialAccess.NONE))

    assert colaborador_caps <= admin_caps
    assert admin_caps <= gestor_caps


def test_capabilities_for_read_only_do_not_include_write() -> None:
    caps = capabilities_for(UserRole.COLABORADOR, FinancialAccess.READ_ONLY)
    assert "financial.read" in caps
    assert "financial.write" not in caps
