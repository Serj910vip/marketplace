# add_ads_table.py
import asyncio
from sqlalchemy import text
from app.database.session import engine

async def add_ads_table():
    async with engine.begin() as conn:
        # Проверяем, существует ли таблица ads
        result = await conn.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='ads'
        """))
        
        if result.fetchone():
            print("ℹ️ Таблица ads уже существует")
            return
        
        # Создаем таблицу ads
        await conn.execute(text("""
            CREATE TABLE ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                photo_url VARCHAR(500),
                category VARCHAR(100),
                price FLOAT,
                status VARCHAR(20) DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """))
        
        # Создаем индексы
        await conn.execute(text("""
            CREATE INDEX idx_ads_user_id ON ads(user_id)
        """))
        await conn.execute(text("""
            CREATE INDEX idx_ads_status ON ads(status)
        """))
        
        print("✅ Таблица ads создана без потери данных!")

if __name__ == "__main__":
    asyncio.run(add_ads_table())