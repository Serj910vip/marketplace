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
            category: str = None, 
            price: float = None, 
            status: str = "active",
            hidden: bool = False, ):
        ad = Ad(
            user_id=user_id,
            title=title,
            description=description,
            photo_url=photo_url,
            category=category,
            price=price,
            status=status,
             hidden=hidden
        )
        self.session.add(ad)
        await self.session.commit()
        await self.session.refresh(ad)
        return ad
    
    async def update_status(self, ad_id: int, status: str):
        ad = await self.get_by_id(ad_id)
        if ad:
            ad.status = status
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