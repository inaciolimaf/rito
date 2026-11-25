import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.image_processing import extension_for, process_image
from app.core.permissions import FinancialAccess, has_financial_access
from app.core.repository import decode_cursor, encode_cursor
from app.core.security import hash_password, validate_password_policy
from app.core.tokens import generate_refresh_token, hash_token
from app.domain.auth.exceptions import WeakPasswordError
from app.domain.users.exceptions import (
    CannotChangeOwnRoleError,
    EmailAlreadyRegisteredError,
    InvalidInvitationError,
    LastActiveGestorError,
    OabRequiredError,
)
from app.domain.users.models import Occupation, User, UserInvitation, UserRole
from app.domain.users.repository import (
    OccupationRepository,
    UserInvitationRepository,
    UserRepository,
)
from app.domain.users.schemas import AcceptInvitationRequest, InviteUserRequest, UserUpdateRequest
from app.integrations.storage.base import FileStorage

_INVITATION_TTL_DAYS = 7

# ---------------------------------------------------------------------------
# Quem pode gravar O QUÊ em `PUT /users/{id}` (spec 135, regra 1).
#
# Até aqui o `update` fazia `setattr` sobre TUDO que viesse no corpo, com uma única
# exceção (`role`/`financial_access` para si mesmo). O corpo carrega `salary` — campo cuja
# LEITURA já exige acesso financeiro — e `points_goal`, que tem endpoint próprio exigindo
# GESTOR: um Colaborador reescrevia o próprio salário e a própria meta pela rota do perfil.
# É a classe "outra rota chega ao mesmo estado, driblando a guarda mais estrita", e não há
# como um teste de cobertura de permissão vê-la: as duas rotas declaram permissão.
#
# A lista é explícita e por perfil, e a pergunta que ela responde é sempre a mesma: quem
# edita a si mesmo não é quem edita um subordinado, e nenhum dos dois é o RH.
# ---------------------------------------------------------------------------

# Dado pessoal. É a pessoa quem sabe o telefone e o número da própria OAB.
_SELF_EDITABLE = frozenset(
    {
        "name",
        "identification",
        "document",
        "birthdate",
        "number_ctps",
        "number_oab",
        "cellphone",
        "phone",
    }
)

# Dado de vínculo: cargo, jornada, datas de admissão/desligamento, perfil de acesso e as
# preferências de relatório. Só ADMINISTRADOR+ grava, e nunca em si mesmo — mudar a própria
# jornada ou o próprio cargo é o mesmo problema de mudar o próprio `role`.
_MANAGED_EDITABLE = frozenset(
    {
        "role",
        "financial_access",
        "occupation_id",
        "admission_date",
        "resignation_date",
        "work_start",
        "work_interval",
        "work_end",
        "report_deadline",
        "report_deleted",
        "is_responsible",
    }
)

# RH. Salário é dinheiro: se a LEITURA exige o eixo financeiro (regra 10 da spec 012), a
# ESCRITA exige FULL — READ_ONLY que grava não é READ_ONLY. E ninguém grava o próprio.
_PAYROLL_EDITABLE = frozenset({"salary"})

# Meta de pontos: tem rota própria em `PUT /users/{id}/points-goal`, com `require_role(GESTOR)`
# e a capacidade `goals.manage`. A rota do perfil não pode ser a porta dos fundos dela.
_GOALS_EDITABLE = frozenset({"points_goal"})

_ADMIN_OR_ABOVE = frozenset({UserRole.ADMINISTRADOR, UserRole.GESTOR})


def editable_fields(actor: User, target: User) -> frozenset[str]:
    """Os campos que `actor` pode gravar em `target`. Nada fora daqui é aplicado."""
    if actor.id == target.id:
        campos = _SELF_EDITABLE
    elif actor.role in _ADMIN_OR_ABOVE:
        campos = _SELF_EDITABLE | _MANAGED_EDITABLE
        if has_financial_access(actor, FinancialAccess.FULL):
            campos |= _PAYROLL_EDITABLE
    else:  # o router já barrou com 403; a lista vazia é a rede de baixo
        campos = frozenset()
    if actor.role == UserRole.GESTOR:
        campos |= _GOALS_EDITABLE
    return campos


class OccupationService:
    """Tabela de referência de profissões. Global, sem `tenant_id` — existe para o
    router não falar com o repositório (spec 118, checagem 2)."""

    def __init__(self, session: AsyncSession) -> None:
        self.occupations = OccupationRepository(session)

    async def list_all(self) -> Sequence[Occupation]:
        return await self.occupations.list_all()


class UserService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.users = UserRepository(session)
        self.invitations = UserInvitationRepository(session)
        self.occupations = OccupationRepository(session)

    async def list_users(
        self,
        *,
        role: UserRole | None,
        is_active: bool | None,
        query: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[Sequence[User], str | None, int]:
        decoded_cursor = decode_cursor(cursor) if cursor else None
        items, total = await self.users.list_filtered(
            role=role, is_active=is_active, query=query, cursor=decoded_cursor, limit=limit
        )
        next_cursor = encode_cursor(items[-1].name, items[-1].id) if len(items) == limit else None
        return items, next_cursor, total

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.users.get_by_id(user_id)

    async def list_mentionable(self, *, query: str | None) -> Sequence[User]:
        """Autocomplete de @menção (spec 035): ativos do tenant, até 10, por nome."""
        items, _total = await self.users.list_filtered(
            is_active=True, query=query, cursor=None, limit=10
        )
        return items

    async def update(self, *, actor: User, target: User, payload: UserUpdateRequest) -> User:
        # Regra 9: usuário edita o próprio perfil, mas não o próprio role/financial_access.
        is_self = actor.id == target.id
        if is_self and (
            payload.role != target.role or payload.financial_access != target.financial_access
        ):
            raise CannotChangeOwnRoleError

        if payload.occupation_id is not None:
            occupation = await self.occupations.get_by_occupation_id(payload.occupation_id)
            # Regra 4: OAB obrigatória se o cargo for de advogado.
            if (
                occupation is not None
                and occupation.name.startswith("Advogado")
                and not payload.number_oab
            ):
                raise OabRequiredError("OAB é obrigatória para o cargo selecionado.")

        # Regra 1 (spec 135): grava só o que este ator pode gravar neste alvo. O que ele
        # não pode fica como está — silenciosamente, e não com 403, porque o corpo do PUT
        # é o objeto INTEIRO: o formulário devolve `salary` e `points_goal` que ele acabou
        # de receber, e recusar a requisição por causa deles quebraria a edição de nome.
        # A resposta é montada a partir do estado real, então quem tentou vê que não mudou.
        permitidos = editable_fields(actor, target)
        for field, value in payload.model_dump().items():
            if field in permitidos:
                setattr(target, field, value)
        return target

    async def deactivate(self, target: User) -> User:
        # Regra 8: não é possível inativar o último GESTOR ativo do tenant.
        if target.role == UserRole.GESTOR:
            remaining = await self.users.count_active_gestores(excluding=target.id)
            if remaining == 0:
                raise LastActiveGestorError
        target.is_active = False
        return target

    async def upload_avatar(
        self, target: User, content: bytes, content_type: str, storage: FileStorage
    ) -> User:
        processed = process_image(content, content_type)
        key = f"avatars/{self.tenant_id}/{target.id}/{uuid.uuid4()}.{extension_for(content_type)}"
        await storage.upload(key=key, content=processed, content_type=content_type)

        target.avatar_key = key
        target.updated_at = datetime.now(UTC)
        return target

    async def invite(
        self, *, actor: User, payload: InviteUserRequest
    ) -> tuple[UserInvitation, str]:
        # Regra 3: e-mail já cadastrado no tenant -> 409.
        existing_user = await self.users.get_by_email(payload.email)
        if existing_user is not None:
            raise EmailAlreadyRegisteredError

        # Regra 1: reenviar invalida o anterior.
        pending = await self.invitations.get_pending_by_email(payload.email)
        if pending is not None:
            await self.invitations.delete(pending)
            await self.session.flush()

        raw_token, token_hash = generate_refresh_token()
        invitation = UserInvitation(
            tenant_id=self.tenant_id,
            email=payload.email,
            role=payload.role,
            financial_access=payload.financial_access,
            occupation_id=payload.occupation_id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=_INVITATION_TTL_DAYS),
            invited_by=actor.id,
        )
        await self.invitations.create(invitation)
        return invitation, raw_token

    async def accept_invitation(self, payload: AcceptInvitationRequest) -> User:
        stored = await self.invitations.get_by_token_hash(hash_token(payload.token))
        if (
            stored is None
            or stored.accepted_at is not None
            or stored.expires_at < datetime.now(UTC)
        ):
            raise InvalidInvitationError

        errors = validate_password_policy(payload.password)
        if errors:
            raise WeakPasswordError(errors)

        user = User(
            tenant_id=stored.tenant_id,
            email=stored.email,
            name=payload.name,
            password_hash=hash_password(payload.password),
            role=stored.role,
            financial_access=stored.financial_access,
            occupation_id=stored.occupation_id,
            is_active=True,
        )
        await self.users.create(user)
        stored.accepted_at = datetime.now(UTC)
        return user
