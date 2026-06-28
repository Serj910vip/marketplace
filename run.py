import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.bot.bot import dp, bot
from app.services.post_scheduler import scheduler_loop


async def run_bot():
    print("🤖 Бот запущен...")
    asyncio.create_task(scheduler_loop())
    await dp.start_polling(
        bot,
        skip_updates=True,
        allowed_updates=["message", "my_chat_member"],
    )


if __name__ == "__main__":
    print("🚀 Запуск Telegram бота...")
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
