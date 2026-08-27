from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.review import Review
from app.models.user import User


class ReviewRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_booking_id(self, booking_id: int) -> Review | None:
        result = await self.session.execute(
            select(Review).where(Review.booking_id == booking_id)
        )
        return result.scalar_one_or_none()

    async def get_by_service_id(self, service_id: int) -> list[Review]:
        query = (
            select(Review)
            .join(Booking, Review.booking_id == Booking.id)
            .where(Booking.service_id == service_id)
            .order_by(Review.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, booking: Booking, rating: int, comment: str | None = None) -> Review:
        review = Review(booking_id=booking.id, rating=rating, comment=comment)
        self.session.add(review)
        await self.session.commit()
        await self.session.refresh(review)

        await self._recalculate_business_rating(booking.owner_id)
        return review

    async def _recalculate_business_rating(self, owner_id: int) -> None:
        query = (
            select(func.avg(Review.rating))
            .join(Booking, Review.booking_id == Booking.id)
            .where(Booking.owner_id == owner_id)
        )
        avg_rating = await self.session.scalar(query)

        owner = await self.session.get(User, owner_id)
        if owner is not None:
            owner.business_rating = round(float(avg_rating or 0.0), 2)
            await self.session.commit()
