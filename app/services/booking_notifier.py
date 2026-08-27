import html

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.handlers.start import MINI_APP_URL
from app.models.booking import Booking
from app.models.service import Service

STATUS_LABELS = {
    "confirmed": "✅ Ваша запись подтверждена",
    "cancelled_by_owner": "❌ Ваша запись отклонена бизнесом",
    "cancelled_by_client": "Запись отменена",
    "completed": "Услуга оказана, будем рады отзыву",
    "no_show": "Отмечено, что вы не пришли на запись",
}


def _format_booking_details(booking: Booking, service: Service) -> str:
    when = booking.starts_at.strftime("%d.%m.%Y %H:%M") if booking.starts_at else "—"
    parts = [
        f"<b>{html.escape(service.title)}</b>",
        f"👤 {html.escape(booking.client_name)}",
    ]
    if booking.client_phone:
        parts.append(f"📞 {html.escape(booking.client_phone)}")
    parts.append(f"🕐 {when}")
    return "\n".join(parts)


async def notify_owner_new_booking(
    bot: Bot, owner_telegram_id: int, booking: Booking, service: Service
) -> None:
    text = "🆕 Новая запись\n\n" + _format_booking_details(booking, service)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"booking:confirm:{booking.id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"booking:decline:{booking.id}"),
    ]])
    await bot.send_message(
        chat_id=owner_telegram_id, text=text, parse_mode="HTML", reply_markup=keyboard
    )


async def notify_client_status_change(bot: Bot, booking: Booking, service: Service) -> None:
    if not booking.client_telegram_id:
        return

    label = STATUS_LABELS.get(booking.status, booking.status)
    text = f"{label}\n\n" + _format_booking_details(booking, service)

    keyboard = None
    if booking.status == "completed":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="⭐ Оставить отзыв",
                web_app=WebAppInfo(url=f"{MINI_APP_URL}/review/{booking.id}"),
            ),
        ]])

    await bot.send_message(
        chat_id=booking.client_telegram_id, text=text, parse_mode="HTML", reply_markup=keyboard
    )


async def notify_reminder(
    bot: Bot,
    booking: Booking,
    service: Service,
    *,
    owner_telegram_id: int | None = None,
) -> None:
    text = "⏰ Напоминание: запись менее чем через час\n\n" + _format_booking_details(booking, service)
    if booking.client_telegram_id:
        await bot.send_message(chat_id=booking.client_telegram_id, text=text, parse_mode="HTML")
    if owner_telegram_id:
        await bot.send_message(chat_id=owner_telegram_id, text=text, parse_mode="HTML")
