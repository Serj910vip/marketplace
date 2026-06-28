import html

from aiogram import Bot

from app.models.ad import Ad


def format_post_message(post: Ad) -> str:
    parts = [f"<b>{html.escape(post.title)}</b>"]
    if post.subtitle:
        parts.append(f"<i>{html.escape(post.subtitle)}</i>")
    if post.description:
        parts.append(html.escape(post.description))
    return "\n\n".join(parts)


async def send_post_to_chat(bot: Bot, chat_id: int, post: Ad) -> int:
    message = await bot.send_message(
        chat_id=chat_id,
        text=format_post_message(post),
        parse_mode="HTML",
    )
    return message.message_id
