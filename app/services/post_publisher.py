import html
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto

from app.bot.bot import get_bot_username
from app.models.ad import Ad
from app.repositories.ad_repository import photos_from_ad

UPLOAD_DIR = Path("uploads")


def format_post_message(post: Ad) -> str:
    parts = [f"<b>{html.escape(post.title)}</b>"]
    if post.subtitle:
        parts.append(f"<i>{html.escape(post.subtitle)}</i>")
    if post.description:
        parts.append(html.escape(post.description))
    return "\n\n".join(parts)


def _resolve_photo_path(url: str) -> Path | None:
    if url.startswith("/uploads/"):
        path = UPLOAD_DIR / url.replace("/uploads/", "", 1)
        return path if path.exists() else None
    return None


async def _booking_keyboard(post: Ad) -> InlineKeyboardMarkup | None:
    """Кнопка «Забронировать» под постом, если он привязан к услуге.

    В группах/каналах кнопки с web_app не работают (ограничение Bot API) — используем
    обычную url-кнопку на t.me/<bot>?start=service_<id>, которая заодно даёт боту право
    писать этому клиенту дальше (см. app/handlers/start.py::_handle_client_start).
    """
    if not post.service_id:
        return None
    username = await get_bot_username()
    url = f"https://t.me/{username}?start=service_{post.service_id}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📅 Забронировать", url=url),
    ]])


async def send_post_to_chat(bot: Bot, chat_id: int, post: Ad) -> int:
    text = format_post_message(post)
    photo_urls = photos_from_ad(post)
    local_files = [p for p in (_resolve_photo_path(u) for u in photo_urls) if p]
    keyboard = await _booking_keyboard(post)

    if not local_files:
        message = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return message.message_id

    if len(local_files) == 1:
        message = await bot.send_photo(
            chat_id=chat_id,
            photo=FSInputFile(local_files[0]),
            caption=text[:1024],
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return message.message_id

    media = []
    for index, file_path in enumerate(local_files):
        media.append(
            InputMediaPhoto(
                media=FSInputFile(file_path),
                caption=text[:1024] if index == 0 else None,
                parse_mode="HTML" if index == 0 else None,
            )
        )
    messages = await bot.send_media_group(chat_id=chat_id, media=media)
    if keyboard:
        # send_media_group не поддерживает reply_markup на самой группе — шлём кнопку отдельным сообщением следом
        await bot.send_message(chat_id=chat_id, text="Хотите записаться?", reply_markup=keyboard)
    return messages[0].message_id
