import json

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ad import Ad


def photos_from_ad(ad: Ad) -> list[str]:
    if ad.photos:
        try:
            parsed = json.loads(ad.photos)
            if isinstance(parsed, list):
                return [p for p in parsed if p][:3]
        except json.JSONDecodeError:
            pass
    if ad.photo_url:
        return [ad.photo_url]
    return []


def set_ad_photos(ad: Ad, photo_urls: list[str]) -> None:
    cleaned = [url for url in photo_urls if url][:3]
    ad.photos = json.dumps(cleaned, ensure_ascii=False) if cleaned else None
    ad.photo_url = cleaned[0] if cleaned else None


class AdRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: int):
        result = await self.session.execute(
            select(Ad).where(Ad.user_id == user_id).order_by(desc(Ad.created_at))
        )
        return result.scalars().all()

    async def get_by_id(self, ad_id: int):
        result = await self.session.execute(
            select(Ad).where(Ad.id == ad_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        title: str,
        subtitle: str | None = None,
        description: str | None = None,
        photos: list[str] | None = None,
        hidden: bool = False,
        status: str = "published",
        scheduled_at=None,
        published_at=None,
    ):
        ad = Ad(
            user_id=user_id,
            title=title,
            subtitle=subtitle,
            description=description,
            hidden=hidden,
            status=status,
            scheduled_at=scheduled_at,
            published_at=published_at,
        )
        if photos:
            set_ad_photos(ad, photos)

        self.session.add(ad)
        await self.session.commit()
        await self.session.refresh(ad)
        return ad

    async def delete(self, ad_id: int):
        ad = await self.get_by_id(ad_id)
        if ad:
            await self.session.delete(ad)
            await self.session.commit()
            return True
        return False

    async def update(self, ad_id: int, data: dict):
        ad = await self.get_by_id(ad_id)
        if not ad:
            return None

        for field in (
            "title", "subtitle", "description", "hidden",
            "status", "scheduled_at", "published_at",
        ):
            if field in data:
                setattr(ad, field, data[field])

        if "photos" in data:
            set_ad_photos(ad, data["photos"])

        await self.session.commit()
        await self.session.refresh(ad)
        return ad

    async def get_active_by_user_id(self, user_id: int):
        result = await self.session.execute(
            select(Ad)
            .where(
                Ad.user_id == user_id,
                Ad.hidden == False,
                Ad.status == "published",
            )
            .order_by(desc(Ad.created_at))
        )
        return result.scalars().all()

    async def get_due_scheduled(self, now=None) -> list[Ad]:
        from datetime import datetime
        now = now or datetime.utcnow()
        result = await self.session.execute(
            select(Ad).where(
                Ad.status == "scheduled",
                Ad.scheduled_at <= now,
            ).order_by(Ad.scheduled_at)
        )
        return list(result.scalars().all())

    async def mark_published(self, ad: Ad):
        from datetime import datetime
        ad.status = "published"
        ad.hidden = False
        ad.published_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(ad)
        return ad
