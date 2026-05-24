# app/main.py (альтернативный запуск, если не через run.py)
import asyncio
import uvicorn
from threading import Thread

from app.bot.bot import dp, bot
from app.handlers.start import router

async def run_bot():
    dp.include_router(router)
    print("🤖 Бот запущен...")
    await dp.start_polling(bot)

def run_api():
    uvicorn.run("app.api.app:app", host="127.0.0.1", port=8000, reload=False)

if __name__ == "__main__":
    Thread(target=run_api, daemon=True).start()
    asyncio.run(run_bot())