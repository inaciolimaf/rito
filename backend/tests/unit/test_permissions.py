import uuid

import pytest

from app.core.permissions import capabilities_for, has_financial_access
from app.domain.users.models import FinancialAccess, User, UserRole
from app.domain.users.service import editable_fields


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


# ---------------------------------------------------------------------------
# Spec 135 — o eixo financeiro como predicado, e a lista de campos por perfil.
# ---------------------------------------------------------------------------


def _usuario(
    *,
    role: UserRole = UserRole.COLABORADOR,
    financial_access: FinancialAccess = FinancialAccess.NONE,
    user_id: uuid.UUID | None = None,
) -> User:
    """Um `User` sem banco: `editable_fields` e `has_financial_access` só olham três
    atributos, e montar tenant/senha só para isso esconderia essa simplicidade."""
    return User(
        id=user_id or uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email=f"{uuid.uuid4()}@example.com",
        password_hash="x",
        name="Fulano",
        role=role,
        financial_access=financial_access,
    )


@pytest.mark.parametrize(
    ("acesso", "minimo", "esperado"),
    [
        (FinancialAccess.NONE, FinancialAccess.READ_ONLY, False),
        (FinancialAccess.NONE, FinancialAccess.FULL, False),
        (FinancialAccess.READ_ONLY, FinancialAccess.READ_ONLY, True),
        (FinancialAccess.READ_ONLY, FinancialAccess.FULL, False),
        (FinancialAccess.FULL, FinancialAccess.READ_ONLY, True),
        (FinancialAccess.FULL, FinancialAccess.FULL, True),
        (FinancialAccess.NONE, FinancialAccess.NONE, True),
    ],
)
def test_has_financial_access_segue_a_mesma_ordem_do_require_financial(
    acesso: FinancialAccess, minimo: FinancialAccess, esperado: bool
) -> None:
    """A tabela inteira, porque a função é o predicado que as BORDAS usam para decidir se
    o campo monetário vem preenchido — e uma inversão aqui não daria erro em lugar nenhum,
    só passaria a mostrar dinheiro para quem não pode ver."""
    assert has_financial_access(_usuario(financial_access=acesso), minimo) is esperado


def test_quem_edita_a_si_mesmo_mexe_em_dado_pessoal_e_so() -> None:
    eu = _usuario(role=UserRole.COLABORADOR)

    campos = editable_fields(eu, eu)

    assert "name" in campos
    assert "cellphone" in campos
    assert "number_oab" in campos
    assert "salary" not in campos
    assert "points_goal" not in campos
    assert "role" not in campos
    assert "admission_date" not in campos


def test_administrador_edita_o_vinculo_do_subordinado_mas_nao_o_salario_sem_full() -> None:
    admin = _usuario(role=UserRole.ADMINISTRADOR, financial_access=FinancialAccess.READ_ONLY)

    campos = editable_fields(admin, _usuario())

    assert {"role", "financial_access", "occupation_id", "admission_date"} <= campos
    assert "salary" not in campos


def test_o_salario_exige_full_e_nunca_e_o_proprio() -> None:
    """As duas metades da mesma regra: o eixo financeiro autoriza mexer no dinheiro do
    escritório, e "RH" é sempre outra pessoa."""
    rh = _usuario(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)

    assert "salary" in editable_fields(rh, _usuario())
    assert "salary" not in editable_fields(rh, rh)


def test_meta_de_pontos_e_do_gestor() -> None:
    """`PUT /users/{id}/points-goal` exige GESTOR (capacidade `goals.manage`); a rota do
    perfil não pode ser a porta dos fundos dela."""
    gestor = _usuario(role=UserRole.GESTOR)
    admin = _usuario(role=UserRole.ADMINISTRADOR, financial_access=FinancialAccess.FULL)

    assert "points_goal" in editable_fields(gestor, _usuario())
    assert "points_goal" not in editable_fields(admin, _usuario())


def test_colaborador_editando_outro_nao_grava_nada() -> None:
    """O router já responde 403 antes de chegar aqui (`_ensure_self_or_administrator`).
    A lista vazia é a rede de baixo: se um dia outra rota chamar o service direto, o
    `setattr` não volta a valer por omissão."""
    assert editable_fields(_usuario(), _usuario()) == frozenset()
