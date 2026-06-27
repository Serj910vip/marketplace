import asyncio

from sqlalchemy import text

from app.database.session import engine


async def add_photos_column():
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'ads' AND column_name = 'photos'
        """))
        if result.scalar():
            print("ℹ️ Колонка photos уже существует")
            return

        await conn.execute(text("""
            ALTER TABLE ads ADD COLUMN photos TEXT
        """))
        print("✅ Колонка photos добавлена в таблицу ads")


if __name__ == "__main__":
    asyncio.run(add_photos_column())
