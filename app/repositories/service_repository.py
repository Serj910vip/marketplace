from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.service import Service

ACTIVE_BOOKING_STATUSES = ("pending", "confirmed")


class ServiceRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: int, status: str | None = None) -> list[Service]:
        query = select(Service).where(Service.user_id == user_id)
        if status:
            query = query.where(Service.status == status)
        query = query.order_by(Service.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_published_by_user_id(self, user_id: int) -> list[Service]:
        return await self.get_by_user_id(user_id, status="published")

    async def get_by_id(self, service_id: int) -> Service | None:
        result = await self.session.execute(select(Service).where(Service.id == service_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        title: str,
        description: str | None = None,
        photo_url: str | None = None,
        category_id: int | None = None,
        price: Decimal | float | None = None,
        duration_minutes: int | None = None,
        capacity: int = 1,
        booking_format: str | None = None,
        status: str = "draft",
    ) -> Service:
        service = Service(
            user_id=user_id,
            title=title,
            description=description,
            photo_url=photo_url,
            category_id=category_id,
            price=price,
            duration_minutes=duration_minutes,
            training_duration=duration_minutes,
            capacity=capacity,
            booking_format=booking_format,
            status=status,
        )
        self.session.add(service)
        await self.session.commit()
        await self.session.refresh(service)
        return service

    async def update(self, service_id: int, data: dict) -> Service | None:
        service = await self.get_by_id(service_id)
        if not service:
            return None

        for field in (
            "title", "description", "photo_url", "category_id",
            "price", "duration_minutes", "capacity", "booking_format",
        ):
            if field in data:
                setattr(service, field, data[field])
                if field == "duration_minutes":
                    service.training_duration = data[field]

        await self.session.commit()
        await self.session.refresh(service)
        return service

    async def _has_future_active_bookings(self, service_id: int) -> bool:
        from datetime import datetime

        query = select(Booking).where(
            Booking.service_id == service_id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            Booking.starts_at.isnot(None),
            Booking.starts_at >= datetime.utcnow(),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None

    async def set_status(self, service_id: int, status: str) -> Service | None:
        service = await self.get_by_id(service_id)
        if not service:
            return None

        if status == "archived" and await self._has_future_active_bookings(service_id):
            raise ValueError("Нельзя архивировать услугу с будущими активными записями")

        service.status = status
        await self.session.commit()
        await self.session.refresh(service)
        return service

    async def delete(self, service_id: int) -> bool:
        if await self._has_future_active_bookings(service_id):
            raise ValueError("Нельзя удалить услугу с будущими активными записями")

        service = await self.get_by_id(service_id)
        if not service:
            return False
        await self.session.delete(service)
        await self.session.commit()
        return True
