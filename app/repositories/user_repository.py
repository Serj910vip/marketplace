from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from datetime import datetime

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
        username: str | None,
        market_name: str | None = None, 
    ) -> User:

        user = User(
            telegram_id=telegram_id,
            username=username,
            market_name=market_name,
            market_created_at=datetime.utcnow()
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

    async def update_profile(
        self,
        user: User,
        *,
        profile_type: str,
        country: str | None = None,
        region: str | None = None,
        city: str | None = None,
    ) -> User:
        if profile_type == "business":
            if country is not None:
                user.business_country = country
            if region is not None:
                user.business_region = region
            if city is not None:
                user.business_city = city
        elif profile_type == "personal":
            if country is not None:
                user.personal_country = country
            if region is not None:
                user.personal_region = region
            if city is not None:
                user.personal_city = city

        await self.session.commit()
        await self.session.refresh(user)

        return user