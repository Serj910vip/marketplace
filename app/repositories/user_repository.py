from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.user import User


class UserRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        query = select(User).where(User.telegram_id == telegram_id)
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
            market_created_at=datetime.utcnow(),
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_role(self, user: User, role: str) -> User:
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

    async def update_business(
        self,
        user: User,
        *,
        market_name: str | None = None,
        business_photo_url: str | None = None,
    ) -> User:
        if market_name is not None:
            user.market_name = market_name
        if business_photo_url is not None:
            user.business_photo_url = business_photo_url

        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def link_chat(
        self,
        user: User,
        *,
        chat_id: int,
        chat_title: str,
        chat_type: str,
    ) -> User:
        user.linked_chat_id = chat_id
        user.linked_chat_title = chat_title
        user.linked_chat_type = chat_type
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def unlink_chat(self, user: User) -> User:
        user.linked_chat_id = None
        user.linked_chat_title = None
        user.linked_chat_type = None
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_booking_settings(
        self,
        user: User,
        *,
        booking_auto_confirm: bool | None = None,
        cancellation_deadline_hours: int | None = ...,
    ) -> User:
        if booking_auto_confirm is not None:
            user.booking_auto_confirm = booking_auto_confirm
        if cancellation_deadline_hours is not ...:
            user.cancellation_deadline_hours = cancellation_deadline_hours

        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_client_base(self, owner_id: int) -> list[dict]:
        """Клиентская база бизнеса, агрегированная по истории записей (без отдельной CRM-таблицы)."""
        query = (
            select(Booking)
            .where(Booking.owner_id == owner_id, Booking.client_telegram_id.isnot(None))
            .order_by(Booking.created_at.desc())
        )
        result = await self.session.execute(query)
        bookings = list(result.scalars().all())

        clients: dict[int, dict] = {}
        for booking in bookings:
            client = clients.setdefault(booking.client_telegram_id, {
                "client_telegram_id": booking.client_telegram_id,
                "client_name": booking.client_name,
                "client_phone": booking.client_phone,
                "visits_count": 0,
                "last_visit_at": booking.starts_at or booking.created_at,
            })
            client["visits_count"] += 1

        return sorted(clients.values(), key=lambda c: c["last_visit_at"] or datetime.min, reverse=True)
