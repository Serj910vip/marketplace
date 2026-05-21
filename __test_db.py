import asyncio
import asyncpg

async def find_password():
    # Список самых частых паролей
    common_passwords = [
        'postgres',
        'password',  # уже пробовали
        'root',
        'admin',
        '123456',
        '123',
        '12345',
        'qwerty',
        'postgresql',
        'Pg123',
        'password123',
        '',  # пустой пароль
        ' ',
        '12345678',
        '123456789',
    ]
    
    print("🔍 Ищем правильный пароль...\n")
    
    for pwd in common_passwords:
        try:
            display_pwd = f"'{pwd}'" if pwd else "(пустой)"
            print(f"Пробуем пароль: {display_pwd}...", end=' ')
            
            conn = await asyncpg.connect(
                host='localhost',
                port=5432,
                user='postgres',
                password=pwd,
                database='postgres',
                timeout=3  # таймаут 3 секунды
            )
            
            print("✅ ПОДОШЕЛ!")
            print(f"\n🎉 Ваш правильный пароль: '{pwd}'")
            print(f"Используйте его в .env файле: DATABASE_URL=postgresql+asyncpg://postgres:{pwd}@localhost:5432/marketplace")
            
            # Проверяем наличие базы данных
            db_exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = 'marketplace'"
            )
            
            if not db_exists:
                print("\n⚠️ База данных 'marketplace' не существует. Создаю...")
                await conn.execute('CREATE DATABASE marketplace')
                print("✅ База данных 'marketplace' создана!")
            else:
                print("✅ База данных 'marketplace' существует!")
            
            await conn.close()
            return pwd
            
        except Exception as e:
            print(f"❌")
            continue
    
    print("\n❌ Ни один из стандартных паролей не подошел!")
    print("Вам нужно сбросить пароль PostgreSQL (см. инструкцию ниже)")
    return None

if __name__ == "__main__":
    asyncio.run(find_password())