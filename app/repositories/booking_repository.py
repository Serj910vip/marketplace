from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking


class BookingRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_owner_id(self, owner_id: int) -> list[Booking]:
        query = (
            select(Booking)
            .where(Booking.owner_id == owner_id)
            .order_by(Booking.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        service_id: int,
        owner_id: int,
        client_name: str,
        booking_day: str,
        booking_time: str,
        client_telegram_id: int | None = None,
        status: str = "pending",
    ) -> Booking:
        booking = Booking(
            service_id=service_id,
            owner_id=owner_id,
            client_name=client_name,
            client_telegram_id=client_telegram_id,
            booking_day=booking_day,
            booking_time=booking_time,
            status=status,
        )
        self.session.add(booking)
        await self.session.commit()
        await self.session.refresh(booking)
        return booking
