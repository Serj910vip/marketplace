#bot.py
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.core.config import settings


# Создаём хранилище для состояний (FSM)
storage = MemoryStorage()

# Создаём бота и диспетчер с хранилищем
bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher(storage=storage)

# ========== ПОДКЛЮЧАЕМ ОБРАБОТЧИКИ КОМАНД ==========
# Импортируем роутер из файла с командами
from app.handlers.start import router as start_router
from app.handlers.groups import router as groups_router
from app.handlers.bookings import router as bookings_router

dp.include_router(start_router)
dp.include_router(groups_router)
dp.include_router(bookings_router)

