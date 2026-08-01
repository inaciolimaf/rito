from sqlalchemy import select

from app.core.repository import BaseRepository
from app.domain.users.models import User


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.scalars(select(User).where(User.email == email))
        return result.first()
