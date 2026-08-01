import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.core.repository import BaseRepository
from app.domain.auth.models import PasswordResetToken, RefreshToken


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.scalars(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.first()

    def revoke(self, token: RefreshToken) -> None:
        token.revoked_at = datetime.now(UTC)

    async def revoke_family(self, family_id: uuid.UUID) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )


class PasswordResetTokenRepository(BaseRepository[PasswordResetToken]):
    model = PasswordResetToken

    async def get_by_token_hash(self, token_hash: str) -> PasswordResetToken | None:
        result = await self.session.scalars(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )
        return result.first()

    def mark_used(self, token: PasswordResetToken) -> None:
        token.used_at = datetime.now(UTC)
