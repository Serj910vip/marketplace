from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    ReplyKeyboardMarkup,
    KeyboardButton,
    MenuButtonWebApp,
    MenuButtonDefault,
)
from aiogram.fsm.context import FSMContext

from app.bot.states.market import MarketCreation
from app.database.session import async_session
from app.repositories.user_repository import UserRepository
from datetime import datetime

router = Router()

MINI_APP_URL = "https://plentora-gs.com"

CONTROL_PANEL_BTN = "🏪 Панель управления"


def get_control_panel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(
                text=CONTROL_PANEL_BTN,
                web_app=WebAppInfo(url=MINI_APP_URL),
            )
        ]],
        resize_keyboard=True,
        is_persistent=True,
    )


async def _set_business_menu_button(message: Message):
    await message.bot.set_chat_menu_button(
        chat_id=message.from_user.id,
        menu_button=MenuButtonWebApp(
            text="🏪 Мой бизнес",
            web_app=WebAppInfo(url=MINI_APP_URL),
        ),
    )


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id

    async with async_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(user_id)

        if user and user.market_name:
            await _set_business_menu_button(message)

            await message.answer(
                f"🏢 С возвращением! Ваш бизнес **{user.market_name}** активен.\n\n"
                f"Используйте кнопку **«{CONTROL_PANEL_BTN}»** внизу для входа в админку.",
                reply_markup=get_control_panel_keyboard(),
                parse_mode="Markdown",
            )
        else:
            await message.bot.set_chat_menu_button(
                chat_id=message.from_user.id,
                menu_button=MenuButtonDefault(),
            )

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


@router.message(F.text == "📝 Создать маркет")
async def create_market_btn_handler(message: Message, state: FSMContext):
    await message.answer(
        "✨ **Отлично!**\n\n"
        "Введите **название вашего бизнеса**:\n"
        "Например: «Парикмахерская Наталья» или «Кофе с собой»",
        parse_mode="Markdown",
    )
    await state.set_state(MarketCreation.waiting_for_market_name)


@router.message(MarketCreation.waiting_for_market_name)
async def process_market_name(message: Message, state: FSMContext):
    market_name = message.text.strip()

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

    async with async_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)

        if user:
            user.market_name = market_name
            user.market_created_at = datetime.utcnow()
            await session.commit()
        else:
            await repo.create(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                market_name=market_name,
            )

    await _set_business_menu_button(message)
    await state.clear()

    await message.answer(
        f"✅ **Отлично!**\n\n"
        f"Ваш бизнес **«{market_name}»** успешно создан!\n\n"
        f"Кнопка **«{CONTROL_PANEL_BTN}»** теперь всегда доступна внизу экрана.",
        reply_markup=get_control_panel_keyboard(),
        parse_mode="Markdown",
    )


@router.message(F.text == CONTROL_PANEL_BTN)
async def control_panel_fallback(message: Message):
    """Запасной обработчик, если WebApp-кнопка не сработала на устройстве."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🚀 Открыть админ панель",
                web_app=WebAppInfo(url=MINI_APP_URL),
            )
        ]]
    )
    await message.answer(
        "Нажмите кнопку ниже, чтобы открыть админ панель:",
        reply_markup=keyboard,
    )
