from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.models.ad import Ad

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
            hidden: bool = False, ):
        ad = Ad(
            user_id=user_id,
            title=title,
            description=description,
            photo_url=photo_url,
            hidden=hidden
        )
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
        
        # Обновляем поля
        if "title" in data:
            ad.title = data["title"]
        if "description" in data:
            ad.description = data["description"]
        if "photo_url" in data:
            ad.photo_url = data["photo_url"]
        if "hidden" in data:
            ad.hidden = data["hidden"]
        
        await self.session.commit()
        await self.session.refresh(ad)
        return ad
    
    async def get_active_by_user_id(self, user_id: int):
        result = await self.session.execute(
            select(Ad)
            .where(
                Ad.user_id == user_id,
                Ad.hidden == False
            )
            .order_by(desc(Ad.created_at))
        )
        return result.scalars().all()