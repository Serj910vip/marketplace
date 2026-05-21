from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(
        self,
        telegram_id: int
    ) -> User | None:

        query = select(User).where(
            User.telegram_id == telegram_id
        )

        result = await self.session.execute(query)

        return result.scalar_one_or_none()

    async def create(
        self,
        telegram_id: int,
        username: str | None
    ) -> User:

        user = User(
            telegram_id=telegram_id,
            username=username
        )

        self.session.add(user)

        await self.session.commit()

        await self.session.refresh(user)

        return user
    
    async def update_role(
        self,
        user: User,
        role: str
    ) -> User:

        user.role = role

        await self.session.commit()

        await self.session.refresh(user)

        return user