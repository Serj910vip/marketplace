from aiogram import Router
from aiogram.types import ChatMemberUpdated

from app.database.session import async_session
from app.repositories.user_repository import UserRepository

router = Router()


@router.my_chat_member()
async def on_bot_chat_member_update(event: ChatMemberUpdated):
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    if old_status in ("left", "kicked") and new_status in ("member", "administrator"):
        if not event.from_user:
            return

        async with async_session() as session:
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(event.from_user.id)
            if not user:
                return

            await repo.link_chat(
                user,
                chat_id=event.chat.id,
                chat_title=event.chat.title or "Без названия",
                chat_type=event.chat.type,
            )

        chat_label = "Канал" if event.chat.type == "channel" else "Группа"
        await event.bot.send_message(
            event.from_user.id,
            f"✅ {chat_label} «{event.chat.title}» подключена!\n\n"
            f"Теперь ваши посты будут публиковаться туда автоматически.",
        )

    elif new_status in ("left", "kicked") and old_status in ("member", "administrator"):
        if not event.from_user:
            return

        async with async_session() as session:
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(event.from_user.id)
            if user and user.linked_chat_id == event.chat.id:
                await repo.unlink_chat(user)
