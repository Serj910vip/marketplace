# reset_db.py
import asyncio
from app.database.session import engine
from app.database.base import Base
from app.models.user import User
from app.models.service import Service
from app.models.booking import Booking

async def reset_database():
    async with engine.begin() as conn:
        # Удаляем все таблицы
        await conn.run_sync(Base.metadata.drop_all)
        print("✅ Старые таблицы удалены")
        
        # Создаем заново
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Новые таблицы созданы")

if __name__ == "__main__":
    asyncio.run(reset_database())