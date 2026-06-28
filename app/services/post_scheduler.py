import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from app.bot.bot import bot
from app.database.session import AsyncSessionLocal
from app.models.user import User
from app.repositories.ad_repository import AdRepository
from app.services.post_publisher import send_post_to_chat

logger = logging.getLogger(__name__)


async def process_scheduled_posts():
    async with AsyncSessionLocal() as session:
        ad_repo = AdRepository(session)
        due_posts = await ad_repo.get_due_scheduled()

        for post in due_posts:
            result = await session.execute(select(User).where(User.id == post.user_id))
            user = result.scalar_one_or_none()
            if not user or not user.linked_chat_id:
                logger.warning("Post %s skipped: no linked chat", post.id)
                continue

            try:
                await send_post_to_chat(bot, user.linked_chat_id, post)
                await ad_repo.mark_published(post)
                logger.info("Scheduled post %s published to chat %s", post.id, user.linked_chat_id)
            except Exception:
                logger.exception("Failed to publish scheduled post %s", post.id)


async def scheduler_loop(interval_seconds: int = 60):
    while True:
        try:
            await process_scheduled_posts()
        except Exception:
            logger.exception("Scheduler iteration failed")
        await asyncio.sleep(interval_seconds)
