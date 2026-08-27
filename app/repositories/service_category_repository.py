from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service_category import ServiceCategory


class ServiceCategoryRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: int) -> list[ServiceCategory]:
        query = (
            select(ServiceCategory)
            .where(ServiceCategory.user_id == user_id)
            .order_by(ServiceCategory.sort_order, ServiceCategory.id)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, category_id: int) -> ServiceCategory | None:
        result = await self.session.execute(
            select(ServiceCategory).where(ServiceCategory.id == category_id)
        )
        return result.scalar_one_or_none()

    async def create(self, user_id: int, name: str, sort_order: int = 0) -> ServiceCategory:
        category = ServiceCategory(user_id=user_id, name=name, sort_order=sort_order)
        self.session.add(category)
        await self.session.commit()
        await self.session.refresh(category)
        return category

    async def rename(self, category: ServiceCategory, name: str) -> ServiceCategory:
        category.name = name
        await self.session.commit()
        await self.session.refresh(category)
        return category

    async def delete(self, category_id: int) -> bool:
        category = await self.get_by_id(category_id)
        if not category:
            return False
        await self.session.delete(category)
        await self.session.commit()
        return True
