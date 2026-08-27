# add_services_v2.py
import asyncio

from sqlalchemy import text

from app.database.session import engine


async def _table_exists(conn, table: str) -> bool:
    result = await conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = :table
        )
    """), {"table": table})
    return bool(result.scalar())


async def _create_table_if_missing(conn, table: str, create_sql: str, index_sql: list[str]):
    if await _table_exists(conn, table):
        print(f"ℹ️ Таблица {table} уже существует")
        return
    await conn.execute(text(create_sql))
    for stmt in index_sql:
        await conn.execute(text(stmt))
    print(f"✅ Таблица {table} создана")


async def _add_columns(conn, table: str, col_defs: list[tuple[str, str]]):
    for col_name, col_type in col_defs:
        result = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = :table AND column_name = :col
        """), {"table": table, "col": col_name})
        if result.scalar():
            print(f"ℹ️ {table}.{col_name} уже существует")
            continue
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
        print(f"✅ Добавлена колонка {table}.{col_name}")


async def add_services_v2():
    async with engine.begin() as conn:
        # ---- новые таблицы ----
        await _create_table_if_missing(
            conn,
            "service_categories",
            """
            CREATE TABLE service_categories (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """,
            ["CREATE INDEX idx_service_categories_user_id ON service_categories(user_id)"],
        )

        await _create_table_if_missing(
            conn,
            "availability_rules",
            """
            CREATE TABLE availability_rules (
                id SERIAL PRIMARY KEY,
                service_id INTEGER NOT NULL,
                weekday INTEGER NOT NULL,
                time_start TIME NOT NULL,
                time_end TIME NOT NULL,
                slot_step_minutes INTEGER,
                FOREIGN KEY (service_id) REFERENCES services(id)
            )
            """,
            ["CREATE INDEX idx_availability_rules_service_id ON availability_rules(service_id)"],
        )

        await _create_table_if_missing(
            conn,
            "reviews",
            """
            CREATE TABLE reviews (
                id SERIAL PRIMARY KEY,
                booking_id INTEGER NOT NULL UNIQUE,
                rating INTEGER NOT NULL,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (booking_id) REFERENCES bookings(id)
            )
            """,
            ["CREATE INDEX idx_reviews_booking_id ON reviews(booking_id)"],
        )

        # ---- новые колонки в существующих таблицах ----
        await _add_columns(conn, "services", [
            ("category_id", "INTEGER REFERENCES service_categories(id)"),
            ("duration_minutes", "INTEGER"),
            ("capacity", "INTEGER DEFAULT 1"),
            ("status", "VARCHAR(20) DEFAULT 'published'"),
        ])

        await _add_columns(conn, "bookings", [
            ("client_phone", "VARCHAR(30)"),
            ("starts_at", "TIMESTAMP"),
            ("ends_at", "TIMESTAMP"),
            ("price_at_booking", "NUMERIC(10, 2)"),
            ("cancel_reason", "TEXT"),
            ("reminder_sent_at", "TIMESTAMP"),
        ])

        await _add_columns(conn, "ads", [
            ("service_id", "INTEGER REFERENCES services(id)"),
        ])

        await _add_columns(conn, "users", [
            ("booking_auto_confirm", "BOOLEAN DEFAULT FALSE NOT NULL"),
            ("cancellation_deadline_hours", "INTEGER DEFAULT 2"),
        ])

        # ---- корректировки существующих колонок ----

        # services.price: FLOAT -> NUMERIC(10, 2), чтобы деньги не округлялись float'ом
        result = await conn.execute(text("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'services' AND column_name = 'price'
        """))
        price_type = result.scalar()
        if price_type == "double precision":
            await conn.execute(text(
                "ALTER TABLE services ALTER COLUMN price TYPE NUMERIC(10, 2) USING price::numeric(10, 2)"
            ))
            print("✅ services.price переведён на NUMERIC(10, 2)")
        else:
            print("ℹ️ services.price уже не FLOAT — пропускаю")

        # bookings.booking_day / booking_time: раньше NOT NULL, теперь новые записи создаются
        # через starts_at/ends_at, поэтому старые текстовые поля становятся необязательными
        for col in ("booking_day", "booking_time"):
            result = await conn.execute(text("""
                SELECT is_nullable FROM information_schema.columns
                WHERE table_name = 'bookings' AND column_name = :col
            """), {"col": col})
            is_nullable = result.scalar()
            if is_nullable == "NO":
                await conn.execute(text(f"ALTER TABLE bookings ALTER COLUMN {col} DROP NOT NULL"))
                print(f"✅ bookings.{col} стал nullable")
            else:
                print(f"ℹ️ bookings.{col} уже nullable")


if __name__ == "__main__":
    asyncio.run(add_services_v2())
