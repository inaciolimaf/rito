import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.image_processing import extension_for, process_image
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
from app.domain.users.models import User, UserInvitation, UserRole
from app.domain.users.repository import (
    OccupationRepository,
    UserInvitationRepository,
    UserRepository,
)
from app.domain.users.schemas import AcceptInvitationRequest, InviteUserRequest, UserUpdateRequest
from app.integrations.storage.base import FileStorage

_INVITATION_TTL_DAYS = 7


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

        for field, value in payload.model_dump().items():
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
