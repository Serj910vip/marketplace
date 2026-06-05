import json

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
        photo_url: str | None = None,
        category: str | None = None,
        price: float | None = None,
        training_duration: int | None = None,
        booking_format: str | None = None,
        working_schedule: dict | None = None,
    ) -> Service:
        service = Service(
            user_id=user_id,
            title=title,
            description=description,
            photo_url=photo_url,
            category=category,
            price=price,
            training_duration=training_duration,
            booking_format=booking_format,
            working_schedule=json.dumps(working_schedule or {}, ensure_ascii=False),
        )
        self.session.add(service)
        await self.session.commit()
        await self.session.refresh(service)
        return service
