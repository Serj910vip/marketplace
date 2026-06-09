import json
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from app.database.session import AsyncSessionLocal
from app.models.booking import Booking
from app.models.service import Service
from app.models.user import User
from app.repositories.booking_repository import BookingRepository
from app.repositories.service_repository import ServiceRepository
from app.repositories.user_repository import UserRepository

app = FastAPI()

MARKETPLACE_NAME = "Tipster my market"

DAY_LABELS = {
    "mon": "Пн", "tue": "Вт", "wed": "Ср", "thu": "Чт",
    "fri": "Пт", "sat": "Сб", "sun": "Вс",
}


class ProfileUpdateRequest(BaseModel):
    profile_type: Literal["business", "personal"]
    country: str
    region: str
    city: str


class BusinessSettingsRequest(BaseModel):
    market_name: Optional[str] = None
    business_photo_url: Optional[str] = None


class ServiceCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    photo_url: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    training_duration: Optional[int] = None
    booking_format: Optional[str] = None
    working_schedule: Optional[dict[str, list[str]]] = None


def _format_address(city: str | None, region: str | None, country: str | None) -> str:
    parts = [p for p in (city, region, country) if p]
    return ", ".join(parts) if parts else "Не указан"


def _user_to_dict(user: User) -> dict:
    return {
        "has_business": bool(user.market_name),
        "business_name": user.market_name or "Не указан",
        "telegram_id": user.telegram_id,
        "username": user.username,
        "created_at": user.market_created_at.isoformat() if user.market_created_at else None,
        "business_photo_url": user.business_photo_url,
        "business_rating": user.business_rating or 0.0,
        "latitude": user.latitude,
        "longitude": user.longitude,
        "business_address": _format_address(
            user.business_city, user.business_region, user.business_country
        ),
        "business_country": user.business_country,
        "business_region": user.business_region,
        "business_city": user.business_city,
        "personal_country": user.personal_country,
        "personal_region": user.personal_region,
        "personal_city": user.personal_city,
        "personal_address": _format_address(
            user.personal_city, user.personal_region, user.personal_country
        ),
    }


def _service_to_dict(service: Service) -> dict:
    schedule = service.get_schedule()
    days_short = ", ".join(
        DAY_LABELS.get(d, d) for d in schedule.keys()
    ) if schedule else "—"
    return {
        "id": service.id,
        "title": service.title,
        "description": service.description,
        "photo_url": service.photo_url,
        "category": service.category,
        "price": service.price,
        "training_duration": service.training_duration,
        "booking_format": service.booking_format,
        "working_schedule": schedule,
        "working_days_label": days_short,
        "created_at": service.created_at.isoformat(),
    }


def _booking_to_dict(booking: Booking, service_title: str) -> dict:
    return {
        "id": booking.id,
        "service_id": booking.service_id,
        "service_title": service_title,
        "client_name": booking.client_name,
        "booking_day": booking.booking_day,
        "booking_day_label": DAY_LABELS.get(booking.booking_day, booking.booking_day),
        "booking_time": booking.booking_time,
        "status": booking.status,
        "created_at": booking.created_at.isoformat(),
    }


# ========== API ==========

@app.get("/api/business/{telegram_id}")
async def get_business_info(telegram_id: int):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                return JSONResponse({"has_business": False, "error": "Пользователь не найден"})
            return JSONResponse(_user_to_dict(user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/business/{telegram_id}/settings")
async def update_business_settings(telegram_id: int, body: BusinessSettingsRequest):
    try:
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(telegram_id)
            if not user:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

            if body.market_name is not None:
                name = body.market_name.strip()
                if len(name) < 3:
                    raise HTTPException(status_code=400, detail="Название слишком короткое")
                if len(name) > 50:
                    raise HTTPException(status_code=400, detail="Название слишком длинное")

            await repo.update_business(
                user,
                market_name=body.market_name.strip() if body.market_name else None,
                business_photo_url=body.business_photo_url,
            )
            return JSONResponse({"success": True, "business": _user_to_dict(user)})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/profile/{telegram_id}")
async def update_profile(telegram_id: int, body: ProfileUpdateRequest):
    try:
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(telegram_id)
            if not user:
                raise HTTPException(status_code=404, detail="Пользователь не найден")
            await repo.update_profile(
                user,
                profile_type=body.profile_type,
                country=body.country,
                region=body.region,
                city=body.city,
            )
            return JSONResponse({"success": True})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/services/{telegram_id}")
async def get_services(telegram_id: int):
    try:
        async with AsyncSessionLocal() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id)
            if not user:
                raise HTTPException(status_code=404, detail="Пользователь не найден")
            service_repo = ServiceRepository(session)
            services = await service_repo.get_by_user_id(user.id)
            return JSONResponse({
                "services": [_service_to_dict(s) for s in services]
            })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/services/{telegram_id}")
async def create_service(telegram_id: int, body: ServiceCreateRequest):
    try:
        async with AsyncSessionLocal() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id)
            if not user:
                raise HTTPException(status_code=404, detail="Пользователь не найден")
            if not body.title.strip():
                raise HTTPException(status_code=400, detail="Название услуги обязательно")

            service_repo = ServiceRepository(session)
            service = await service_repo.create(
                user_id=user.id,
                title=body.title.strip(),
                description=body.description,
                photo_url=body.photo_url,
                category=body.category,
                price=body.price,
                training_duration=body.training_duration,
                booking_format=body.booking_format,
                working_schedule=body.working_schedule,
            )
            return JSONResponse({
                "success": True,
                "service": _service_to_dict(service),
            })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bookings/{telegram_id}")
async def get_bookings(telegram_id: int):
    try:
        async with AsyncSessionLocal() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id)
            if not user:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

            booking_repo = BookingRepository(session)
            bookings = await booking_repo.get_by_owner_id(user.id)

            service_titles: dict[int, str] = {}
            if bookings:
                service_ids = {b.service_id for b in bookings}
                result = await session.execute(
                    select(Service).where(Service.id.in_(service_ids))
                )
                for svc in result.scalars().all():
                    service_titles[svc.id] = svc.title

            return JSONResponse({
                "bookings": [
                    _booking_to_dict(b, service_titles.get(b.service_id, "Услуга"))
                    for b in bookings
                ]
            })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats/{telegram_id}")
async def get_stats(telegram_id: int):
    try:
        async with AsyncSessionLocal() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id)
            if not user:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

            total = await session.scalar(
                select(func.count()).select_from(Booking).where(Booking.owner_id == user.id)
            ) or 0
            successful = await session.scalar(
                select(func.count()).select_from(Booking).where(
                    Booking.owner_id == user.id,
                    Booking.status == "confirmed",
                )
            ) or 0
            cancelled = await session.scalar(
                select(func.count()).select_from(Booking).where(
                    Booking.owner_id == user.id,
                    Booking.status == "cancelled",
                )
            ) or 0

            return JSONResponse({
                "total_requests": total,
                "successful_requests": successful,
                "cancelled_requests": cancelled,
            })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== HTML ==========

COMMON_STYLES = """
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: var(--tg-theme-bg-color, #f5f5f5);
        color: var(--tg-theme-text-color, #1a1a1a);
        min-height: 100vh;
    }
    .app { max-width: 480px; margin: 0 auto; min-height: 100vh; display: flex; flex-direction: column; }
    .content { flex: 1; padding: 16px 16px 88px; overflow-y: auto; }
    .hidden { display: none !important; }

    /* НОВЫЕ СТИЛИ ДЛЯ МЕНЮ */
    .bottom-nav {
        position: fixed; bottom: 0; left: 50%; transform: translateX(-50%);
        width: 100%; max-width: 480px; display: flex; gap: 8px;
        background: var(--tg-theme-secondary-bg-color, #fff);
        border-top: 1px solid rgba(0,0,0,0.08); z-index: 100;
        padding: 8px 12px env(safe-area-inset-bottom, 0);
        justify-content: space-around;
    }

    .nav-item {
        flex: 0 1 auto;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 10px;
        border: none;
        background: transparent;
        border-radius: 12px;
        cursor: pointer;
        transition: all 0.2s ease;
        color: var(--tg-theme-hint-color, #8e8e93);
        min-width: 60px;
    }

    .nav-item .nav-icon {
        font-size: 24px;
    }

    .nav-item .nav-label {
        display: none;  /* По умолчанию текст скрыт */
        font-size: 14px;
        font-weight: 500;
        margin-left: 8px;
    }

    /* Активный пункт - показываем иконку и текст, с белым фоном */
    .nav-item.active {
        background: var(--tg-theme-button-text-color, #ffffff);
        color: var(--tg-theme-button-color, #007aff);
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        padding: 10px 16px;
    }

    .nav-item.active .nav-label {
        display: inline;  /* Показываем текст только у активного */
    }
    /* КОНЕЦ НОВЫХ СТИЛЕЙ */

    .user-header {
        background: var(--tg-theme-secondary-bg-color, #fff);
        border-radius: 16px;
        padding: 16px 20px;
        margin-bottom: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        display: flex;
        align-items: baseline;
        gap: 8px;
        flex-wrap: wrap;
    }
    .user-role {
        font-size: 14px;
        color: var(--tg-theme-button-color, #2481cc);
        font-weight: 500;
    }
    .user-name {
        font-size: 18px;
        font-weight: 700;
        color: var(--tg-theme-text-color, #1a1a1a);
    }

    .business-card {
        background: var(--tg-theme-secondary-bg-color, #fff);
        border-radius: 16px; padding: 20px; margin-bottom: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06); text-align: center;
    }
    .business-photo, .photo-preview {
        width: 90px; height: 90px; border-radius: 50%; object-fit: cover;
        margin: 0 auto 12px; display: block;
        background: var(--tg-theme-bg-color, #eee);
        border: 3px solid var(--tg-theme-button-color, #2481cc);
    }
    .photo-placeholder, .photo-upload-box {
        width: 90px; height: 90px; border-radius: 50%; margin: 0 auto 12px;
        display: flex; align-items: center; justify-content: center;
        font-size: 36px; background: var(--tg-theme-bg-color, #eee);
        border: 3px dashed var(--tg-theme-button-color, #2481cc);
        cursor: pointer; overflow: hidden;
    }
    .photo-upload-box.lg { width: 120px; height: 120px; border-radius: 16px; font-size: 40px; }
    .photo-upload-box img { width: 100%; height: 100%; object-fit: cover; }
    .business-card .name { font-size: 18px; font-weight: 700; margin-bottom: 6px; }
    .business-card .rating { font-size: 14px; margin-bottom: 6px; color: #f5a623; }
    .business-card .address { font-size: 13px; color: var(--tg-theme-hint-color, #707579); }

    .section-title {
        font-size: 16px; font-weight: 700; margin-bottom: 12px; padding-bottom: 8px;
        border-bottom: 2px solid var(--tg-theme-button-color, #2481cc);
    }
    .menu-card {
        background: var(--tg-theme-secondary-bg-color, #fff); border-radius: 12px;
        padding: 14px 16px; margin-bottom: 10px;
        display: flex; align-items: center; justify-content: space-between;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }
    .menu-card .left { display: flex; align-items: center; gap: 10px; }
    .menu-card .icon { font-size: 22px; }
    .menu-card .label { font-size: 15px; font-weight: 600; }
    .badge {
        font-size: 11px; padding: 4px 8px; border-radius: 8px;
        background: #fff3cd; color: #856404; font-weight: 600; white-space: nowrap;
    }
    .btn-sm {
        background: var(--tg-theme-button-color, #2481cc);
        color: var(--tg-theme-button-text-color, #fff);
        border: none; padding: 8px 14px; border-radius: 8px;
        font-size: 13px; font-weight: 600; cursor: pointer;
    }
    .btn {
        width: 100%; background: var(--tg-theme-button-color, #2481cc);
        color: var(--tg-theme-button-text-color, #fff);
        border: none; padding: 14px; border-radius: 12px;
        font-size: 16px; font-weight: 600; cursor: pointer; margin-top: 10px;
    }
    .btn-secondary {
        background: var(--tg-theme-secondary-bg-color, #e8e8e8);
        color: var(--tg-theme-text-color, #000);
    }

    .service-card {
        background: var(--tg-theme-secondary-bg-color, #fff);
        border-radius: 12px; padding: 12px; margin-bottom: 10px;
        display: flex; gap: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }
    .service-card .svc-photo {
        width: 64px; height: 64px; border-radius: 10px; object-fit: cover;
        background: var(--tg-theme-bg-color, #eee); flex-shrink: 0;
        display: flex; align-items: center; justify-content: center; font-size: 28px;
    }
    .service-card .svc-body { flex: 1; min-width: 0; }
    .service-card .svc-title { font-weight: 700; font-size: 15px; margin-bottom: 4px; }
    .service-card .svc-meta { font-size: 12px; color: var(--tg-theme-hint-color, #707579); line-height: 1.5; }
    .service-card .svc-price { font-weight: 700; color: var(--tg-theme-button-color, #2481cc); margin-top: 4px; font-size: 14px; }

    .booking-card {
        background: var(--tg-theme-secondary-bg-color, #fff);
        border-radius: 12px; padding: 14px; margin-bottom: 10px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }
    .booking-card .bk-title { font-weight: 700; margin-bottom: 6px; }
    .booking-card .bk-meta { font-size: 13px; color: var(--tg-theme-hint-color, #707579); }
    .status-badge {
        display: inline-block; font-size: 11px; padding: 3px 8px;
        border-radius: 6px; font-weight: 600; margin-top: 6px;
    }
    .status-pending { background: #fff3cd; color: #856404; }
    .status-confirmed { background: #d4edda; color: #155724; }
    .status-cancelled { background: #f8d7da; color: #721c24; }

    .empty { text-align: center; color: var(--tg-theme-hint-color, #999); padding: 30px 10px; font-size: 14px; }
    .stat-card {
        background: var(--tg-theme-secondary-bg-color, #fff); border-radius: 14px;
        padding: 20px; margin-bottom: 12px; text-align: center;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }
    .stat-card .number { font-size: 32px; font-weight: 800; color: var(--tg-theme-button-color, #2481cc); }
    .stat-card .label { font-size: 14px; color: var(--tg-theme-hint-color, #707579); margin-top: 4px; }
    .stat-card.success .number { color: #4caf50; }
    .stat-card.cancel .number { color: #f44336; }


    .page-title { font-size: 20px; font-weight: 700; text-align: center; margin-bottom: 20px; }
    .tabs { display: flex; gap: 8px; margin-bottom: 20px; }
    .tab {
        flex: 1; padding: 12px 8px; border: none; border-radius: 10px;
        font-size: 14px; font-weight: 600; cursor: pointer;
        background: var(--tg-theme-secondary-bg-color, #e8e8e8);
        color: var(--tg-theme-text-color, #000);
    }
    .tab.active { background: var(--tg-theme-button-color, #2481cc); color: var(--tg-theme-button-text-color, #fff); }

    .field-label { font-size: 13px; font-weight: 600; margin-bottom: 6px; color: var(--tg-theme-hint-color, #707579); }
    .field-group { margin-bottom: 16px; }
    select, input[type="text"], input[type="number"], textarea {
        width: 100%; padding: 12px; border-radius: 10px;
        border: 1px solid var(--tg-theme-hint-color, #ccc);
        font-size: 15px; background: var(--tg-theme-bg-color, #fff);
        color: var(--tg-theme-text-color, #000);
    }
    textarea { resize: vertical; min-height: 80px; }
    .back-link {
        display: inline-block; margin-bottom: 16px;
        color: var(--tg-theme-link-color, #2481cc);
        font-size: 15px; cursor: pointer; border: none; background: none;
    }
    .error { background: #ffebee; color: #c62828; padding: 16px; border-radius: 12px; text-align: center; }
    .profile-info { background: var(--tg-theme-secondary-bg-color, #fff); border-radius: 12px; padding: 16px; margin-bottom: 16px; }
    .profile-info .row { margin-bottom: 8px; font-size: 14px; }
    .profile-info .row strong { color: var(--tg-theme-hint-color, #707579); }

    .format-toggle { display: flex; gap: 8px; }
    .format-btn {
        flex: 1; padding: 12px; border: 2px solid var(--tg-theme-hint-color, #ccc);
        border-radius: 10px; background: var(--tg-theme-bg-color, #fff);
        font-size: 14px; font-weight: 600; cursor: pointer; text-align: center;
    }
    .format-btn.active {
        border-color: var(--tg-theme-button-color, #2481cc);
        background: var(--tg-theme-button-color, #2481cc);
        color: var(--tg-theme-button-text-color, #fff);
    }

    .days-row { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
    .day-btn {
        width: 40px; height: 40px; border-radius: 50%; border: 2px solid var(--tg-theme-hint-color, #ccc);
        background: var(--tg-theme-bg-color, #fff); font-size: 12px; font-weight: 700;
        cursor: pointer; display: flex; align-items: center; justify-content: center;
    }
    .day-btn.active {
        border-color: var(--tg-theme-button-color, #2481cc);
        background: var(--tg-theme-button-color, #2481cc);
        color: var(--tg-theme-button-text-color, #fff);
    }

    .day-schedule {
        background: var(--tg-theme-secondary-bg-color, #f8f8f8);
        border-radius: 10px; padding: 12px; margin-bottom: 10px;
    }
    .day-schedule .day-name { font-weight: 700; font-size: 14px; margin-bottom: 8px; }
    .time-slots { display: flex; flex-wrap: wrap; gap: 6px; }
    .time-chip {
        padding: 8px 12px; border-radius: 8px; border: 1px solid var(--tg-theme-hint-color, #ccc);
        background: var(--tg-theme-bg-color, #fff); font-size: 13px; cursor: pointer;
    }
    .time-chip.active {
        background: var(--tg-theme-button-color, #2481cc);
        color: var(--tg-theme-button-text-color, #fff);
        border-color: var(--tg-theme-button-color, #2481cc);
    }

    .form-card {
        background: var(--tg-theme-secondary-bg-color, #fff);
        border-radius: 14px; padding: 16px; margin-bottom: 16px;
    }
    input[type="file"] { display: none; }
"""

WEBAPP_INIT = """
    const tg = window.Telegram.WebApp;
    tg.ready();
    tg.expand();
    const tgUser = tg.initDataUnsafe.user;
"""



LOCATION_DATA_JS = """
    const COUNTRIES = ['Россия','Беларусь','Казахстан','Украина','Узбекистан','Армения','Грузия'];
    const REGIONS = {
        'Россия': ['Москва','Московская область','Санкт-Петербург','Ленинградская область','Краснодарский край','Свердловская область','Новосибирская область','Ростовская область','Татарстан','Башкортостан'],
        'Беларусь': ['Минск','Минская область','Гомельская область','Брестская область'],
        'Казахстан': ['Алматы','Астана','Шымкент','Карагандинская область'],
        'Украина': ['Киев','Киевская область','Львовская область','Одесская область'],
    };
    const CITIES = {
        'Москва': ['Москва'], 'Московская область': ['Химки','Подольск','Мытищи','Королёв','Балашиха','Другой город'],
        'Санкт-Петербург': ['Санкт-Петербург'], 'Ленинградская область': ['Гатчина','Выборг','Всеволожск','Другой город'],
        'Краснодарский край': ['Краснодар','Сочи','Новороссийск','Анапа','Другой город'],
        'Свердловская область': ['Екатеринбург','Нижний Тагил','Другой город'],
        'Новосибирская область': ['Новосибирск','Бердск','Другой город'],
        'Ростовская область': ['Ростов-на-Дону','Таганрог','Другой город'],
        'Татарстан': ['Казань','Набережные Челны','Другой город'],
        'Башкортостан': ['Уфа','Стерлитамак','Другой город'],
        'Минск': ['Минск'], 'Минская область': ['Борисов','Солигорск','Другой город'],
        'Алматы': ['Алматы'], 'Астана': ['Астана'], 'Киев': ['Киев'],
    };
    function getRegions(country) { return REGIONS[country] || []; }
    function getCities(region) { return CITIES[region] || ['Другой город']; }
    function fillSelect(el, items, placeholder, selected) {
        el.innerHTML = `<option value="">${placeholder}</option>` +
            items.map(i => `<option value="${i}" ${i===selected?'selected':''}>${i}</option>`).join('');
    }
"""

SERVICE_HELPERS_JS = """
    const FITNESS_CATEGORIES = [
        'Персональные тренировки', 'Групповые занятия', 'Йога', 'Пилатес',
        'Кроссфит', 'Кардио', 'Силовые тренировки', 'Стретчинг',
        'Бокс / единоборства', 'Функциональный тренинг'
    ];
    const DURATIONS = [30, 45, 60, 90];
    const DAYS = [
        {key:'mon',label:'Пн'},{key:'tue',label:'Вт'},{key:'wed',label:'Ср'},
        {key:'thu',label:'Чт'},{key:'fri',label:'Пт'},{key:'sat',label:'Сб'},{key:'sun',label:'Вс'}
    ];
    const DAY_FULL = {mon:'Понедельник',tue:'Вторник',wed:'Среда',thu:'Четверг',fri:'Пятница',sat:'Суббота',sun:'Воскресенье'};

    function generateTimeSlots(durationMin) {
        const slots = [];
        const start = 8 * 60, end = 21 * 60;
        for (let m = start; m + durationMin <= end; m += durationMin) {
            const h = Math.floor(m/60), min = m % 60;
            slots.push(`${String(h).padStart(2,'0')}:${String(min).padStart(2,'0')}`);
        }
        return slots;
    }

    function formatLabel(fmt) {
        if (fmt === 'online') return '🌐 Онлайн';
        if (fmt === 'offline') return '🏢 Офлайн';
        return fmt || '—';
    }

    function serviceCardHtml(s) {
        const photo = s.photo_url
            ? `<img class="svc-photo" src="${s.photo_url}" alt="">`
            : `<div class="svc-photo">🛠️</div>`;
        const dur = s.training_duration ? s.training_duration + ' мин' : '—';
        return `<div class="service-card">
            ${photo}
            <div class="svc-body">
                <div class="svc-title">${s.title}</div>
                <div class="svc-meta">
                    ${s.category || 'Без категории'} · ${dur}<br>
                    ${formatLabel(s.booking_format)} · ${s.working_days_label}
                </div>
                ${s.price ? `<div class="svc-price">${s.price} ₽</div>` : ''}
            </div>
        </div>`;
    }

    function readPhotoFile(input, callback) {
        const file = input.files[0];
        if (!file) return;
        if (file.size > 3 * 1024 * 1024) { tg.showAlert('Фото не больше 3 МБ'); return; }
        const reader = new FileReader();
        reader.onload = e => callback(e.target.result);
        reader.readAsDataURL(file);
    }
"""


@app.get("/", response_class=HTMLResponse)
async def main_app():
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>{COMMON_STYLES}</style>
        <title>{MARKETPLACE_NAME}</title>
    </head>
    <body>
        <div class="app">
            <div class="content" id="main-content"></div>
                <nav class="bottom-nav" id="bottom-nav">
                    <button class="nav-item active" data-tab="home" onclick="switchTab('home')">
                        <span class="nav-icon">🏠</span>
                        <span class="nav-label">Главная</span>
                    </button>
                    <button class="nav-item" data-tab="stats" onclick="switchTab('stats')">
                        <span class="nav-icon">📊</span>
                        <span class="nav-label">Статистика</span>
                    </button>
                    <button class="nav-item" data-tab="bookings" onclick="switchTab('bookings')">
                        <span class="nav-icon">📋</span>
                        <span class="nav-label">Заявки</span>
                    </button>
                    <button class="nav-item" data-tab="profile" onclick="switchTab('profile')">
                        <span class="nav-icon">👤</span>
                        <span class="nav-label">Профиль</span>
                    </button>
                </nav>
            </div>
        <script>
        {WEBAPP_INIT}
        {SERVICE_HELPERS_JS}

        const MARKETPLACE = "{MARKETPLACE_NAME}";
        let businessData = null, servicesList = [], statsData = null, bookingsList = [];
        let currentTab = 'home';

        function renderStars(rating) {{
            const full = Math.floor(rating);
            let s = '';
            for (let i = 0; i < 5; i++) s += i < full ? '★' : '☆';
            return s + ' ' + rating.toFixed(1);
        }}

        function renderHome() {{
            if (!businessData?.has_business) {{
                document.getElementById('main-content').innerHTML =
                    '<div class="error">Бизнес не зарегистрирован. Создайте его в боте.</div>';
                return;
            }}
            const photo = businessData.business_photo_url
                ? `<img class="business-photo" src="${{businessData.business_photo_url}}" alt="">`
                : '<div class="photo-placeholder">🏪</div>';
            const name = tgUser?.username ? '@' + tgUser.username : (tgUser?.first_name || 'Пользователь');

            document.getElementById('main-content').innerHTML = `
                <div class="user-header">
                    <div class="user-role">Основатель</div>
                    <div class="user-name">${{name}}</div>
                </div>

                <div class="business-card">
                    ${{photo}}
                    <div class="name">${{businessData.business_name}}</div>
                    <div class="rating">${{renderStars(businessData.business_rating)}}</div>
                    <div class="address">📍 ${{businessData.business_address}}</div>
                </div>
                <div class="section-title">Главное меню</div>
                <div class="menu-card">
                    <div class="left"><span class="icon">🛠️</span><span class="label">Услуга</span></div>
                    <button class="btn-sm" onclick="goCreateService()">+ Создать</button>
                </div>
                <div id="home-services">${{servicesList.length ? servicesList.slice(0,3).map(serviceCardHtml).join('') : '<div class="empty">Услуги пока не созданы</div>'}}</div>
                <div class="menu-card">
                    <div class="left"><span class="icon">📦</span><span class="label">Товар</span></div>
                    <span class="badge">Функция временно не работает</span>
                </div>
                <div class="menu-card">
                    <div class="left"><span class="icon">📅</span><span class="label">Событие</span></div>
                    <button class="btn-sm" onclick="tg.showAlert('Скоро будет доступно')">+ Создать</button>
                </div>
                <div class="menu-card">
                    <div class="left"><span class="icon">📢</span><span class="label">Объявление</span></div>
                    <button class="btn-sm" onclick="tg.showAlert('Скоро будет доступно')">+ Создать</button>
                </div>
                <div class="menu-card">
                    <div class="left"><span class="icon">🏠</span><span class="label">Аренда</span></div>
                    <span class="badge">Функция временно не работает</span>
                </div>
            `;
        }}

        function renderStats() {{
            const s = statsData || {{ total_requests:0, successful_requests:0, cancelled_requests:0 }};
            document.getElementById('main-content').innerHTML = `
                <div class="page-title">📊 Статистика</div>
                <div class="stat-card"><div class="number">${{s.total_requests}}</div><div class="label">Заявки</div></div>
                <div class="stat-card success"><div class="number">${{s.successful_requests}}</div><div class="label">Успешные заявки</div></div>
                <div class="stat-card cancel"><div class="number">${{s.cancelled_requests}}</div><div class="label">Отменённые заявки</div></div>
            `;
        }}

        function renderServices() {{
            document.getElementById('main-content').innerHTML = `
                <div class="page-title">🛠️ Мои услуги</div>
                <button class="btn" onclick="goCreateService()">+ Создать услугу</button>
                <div style="margin-top:16px">${{servicesList.length ? servicesList.map(serviceCardHtml).join('') : '<div class="empty">Услуги пока не созданы</div>'}}</div>
            `;
        }}

        function statusBadge(status) {{
            const labels = {{pending:'Ожидает',confirmed:'Подтверждена',cancelled:'Отменена'}};
            return `<span class="status-badge status-${{status}}">${{labels[status] || status}}</span>`;
        }}

        function renderBookings() {{
            const html = bookingsList.length ? bookingsList.map(b => `
                <div class="booking-card">
                    <div class="bk-title">${{b.service_title}}</div>
                    <div class="bk-meta">
                        👤 ${{b.client_name}}<br>
                        📅 ${{b.booking_day_label}}, ${{b.booking_time}}
                    </div>
                    ${{statusBadge(b.status)}}
                </div>
            `).join('') : '<div class="empty">Бронирований пока нет</div>';

            document.getElementById('main-content').innerHTML = `
                <div class="page-title">📋 Заявки</div>
                ${{html}}
            `;
        }}

        function renderProfile() {{
            const b = businessData || {{}};
            const photo = b.business_photo_url
                ? `<img src="${{b.business_photo_url}}" id="profile-photo-preview" class="photo-preview" alt="">`
                : `<div class="photo-upload-box" id="profile-photo-box" onclick="document.getElementById('biz-photo-input').click()">📷</div>`;

            document.getElementById('main-content').innerHTML = `
                <div class="page-title">👤 Профиль</div>
                <div class="form-card" style="text-align:center">
                    <div class="field-label">Главная фотография бизнеса</div>
                    <div onclick="document.getElementById('biz-photo-input').click()" style="cursor:pointer">
                        ${{b.business_photo_url ? `<img src="${{b.business_photo_url}}" id="profile-photo-preview" class="photo-preview" alt="">` : `<div class="photo-upload-box" id="profile-photo-box">📷</div>`}}
                    </div>
                    <input type="file" id="biz-photo-input" accept="image/*" onchange="onBizPhotoSelect(this)">
                    <div style="font-size:12px;color:var(--tg-theme-hint-color,#999);margin-top:6px">Нажмите, чтобы загрузить фото</div>
                </div>
                <div class="form-card">
                    <div class="field-label">Название бизнеса</div>
                    <input type="text" id="biz-name" value="${{b.business_name || ''}}" maxlength="50" placeholder="Название бизнеса">
                </div>
                <div class="profile-info">
                    <div class="row"><strong>Адрес бизнеса:</strong> ${{b.business_address || '—'}}</div>
                    <div class="row"><strong>Личный адрес:</strong> ${{b.personal_address || '—'}}</div>
                </div>
                <button class="btn" onclick="saveBusinessSettings()">💾 Сохранить изменения</button>
                <button class="btn btn-secondary" onclick="window.location.href='/profile'">📝 Заполнить адрес профиля</button>
            `;
        }}

        let pendingBizPhoto = null;

        function onBizPhotoSelect(input) {{
            readPhotoFile(input, dataUrl => {{
                pendingBizPhoto = dataUrl;
                const box = document.getElementById('profile-photo-box');
                const preview = document.getElementById('profile-photo-preview');
                if (preview) {{
                    preview.src = dataUrl;
                }} else if (box) {{
                    box.innerHTML = `<img src="${{dataUrl}}" style="width:100%;height:100%;object-fit:cover">`;
                }}
            }});
        }}

        async function saveBusinessSettings() {{
            const name = document.getElementById('biz-name').value.trim();
            if (!name || name.length < 3) {{ tg.showAlert('Название бизнеса — минимум 3 символа'); return; }}
            const body = {{ market_name: name }};
            if (pendingBizPhoto) body.business_photo_url = pendingBizPhoto;
            try {{
                const res = await fetch(`/api/business/${{tgUser.id}}/settings`, {{
                    method: 'POST',
                    headers: {{'Content-Type':'application/json'}},
                    body: JSON.stringify(body),
                }});
                if (!res.ok) throw new Error('Ошибка сохранения');
                const data = await res.json();
                businessData = data.business;
                pendingBizPhoto = null;
                tg.showAlert('Сохранено!');
                renderProfile();
            }} catch(e) {{ tg.showAlert('Ошибка: ' + e.message); }}
        }}

        function goCreateService() {{ window.location.href = '/service/create'; }}

        function switchTab(tab) {{
            currentTab = tab;
            document.querySelectorAll('.nav-item').forEach(el =>
                el.classList.toggle('active', el.dataset.tab === tab));
            if (tab === 'home') renderHome();
            else if (tab === 'stats') renderStats();
            else if (tab === 'bookings') renderBookings();
            else if (tab === 'profile') renderProfile();
        }}

        async function loadAll() {{
            const [biz, svc, stats, bookings] = await Promise.all([
                fetch(`/api/business/${{tgUser.id}}`).then(r => r.json()),
                fetch(`/api/services/${{tgUser.id}}`).then(r => r.json()),
                fetch(`/api/stats/${{tgUser.id}}`).then(r => r.json()),
                fetch(`/api/bookings/${{tgUser.id}}`).then(r => r.json()),
            ]);
            businessData = biz;
            servicesList = svc.services || [];
            statsData = stats;
            bookingsList = bookings.bookings || [];
        }}

        async function init() {{
            if (!tgUser) {{
                document.getElementById('main-content').innerHTML = '<div class="error">Не удалось получить данные пользователя</div>';
                document.getElementById('bottom-nav').classList.add('hidden');
                return;
            }}
            try {{
                await loadAll();
                switchTab('home');
            }} catch(e) {{
                document.getElementById('main-content').innerHTML = `<div class="error">Ошибка: ${{e.message}}</div>`;
            }}
        }}
        init();
        </script>
    </body>
    </html>
    """


# @app.get("/service/create", response_class=HTMLResponse)
# async def create_service_page():
#     return f"""
#     <html>
#     <head>
#         <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
#         <script src="https://telegram.org/js/telegram-web-app.js"></script>
#         <style>{COMMON_STYLES}</style>
#         <title>Создание услуги</title>
#     </head>
#     <body>
#         <div class="app">
#             <div class="content">
#                 <button class="back-link" onclick="window.location.href='/'">← Назад</button>
#                 <div class="page-title">Создание услуги</div>

#                 <div class="form-card" style="text-align:center">
#                     <div class="field-label">Добавить фото</div>
#                     <div class="photo-upload-box lg" id="svc-photo-box" onclick="document.getElementById('svc-photo-input').click()">📷</div>
#                     <input type="file" id="svc-photo-input" accept="image/*" onchange="onSvcPhotoSelect(this)">
#                 </div>

#                 <div class="field-group">
#                     <div class="field-label">Название услуги *</div>
#                     <input type="text" id="svc-title" maxlength="100" placeholder="Например: Персональная тренировка">
#                 </div>
#                 <div class="field-group">
#                     <div class="field-label">Описание</div>
#                     <textarea id="svc-desc" placeholder="Опишите услугу"></textarea>
#                 </div>
#                 <div class="field-group">
#                     <div class="field-label">Категория</div>
#                     <select id="svc-category"></select>
#                 </div>
#                 <div class="field-group">
#                     <div class="field-label">Цена услуги (₽)</div>
#                     <input type="number" id="svc-price" min="0" placeholder="1500">
#                 </div>
#                 <div class="field-group">
#                     <div class="field-label">Время тренировки</div>
#                     <select id="svc-duration" onchange="onDurationChange()"></select>
#                 </div>
#                 <div class="field-group">
#                     <div class="field-label">Формат брони</div>
#                     <div class="format-toggle">
#                         <button type="button" class="format-btn active" id="fmt-online" onclick="setFormat('online')">🌐 Онлайн</button>
#                         <button type="button" class="format-btn" id="fmt-offline" onclick="setFormat('offline')">🏢 Офлайн</button>
#                     </div>
#                 </div>
#                 <div class="field-group">
#                     <div class="field-label">Рабочие дни</div>
#                     <div class="days-row" id="days-row"></div>
#                     <div id="schedule-area"></div>
#                 </div>

#                 <button class="btn" onclick="createService()">Создать</button>
#             </div>
#         </div>
#         <script>
#         {WEBAPP_INIT}
#         {SERVICE_HELPERS_JS}

#         let svcPhoto = null;
#         let bookingFormat = 'online';
#         let activeDays = {{}};
#         let selectedDuration = 60;

#         function onSvcPhotoSelect(input) {{
#             readPhotoFile(input, dataUrl => {{
#                 svcPhoto = dataUrl;
#                 document.getElementById('svc-photo-box').innerHTML =
#                     `<img src="${{dataUrl}}" style="width:100%;height:100%;object-fit:cover">`;
#             }});
#         }}

#         function setFormat(fmt) {{
#             bookingFormat = fmt;
#             document.getElementById('fmt-online').classList.toggle('active', fmt === 'online');
#             document.getElementById('fmt-offline').classList.toggle('active', fmt === 'offline');
#         }}

#         function renderDays() {{
#             document.getElementById('days-row').innerHTML = DAYS.map(d => `
#                 <button type="button" class="day-btn ${{activeDays[d.key] ? 'active' : ''}}"
#                     onclick="toggleDay('${{d.key}}')">${{d.label}}</button>
#             `).join('');
#             renderSchedule();
#         }}

#         function toggleDay(key) {{
#             if (activeDays[key]) delete activeDays[key];
#             else activeDays[key] = [];
#             renderDays();
#         }}

#         function toggleTime(dayKey, time) {{
#             if (!activeDays[dayKey]) return;
#             const arr = activeDays[dayKey];
#             const idx = arr.indexOf(time);
#             if (idx >= 0) arr.splice(idx, 1);
#             else arr.push(time);
#             arr.sort();
#             renderSchedule();
#         }}

#         function onDurationChange() {{
#             selectedDuration = parseInt(document.getElementById('svc-duration').value) || 60;
#             for (const key of Object.keys(activeDays)) activeDays[key] = [];
#             renderSchedule();
#         }}

#         function renderSchedule() {{
#             const duration = selectedDuration;
#             const slots = generateTimeSlots(duration);
#             const html = Object.keys(activeDays).map(key => `
#                 <div class="day-schedule">
#                     <div class="day-name">${{DAY_FULL[key]}}</div>
#                     <div class="time-slots">
#                         ${{slots.map(t => `
#                             <button type="button" class="time-chip ${{(activeDays[key]||[]).includes(t)?'active':''}}"
#                                 onclick="toggleTime('${{key}}','${{t}}')">${{t}}</button>
#                         `).join('')}}
#                     </div>
#                 </div>
#             `).join('');
#             document.getElementById('schedule-area').innerHTML = html;
#         }}

#         async function createService() {{
#             const title = document.getElementById('svc-title').value.trim();
#             if (!title) {{ tg.showAlert('Введите название услуги'); return; }}
#             const category = document.getElementById('svc-category').value;
#             const description = document.getElementById('svc-desc').value.trim();
#             const priceVal = document.getElementById('svc-price').value;
#             const price = priceVal ? parseFloat(priceVal) : null;
#             const training_duration = selectedDuration;

#             const schedule = {{}};
#             for (const [day, times] of Object.entries(activeDays)) {{
#                 if (times.length) schedule[day] = times;
#             }}
#             if (!Object.keys(schedule).length) {{
#                 tg.showAlert('Выберите рабочие дни и время занятий');
#                 return;
#             }}

#             try {{
#                 const res = await fetch(`/api/services/${{tgUser.id}}`, {{
#                     method: 'POST',
#                     headers: {{'Content-Type':'application/json'}},
#                     body: JSON.stringify({{
#                         title, description: description || null, photo_url: svcPhoto,
#                         category, price, training_duration,
#                         booking_format: bookingFormat,
#                         working_schedule: schedule,
#                     }}),
#                 }});
#                 if (!res.ok) throw new Error('Ошибка сохранения');
#                 tg.showAlert('Услуга создана!', () => {{ window.location.href = '/'; }});
#             }} catch(e) {{ tg.showAlert('Ошибка: ' + e.message); }}
#         }}

#         function init() {{
#             if (!tgUser) return;
#             fillSelect(document.getElementById('svc-category'),
#                 FITNESS_CATEGORIES, 'Выберите категорию', '');
#             const durEl = document.getElementById('svc-duration');
#             durEl.innerHTML = '<option value="">Выберите длительность</option>' +
#                 DURATIONS.map(d => `<option value="${{d}}" ${{d===60?'selected':''}}>${{d}} мин</option>`).join('');
#             selectedDuration = 60;
#             renderDays();
#         }}
#         init();

#         function fillSelect(el, items, placeholder, selected) {{
#             if (!el) return;
#             el.innerHTML = `<option value="">${{placehol{{d}}" ${{d===60?'selected':''}}>${{d}} мин</option>`).join('');

#             // Устанавливаем начальную длительность
#             selectedDuration = 60;

#             // Добавляем обработчик изменения длительности
#             durEl.onchange = function() {{
#                 selectedDuration = parseInt(this.value) || 60;
#                 // Очищаем выбранные времена для всех дней (так как слоты изменятся)
#                 for (const key of Object.keys(activeDays)) {{
#                     activeDays[key] = [];
#                 }}
#                 renderSchedule(); // Перерисовываем расписание с новыми слотами
#                 renderDays();     // Обновляем отображение дней
#             }};

#             // Отрисовываем дни и расписание
#             renderDays();
#         }}
#         init();
#         </script>
#     </body>
#     </html>
#     """

@app.get("/service/create", response_class=HTMLResponse)
async def create_service_page():
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>{COMMON_STYLES}</style>
        <title>Создание услуги</title>
    </head>
    <body>
        <div class="app">
            <div class="content">
                <button class="back-link" onclick="window.location.href='/'">← Назад</button>
                <div class="page-title">Создание услуги</div>

                <div class="form-card" style="text-align:center">
                    <div class="field-label">Добавить фото</div>
                    <div class="photo-upload-box lg" id="svc-photo-box" onclick="document.getElementById('svc-photo-input').click()">📷</div>
                    <input type="file" id="svc-photo-input" accept="image/*" onchange="onSvcPhotoSelect(this)">
                </div>

                <div class="field-group">
                    <div class="field-label">Название услуги *</div>
                    <input type="text" id="svc-title" maxlength="100" placeholder="Например: Персональная тренировка">
                </div>
                <div class="field-group">
                    <div class="field-label">Описание</div>
                    <textarea id="svc-desc" placeholder="Опишите услугу"></textarea>
                </div>
                <div class="field-group">
                    <div class="field-label">Категория</div>
                    <select id="svc-category"></select>
                </div>
                <div class="field-group">
                    <div class="field-label">Цена услуги (₽)</div>
                    <input type="number" id="svc-price" min="0" placeholder="1500">
                </div>
                <div class="field-group">
                    <div class="field-label">Время тренировки</div>
                    <select id="svc-duration"></select>
                </div>
                <div class="field-group">
                    <div class="field-label">Формат брони</div>
                    <div class="format-toggle">
                        <button type="button" class="format-btn active" id="fmt-online" onclick="setFormat('online')">🌐 Онлайн</button>
                        <button type="button" class="format-btn" id="fmt-offline" onclick="setFormat('offline')">🏢 Офлайн</button>
                    </div>
                </div>
                <div class="field-group">
                    <div class="field-label">Рабочие дни</div>
                    <div class="days-row" id="days-row"></div>
                    <div id="schedule-area"></div>
                </div>

                <button class="btn" onclick="createService()">Создать</button>
            </div>
        </div>
        <script>
        {WEBAPP_INIT}
        {SERVICE_HELPERS_JS}

        let svcPhoto = null;
        let bookingFormat = 'online';
        let activeDays = {{}};
        let selectedDuration = 60;

        function onSvcPhotoSelect(input) {{
            readPhotoFile(input, dataUrl => {{
                svcPhoto = dataUrl;
                document.getElementById('svc-photo-box').innerHTML =
                    `<img src="${{dataUrl}}" style="width:100%;height:100%;object-fit:cover">`;
            }});
        }}

        function setFormat(fmt) {{
            bookingFormat = fmt;
            document.getElementById('fmt-online').classList.toggle('active', fmt === 'online');
            document.getElementById('fmt-offline').classList.toggle('active', fmt === 'offline');
        }}

        function renderDays() {{
            const container = document.getElementById('days-row');
            if (!container) return;
            container.innerHTML = DAYS.map(d => `
                <button type="button" class="day-btn ${{activeDays[d.key] ? 'active' : ''}}"
                    onclick="toggleDay('${{d.key}}')">${{d.label}}</button>
            `).join('');
            renderSchedule();
        }}

        function toggleDay(key) {{
            if (activeDays[key]) delete activeDays[key];
            else activeDays[key] = [];
            renderDays();
        }}

        function toggleTime(dayKey, time) {{
            if (!activeDays[dayKey]) return;
            const arr = activeDays[dayKey];
            const idx = arr.indexOf(time);
            if (idx >= 0) arr.splice(idx, 1);
            else arr.push(time);
            arr.sort();
            renderSchedule();
        }}

        function renderSchedule() {{
            const duration = selectedDuration;
            const slots = generateTimeSlots(duration);
            const container = document.getElementById('schedule-area');
            if (!container) return;
            const html = Object.keys(activeDays).map(key => `
                <div class="day-schedule">
                    <div class="day-name">${{DAY_FULL[key]}}</div>
                    <div class="time-slots">
                        ${{slots.map(t => `
                            <button type="button" class="time-chip ${{(activeDays[key]||[]).includes(t) ? 'active' : ''}}"
                                onclick="toggleTime('${{key}}','${{t}}')">${{t}}</button>
                        `).join('')}}
                    </div>
                </div>
            `).join('');
            container.innerHTML = html;
        }}

        async function createService() {{
            const title = document.getElementById('svc-title').value.trim();
            if (!title) {{ tg.showAlert('Введите название услуги'); return; }}
            const category = document.getElementById('svc-category').value;
            const description = document.getElementById('svc-desc').value.trim();
            const priceVal = document.getElementById('svc-price').value;
            const price = priceVal ? parseFloat(priceVal) : null;
            const training_duration = selectedDuration;

            const schedule = {{}};
            for (const [day, times] of Object.entries(activeDays)) {{
                if (times.length) schedule[day] = times;
            }}
            if (!Object.keys(schedule).length) {{
                tg.showAlert('Выберите рабочие дни и время занятий');
                return;
            }}

            try {{
                const res = await fetch(`/api/services/${{tgUser.id}}`, {{
                    method: 'POST',
                    headers: {{'Content-Type':'application/json'}},
                    body: JSON.stringify({{
                        title, description: description || null, photo_url: svcPhoto,
                        category, price, training_duration,
                        booking_format: bookingFormat,
                        working_schedule: schedule,
                    }}),
                }});
                if (!res.ok) throw new Error('Ошибка сохранения');
                tg.showAlert('Услуга создана!', () => {{ window.location.href = '/'; }});
            }} catch(e) {{ tg.showAlert('Ошибка: ' + e.message); }}
        }}

        function init() {{
            if (!tgUser) return;

            // Заполняем категории
            const catSelect = document.getElementById('svc-category');
            if (catSelect) {{
                catSelect.innerHTML = '<option value="">Выберите категорию</option>' +
                    FITNESS_CATEGORIES.map(c => `<option value="${{c}}">${{c}}</option>`).join('');
            }}

            // Заполняем длительности
            const durEl = document.getElementById('svc-duration');
            if (durEl) {{
                durEl.innerHTML = '<option value="">Выберите длительность</option>' +
                    DURATIONS.map(d => `<option value="${{d}}" ${{d === 60 ? 'selected' : ''}}>${{d}} мин</option>`).join('');
                
                durEl.onchange = function() {{
                    selectedDuration = parseInt(this.value) || 60;
                    for (const key of Object.keys(activeDays)) {{
                        activeDays[key] = [];
                    }}
                    renderSchedule();
                    renderDays();
                }};
            }}

            renderDays();
        }}

        init();
        </script>
    </body>
    </html>
    """




@app.get("/profile", response_class=HTMLResponse)
async def profile_fill_page():
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>{COMMON_STYLES}</style>
        <title>Заполнение профиля</title>
    </head>
    <body>
        <div class="app">
            <div class="content">
                <button class="back-link" onclick="window.location.href='/'">← Назад</button>
                <div class="page-title">Заполнение профиля</div>
                <div class="tabs">
                    <button class="tab active" id="tab-business" onclick="switchTab('business')">Бизнес профиль</button>
                    <button class="tab" id="tab-personal" onclick="switchTab('personal')">Личный профиль</button>
                </div>
                <div id="form-area"></div>
            </div>
        </div>
        <script>
        {WEBAPP_INIT}
        {LOCATION_DATA_JS}

        let activeTab = 'business', profileData = {{}};

        function switchTab(tab) {{
            activeTab = tab;
            document.getElementById('tab-business').classList.toggle('active', tab === 'business');
            document.getElementById('tab-personal').classList.toggle('active', tab === 'personal');
            renderForm();
        }}

        function onCountryChange() {{
            fillSelect(document.getElementById('region'), getRegions(document.getElementById('country').value), 'Выберите область/край', '');
            fillSelect(document.getElementById('city'), [], 'Сначала выберите область', '');
        }}
        function onRegionChange() {{
            fillSelect(document.getElementById('city'), getCities(document.getElementById('region').value), 'Выберите город', '');
        }}

        function renderForm() {{
            const prefix = activeTab === 'business' ? 'business' : 'personal';
            const saved = {{
                country: profileData[prefix + '_country'] || '',
                region: profileData[prefix + '_region'] || '',
                city: profileData[prefix + '_city'] || '',
            }};
            const label = activeTab === 'business' ? 'бизнеса' : 'личного профиля';
            document.getElementById('form-area').innerHTML = `
                <div class="field-group"><div class="field-label">Страна ${{label}}</div><select id="country" onchange="onCountryChange()"></select></div>
                <div class="field-group"><div class="field-label">Область / край</div><select id="region" onchange="onRegionChange()"></select></div>
                <div class="field-group"><div class="field-label">Город</div><select id="city"></select></div>
                <button class="btn" onclick="saveProfile()">Сохранить</button>
            `;
            fillSelect(document.getElementById('country'), COUNTRIES, 'Выберите страну', saved.country);
            fillSelect(document.getElementById('region'), getRegions(saved.country), 'Выберите область/край', saved.region);
            fillSelect(document.getElementById('city'), getCities(saved.region), 'Выберите город', saved.city);
        }}

        async function saveProfile() {{
            const country = document.getElementById('country').value;
            const region = document.getElementById('region').value;
            const city = document.getElementById('city').value;
            if (!country || !region || !city) {{ tg.showAlert('Заполните все поля'); return; }}
            try {{
                const res = await fetch(`/api/profile/${{tgUser.id}}`, {{
                    method: 'POST', headers: {{'Content-Type':'application/json'}},
                    body: JSON.stringify({{ profile_type: activeTab, country, region, city }}),
                }});
                if (!res.ok) throw new Error('Ошибка');
                tg.showAlert('Профиль сохранён!', () => {{ window.location.href = '/'; }});
            }} catch(e) {{ tg.showAlert('Ошибка: ' + e.message); }}
        }}

        async function init() {{
            if (!tgUser) return;
            profileData = await fetch(`/api/business/${{tgUser.id}}`).then(r => r.json());
            renderForm();
        }}
        init();
        </script>
    </body>
    </html>
    """
