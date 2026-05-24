# app/bot/bot.py
from aiogram import Bot, Dispatcher
from app.core.config import settings

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()