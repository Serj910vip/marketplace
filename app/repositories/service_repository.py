from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service import Service


class ServiceRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: int) -> list[Service]:
        query = (
            select(Service)
            .where(Service.user_id == user_id)
            .order_by(Service.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        user_id: int,
        title: str,
        description: str | None = None,
        price: float | None = None,
    ) -> Service:
        service = Service(
            user_id=user_id,
            title=title,
            description=description,
            price=price,
        )
        self.session.add(service)
        await self.session.commit()
        await self.session.refresh(service)
        return service
