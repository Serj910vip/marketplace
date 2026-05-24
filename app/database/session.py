# app/database/session.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class async_session:
    async def __aenter__(self):
        self.session = AsyncSessionLocal()
        return self.session
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()