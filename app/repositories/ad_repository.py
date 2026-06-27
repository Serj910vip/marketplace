import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.ad import Ad


def photos_from_ad(ad: Ad) -> list[str]:
    if ad.photos:
        try:
            parsed = json.loads(ad.photos)
            if isinstance(parsed, list):
                return [p for p in parsed if p]
        except json.JSONDecodeError:
            pass
    if ad.photo_url:
        return [ad.photo_url]
    return []


def set_ad_photos(ad: Ad, photo_urls: list[str]) -> None:
    cleaned = [url for url in photo_urls if url]
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
        description: str = None,
        photo_url: str = None,
        photos: list[str] | None = None,
        hidden: bool = False,
    ):
        ad = Ad(
            user_id=user_id,
            title=title,
            description=description,
            photo_url=photo_url,
            hidden=hidden,
        )
        if photos:
            set_ad_photos(ad, photos)
        elif photo_url:
            set_ad_photos(ad, [photo_url])

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

        if "title" in data:
            ad.title = data["title"]
        if "description" in data:
            ad.description = data["description"]
        if "hidden" in data:
            ad.hidden = data["hidden"]
        if "photos" in data:
            set_ad_photos(ad, data["photos"])
        elif "photo_url" in data:
            set_ad_photos(ad, [data["photo_url"]] if data["photo_url"] else [])

        await self.session.commit()
        await self.session.refresh(ad)
        return ad

    async def get_active_by_user_id(self, user_id: int):
        result = await self.session.execute(
            select(Ad)
            .where(
                Ad.user_id == user_id,
                Ad.hidden == False,
            )
            .order_by(desc(Ad.created_at))
        )
        return result.scalars().all()
