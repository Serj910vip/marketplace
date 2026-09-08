from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.user import User

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"confirmed", "cancelled_by_owner", "cancelled_by_client"},
    "confirmed": {"completed", "cancelled_by_owner", "cancelled_by_client", "no_show"},
    "completed": set(),
    "cancelled_by_owner": set(),
    "cancelled_by_client": set(),
    "no_show": set(),
}


class BookingRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_owner_id(
        self, owner_id: int, status: str | None = None
    ) -> list[Booking]:
        query = select(Booking).where(Booking.owner_id == owner_id)
        if status:
            query = query.where(Booking.status == status)
        query = query.order_by(Booking.starts_at.desc().nullslast(), Booking.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_owner_and_client(
        self, owner_id: int, client_telegram_id: int
    ) -> list[Booking]:
        query = (
            select(Booking)
            .where(Booking.owner_id == owner_id, Booking.client_telegram_id == client_telegram_id)
            .order_by(Booking.starts_at.desc().nullslast(), Booking.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, booking_id: int) -> Booking | None:
        result = await self.session.execute(select(Booking).where(Booking.id == booking_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        service_id: int,
        owner_id: int,
        client_name: str,
        starts_at: datetime,
        ends_at: datetime,
        price_at_booking: Decimal | float | None = None,
        client_phone: str | None = None,
        client_telegram_id: int | None = None,
        status: str = "pending",
    ) -> Booking:
        booking = Booking(
            service_id=service_id,
            owner_id=owner_id,
            client_name=client_name,
            client_phone=client_phone,
            client_telegram_id=client_telegram_id,
            starts_at=starts_at,
            ends_at=ends_at,
            price_at_booking=price_at_booking,
            status=status,
        )
        self.session.add(booking)
        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    async def update_status(
        self, booking_id: int, new_status: str, cancel_reason: str | None = None
    ) -> Booking:
        booking = await self.get_by_id(booking_id)
        if not booking:
            raise ValueError("Запись не найдена")

        allowed = ALLOWED_TRANSITIONS.get(booking.status, set())
        if new_status not in allowed:
            raise ValueError(f"Недопустимый переход статуса: {booking.status} -> {new_status}")

        booking.status = new_status
        if cancel_reason:
            booking.cancel_reason = cancel_reason

        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    async def client_can_cancel(self, booking: Booking, owner: User) -> bool:
        if booking.status not in ("pending", "confirmed"):
            return False
        if owner.cancellation_deadline_hours is None:
            return False
        if not booking.starts_at:
            return False
        deadline = booking.starts_at - timedelta(hours=owner.cancellation_deadline_hours)
        return datetime.utcnow() <= deadline

    async def get_due_reminders(self, minutes_before: int = 60) -> list[Booking]:
        now = datetime.utcnow()
        query = select(Booking).where(
            Booking.status == "confirmed",
            Booking.reminder_sent_at.is_(None),
            Booking.starts_at.isnot(None),
            Booking.starts_at <= now + timedelta(minutes=minutes_before),
            Booking.starts_at > now,
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def mark_reminder_sent(self, booking: Booking) -> None:
        booking.reminder_sent_at = datetime.utcnow()
        await self.session.commit()

    async def get_past_due_confirmed(self) -> list[Booking]:
        now = datetime.utcnow()
        query = select(Booking).where(
            Booking.status == "confirmed",
            Booking.ends_at.isnot(None),
            Booking.ends_at <= now,
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
