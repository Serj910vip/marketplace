import html
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto

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


async def send_post_to_chat(bot: Bot, chat_id: int, post: Ad) -> int:
    text = format_post_message(post)
    photo_urls = photos_from_ad(post)
    local_files = [p for p in (_resolve_photo_path(u) for u in photo_urls) if p]

    if not local_files:
        message = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
        )
        return message.message_id

    if len(local_files) == 1:
        message = await bot.send_photo(
            chat_id=chat_id,
            photo=FSInputFile(local_files[0]),
            caption=text[:1024],
            parse_mode="HTML",
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
    return messages[0].message_id
