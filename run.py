# run.py
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(__file__))


# ФИКС ДЛЯ WINDOWS (ВАЖНО!)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )

from app.bot.bot import dp, bot

async def run_bot():
    print("🤖 Бот запущен...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    
    print("🚀Запуск Telegram бота...")

    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
