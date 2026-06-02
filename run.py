import sys
import os
import asyncio
import uvicorn
from threading import Thread

sys.path.insert(0, os.path.dirname(__file__))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.bot.bot import dp, bot

async def run_bot():
    print("🤖 Бот запущен...")
    await dp.start_polling(bot, skip_updates=True)

def run_api():
    uvicorn.run(
        "app.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False
    )

if __name__ == "__main__":
    api_thread = Thread(target=run_api, daemon=True)
    api_thread.start()

    print("🌐 API сервер запущен на http://127.0.0.1:8000")

    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
