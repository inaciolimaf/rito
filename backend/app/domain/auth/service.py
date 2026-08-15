import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.rate_limit import check_and_increment
from app.core.security import hash_password, validate_password_policy, verify_password
from app.core.tokens import create_access_token, generate_refresh_token, hash_token
from app.domain.account.repository import AccountRepository
from app.domain.auth.exceptions import (
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidResetTokenError,
    RateLimitExceededError,
    WeakPasswordError,
)
from app.domain.auth.models import PasswordResetToken, RefreshToken
from app.domain.auth.repository import PasswordResetTokenRepository, RefreshTokenRepository
from app.domain.reports.models import AccessLog
from app.domain.users.repository import UserRepository

logger = logging.getLogger(__name__)

# Configurável por ambiente (spec 036): o e2e faz 6+ logins no mesmo minuto — com o
# limite de produção a 6ª jornada tomava 429. Produção segue 5/60s.
_LOGIN_RATE_LIMIT = int(os.environ.get("LOGIN_RATE_LIMIT", "5"))
_LOGIN_RATE_WINDOW_SECONDS = int(os.environ.get("LOGIN_RATE_WINDOW_SECONDS", "60"))


class AuthService:
    def __init__(self, session: AsyncSession, redis: Redis, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.redis = redis
        self.tenant_id = tenant_id
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.password_resets = PasswordResetTokenRepository(session)
        self.accounts = AccountRepository(session)

    async def login(
        self, email: str, password: str, client_ip: str, user_agent: str | None = None
    ) -> tuple[str, str, int]:
        allowed = await check_and_increment(
            self.redis,
            f"login_attempts:{email}:{client_ip}",
            limit=_LOGIN_RATE_LIMIT,
            window_seconds=_LOGIN_RATE_WINDOW_SECONDS,
        )
        if not allowed:
            raise RateLimitExceededError

        user = await self.users.get_by_email(email)
        if (
            user is None
            or user.password_hash is None
            or not verify_password(password, user.password_hash)
            or not user.is_active
        ):
            raise InvalidCredentialsError

        user.last_login_at = datetime.now(UTC)

        # Spec 073, regra 1/3: só grava se o rastreamento estiver ligado; refresh
        # nunca passa por aqui — só um login bem-sucedido registra.
        account = await self.accounts.get_current()
        if account is not None and account.track_access_logs:
            self.session.add(
                AccessLog(
                    tenant_id=self.tenant_id,
                    user_id=user.id,
                    ip_address=client_ip if client_ip != "unknown" else None,
                    user_agent=user_agent,
                )
            )

        return await self._issue_tokens(user_id=user.id, family_id=uuid.uuid4())

    async def refresh(self, raw_refresh_token: str) -> tuple[str, str, int]:
        stored = await self.refresh_tokens.get_by_token_hash(hash_token(raw_refresh_token))
        if stored is None:
            raise InvalidRefreshTokenError

        if stored.revoked_at is not None:
            # Reuso de token já revogado: alguém mais tem esse token. Derruba a família
            # inteira e commita na hora — a rota vai propagar um 401 depois, e a sessão
            # de `get_session` faz ROLLBACK em qualquer exceção, o que apagaria esta
            # revogação se não commitássemos explicitamente antes.
            await self.refresh_tokens.revoke_family(stored.family_id)
            await self.session.commit()
            raise InvalidRefreshTokenError

        if stored.expires_at < datetime.now(UTC):
            raise InvalidRefreshTokenError

        self.refresh_tokens.revoke(stored)
        return await self._issue_tokens(user_id=stored.user_id, family_id=stored.family_id)

    async def logout(self, raw_refresh_token: str) -> None:
        stored = await self.refresh_tokens.get_by_token_hash(hash_token(raw_refresh_token))
        if stored is not None and stored.revoked_at is None:
            self.refresh_tokens.revoke(stored)

    async def forgot_password(self, email: str) -> str | None:
        """Devolve o token bruto (para envio por e-mail) ou None se não achou usuário.

        O envio real por e-mail fica para a spec de notificações — ver Descobertas
        da 004. O router nunca repassa esse retorno na resposta HTTP (sempre 202
        sem corpo), senão a rota vira um oráculo de "esse e-mail existe".
        """
        user = await self.users.get_by_email(email)
        if user is None or not user.is_active:
            return None

        raw_token, token_hash = generate_refresh_token()
        await self.password_resets.create(
            PasswordResetToken(
                tenant_id=self.tenant_id,
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        # Nunca logar o token bruto nem o hash — só o fato de ter sido gerado.
        logger.info("Token de recuperação de senha gerado", extra={"user_id": str(user.id)})
        return raw_token

    async def reset_password(self, raw_token: str, new_password: str) -> None:
        errors = validate_password_policy(new_password)
        if errors:
            raise WeakPasswordError(errors)

        stored = await self.password_resets.get_by_token_hash(hash_token(raw_token))
        if stored is None or stored.used_at is not None or stored.expires_at < datetime.now(UTC):
            raise InvalidResetTokenError

        user = await self.users.get_by_id(stored.user_id)
        if user is None:
            raise InvalidResetTokenError

        user.password_hash = hash_password(new_password)
        self.password_resets.mark_used(stored)

    async def _issue_tokens(
        self, *, user_id: uuid.UUID, family_id: uuid.UUID
    ) -> tuple[str, str, int]:
        settings = get_settings()
        raw_refresh, token_hash = generate_refresh_token()
        await self.refresh_tokens.create(
            RefreshToken(
                tenant_id=self.tenant_id,
                user_id=user_id,
                token_hash=token_hash,
                family_id=family_id,
                expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
            )
        )
        access_token = create_access_token(user_id=user_id, tenant_id=self.tenant_id)
        return access_token, raw_refresh, settings.access_token_ttl_minutes * 60
