from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.service import Service
from app.models.user import User

CANCELLED_BOOKING_STATUSES = ("cancelled_by_client", "cancelled_by_owner", "no_show")


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

        service_ids = {b.service_id for b in bookings}
        service_titles: dict[int, str] = {}
        if service_ids:
            svc_result = await self.session.execute(
                select(Service).where(Service.id.in_(service_ids))
            )
            service_titles = {s.id: s.title for s in svc_result.scalars().all()}

        clients: dict[int, dict] = {}
        service_counts: dict[int, dict[int, int]] = {}

        for booking in bookings:
            cid = booking.client_telegram_id
            client = clients.setdefault(cid, {
                "client_telegram_id": cid,
                "client_name": booking.client_name,
                "client_phone": booking.client_phone,
                "visits_count": 0,
                "completed_count": 0,
                "cancelled_count": 0,
                "total_spent": 0.0,
                "last_visit_at": booking.starts_at or booking.created_at,
                "last_service_title": service_titles.get(booking.service_id, "Услуга"),
            })
            client["visits_count"] += 1
            if booking.status == "completed":
                client["completed_count"] += 1
                if booking.price_at_booking:
                    client["total_spent"] += float(booking.price_at_booking)
            elif booking.status in CANCELLED_BOOKING_STATUSES:
                client["cancelled_count"] += 1

            counts = service_counts.setdefault(cid, {})
            counts[booking.service_id] = counts.get(booking.service_id, 0) + 1

        for cid, client in clients.items():
            counts = service_counts.get(cid, {})
            favorite_id = max(counts, key=counts.get) if counts else None
            client["favorite_service_title"] = service_titles.get(favorite_id) if favorite_id else None

        return sorted(clients.values(), key=lambda c: c["last_visit_at"] or datetime.min, reverse=True)
