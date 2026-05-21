import asyncio
import asyncpg

async def test_password():
    # Пробуем подключиться с паролем из .env
    try:
        conn = await asyncpg.connect(
            host='localhost',
            port=5432,
            user='postgres',
            password='password',  # Ваш пароль из .env
            database='postgres'
        )
        print("✅ Пароль 'password' ПРАВИЛЬНЫЙ!")
        print("База данных работает с этим паролем")
        await conn.close()
        return True
    except Exception as e:
        print(f"❌ Пароль 'password' НЕПРАВИЛЬНЫЙ!")
        print(f"Ошибка: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_password())