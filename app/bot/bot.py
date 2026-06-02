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
from app.handlers.start import router

# Регистрируем роутер в диспетчере
dp.include_router(router)

