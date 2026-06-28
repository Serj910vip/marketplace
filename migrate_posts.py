import asyncio

from sqlalchemy import text

from app.database.session import engine


async def migrate_posts():
    async with engine.begin() as conn:
        columns = [
            ("subtitle", "VARCHAR(200)"),
            ("status", "VARCHAR(20) DEFAULT 'published'"),
            ("scheduled_at", "TIMESTAMP"),
            ("published_at", "TIMESTAMP"),
        ]
        for table, col_defs in [("ads", columns), ("users", [
            ("linked_chat_id", "BIGINT"),
            ("linked_chat_title", "VARCHAR(255)"),
            ("linked_chat_type", "VARCHAR(50)"),
        ])]:
            for col_name, col_type in col_defs:
                result = await conn.execute(text(f"""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = '{table}' AND column_name = '{col_name}'
                """))
                if result.scalar():
                    print(f"ℹ️ {table}.{col_name} уже существует")
                    continue
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
                print(f"✅ Добавлена колонка {table}.{col_name}")


if __name__ == "__main__":
    asyncio.run(migrate_posts())
