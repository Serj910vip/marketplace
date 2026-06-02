# app/main.py
import asyncio
import sys
import uvicorn
from threading import Thread

# КРИТИЧЕСКИ ВАЖНО ДЛЯ WINDOWS - исправляет проблему с таймаутами
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.bot.bot import dp, bot
from app.handlers.start import router

async def run_bot():
    """Запуск Telegram бота"""
    dp.include_router(router)
    print("🤖 Бот запущен...")
    # Добавляем skip_updates для игнорирования старых обновлений
    await dp.start_polling(bot, skip_updates=True)

def run_api():
    """Запуск FastAPI сервера (опционально)"""
    # Для Windows лучше использовать 127.0.0.1, а не 0.0.0.0
    uvicorn.run(
        "app.api.app:app", 
        host="127.0.0.1", 
        port=8000, 
        reload=False,
        log_level="warning"  # Меньше логов
    )

if __name__ == "__main__":
    print("🚀 Запуск приложения...")
    
    # Запускаем API в отдельном потоке (если нужен)
    # Если API не нужен для локальной разработки, закомментируйте эти строки
    # api_thread = Thread(target=run_api, daemon=True)
    # api_thread.start()
    # print("🌐 API сервер запущен на http://127.0.0.1:8000")
    
    # Запускаем бота
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")