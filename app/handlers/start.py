from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from app.bot.states.market import MarketCreation
from app.database.session import async_session
from app.repositories.user_repository import UserRepository
from datetime import datetime 

router = Router()

# URL твоего мини-аппа (замени на свой)
MINI_APP_URL = "http://127.0.0.1:8000"  # Для теста локально

@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Проверяем, есть ли уже бизнес
    async with async_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(user_id)
        
        if user and user.market_name:
            # У пользователя уже есть бизнес - показываем мини-апп сразу
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🏪 Открыть панель управления",
                    web_app=WebAppInfo(url=MINI_APP_URL)
                )],
                [InlineKeyboardButton(
                    text="📊 Статистика",
                    callback_data="stats"
                )]
            ])
            await message.answer(
                f"🏢 С возвращением, {message.from_user.first_name}!\n\n"
                f"Ваш бизнес **{user.market_name}** активен.\n\n"
                f"Нажмите на кнопку, чтобы открыть админку:",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            # Новый пользователь - начинаем регистрацию
            await message.answer(
                f"👋 Добро пожаловать в Маркетплейс, {message.from_user.first_name}!\n\n"
                f"Давайте создадим ваш бизнес!\n\n"
                f"✨ **Введите название вашего бизнеса:**\n"
                f"Например: «Парикмахерская Наталья» или «Кофе с собой»",
                parse_mode="Markdown"
            )
            await state.set_state(MarketCreation.waiting_for_market_name)


@router.message(MarketCreation.waiting_for_market_name)
async def process_market_name(message: Message, state: FSMContext):
    market_name = message.text.strip()
    
    # Валидация
    if len(market_name) < 3:
        await message.answer("❌ Название слишком короткое (минимум 3 символа). Попробуйте еще раз:")
        return
    
    if len(market_name) > 50:
        await message.answer("❌ Название слишком длинное (максимум 50 символов). Попробуйте еще раз:")
        return
    
    # Сохраняем в БД
    async with async_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)
        
        if user:
            # Обновляем существующего
            user.market_name = market_name
            user.market_created_at = datetime.utcnow()
        else:
            # Создаем нового
            user = await repo.create(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                market_name=market_name
            )
        
        await session.commit()
    
    # Очищаем состояние
    await state.clear()
    
    # Показываем кнопку с мини-аппом
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🚀 Открыть панель управления",
            web_app=WebAppInfo(url=MINI_APP_URL)
        )]
    ])
    
    await message.answer(
        f"✅ **Отлично!**\n\n"
        f"Ваш бизнес **«{market_name}»** успешно создан!\n\n"
        f"Теперь нажмите на кнопку, чтобы открыть админку.\n"
        f"Там вы увидите свои данные из Telegram и сможете управлять бизнесом.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.message(lambda message: message.text == "Создать маркет")
async def create_market_btn_handler(message: Message, state: FSMContext):
    """Обработчик кнопки 'Создать маркет'"""
    await message.answer("Введите название вашего бизнеса:")
    await state.set_state(MarketCreation.waiting_for_market_name)