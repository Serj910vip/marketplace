import asyncio
import logging

from app.bot.bot import bot
from app.database.session import AsyncSessionLocal
from app.models.user import User
from app.repositories.booking_repository import BookingRepository
from app.repositories.service_repository import ServiceRepository
from app.services.booking_notifier import notify_reminder

logger = logging.getLogger(__name__)

REMINDER_MINUTES_BEFORE = 60


async def process_reminders():
    async with AsyncSessionLocal() as session:
        booking_repo = BookingRepository(session)
        service_repo = ServiceRepository(session)

        due = await booking_repo.get_due_reminders(minutes_before=REMINDER_MINUTES_BEFORE)
        for booking in due:
            service = await service_repo.get_by_id(booking.service_id)
            owner = await session.get(User, booking.owner_id)
            if not service or not owner:
                continue

            try:
                await notify_reminder(bot, booking, service, owner_telegram_id=owner.telegram_id)
                await booking_repo.mark_reminder_sent(booking)
                logger.info("Reminder sent for booking %s", booking.id)
            except Exception:
                logger.exception("Failed to send reminder for booking %s", booking.id)


async def process_autocomplete():
    async with AsyncSessionLocal() as session:
        booking_repo = BookingRepository(session)

        due = await booking_repo.get_past_due_confirmed()
        for booking in due:
            try:
                await booking_repo.update_status(booking.id, "completed")
                logger.info("Booking %s auto-completed", booking.id)
            except Exception:
                logger.exception("Failed to auto-complete booking %s", booking.id)


async def booking_scheduler_loop(interval_seconds: int = 60):
    while True:
        try:
            await process_reminders()
            await process_autocomplete()
        except Exception:
            logger.exception("Booking scheduler iteration failed")
        await asyncio.sleep(interval_seconds)
