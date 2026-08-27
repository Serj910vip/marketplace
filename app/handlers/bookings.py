from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.database.session import async_session
from app.repositories.booking_repository import BookingRepository
from app.repositories.service_repository import ServiceRepository
from app.services.booking_notifier import notify_client_status_change

router = Router()

ACTION_TO_STATUS = {
    "confirm": "confirmed",
    "decline": "cancelled_by_owner",
}

STATUS_TO_LABEL = {
    "confirmed": "✅ Подтверждена",
    "cancelled_by_owner": "❌ Отклонена",
}


@router.callback_query(F.data.startswith("booking:"))
async def handle_booking_action(callback: CallbackQuery):
    _, action, booking_id_str = callback.data.split(":")
    new_status = ACTION_TO_STATUS.get(action)
    if not new_status:
        await callback.answer("Неизвестное действие", show_alert=True)
        return

    booking_id = int(booking_id_str)

    async with async_session() as session:
        booking_repo = BookingRepository(session)
        booking = await booking_repo.get_by_id(booking_id)
        if not booking:
            await callback.answer("Запись не найдена", show_alert=True)
            return

        try:
            booking = await booking_repo.update_status(booking_id, new_status)
        except ValueError as e:
            await callback.answer(str(e), show_alert=True)
            return

        service_repo = ServiceRepository(session)
        service = await service_repo.get_by_id(booking.service_id)
        if service:
            await notify_client_status_change(callback.bot, booking, service)

    if callback.message:
        await callback.message.edit_text(
            f"{callback.message.text}\n\n{STATUS_TO_LABEL[new_status]}",
            reply_markup=None,
        )
    await callback.answer()
