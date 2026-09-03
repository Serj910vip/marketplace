import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.bot.bot import bot
from app.database.session import AsyncSessionLocal
from app.models.booking import Booking
from app.models.service import Service
from app.models.user import User
from app.repositories.availability_repository import AvailabilityRepository
from app.repositories.booking_repository import BookingRepository
from app.repositories.review_repository import ReviewRepository
from app.repositories.service_category_repository import ServiceCategoryRepository
from app.repositories.service_repository import ServiceRepository
from app.repositories.user_repository import UserRepository
from app.services.booking_notifier import notify_client_status_change, notify_owner_new_booking

logger = logging.getLogger(__name__)

router = APIRouter()


async def _safe_notify(coro) -> None:
    """Уведомление в Telegram не должно ронять запрос — бронь уже сохранена в БД."""
    try:
        await coro
    except Exception:
        logger.exception("Failed to send Telegram notification")


# ========== Pydantic-модели ==========

class CategoryCreateRequest(BaseModel):
    name: str


class AvailabilityRuleIn(BaseModel):
    weekday: int  # 0 = понедельник ... 6 = воскресенье
    time_start: str  # "HH:MM"
    time_end: str  # "HH:MM"


class ServiceCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    photo_url: Optional[str] = None
    category_id: Optional[int] = None
    price: Optional[float] = None
    duration_minutes: Optional[int] = None
    capacity: int = 1
    booking_format: Optional[str] = None
    status: Literal["draft", "published"] = "draft"
    availability: list[AvailabilityRuleIn] = []


class ServiceUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    photo_url: Optional[str] = None
    category_id: Optional[int] = None
    price: Optional[float] = None
    duration_minutes: Optional[int] = None
    capacity: Optional[int] = None
    booking_format: Optional[str] = None
    availability: Optional[list[AvailabilityRuleIn]] = None


class ServiceStatusRequest(BaseModel):
    status: Literal["draft", "published", "hidden", "archived"]


class BookingCreateRequest(BaseModel):
    service_id: int
    client_telegram_id: int
    client_name: str
    client_phone: Optional[str] = None
    starts_at: datetime


class BookingStatusRequest(BaseModel):
    status: Literal["confirmed", "cancelled_by_owner", "completed", "no_show"]
    cancel_reason: Optional[str] = None


class BookingCancelRequest(BaseModel):
    client_telegram_id: int
    cancel_reason: Optional[str] = None


class ReviewCreateRequest(BaseModel):
    booking_id: int
    client_telegram_id: int
    rating: int
    comment: Optional[str] = None


# ========== Вспомогательное ==========

def _parse_time(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def _service_to_dict(service: Service, category_name: str | None = None) -> dict:
    return {
        "id": service.id,
        "title": service.title,
        "description": service.description,
        "photo_url": service.photo_url,
        "category_id": service.category_id,
        "category_name": category_name,
        "price": float(service.price) if service.price is not None else None,
        "duration_minutes": service.duration_minutes or service.training_duration,
        "capacity": service.capacity,
        "status": service.status,
        "booking_format": service.booking_format,
        "created_at": service.created_at.isoformat(),
    }


def _booking_to_dict(booking: Booking, service_title: str = "") -> dict:
    return {
        "id": booking.id,
        "service_id": booking.service_id,
        "service_title": service_title,
        "client_name": booking.client_name,
        "client_phone": booking.client_phone,
        "starts_at": booking.starts_at.isoformat() if booking.starts_at else None,
        "ends_at": booking.ends_at.isoformat() if booking.ends_at else None,
        "status": booking.status,
        "price_at_booking": float(booking.price_at_booking) if booking.price_at_booking is not None else None,
        "cancel_reason": booking.cancel_reason,
        "created_at": booking.created_at.isoformat(),
    }


# ========== Категории ==========

@router.get("/api/categories/{telegram_id}")
async def get_categories(telegram_id: int):
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        cat_repo = ServiceCategoryRepository(session)
        categories = await cat_repo.get_by_user_id(user.id)
        return JSONResponse({
            "categories": [{"id": c.id, "name": c.name} for c in categories]
        })


@router.post("/api/categories/{telegram_id}")
async def create_category(telegram_id: int, body: CategoryCreateRequest):
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        if not body.name.strip():
            raise HTTPException(status_code=400, detail="Название категории обязательно")

        cat_repo = ServiceCategoryRepository(session)
        category = await cat_repo.create(user_id=user.id, name=body.name.strip())
        return JSONResponse({"success": True, "category": {"id": category.id, "name": category.name}})


@router.delete("/api/categories/{telegram_id}/{category_id}")
async def delete_category(telegram_id: int, category_id: int):
    async with AsyncSessionLocal() as session:
        cat_repo = ServiceCategoryRepository(session)
        deleted = await cat_repo.delete(category_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Категория не найдена")
        return JSONResponse({"success": True})


# ========== Услуги ==========

@router.get("/api/services/{telegram_id}")
async def get_services(telegram_id: int, status: Optional[str] = Query(default=None)):
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        svc_repo = ServiceRepository(session)
        services = await svc_repo.get_by_user_id(user.id, status=status)

        cat_repo = ServiceCategoryRepository(session)
        categories = {c.id: c.name for c in await cat_repo.get_by_user_id(user.id)}

        return JSONResponse({
            "services": [
                _service_to_dict(s, categories.get(s.category_id)) for s in services
            ]
        })


@router.post("/api/services/{telegram_id}")
async def create_service(telegram_id: int, body: ServiceCreateRequest):
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        if not body.title.strip():
            raise HTTPException(status_code=400, detail="Название услуги обязательно")

        svc_repo = ServiceRepository(session)
        service = await svc_repo.create(
            user_id=user.id,
            title=body.title.strip(),
            description=body.description,
            photo_url=body.photo_url,
            category_id=body.category_id,
            price=Decimal(str(body.price)) if body.price is not None else None,
            duration_minutes=body.duration_minutes,
            capacity=body.capacity,
            booking_format=body.booking_format,
            status=body.status,
        )

        if body.availability:
            avail_repo = AvailabilityRepository(session)
            await avail_repo.replace_rules(service.id, [
                {
                    "weekday": r.weekday,
                    "time_start": _parse_time(r.time_start),
                    "time_end": _parse_time(r.time_end),
                }
                for r in body.availability
            ])

        category_name = None
        if service.category_id:
            cat_repo = ServiceCategoryRepository(session)
            category = await cat_repo.get_by_id(service.category_id)
            category_name = category.name if category else None

        return JSONResponse({"success": True, "service": _service_to_dict(service, category_name)})


@router.patch("/api/services/{telegram_id}/{service_id}")
async def update_service(telegram_id: int, service_id: int, body: ServiceUpdateRequest):
    async with AsyncSessionLocal() as session:
        svc_repo = ServiceRepository(session)
        data = {k: v for k, v in body.model_dump(exclude={"availability"}).items() if v is not None}
        if "price" in data:
            data["price"] = Decimal(str(data["price"]))

        service = await svc_repo.update(service_id, data)
        if not service:
            raise HTTPException(status_code=404, detail="Услуга не найдена")

        if body.availability is not None:
            avail_repo = AvailabilityRepository(session)
            await avail_repo.replace_rules(service_id, [
                {
                    "weekday": r.weekday,
                    "time_start": _parse_time(r.time_start),
                    "time_end": _parse_time(r.time_end),
                }
                for r in body.availability
            ])

        category_name = None
        if service.category_id:
            cat_repo = ServiceCategoryRepository(session)
            category = await cat_repo.get_by_id(service.category_id)
            category_name = category.name if category else None

        return JSONResponse({"success": True, "service": _service_to_dict(service, category_name)})


@router.patch("/api/services/{telegram_id}/{service_id}/status")
async def set_service_status(telegram_id: int, service_id: int, body: ServiceStatusRequest):
    async with AsyncSessionLocal() as session:
        svc_repo = ServiceRepository(session)
        try:
            service = await svc_repo.set_status(service_id, body.status)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        if not service:
            raise HTTPException(status_code=404, detail="Услуга не найдена")
        return JSONResponse({"success": True, "service": _service_to_dict(service)})


@router.delete("/api/services/{telegram_id}/{service_id}")
async def delete_service(telegram_id: int, service_id: int):
    async with AsyncSessionLocal() as session:
        svc_repo = ServiceRepository(session)
        try:
            deleted = await svc_repo.delete(service_id)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        if not deleted:
            raise HTTPException(status_code=404, detail="Услуга не найдена")
        return JSONResponse({"success": True})


@router.get("/api/services/{service_id}/slots")
async def get_service_slots(
    service_id: int,
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
):
    async with AsyncSessionLocal() as session:
        svc_repo = ServiceRepository(session)
        service = await svc_repo.get_by_id(service_id)
        if not service or service.status != "published":
            raise HTTPException(status_code=404, detail="Услуга недоступна")

        start = date.fromisoformat(date_from) if date_from else date.today()
        end = date.fromisoformat(date_to) if date_to else start + timedelta(days=14)

        avail_repo = AvailabilityRepository(session)
        slots = await avail_repo.get_available_slots(service, start, end)
        return JSONResponse({
            "slots": [
                {"starts_at": s["starts_at"].isoformat(), "ends_at": s["ends_at"].isoformat()}
                for s in slots
            ]
        })


@router.get("/api/services/{service_id}/reviews")
async def get_service_reviews(service_id: int):
    async with AsyncSessionLocal() as session:
        review_repo = ReviewRepository(session)
        reviews = await review_repo.get_by_service_id(service_id)
        return JSONResponse({
            "reviews": [
                {"id": r.id, "rating": r.rating, "comment": r.comment, "created_at": r.created_at.isoformat()}
                for r in reviews
            ]
        })


# ========== Записи (брони) ==========

@router.post("/api/bookings")
async def create_booking(body: BookingCreateRequest):
    async with AsyncSessionLocal() as session:
        svc_repo = ServiceRepository(session)
        service = await svc_repo.get_by_id(body.service_id)
        if not service or service.status != "published":
            raise HTTPException(status_code=404, detail="Услуга недоступна")

        duration = timedelta(minutes=service.duration_minutes or service.training_duration or 30)
        ends_at = body.starts_at + duration

        avail_repo = AvailabilityRepository(session)
        if not await avail_repo.is_slot_available(service, body.starts_at, ends_at):
            raise HTTPException(status_code=409, detail="Это время уже недоступно")

        owner = await session.get(User, service.user_id)
        if not owner:
            raise HTTPException(status_code=404, detail="Бизнес не найден")

        status = "confirmed" if owner.booking_auto_confirm else "pending"

        booking_repo = BookingRepository(session)
        booking = await booking_repo.create(
            service_id=service.id,
            owner_id=owner.id,
            client_name=body.client_name.strip(),
            starts_at=body.starts_at,
            ends_at=ends_at,
            price_at_booking=service.price,
            client_phone=body.client_phone,
            client_telegram_id=body.client_telegram_id,
            status=status,
        )

        if status == "pending":
            await _safe_notify(notify_owner_new_booking(bot, owner.telegram_id, booking, service))
        else:
            await _safe_notify(notify_client_status_change(bot, booking, service))

        return JSONResponse({"success": True, "booking": _booking_to_dict(booking, service.title)})


@router.get("/api/bookings/{telegram_id}")
async def get_bookings(
    telegram_id: int,
    status: Optional[str] = Query(default=None),
):
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        booking_repo = BookingRepository(session)
        bookings = await booking_repo.get_by_owner_id(user.id, status=status)

        svc_repo = ServiceRepository(session)
        service_titles: dict[int, str] = {}
        for b in bookings:
            if b.service_id not in service_titles:
                svc = await svc_repo.get_by_id(b.service_id)
                service_titles[b.service_id] = svc.title if svc else "Услуга"

        return JSONResponse({
            "bookings": [_booking_to_dict(b, service_titles.get(b.service_id, "Услуга")) for b in bookings]
        })


@router.patch("/api/bookings/{telegram_id}/{booking_id}")
async def update_booking_status(telegram_id: int, booking_id: int, body: BookingStatusRequest):
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        booking_repo = BookingRepository(session)
        booking = await booking_repo.get_by_id(booking_id)
        if not booking or booking.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Запись не найдена")

        try:
            booking = await booking_repo.update_status(booking_id, body.status, body.cancel_reason)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

        svc_repo = ServiceRepository(session)
        service = await svc_repo.get_by_id(booking.service_id)
        if service:
            await _safe_notify(notify_client_status_change(bot, booking, service))

        return JSONResponse({"success": True, "booking": _booking_to_dict(booking, service.title if service else "")})


@router.post("/api/bookings/{booking_id}/cancel")
async def cancel_booking(booking_id: int, body: BookingCancelRequest):
    async with AsyncSessionLocal() as session:
        booking_repo = BookingRepository(session)
        booking = await booking_repo.get_by_id(booking_id)
        if not booking or booking.client_telegram_id != body.client_telegram_id:
            raise HTTPException(status_code=404, detail="Запись не найдена")

        owner = await session.get(User, booking.owner_id)
        if not owner or not await booking_repo.client_can_cancel(booking, owner):
            raise HTTPException(status_code=409, detail="Отмена уже недоступна, обратитесь к бизнесу напрямую")

        booking = await booking_repo.update_status(booking_id, "cancelled_by_client", body.cancel_reason)

        if owner.telegram_id:
            reason_note = f"\nПричина: {body.cancel_reason}" if body.cancel_reason else ""
            await _safe_notify(bot.send_message(
                chat_id=owner.telegram_id,
                text=f"❌ Клиент {booking.client_name} отменил запись.{reason_note}",
            ))

        return JSONResponse({"success": True, "booking": _booking_to_dict(booking)})


# ========== Отзывы ==========

@router.post("/api/reviews")
async def create_review(body: ReviewCreateRequest):
    if not 1 <= body.rating <= 5:
        raise HTTPException(status_code=400, detail="Оценка должна быть от 1 до 5")

    async with AsyncSessionLocal() as session:
        booking_repo = BookingRepository(session)
        booking = await booking_repo.get_by_id(body.booking_id)
        if not booking or booking.client_telegram_id != body.client_telegram_id:
            raise HTTPException(status_code=404, detail="Запись не найдена")
        if booking.status != "completed":
            raise HTTPException(status_code=409, detail="Отзыв можно оставить только после оказания услуги")

        review_repo = ReviewRepository(session)
        if await review_repo.get_by_booking_id(booking.id):
            raise HTTPException(status_code=409, detail="Отзыв уже оставлен")

        review = await review_repo.create(booking, rating=body.rating, comment=body.comment)
        return JSONResponse({"success": True, "review_id": review.id})


# ========== Клиентская база ==========

@router.get("/api/clients/{telegram_id}")
async def get_clients(telegram_id: int):
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        clients = await user_repo.get_client_base(user.id)
        return JSONResponse({
            "clients": [
                {
                    **c,
                    "last_visit_at": c["last_visit_at"].isoformat() if c["last_visit_at"] else None,
                }
                for c in clients
            ]
        })


SERVICES_LIST_CSS = """
    .services-filter-tabs {
        display: flex;
        justify-content: space-around;
        gap: 8px;
        margin-bottom: 19px;
    }

    .services-filter-tab {
        flex: 1;
        padding: 14px 4px;
        margin-top: 10px;
        background: #121918;
        border: 0.5px solid #0073FF;
        border-radius: 10px;
        color: #FFFFFF;
        font-size: 10px;
        font-weight: 500;
        cursor: pointer;
        text-align: center;
    }

    .services-filter-tab.active {
        background: #003A81;
        border: 0.5px solid #0073FF;
        color: #FFFFFF;
    }

    .services-filter-tab:hover {
        background: #003A81;
    }
"""

SERVICE_STATUS_TAB_LABELS = {
    "published": "Активные",
    "draft": "Черновики",
    "hidden": "Скрытые",
    "archived": "Архив",
}


def register_service_pages(app, common_styles: str, webapp_init: str, render_back_header):
    styles = common_styles + SERVICES_LIST_CSS

    @app.get("/services", response_class=HTMLResponse)
    async def services_list_page():
        return f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
            <style>{styles}</style>
            <title>Услуги</title>
        </head>
        <body>
            <div class="app">
                <div class="content" style="padding-top:0;">
                    {render_back_header("window.location.href='/'", "Услуги")}
                    <div class="container-post">
                        <div class="ads-create-btn-wrapper">
                            <button class="ads-create-btn" onclick="window.location.href='/service/create'">Создать услугу</button>
                        </div>
                    </div>

                    <div class="services-filter-tabs" id="status-tabs">
                        <button class="services-filter-tab active" data-status="published" onclick="filterServices('published')">Активные</button>
                        <button class="services-filter-tab" data-status="draft" onclick="filterServices('draft')">Черновики</button>
                        <button class="services-filter-tab" data-status="hidden" onclick="filterServices('hidden')">Скрытые</button>
                        <button class="services-filter-tab" data-status="archived" onclick="filterServices('archived')">Архив</button>
                    </div>
                    <div class="ads-count" id="services-count">Услуги: 0</div>
                    <div class="ads-list-container" id="services-list">
                        <div class="ads-empty">Список услуг пуст</div>
                    </div>
                </div>
            </div>
            <script>
            {webapp_init}
            let allServices = [];
            let currentFilter = 'published';
            let telegramId = tgUser?.id;

            function filterServices(status) {{
                currentFilter = status;
                document.querySelectorAll('.services-filter-tab').forEach(el =>
                    el.classList.toggle('active', el.dataset.status === status));
                renderServicesList();
            }}

            function renderServicesList() {{
                const filtered = allServices.filter(s => s.status === currentFilter);
                const container = document.getElementById('services-list');
                document.getElementById('services-count').textContent = `Услуги: ${{filtered.length}}`;

                if (!filtered.length) {{
                    const labels = {{
                        published: 'активных', draft: 'черновиков', hidden: 'скрытых', archived: 'архивных',
                    }};
                    container.innerHTML = `<div class="ads-empty">Нет ${{labels[currentFilter]}} услуг</div>`;
                    return;
                }}

                container.innerHTML = filtered.map((s, index) => {{
                    const num = String(index + 1).padStart(3, '0');
                    const date = s.created_at ? new Date(s.created_at).toLocaleString('ru-RU') : '';
                    const meta = [s.category_name || 'Без категории', s.price ? s.price + ' ₽' : null]
                        .filter(Boolean).join(' · ');
                    return `
                        <div class="add-item">
                            <div class="add-item-date-block">
                                <div class="add-item-number">#${{num}}</div>
                                <div class="add-item-date">Создано: ${{date.split(' ')[0]}}</div>
                            </div>
                            <div class="add-item-title-block">
                                <div class="add-item-title">${{s.title}}</div>
                                <div class="add-item-subtitle">${{meta}}</div>
                            </div>
                            <div class="add-item-actions">
                                <button class="add-item-btn add-item-btn-edit" onclick="editService(${{s.id}})">Редактировать</button>
                            </div>
                        </div>`;
                }}).join('');
            }}

            function editService(id) {{ window.location.href = `/service/edit/${{id}}`; }}

            async function loadServices() {{
                if (!telegramId) return;
                const res = await fetch(`/api/services/${{telegramId}}`);
                const data = await res.json();
                allServices = data.services || [];
                renderServicesList();
            }}
            loadServices();
            </script>
        </body>
        </html>
        """
