from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.fsm.context import FSMContext

from app.bot.states.market import MarketCreation
from app.database.session import async_session
from app.repositories.user_repository import UserRepository
from datetime import datetime

router = Router()

# URL твоего мини-аппа (замени на свой)
MINI_APP_URL = "https://marketplace--sergeyvip911.replit.app/"


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id

    async with async_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(user_id)

        if user and user.market_name:
            # Уже есть бизнес
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="🏪 Открыть панель управления",
                        web_app=WebAppInfo(url=MINI_APP_URL),
                    )],
                ]
            )
            await message.answer(
                f"🏢 С возвращением! Ваш бизнес **{user.market_name}** активен.",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        else:
            # НОВЫЙ ПОЛЬЗОВАТЕЛЬ - ПОКАЗЫВАЕМ КНОПКУ
            keyboard = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📝 Создать маркет")]],
                resize_keyboard=True,
            )
            await message.answer(
                f"👋 Добро пожаловать!\n\n"
                f"✨ **Возможности вашего маркетплейса:**\n"
                f"• 🛍️ Создание товаров и услуг\n"
                f"• 💳 Приём платежей\n"
                f"• 📊 Аналитика продаж\n\n"
                f"Нажмите на кнопку **«📝 Создать маркет»**, чтобы начать:",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )


# Обработчик кнопки "📝 Создать маркет"
@router.message(F.text == "📝 Создать маркет")
async def create_market_btn_handler(message: Message, state: FSMContext):
    """Обработчик кнопки 'Создать маркет'"""
    await message.answer(
        "✨ **Отлично!**\n\n"
        "Введите **название вашего бизнеса**:\n"
        "Например: «Парикмахерская Наталья» или «Кофе с собой»",
        parse_mode="Markdown"
    )
    await state.set_state(MarketCreation.waiting_for_market_name)


@router.message(MarketCreation.waiting_for_market_name)
async def process_market_name(message: Message, state: FSMContext):
    market_name = message.text.strip()

    # Валидация
    if len(market_name) < 3:
        await message.answer(
            "❌ Название слишком короткое (минимум 3 символа). Попробуйте еще раз:"
        )
        return

    if len(market_name) > 50:
        await message.answer(
            "❌ Название слишком длинное (максимум 50 символов). Попробуйте еще раз:"
        )
        return

    # Сохраняем в БД
    async with async_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)

        if user:
            # Обновляем существующего
            user.market_name = market_name
            user.market_created_at = datetime.utcnow()
            await session.commit()
        else:
            # Создаем нового
            user = await repo.create(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                market_name=market_name,
            )

    # Очищаем состояние
    await state.clear()

    # Показываем кнопку с мини-аппом
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Открыть панель управления",
                    web_app=WebAppInfo(url=MINI_APP_URL),
                )
            ]
        ]
    )

    await message.answer(
        f"✅ **Отлично!**\n\n"
        f"Ваш бизнес **«{market_name}»** успешно создан!\n\n"
        f"Теперь нажмите на кнопку, чтобы открыть админку.",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )