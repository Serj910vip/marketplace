import json
from typing import Any, Literal, Optional


import uuid
from pathlib import Path

from pydantic import BaseModel
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
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
from app.models.ad import Ad
from app.repositories.ad_repository import AdRepository
from app.services.file_service import save_file


from fastapi.staticfiles import StaticFiles

import os
os.makedirs("uploads", exist_ok=True)

app = FastAPI()

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

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

class AdCreateRequest(BaseModel):
    telegram_id: int
    title: str
    description: Optional[str] = None
    hidden: bool = False 

class AdUpdateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    photo_url: Optional[str] = None
    hidden: bool = False


def _ad_to_dict(ad: Ad) -> dict:
    return {
        "id": ad.id,
        "title": ad.title,
        "subtitle": ad.subtitle,
        "description": ad.description,
        "content": ad.description,
        "status": getattr(ad, "status", None) or "published",
        "hidden": ad.hidden,
        "scheduled_at": ad.scheduled_at.isoformat() if ad.scheduled_at else None,
        "published_at": ad.published_at.isoformat() if ad.published_at else None,
        "created_at": ad.created_at.isoformat() if ad.created_at else None,
    }


def _parse_hidden(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "yes")


async def _save_upload_files(files: list[UploadFile]) -> list[str]:
    urls: list[str] = []
    for file in files:
        if file and file.filename:
            urls.append(await save_file(file))
    return urls

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
            
            ads_count = await session.scalar(
                select(func.count()).select_from(Ad).where(Ad.user_id == user.id)
            ) or 0

            return JSONResponse({
                "total_requests": total,
                "successful_requests": successful,
                "cancelled_requests": cancelled,
                "ads_count": ads_count,
            })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== HTML ==========

COMMON_STYLES = """
     /* НОВЫЕ СТИЛИ ДЛЯ МЕНЮ
    :root {
        /* Цвета Telegram для светлой темы */
        --tg-theme-bg-color: #ffffff;
        --tg-theme-secondary-bg-color: #ff0000;
        --tg-theme-text-color: #000000;
        --tg-theme-hint-color: #999999;
        --tg-theme-link-color: #2481cc;
        --tg-theme-button-color: #2481cc;
        --tg-theme-button-text-color: #ffffff;
        --tg-theme-header-bg-color: #ffffff;
        --tg-theme-accent-text-color: #2481cc;
        --tg-theme-section-bg-color: #f0f0f0;
        --tg-theme-subtitle-text-color: #666666;
        --tg-theme-destructive-text-color: #e74c3c;
    }
     */
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: #0A0E0D;
        color: var(--tg-theme-text-color, #1a1a1a);
        min-height: 100vh;
        margin: 0;
    }
    .app { max-width: 480px; margin: 0 auto; min-height: 100vh; display: flex; flex-direction: column; }
    .content { flex: 1; padding: 16px 16px 88px; overflow-y: auto; }
    .hidden { display: none !important; }

    /* НОВЫЕ СТИЛИ ДЛЯ МЕНЮ */
    .bottom-nav {
        position: fixed;
        bottom: 16px;
        left: 50%;
        transform: translateX(-50%);
        width: 360px;
        height: 56px;
        background: #121918;
        border-radius: 15px;
        display: flex;
        align-items: center;
        justify-content: space-around;
        z-index: 100;
        border: 1px solid #0073FF;
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
        color: #FFFFFF;
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

    .nav-item .nav-icon svg {
        width: 24px;
        height: 24px;
        display: block;
    }

    /* Стиль для кнопки TipsterMarket */
    .my-tipmarket-btn {
        width: 100%;
        height: 70px;
        background: #003A81;
        border: none;
        border-radius: 20px;
        color: #FFFFFF;
        font-size: 20px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 4px 15px rgba(0, 58, 129, 0.25);
        margin-top: 10px;
        padding: 0 20px;
    }

    .my-tipmarket-btn:hover {
        background: rgba(0, 58, 129, 0.3);
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 58, 129, 0.3);
    }

    .my-tipmarket-btn:active {
        transform: translateY(0px);
    }

    /* Стиль для кнопки My Market */
    .my-market-btn {
        width: 100%;
        height: 70px;
        background: #121918;
        border: 1px solid #0073FF;
        border-radius: 20px;
        color: #0073FF;
        font-size: 20px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 4px 15px rgba(0, 58, 129, 0.25);
        margin-top: 10px;
        padding: 0 20px;
    }

    .my-market-btn:hover {
        background: rgba(0, 58, 129, 0.3);
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 58, 129, 0.3);
    }

    .my-market-btn:active {
        transform: translateY(0px);
    }

    .add-bot-btn {
        width: 100%;
        height: 56px;
        background: transparent;
        border: 1px solid #0073FF;
        border-radius: 20px;
        color: #FFFFFF;
        font-size: 16px;
        font-weight: 500;
        cursor: pointer;
        margin-top: 10px;
        padding: 0 20px;
    }

    .add-bot-btn:hover {
        background: rgba(0, 115, 255, 0.15);
    }

    .linked-chat-info {
        font-size: 12px;
        color: rgba(255,255,255,0.85);
        margin-top: 8px;
        text-align: center;
    }

    .post-actions-row {
        display: flex;
        gap: 10px;
        margin-top: 8px;
    }

    .post-actions-row .ad-btn-create {
        flex: 1;
        margin-top: 0;
    }

    .ad-btn-secondary {
        background: rgba(0, 58, 129, 0.3) !important;
        border: 0.5px solid #0073FF !important;
    }



    /* Линия разделитель */
    .divider-line {
        width: 360px;
        height: 1px;
        background: #435450;
        margin: 22px auto 22px auto;
    }

    /* Активный пункт - показываем иконку и текст, с белым фоном */
    .nav-item.active {
        background: #003A81;
        color: #FFFFFF;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        padding: 10px 16px;
    }

    .nav-item.active .nav-label {
        display: inline;  /* Показываем текст только у активного */
    }
    /* КОНЕЦ НОВЫХ СТИЛЕЙ */

    /* Стили для публичной страницы маркета */
    .market-header-block {
        border-bottom-left-radius: 20px;
        border-bottom-right-radius: 20px;
        padding: 0px 20px 0px 25px;
        margin-left: -16px;
        margin-right: -16px;
        box-sizing: border-box;
        margin-top: 17px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }

    .market-info-row {
        display: flex;
        align-items: flex-start;
        gap: 16px;
        margin-top: 20px;
    }

    .market-photo-wrapper {
        flex-shrink: 0;
    }

    .market-photo {
        width: 80px;
        height: 80px;
        border-radius: 50%;
        object-fit: cover;
        border: 3px solid rgba(255, 255, 255, 0.3);
    }

    .market-photo-placeholder {
        width: 80px;
        height: 80px;
        border-radius: 20%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 36px;
        background: rgba(255, 255, 255, 0.2);
        border: 3px dashed rgba(255, 255, 255, 0.3);
    }

    .market-info-wrapper {
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 6px;
    }

    .market-name {
        font-size: 14px;
        font-weight: 700;
        color: #FFFFFF;
    }

    .market-username {
        font-size: 14px;
        color: rgba(255, 255, 255, 0.7);
    }

    .market-rating {
        font-size: 14px;
        color: #f5a623;
    }

    .market-address {
        font-size: 12px;
        color: rgba(255, 255, 255, 0.8);
        margin-top: 33px;
        padding-bottom: 5px;
    }

    /* Меню квадратиками */
    .market-menu-grid {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 10px;
        margin: 20px 0;
    }

    .market-menu-item {
        background: rgba(0, 58, 129, 0.2);
        width: 60px;
        height: 60px;
        border-radius: 15px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
        border: 0.5px solid rgba(0, 115, 255, 0.4);
    }

    .market-menu-item:hover {
        background: var(--tg-theme-bg-color, #f0f0f0);
        transform: scale(0.98);
    }

    .market-menu-item.active {
        border: 0.5px solid #0073FF;
        background: #003A81;
        box-shadow: 1px 2px 6px rgb(255 255 255 / 60%);
    }

    .market-menu-item.active .market-menu-label {
        color: #FFFFFF;
    }

    .market-menu-icon {
        font-size: 24px;
    }

    .market-menu-label {
        font-size: 10px;
        font-weight: 700;
        color: #8A9593;
        text-align: center;
    }

    .market-menu-item.active .market-menu-label {
        color: #FFFFFF;
    }
    

    /* Стили для главной страницы */
    .home-header-block {
        height: 200px;
        border-bottom-left-radius: 20px;
        border-bottom-right-radius: 20px;
        padding: 20px 20px 20px 20px;
        margin-bottom: 340px;
        margin-left: -16px;
        margin-right: -16px;
        box-sizing: border-box;
        margin-top: -16px;  /* Прижимаем к верхнему краю */
    }

    .home-user-inline {
        display: flex;
        align-items: baseline;
        gap: 8px;
        margin-bottom: 16px;
    }

    .home-user-role {
        font-size: 14px;
        color: rgba(255, 255, 255, 0.7);
        font-weight: 500;
    }

    .home-user-name {
        font-size: 14px;
        font-weight: 700;
        color: #FFFFFF;
    }

    .home-business-card {
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        text-align: center;
        
    }

    .home-business-card .business-photo {
        width: 80px;
        height: 80px;
        border-radius: 20%;
        object-fit: cover;
        margin: 0 auto 12px;
        display: block;
        background: var(--tg-theme-bg-color, #eee);
        border: 3px solid rgba(255, 255, 255, 0.3);
    }

    .home-business-card .photo-placeholder {
        width: 80px;
        height: 80px;
        border-radius: 20%;
        margin: 0 auto 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 36px;
        background: rgba(255, 255, 255, 0.2);
        border: 3px dashed rgba(255, 255, 255, 0.3);
    }

    .home-business-name {
        font-size: 14px;
        font-weight: 700;
        color: #FFFFFF;
        margin-top: 17px;
        margin-bottom: 20px;
    }

    .home-business-rating {
        font-size: 14px;
        color: #f5a623;
        margin-top: 14px;
        margin-bottom: 13px;
    }

    .home-business-address {
        font-size: 13px;
        color: #FFFFFF;
        margin-bottom: 20px;
    }

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
        width: 80px; height: 80px; border-radius: 20%; object-fit: cover;
        margin: 0 auto 12px; display: block;
        background: var(--tg-theme-bg-color, #eee);
        border: 3px solid var(--tg-theme-button-color, #2481cc);
    }
    .photo-placeholder, .photo-upload-box {
        width: 80px; height: 80px; border-radius: 20%; margin: 0 auto 12px;
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
        font-size: 10px; 
        margin-bottom: 12px; 
        padding-bottom: 8px;
        margin-top: 15px;
        margin-left: 10px;
    }
    /*
    .menu-card {
        background: rgba(0, 58, 129, 0.3); 
        border-radius: 12px;
        padding: 14px 16px; 
        margin-bottom: 10px;
        display: flex; 
        align-items: center; 
        justify-content: space-between;
        border: 0.5px solid rgba(0, 115, 255, 0.6);
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }

    .menu-card {
        background: #FFFFFF;  
        border-radius: 20px;  
        padding: 14px 16px;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);  
        border: 1px solid rgba(0, 0, 0, 0.2);  
    }
    .menu-card .left { display: flex; align-items: center; gap: 10px; }
    .menu-card .icon { font-size: 22px; }
    .menu-card .label { font-size: 20px; font-weight: 600; }*/


    



    /* НОВЫЕ СТИЛИ ДЛЯ КНОПОК (ГЛАВНАЯ И СТАТИСТИКА) */
   /* Одна общая белая рамка для всех кнопок на главной */
    .accordion-item {
        background: #FFFFFF;
        border-radius: 20px;
        padding: 8px 12px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        border: 1px solid rgba(0, 0, 0, 0.2);
        margin-bottom: 10px;
        position: relative;
        z-index: 2;
    }

    .accordion-item:first-of-type {
        margin-top: 35px;
    }

    .accordion-item:not(:first-of-type) {
        margin-top: 0;
        margin-bottom: 10px;
    }

    
    .menu-container-home {
        background: #121918;
        border-radius: 20px;
        padding: 8px 12px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        border: 0.5px solid rgba(67, 84, 80, 0.6);
        margin-bottom: 10px;
        position: relative;
        z-index: 2;
        margin-top: 20px;  /* Убираем отрицательный отступ */
    }

    .menu-container-stats {
        background: #121918;
        border-radius: 20px;
        padding: 8px 12px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        border: 0.5px solid rgba(67, 84, 80, 0.6);
        margin-bottom: 10px;
        position: relative;
        z-index: 2;
        margin-top: -35px;  /* Оставляем наезжание только для статистики */
    }

    /* Кнопки внутри рамки */
    .menu-card {
        background: rgba(0, 58, 129, 0.3);
        border-radius: 20px;
        padding: 14px 16px;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: none;
        border: none;
        width: 100%;
        min-height: 68px;
        box-sizing: border-box;
        cursor: pointer;
        transition: background 0.2s ease;
        border: 0.5px solid #0073FF;
    }

    .menu-card:last-child {
        margin-bottom: 0;
    }

    .menu-card:hover {
        background: #dddcdc;
    }

    .menu-card .left {
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .menu-card .icon {
        font-size: 22px;
    }

    .menu-card .label {
        font-size: 20px;
        font-weight: 500;
        color: #FFFFFF;
    }

    .menu-card .accordion-arrow {
        font-size: 14px;
        color: #707579;
        transition: transform 0.2s ease;
    }


    /* Стили для аккордеона */
    .accordion-header {
        cursor: pointer;
        transition: background 0.2s ease;
    }

    .accordion-header:hover {
        background: var(--tg-theme-bg-color, #f0f0f0);
    }

    .accordion-arrow {
        font-size: 14px;
        color: var(--tg-theme-hint-color, #707579);
        transition: transform 0.2s ease;
    }

    .accordion-content {
        display: none;
        padding: 12px 16px 16px 40px;
        background: rgba(0, 58, 129, 0.7);
        border-radius: 12px;
        margin-top: -8px;
        margin-bottom: 12px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }

    .accordion-btn {
        margin-top: 0;
        width: auto;
        background: var(--tg-theme-button-color, #2481cc);
    }

    .services-list {
        margin-top: 12px;
    }

    .services-list .service-card {
        margin-bottom: 8px;
    }

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

    /* Стили для карты баланса 
    .balance-card {
        width: 360px;
        height: 165px;
        margin: 0 auto 20px auto;
        background: rgba(255, 255, 255, 0.2);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 16px 20px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.3);
        position: relative;
    }

    .balance-row {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        margin-top: 20px;
        margin-bottom: 20px;
    }

    .balance-label {
        font-size: 16px;
        font-weight: 600;
        color: var(--tg-theme-text-color, #1a1a1a);
        opacity: 0.8;
    }

    .balance-amount {
        font-size: 22px;
        font-weight: 800;
        color: var(--tg-theme-button-color, #2481cc);
    }

    .account-label {
        font-size: 12px;
        font-weight: 500;
        color: var(--tg-theme-text-color, #1a1a1a);
        opacity: 0.6;
        margin-bottom: 4px;
        display: block;
    }

    .account-number {
        font-size: 14px;
        font-weight: 600;
        color: var(--tg-theme-text-color, #1a1a1a);
        letter-spacing: 0.5px;
        word-break: break-all;
    }
    */


    .page-title { font-size: 20px; font-weight: 700; text-align: center; margin-bottom: 20px; }
    .tabs { display: flex; gap: 8px; margin-bottom: 20px; }
    .tab {
        flex: 1; padding: 12px 8px; border: none; border-radius: 10px;
        font-size: 14px; font-weight: 600; cursor: pointer;
        background: var(--tg-theme-secondary-bg-color, #e8e8e8);
        color: var(--tg-theme-text-color, #000);
    }
    .tab.active { background: var(--tg-theme-button-color, #2481cc); color: var(--tg-theme-button-text-color, #fff); }

    .field-label { 
        font-size: 13px; 
        font-weight: 600; 
        margin-bottom: 6px; 
        text-align: center;
        margin-bottom: 20px;
        color: var(--tg-theme-hint-color, #707579); 
    }
    .field-group { margin-bottom: 16px; }
    select, input[type="text"], input[type="number"], textarea {
        width: 100%; 
        padding: 12px; 
        border-radius: 10px;
        border: 0.5px solid #0073FF;
        font-size: 15px; 
        background: rgba(0, 58, 129, 0.3);
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

    /* Стили для профиля */
    .profile-card {
        border-radius: 16px;
        margin-bottom: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }

    .profile-photo-section {
        margin-bottom: 20px;
    }

    .profile-info-section {
        text-align: center;
        margin-bottom: 20px;
    }

    .profile-business-name {
        font-size: 14px;
        font-weight: 700;
        color: #FFFFFF;
        margin-bottom: 6px;
    }

    .profile-business-address {
        font-size: 14px;
        margin-top: 16px;
        color: var(--tg-theme-hint-color, #707579);
    }

    .profile-divider {
        height: 1px;
        background: rgba(67, 84, 80, 0.6);
        margin: 10px 0;
    }
    .profile-divider-stats {
        height: 1px;
        background: rgba(67, 84, 80, 0.6);
    }

    .btn-edit-profile {
        background: #003A81;
        color: #FFFFFF;
        font-weight: 500;
        font-size: 20px;
        margin-top: 0px;
        height: 68px;
        margin-bottom: 10px;
        border-radius: 20px;

    }

    .btn-edit-profile:hover {
        background: var(--tg-theme-button-color, #2481cc);
        color: var(--tg-theme-button-text-color, #fff);
    }

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

    /* Стили для меню профиля */
    .profile-menu-section {
        margin-bottom: 20px;
    }

    .profile-menu-item {
        background: var(--tg-theme-secondary-bg-color, #fff);
        border-radius: 12px;
        padding: 14px 16px;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        cursor: pointer;
        transition: background 0.2s ease;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }

    .profile-menu-item:hover {
        background: var(--tg-theme-bg-color, #f0f0f0);
    }

    .profile-menu-left {
        display: flex;
        align-items: center;
        gap: 12px;
    }



    .profile-menu-label {
        font-size: 15px;
        font-weight: 600;
        color: var(--tg-theme-text-color, #1a1a1a);
    }

    .profile-menu-arrow {
        font-size: 14px;
        color: var(--tg-theme-hint-color, #707579);
    }

    .btn-delete-market {
        color: #FFFFFF;
        margin-top: 0px;
        font-size: 20px;
        font-weight: 500;
        height: 70px;
        background: #FF8282;
        border-radius: 20px;
        border: 0.5px solid #0073FF;
    }

    .btn-delete-market:hover {
        background: #ff3b30;
        color: #fff;
    }

    
    /* Стили для верхнего блока заявки */
    /* Стили для страницы заявок */

    .books-stats {
        background: #121918;
        padding: 6px;
        border-radius: 20px;
    }
    .bookings-menu-grid {
        display: flex;
        justify-content: space-around;
        gap: 10px;
        margin-bottom: 20px;
        flex-wrap: wrap;
    }

    .bookings-menu-item {
        background: rgba(0, 58, 129, 0.2);
        border-radius: 15px;
        width: 60px;
        height: 60px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 4px;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        border: 0.5px solid rgba(0, 115, 255, 0.4);
        text-align: center;
    }


    .bookings-menu-item:hover {
        background: #003A81;
        border-color: #0073FF;
        box-shadow: 1px 1px 4px #FFFF;
        border: 0.5px solid rgba(0, 115, 255, 0.6);
    }

    .bookings-menu-label {
        font-size: 10px;
        font-weight: 700;
        color: #8A9593;
    }

    .bookings-filter-buttons {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        justify-content: center;
        margin-bottom: 20px;
    }

    .booking-filter-btn {
        width: 160px;
        height: 41px;
        background: rgba(0, 58, 129, 0.2);
        color: #8A9593;
        border-radius: 10px;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        border: 0.5px solid rgba(0, 115, 255, 0.4);
        transition: all 0.2s ease;
    }

    .booking-filter-btn:hover {
        background: #003A81;
        color: #FFFFFF;
        border-color: #0073FF;
        box-shadow: 1px 1px 4px #FFFF;
        border: 0.5px solid rgba(0, 115, 255, 0.6);
    }

    
    /* Стили для детальной статистики */
    .stats-detail {
        padding: 8px 0;
    }

    .stats-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 3px 0px;
        margin-left: -23px;
       
    }

    .stats-row:last-child {
        border-bottom: none;
    }

    .stats-row span:first-child {
        font-size: 10px;
        color: #FFFFFF;
    }

    .stats-value {
        font-size: 10px;
        font-weight: 500;
        color: #FFFFFF;
    }


    /* Стили для единого блока статистики */
    .stats-header-block {
        height: 314px;
        border-bottom-left-radius: 20px;
        border-bottom-right-radius: 20px;
        padding: 20px 16px 0 16px;
        margin-bottom: 0;  /* Убираем отступ снизу */
        margin-left: -16px;
        margin-right: -16px;
        box-sizing: border-box;
        margin-top: -16px;
    }
    /* Стили для блока кошелька */
    .wallet-header-block {
        background: #003A81;
        height: 228px;
        border-bottom-left-radius: 20px;
        border-bottom-right-radius: 20px;
        padding: 20px 20px 0 20px;
        margin-bottom: 0;
        margin-left: -16px;
        margin-right: -16px;
        box-sizing: border-box;
    }

    /* Стили для блока подписки */
    .subscription-header-block {
        background: #003A81;
        height: 228px;
        border-bottom-left-radius: 20px;
        border-bottom-right-radius: 20px;
        padding: 20px 20px 0 20px;
        margin-bottom: 0;
        margin-left: -16px;
        margin-right: -16px;
        box-sizing: border-box;
    }

    .back-link-white {
        display: inline-block;
        color: #FFFFFF;
        font-size: 10px;
        cursor: pointer;
        border: none;
        background: none;
        padding: 0;
    }

    .back-link-white:hover {
        color: #FFFFFF;
    }

    .subscription-title {
        color: #FFFFFF;
        font-size: 22px;
        font-weight: 700;
    }

    /* Стили для блока клиентской базы */
    .clients-header-block {
        background: #003A81;
        height: 228px;
        border-bottom-left-radius: 20px;
        border-bottom-right-radius: 20px;
        padding: 20px 20px 0 20px;
        margin-bottom: 0;
        margin-left: -16px;
        margin-right: -16px;
        box-sizing: border-box;
        margin-top: -16px;  /* Прижимаем к верхнему краю */
    }

    .clients-title {
        color: #FFFFFF;
        font-size: 22px;
        font-weight: 700;
    }

    .clients-count {
        color: rgba(255, 255, 255, 0.8);
        font-size: 14px;
        margin-top: 12px;
    }
    /**/

    /* Стили для блока дополнительных сервисов */
    .services-extra-header-block {
        background: #003A81;
        height: 228px;
        border-bottom-left-radius: 20px;
        border-bottom-right-radius: 20px;
        padding: 20px 20px 0 20px;
        margin-bottom: 0;
        margin-left: -16px;
        margin-right: -16px;
        box-sizing: border-box;
        margin-top: -16px;  /* Прижимаем к верхнему краю */
    }

    .services-extra-title {
        color: #FFFFFF;
        font-size: 22px;
        font-weight: 700;
    }

    .services-extra-subtitle {
        color: rgba(255, 255, 255, 0.8);
        font-size: 14px;
        margin-top: 8px;
    }

    /* Стили для блока настроек */
    .settings-header-block {
        background: #003A81;
        height: 228px;
        border-bottom-left-radius: 20px;
        border-bottom-right-radius: 20px;
        padding: 20px 20px 0 20px;
        margin-bottom: 0;
        margin-left: -16px;
        margin-right: -16px;
        box-sizing: border-box;
        margin-top: -16px;  /* Прижимаем к верхнему краю */
    }

    .settings-title {
        color: #FFFFFF;
        font-size: 22px;
        font-weight: 700;
    }

    .settings-subtitle {
        color: rgba(255, 255, 255, 0.8);
        font-size: 14px;
        margin-top: 8px;
    }


    /* Стили для блока политики и конфиденциальности */
    .privacy-header-block {
        background: #003A81;
        height: 228px;
        border-bottom-left-radius: 20px;
        border-bottom-right-radius: 20px;
        padding: 20px 20px 0 20px;
        margin-bottom: 0;
        margin-left: -16px;
        margin-right: -16px;
        box-sizing: border-box;
        margin-top: -16px;  /* Прижимаем к верхнему краю */
    }

    .privacy-title {
        color: #FFFFFF;
        font-size: 22px;
        font-weight: 700;
    }

    .privacy-subtitle {
        color: rgba(255, 255, 255, 0.8);
        font-size: 14px;
        margin-top: 8px;
    }

    .user-header-inline {
        margin-bottom: 24px;
    }

    .user-header-inline .user-role {
        color: rgba(255, 255, 255, 0.7);
        font-size: 14px;
        margin-bottom: 4px;
    }

    .user-header-inline .user-name {
        color: #FFFFFF;
        font-size: 18px;
        font-weight: 700;
    }

    .balance-card-flat {
        background: #121918;
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 16px 20px;
        height: 150px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        border: 0.3px solid rgba(67, 84, 80, 0.6);
        margin-top: 10px;
        margin-bottom: 20px;
    }

    .balance-row-flat {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        margin-top: 60px;
        margin-bottom: 20px;
    }

    .balance-label-flat {
        font-size: 16px;
        font-weight: 500;
        color: #8A9593;
    }

    .balance-amount-flat {
        font-size: 32px;
        font-weight: 700;
        color: #8A9593;
    }

    .account-label-flat {
        font-size: 10px;
        color: #8A9593;
        margin-bottom: 4px;
        display: block;
    }

    .account-number-flat {
        font-size: 10px;
        color: #8A9593;
        letter-spacing: 0.5px;
        word-break: break-all;
    }

    /* Наезжание блоков на синий блок */
    .accordion-item {
        position: relative;
        margin-top: -15px;
        z-index: 2;
    }

    /* Первый аккордеон (Услуги) - отступ от карты баланса 35px */
    .accordion-item:first-of-type {
        margin-top: 35px;
    }

    /* Остальные аккордеоны */
    .accordion-item:not(:first-of-type) {
        margin-top: 0;
        margin-bottom: 10px;
    }

    /* Стили для меню профиля (аналогично menu-container-home) */
    .profile-menu-container {
        background: #121918;
        border-radius: 20px;
        padding: 8px 12px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        border: 0.5px solid rgba(67, 84, 80, 0.6);
        margin-bottom: 10px;
        position: relative;
        z-index: 2;
        margin-top: 228px;
    }

    /* Стили для пунктов меню профиля (аналогично menu-card) */
    .profile-menu-card {
        background: rgba(0, 58, 129, 0.3);
        border-radius: 20px;
        padding: 14px 16px;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: none;
        border: none;
        width: 100%;
        min-height: 68px;
        box-sizing: border-box;
        cursor: pointer;
        transition: background 0.2s ease;
        border: 0.5px solid rgba(0, 115, 255, 0.6);
    }

    .profile-menu-card:last-child {
        margin-bottom: 0;
    }

    .profile-menu-card:hover {
        background: var(--tg-theme-hint-color, #dddcdc);
    }

    .profile-menu-card .left {
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .profile-menu-card .icon {
        font-size: 22px;
    }

    .profile-menu-card .label {
        font-size: 20px;
        font-weight: 500;
        color: #FFFFFF;
    }

    .profile-menu-card .accordion-arrow {
        font-size: 14px;
        color: #FFFFFF;
        transition: transform 0.2s ease;
    }

    /* ===== СТИЛИ ДЛЯ СТРАНИЦЫ ОБЪЯВЛЕНИЙ ===== */

    /* Верхний блок с шапкой */
    .ads-header-block {
        padding: 20px 20px 0 20px;
        margin-bottom: 0;
        margin-left: -16px;
        margin-right: -16px;
        box-sizing: border-box;
        margin-top: -16px;
        display: flex;
        align-items: flex-start;
    }

    .ads-header-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        width: 100%;
        margin-top: 20px;
    }

    .ads-header-title {
        color: #FFFFFF;
        font-size: 12px;
        font-weight: 500;
        margin-right: 20px;
    }

    /* Кнопка создания объявления */
    .ads-create-container {
        background: #121918;
        border-radius: 20px;
        padding: 13px 17px;
        border: 0.3px solid rgba(67, 84, 80, 0.6);
        margin-top: 20px;
        width: 100%;
        box-sizing: border-box;
    }

    .ads-create-btn {
        width: 100%;
        height: 68px;
        background: #003A81;
        border: 0.5px solid #0073FF;
        border-radius: 10px;
        color: #FFFFFF;
        font-size: 20px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .ads-create-btn:hover {
        background: rgba(0, 58, 129, 0.7);
        transform: translateY(-2px);
        box-shadow: 0 4px 15px rgba(0, 58, 129, 0.3);
    }

    .ads-create-btn:active {
        transform: translateY(0px);
    }

    /* Линия разделитель */
    .ads-divider {
        width: 100%;
        height: 1px;
        background: #435450;
        margin: 22px 0;
    }

    /* Счетчик объявлений */
    .ads-count {
        font-size: 16px;
        font-weight: 500;
        color: #FFFFFF;
        margin-bottom: 16px;
    }

    /* Контейнер со списком объявлений */
    .ads-list-container {
        background: #121918;
        border-radius: 20px;
        padding: 20px;
        border: 0.5px solid rgba(67, 84, 80, 0.6);
        min-height: 200px;
    }

    /* Пустой список */
    .ads-empty {
        text-align: center;
        color: #8A9593;
        font-size: 14px;
        padding: 40px 10px;
    }

    /* Элемент объявления */
    .ads-item {
        background: rgba(0, 58, 129, 0.2);
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 10px;
        border: 0.5px solid rgba(0, 115, 255, 0.4);
    }

    .ads-item:last-child {
        margin-bottom: 0;
    }

    .ads-item-title {
        font-size: 16px;
        font-weight: 600;
        color: #FFFFFF;
        margin-bottom: 6px;
    }

    .ads-item-meta {
        font-size: 13px;
        color: #8A9593;
        margin-bottom: 6px;
    }

    .ads-item-status {
        font-size: 12px;
        color: #4caf50;
        font-weight: 500;
    }

    /* Стили для объявлений на публичной странице */
    .market-ad-item {
        background: rgba(0, 58, 129, 0.2);
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 10px;
        border: 0.5px solid rgba(0, 115, 255, 0.4);
    }

    .market-ad-item:last-child {
        margin-bottom: 0;
    }

    .market-ad-title {
        font-size: 16px;
        font-weight: 600;
        color: #FFFFFF;
        margin-bottom: 6px;
    }

    .market-ad-meta {
        font-size: 13px;
        color: #8A9593;
        margin-bottom: 6px;
    }

    .market-ad-price {
        font-size: 14px;
        font-weight: 600;
        color: #f5a623;
        margin-bottom: 6px;
    }

    .market-ad-status {
        font-size: 12px;
        color: #4caf50;
        font-weight: 500;
    }

    /* ===== СТИЛИ ДЛЯ СТРАНИЦЫ СОЗДАНИЯ ОБЪЯВЛЕНИЯ ===== */
    .ad-create-main-block {
        background: #121918;
        border-radius: 20px;
        padding: 24px 20px 20px;
        border: 0.5px solid rgba(67, 84, 80, 0.6);
        margin-bottom: 20px;
    }

    .ad-create-main-block .form-title {
        font-size: 18px;
        font-weight: 600;
        color: #FFFFFF;
        margin-bottom: 20px;
        text-align: center;
    }

    .ad-field-group {
        margin-bottom: 16px;
    }
    .ad-field-group:last-child {
        margin-bottom: 0;
    }

    .ad-field-label {
        font-size: 10px;
        font-weight: 500;
        color: #8A9593;
        margin-bottom: 12px;
        display: block;
    }

    .ad-field-input {
        width: 100%;
        padding: 14px 16px;
        background: rgba(0, 58, 129, 0.3);
        border: 0.5px solid #0073FF;
        border-radius: 20px;
        color: #FFFFFF;
        font-size: 15px;
        outline: none;
        transition: border-color 0.2s ease;
        font-family: inherit;
    }
    .ad-field-input::placeholder {
        color: rgba(255, 255, 255, 0.4);
    }
    .ad-field-input:focus {
        border-color: #4a9eff;
    }

    textarea.ad-field-input {
        min-height: 100px;
        resize: vertical;
        font-family: inherit;
    }

    select.ad-field-input {
        appearance: none;
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%238A9593' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");
        background-repeat: no-repeat;
        background-position: right 16px center;
        cursor: pointer;
    }
    select.ad-field-input option {
        background: #121918;
        color: #FFFFFF;
    }

    .ad-photo-upload-box {
        width: 100%;
        height: 160px;
        background: rgba(0, 58, 129, 0.3);
        border: 0.5px solid #0073FF;
        border-radius: 20px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 48px;
        cursor: pointer;
        transition: all 0.2s ease;
        overflow: hidden;
        color: #8A9593;
    }
    .ad-photo-upload-box:hover {
        border-color: #4a9eff;
        background: rgba(0, 58, 129, 0.4);
    }
    .ad-photo-upload-box img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }
    .ad-photo-hint {
        font-size: 12px;
        color: #8A9593;
        margin-top: 6px;
        text-align: center;
    }
    .ad-photos-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 12px;
    }
    .ad-photo-block {
        position: relative;
    }
    .ad-photo-block .ad-photo-upload-box {
        height: 120px;
        font-size: 32px;
    }
    .ad-photo-remove {
        position: absolute;
        top: 6px;
        right: 6px;
        width: 28px;
        height: 28px;
        border: none;
        border-radius: 50%;
        background: rgba(0,0,0,0.65);
        color: #fff;
        font-size: 14px;
        cursor: pointer;
        z-index: 2;
    }
    .ad-photo-add {
        border-style: dashed;
    }
    .ad-input-file {
        display: none;
    }

    .ad-btn-create {
        width: 100%;
        padding: 16px;
        background: #003A81;
        border: 0.5px solid #0073FF;
        border-radius: 10px;
        color: #FFFFFF;
        font-size: 20px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
        margin-top: 8px;
    }
    .ad-btn-create:hover {
        background: rgba(0, 58, 129, 0.8);
        transform: translateY(-1px);
    }
    .ad-btn-create:active {
        transform: translateY(0px);
    }

    /* Стили для верхнего блока объявлений */
    .ad-header-block {
        padding: 20px 20px 0 20px;
        margin-bottom: 0;
        margin-left: -16px;
        margin-right: -16px;
        box-sizing: border-box;
        margin-top: -16px;
        display: flex;
        align-items: flex-start;
    }

    .ad-header-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        width: 100%;
        margin-top: 20px;
    }

    .ad-header-title {
        color: #FFFFFF;
        font-size: 12px;
        font-weight: 500;
        margin-right: 20px;
    }
    
    /* ===== НОВЫЕ СТИЛИ ДЛЯ КАРТОЧЕК ОБЪЯВЛЕНИЙ ===== */
    .add-item{
        display: block !important;
        background: rgba(0, 58, 129, 0.3);
        border-radius: 20px;
        padding: 20px;
        border: 0.5px solid #0073FF;
        margin-bottom: 16px;
        position: relative;
    }

    .add-item-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 6px;
    }

    .add-item-title-block {
    }

    .add-item-title {
        font-size: 16px;
        font-weight: 600;
        color: #FFFFFF;
        margin-bottom: 17px;
    }

    .add-item-subtitle {
        font-size: 13px;
        color: #8A9593;
    }

    .add-item-number {
        font-size: 12px;
        color: #8A9593;
        white-space: nowrap;
        margin-left: 16px;
        padding: 4px 10px;
        background: rgba(0, 58, 129, 0.3);
        border-radius: 12px;
        border: 0.5px solid rgba(0, 115, 255, 0.4);
    }

    .add-item-date {
        font-size: 12px;
        color: #8A9593;
        margin-bottom: 16px;
    }

    .add-item-actions {
        display: flex;
        justify-content: center;
        gap: 12px;
        margin-top: 12px;
        padding-top: 12px;
    }

    .add-item-btn {
        padding: 10px 32px;
        border-radius: 12px;
        border: 0.5px solid #0073FF;
        background: #003A81;
        color: #FFFFFF;
        font-size: 20px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
        min-width: 120px;
        width: 100%;
        height: 68px;
    }

    .add-item-btn:hover {
        background: #003A81;
        transform: translateY(-1px);
        box-shadow: 0 4px 15px rgba(0, 58, 129, 0.3);
    }

    .add-item-btn:active {
        transform: translateY(0px);
    }

    .add-item-btn-edit {
        background: #003A81;
    }

    .add-item-btn-edit:hover {
        background: rgba(0, 58, 129, 0.7);
    }

    .add-item-btn-delete {
        border-color: #ff3b30;
        color: #ff3b30;
    }

    .add-item-btn-delete:hover {
        background: rgba(255, 59, 48, 0.2);
        border-color: #ff3b30;
    }

    /* ===== СТИЛИ ДЛЯ КАРТОЧЕК ОБЪЯВЛЕНИЙ НА СТРАНИЦЕ МОЙ МАРКЕТ ===== */
    .market-ads-container {
        background: #121918;
        border-radius: 20px;
        padding: 16px;
        border: 0.5px solid rgba(67, 84, 80, 0.6);
    }

    .market-ad-card {
        background: #121918;
        border-radius: 20px;
        overflow: hidden;
        margin-bottom: 16px;
        border: 0.5px solid rgba(67, 84, 80, 0.6);
    }

    .market-ad-card:last-child {
        margin-bottom: 0;
    }

    .market-ad-card-image {
        width: 100%;
        height: 157px;
        object-fit: cover;
        display: block;
        background: rgba(0, 58, 129, 0.2);
    }

    .market-ad-card-image-placeholder {
        width: 100%;
        height: 157px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(0, 58, 129, 0.2);
        font-size: 48px;
        color: #8A9593;
    }

    .market-ad-card-body {
        padding: 16px;
    }

    .market-ad-card-title {
        font-size: 16px;
        font-weight: 600;
        color: #FFFFFF;
        margin-bottom: 4px;
    }

    .market-ad-card-subtitle {
        font-size: 13px;
        color: #8A9593;
        margin-bottom: 12px;
    }

    .market-ad-card-footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
    }

    .market-ad-card-date {
        font-size: 12px;
        color: #8A9593;
    }

    .market-ad-card-rating {
        font-size: 12px;
        color: #f5a623;
    }

    .market-ad-card-btn {
        padding: 8px 20px;
        border-radius: 12px;
        border: 0.5px solid #0073FF;
        background: #003A81;
        color: #FFFFFF;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
        white-space: nowrap;
    }

    .market-ad-card-btn:hover {
        background: rgba(0, 58, 129, 0.7);
        transform: translateY(-1px);
    }

    /* ===== СТИЛИ ДЛЯ СТРАНИЦЫ ПРОСМОТРА ОБЪЯВЛЕНИЯ ===== */
    .ad-detail-page {
        padding: 0;
    }

    .ad-detail-image {
        width: 100%;
        height: 300px;
        object-fit: cover;
        display: block;
        background: rgba(0, 58, 129, 0.2);
        border-radius: 0 0 20px 20px;
    }

    .ad-detail-image-placeholder {
        width: 100%;
        height: 300px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(0, 58, 129, 0.2);
        font-size: 64px;
        color: #8A9593;
        border-radius: 0 0 20px 20px;
    }

    .ad-detail-content {
        padding: 20px 16px;
    }

    .ad-detail-title {
        font-size: 22px;
        font-weight: 700;
        color: #FFFFFF;
        margin-bottom: 8px;
    }

    .ad-detail-subtitle {
        font-size: 14px;
        color: #8A9593;
        margin-bottom: 16px;
    }

    .ad-detail-meta {
        display: flex;
        align-items: center;
        gap: 16px;
        margin-bottom: 16px;
        padding-bottom: 16px;
        border-bottom: 0.5px solid rgba(67, 84, 80, 0.6);
    }

    .ad-detail-date {
        font-size: 13px;
        color: #8A9593;
    }

    .ad-detail-rating {
        font-size: 13px;
        color: #f5a623;
    }

    .ad-detail-description {
        font-size: 15px;
        color: #FFFFFF;
        line-height: 1.6;
        margin-bottom: 24px;
        white-space: pre-wrap;
    }

    .ad-detail-rating-section {
        display: flex;
        align-items: center;
        gap: 16px;
        padding-top: 16px;
        border-top: 0.5px solid rgba(67, 84, 80, 0.6);
    }

    .ad-detail-rating-label {
        font-size: 14px;
        color: #8A9593;
    }

    .ad-detail-stars {
        display: flex;
        gap: 4px;
    }

    .ad-detail-star {
        font-size: 28px;
        cursor: pointer;
        color: #435450;
        transition: all 0.2s ease;
        background: none;
        border: none;
        padding: 0;
        line-height: 1;
    }

    .ad-detail-star:hover {
        transform: scale(1.1);
    }

    .ad-detail-star.active {
        color: #f5a623;
    }

    .ad-detail-rating-value {
        font-size: 14px;
        color: #f5a623;
        font-weight: 600;
    }

    /* ===== СТИЛИ ДЛЯ ФИЛЬТРА ОБЪЯВЛЕНИЙ ===== */
    .ads-filter-container {
        display: flex;
        gap: 12px;
        justify-content: center;
        margin-bottom: 20px;
    }

    .ads-filter-btn {
        width: 158px;
        height: 38px;
        border-radius: 10px;
        border: 0.5px solid rgba(0, 115, 255, 0.4);
        background: rgba(0, 58, 129, 0.2);
        color: #8A9593;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .ads-filter-btn:hover {
        background: rgba(0, 58, 129, 0.4);
        border-color: #0073FF;
    }

    .ads-filter-btn.active {
        background: #003A81;
        color: #FFFFFF;
        border-color: #0073FF;
        box-shadow: 0 2px 8px rgba(0, 58, 129, 0.3);
    }

    /* ===== СТИЛИ ДЛЯ ПОЛЗУНКА (TOGGLE) ===== */
    .toggle-container {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-top: 8px;
        padding: 12px 16px;
        background: rgba(0, 58, 129, 0.2);
        border-radius: 12px;
        border: 0.5px solid rgba(0, 115, 255, 0.4);
    }

    .toggle-label {
        font-size: 14px;
        color: #FFFFFF;
        font-weight: 500;
    }

    .toggle-status {
        font-size: 13px;
        color: #8A9593;
        margin-left: auto;
    }

    .toggle-status.active {
        color: #4caf50;
    }

    .toggle-status.inactive {
        color: #ff6b6b;
    }

    .switch {
        position: relative;
        display: inline-block;
        width: 63px;
        height: 25px;
        flex-shrink: 0;
    }

    .switch input {
        opacity: 0;
        width: 0;
        height: 0;
    }

    .slider {
        position: absolute;
        cursor: pointer;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 58, 129, 0.3);
        transition: .3s;
        border-radius: 10px;
        border: 1px solid #0073FF;
    }

    .slider:before {
        position: absolute;
        content: "";
        height: 23px;
        width: 32px;
        left: 3px;
        bottom: 1px;
        background: #0073FF;
        transition: .3s;
        border-radius: 50%;
    }

    .switch input:checked + .slider {
        background: #003A81;
    }

    .switch input:checked + .slider:before {
        transform: translateX(22px);
    }



    


    input[type="file"] { display: none; }
"""

WEBAPP_INIT = """
    const tg = window.Telegram.WebApp;
    tg.ready();
    tg.expand();
    let tgUser = tg.initDataUnsafe.user;
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

AD_PHOTOS_JS = """
    const MAX_AD_PHOTOS = 10;
    let adPhotoItems = [];

    function initAdPhotosFromUrls(urls) {
        adPhotoItems = (urls || []).filter(Boolean).map(url => ({ kind: 'existing', url }));
        renderAdPhotoBlocks();
    }

    function renderAdPhotoBlocks() {
        const grid = document.getElementById('ad-photos-grid');
        if (!grid) return;

        let html = adPhotoItems.map((item, index) => {
            const src = item.kind === 'existing' ? item.url : item.preview;
            return `
                <div class="ad-photo-block">
                    <div class="ad-photo-upload-box" onclick="replaceAdPhoto(${index})">
                        <img src="${src}" alt="Фото">
                    </div>
                    <button type="button" class="ad-photo-remove" onclick="removeAdPhoto(${index})">✕</button>
                </div>
            `;
        }).join('');

        if (adPhotoItems.length < MAX_AD_PHOTOS) {
            html += `
                <div class="ad-photo-block">
                    <div class="ad-photo-upload-box ad-photo-add" onclick="addAdPhotoSlot()">📷 ➕</div>
                </div>
            `;
        }

        grid.innerHTML = html;
    }

    let adPhotoReplaceIndex = null;

    function addAdPhotoSlot() {
        adPhotoReplaceIndex = null;
        document.getElementById('ad-photo-input').click();
    }

    function replaceAdPhoto(index) {
        adPhotoReplaceIndex = index;
        document.getElementById('ad-photo-input').click();
    }

    function removeAdPhoto(index) {
        adPhotoItems.splice(index, 1);
        renderAdPhotoBlocks();
    }

    function onAdPhotoSelected(input) {
        const file = input.files[0];
        input.value = '';
        if (!file) return;

        if (file.size > 3 * 1024 * 1024) {
            tg.showAlert('Фото не больше 3 МБ');
            return;
        }

        const reader = new FileReader();
        reader.onload = e => {
            const item = { kind: 'new', file, preview: e.target.result };
            if (adPhotoReplaceIndex !== null) {
                adPhotoItems[adPhotoReplaceIndex] = item;
                adPhotoReplaceIndex = null;
            } else {
                adPhotoItems.push(item);
            }
            renderAdPhotoBlocks();
        };
        reader.readAsDataURL(file);
    }

    function appendAdPhotosToFormData(formData) {
        const kept = adPhotoItems
            .filter(item => item.kind === 'existing')
            .map(item => item.url);
        formData.append('existing_photos', JSON.stringify(kept));
        adPhotoItems
            .filter(item => item.kind === 'new')
            .forEach(item => formData.append('files', item.file));
    }

    function hasAdPhotos() {
        return adPhotoItems.length > 0;
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
                        <span class="nav-icon">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <g clip-path="url(#clip0_288_202)">
                                    <path d="M13.338 0.833788C12.9707 0.503224 12.4941 0.320312 12 0.320312C11.5059 0.320313 11.0293 0.503224 10.662 0.833788L0 10.4298V20.8298C0 21.6785 0.337142 22.4924 0.937258 23.0925C1.53737 23.6926 2.35131 24.0298 3.2 24.0298H20.8C21.6487 24.0298 22.4626 23.6926 23.0627 23.0925C23.6629 22.4924 24 21.6785 24 20.8298V10.4298L13.338 0.833788ZM15 22.0268H9V17.0008C9 16.2051 9.31607 15.4421 9.87868 14.8795C10.4413 14.3169 11.2044 14.0008 12 14.0008C12.7956 14.0008 13.5587 14.3169 14.1213 14.8795C14.6839 15.4421 15 16.2051 15 17.0008V22.0268ZM22 20.8268C22 21.1451 21.8736 21.4503 21.6485 21.6753C21.4235 21.9004 21.1183 22.0268 20.8 22.0268H17V17.0008C17 15.6747 16.4732 14.4029 15.5355 13.4653C14.5979 12.5276 13.3261 12.0008 12 12.0008C10.6739 12.0008 9.40215 12.5276 8.46447 13.4653C7.52678 14.4029 7 15.6747 7 17.0008V22.0268H3.2C2.88174 22.0268 2.57652 21.9004 2.35147 21.6753C2.12643 21.4503 2 21.1451 2 20.8268V11.3198L12 2.31979L22 11.3198V20.8268Z" fill="currentColor"/>
                                </g>
                                <defs>
                                    <clipPath id="clip0_288_202">
                                        <rect width="24" height="24" fill="white"/>
                                    </clipPath>
                                </defs>
                            </svg>
                            
                        </span>
                        <span class="nav-label">Главная</span>
                    </button>
                    <button class="nav-item" data-tab="stats" onclick="switchTab('stats')">
                        <span class="nav-icon">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <g clip-path="url(#clip0_288_205)">
                                    <path d="M3 21.976C2.73478 21.976 2.48043 21.8706 2.29289 21.6831C2.10536 21.4956 2 21.2412 2 20.976V0H0V20.976C0 21.7716 0.31607 22.5347 0.87868 23.0973C1.44129 23.6599 2.20435 23.976 3 23.976H24V21.976H3Z" fill="currentColor"/>
                                    <path d="M7 12H5V19H7V12Z" fill="currentColor"/>
                                    <path d="M12 10H10V19H12V10Z" fill="currentColor"/>
                                    <path d="M17 13H15V19H17V13Z" fill="currentColor"/>
                                    <path d="M22 9H20V19H22V9Z" fill="currentColor"/>
                                    <path d="M11 4.41397L16 9.41397L23.707 1.70697L22.293 0.292969L16 6.58597L11 1.58597L5.29297 7.29297L6.70697 8.70697L11 4.41397Z" fill="currentColor"/>
                                </g>
                                <defs>
                                    <clipPath id="clip0_288_205">
                                        <rect width="24" height="24" fill="white"/>
                                    </clipPath>
                                </defs>
                            </svg>

                        </span>
                        <span class="nav-label">Статистика</span>
                    </button>
                    <button class="nav-item" data-tab="bookings" onclick="switchTab('bookings')">
                        <span class="nav-icon">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <g clip-path="url(#clip0_288_206)">
                                <path d="M23.2594 16.2002L20.6594 6.82917C20.1042 4.82459 18.8945 3.06331 17.2227 1.82566C15.5509 0.588005 13.5132 -0.0549039 11.4339 -0.000744217C9.35453 0.0534155 7.35306 0.801531 5.74799 2.12454C4.14292 3.44754 3.02649 5.26941 2.5764 7.30017L0.565404 16.3502C0.468096 16.7886 0.47047 17.2433 0.572349 17.6807C0.674228 18.1181 0.873013 18.5271 1.15404 18.8774C1.43506 19.2277 1.79116 19.5105 2.19605 19.7048C2.60094 19.8991 3.04429 20.0001 3.4934 20.0002H7.1004C7.32992 21.1305 7.94313 22.1466 8.83615 22.8766C9.72916 23.6065 10.847 24.0052 12.0004 24.0052C13.1538 24.0052 14.2716 23.6065 15.1647 22.8766C16.0577 22.1466 16.6709 21.1305 16.9004 20.0002H20.3704C20.8325 20 21.2883 19.893 21.7023 19.6876C22.1163 19.4823 22.4772 19.184 22.7569 18.8162C23.0367 18.4484 23.2276 18.0209 23.315 17.5672C23.4023 17.1134 23.3836 16.6455 23.2604 16.2002H23.2594ZM12.0004 22.0002C11.3821 21.9976 10.7798 21.8041 10.2757 21.4461C9.77164 21.0881 9.39049 20.5831 9.1844 20.0002H14.8164C14.6103 20.5831 14.2292 21.0881 13.7251 21.4461C13.221 21.8041 12.6187 21.9976 12.0004 22.0002ZM21.1654 17.6052C21.0721 17.7289 20.9512 17.829 20.8123 17.8976C20.6734 17.9662 20.5203 18.0013 20.3654 18.0002H3.4934C3.34367 18.0001 3.19584 17.9665 3.06085 17.9017C2.92586 17.8369 2.80714 17.7426 2.71346 17.6258C2.61978 17.509 2.55352 17.3726 2.51959 17.2268C2.48566 17.0809 2.48491 16.9293 2.5174 16.7832L4.5284 7.73317C4.88276 6.13938 5.75971 4.70978 7.01986 3.67162C8.28001 2.63347 9.85103 2.04634 11.4832 2.00359C13.1153 1.96083 14.7149 2.46489 16.0277 3.43564C17.3405 4.40639 18.2911 5.78812 18.7284 7.36117L21.3284 16.7322C21.3709 16.8804 21.3782 17.0364 21.3499 17.1879C21.3216 17.3394 21.2585 17.4823 21.1654 17.6052Z" fill="currentColor"/>
                            </g>
                            <defs>
                                <clipPath id="clip0_288_206">
                                    <rect width="24" height="24" fill="white"/>
                                </clipPath>
                            </defs>
                        </svg>
                        </span>
                        <span class="nav-label">Заявки</span>
                    </button>
                    <button class="nav-item" data-tab="profile" onclick="switchTab('profile')">
                        <span class="nav-icon">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M21 24H19V18.957C18.9992 18.173 18.6874 17.4213 18.133 16.867C17.5787 16.3126 16.827 16.0008 16.043 16H7.957C7.173 16.0008 6.42134 16.3126 5.86696 16.867C5.31259 17.4213 5.00079 18.173 5 18.957V24H3V18.957C3.00159 17.6428 3.52435 16.3829 4.45363 15.4536C5.3829 14.5244 6.64281 14.0016 7.957 14H16.043C17.3572 14.0016 18.6171 14.5244 19.5464 15.4536C20.4756 16.3829 20.9984 17.6428 21 18.957V24Z" fill="currentColor"/>
                                <path d="M12 12C10.8133 12 9.65328 11.6481 8.66658 10.9888C7.67989 10.3295 6.91085 9.39246 6.45673 8.2961C6.0026 7.19975 5.88378 5.99335 6.11529 4.82946C6.3468 3.66558 6.91825 2.59648 7.75736 1.75736C8.59648 0.918247 9.66558 0.346802 10.8295 0.115291C11.9933 -0.11622 13.1997 0.00259972 14.2961 0.456726C15.3925 0.910851 16.3295 1.67989 16.9888 2.66658C17.6481 3.65328 18 4.81331 18 6C17.9984 7.59081 17.3658 9.11602 16.2409 10.2409C15.116 11.3658 13.5908 11.9984 12 12ZM12 2C11.2089 2 10.4355 2.2346 9.77772 2.67412C9.11993 3.11365 8.60724 3.73836 8.30448 4.46927C8.00173 5.20017 7.92252 6.00444 8.07686 6.78036C8.2312 7.55629 8.61217 8.26902 9.17158 8.82843C9.73099 9.38784 10.4437 9.7688 11.2196 9.92314C11.9956 10.0775 12.7998 9.99827 13.5307 9.69552C14.2616 9.39277 14.8864 8.88008 15.3259 8.22228C15.7654 7.56449 16 6.79113 16 6C16 4.93914 15.5786 3.92172 14.8284 3.17158C14.0783 2.42143 13.0609 2 12 2Z" fill="currentColor"/>
                            </svg>
                        
                        </span>
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
                <!-- Синий блок с наложением -->
                <div class="home-header-block">
                    <div class="home-business-card">
                        ${{photo}}
                        <div class="home-business-name">${{businessData.business_name}}</div>
                        <span class="home-user-name">${{name}}</span>
                        <div class="home-business-rating">${{renderStars(businessData.business_rating)}}</div>
                        <div class="home-business-address">📍 ${{businessData.business_address}}</div>
                    
                        
                        
                        <!-- КНОПКА MY MARKET -->
                        <div class="home-market-button">
                            <button class="my-tipmarket-btn" onclick="window.location.href='/market/${{tgUser.id}}'">
                                TipsterMarket
                            </button>
                            <button class="my-market-btn" onclick="window.location.href='/market/${{tgUser.id}}'">
                                My Market
                            </button>
                            <button class="add-bot-btn" onclick="addBotToGroup()">Добавить My Market в группу</button>
                            <div class="linked-chat-info" id="linked-chat-info"></div>
                        </div>
                    </div>
                </div>

                <!-- ЛИНИЯ -->
                <div class="divider-line"></div>


                <!-- БЛОК ПОСТОВ -->

                
                <div class="menu-container-home" style="margin-top: 20px !important;">
                    <div class="section-title">Доступно:</div>
                        <div class="menu-card" onclick="window.location.href='/posts'">
                            <div class="left">
                                <span class="label">Посты</span>
                            </div>
                            <span class="accordion-arrow" id="arrow-ad">
                                <svg width="11" height="19" viewBox="0 0 11 19" fill="none" xmlns="http://www.w3.org/2000/svg">
                                    <path d="M1.12 18.4798L1.19209e-07 17.3998L8.16 9.23984L1.19209e-07 1.07984L1.12 -0.000156403L10.36 9.23984L1.12 18.4798Z" fill="#003A81"/>
                                </svg>
                            </span>
                        </div>
                </div>
                
                
                

                <!-- ОДИН БОЛЬШОЙ БЕЛЫЙ БЛОК -->
                <div class="menu-container-home" style="margin-top: 20px !important;">
                    <div class="section-title">Создать по подписке:</div>
                    <!-- Услуги -->
                    <div class="menu-card accordion-header" onclick="toggleAccordion('service')">
                        <div class="left">
                            <span class="label">Услуги</span>
                        </div>
                        <span class="accordion-arrow" id="arrow-service">
                            <svg width="11" height="19" viewBox="0 0 11 19" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M1.12 18.4798L1.19209e-07 17.3998L8.16 9.23984L1.19209e-07 1.07984L1.12 -0.000156403L10.36 9.23984L1.12 18.4798Z" fill="#003A81"/>
                            </svg>

                        </span>
                    </div>
                    <div class="accordion-content" id="content-service">
                        <button class="btn-sm accordion-btn" onclick="goCreateService()">+ Создать услугу</button>
                        <div id="services-list" class="services-list"></div>
                    </div>

                    <!-- Товары -->
                    <div class="menu-card accordion-header" onclick="toggleAccordion('product')">
                        <div class="left">
                            <span class="label">Товары</span>
                        </div>
                        <span class="accordion-arrow" id="arrow-product">▶</span>
                    </div>
                    <div class="accordion-content" id="content-product">
                        <div class="empty">Функция временно не работает</div>
                    </div>

                    <!-- Аренда -->
                    <div class="menu-card accordion-header" onclick="toggleAccordion('rent')">
                        <div class="left">
                            <span class="label">Аренда</span>
                        </div>
                        <span class="accordion-arrow" id="arrow-rent">▶</span>
                    </div>
                    <div class="accordion-content" id="content-rent">
                        <div class="empty">Функция временно не работает</div>
                    </div>

                    <!-- События -->
                    <div class="menu-card accordion-header" onclick="toggleAccordion('event')">
                        <div class="left">
                            <span class="label">События</span>
                        </div>
                        <span class="accordion-arrow" id="arrow-event">▶</span>
                    </div>
                    <div class="accordion-content" id="content-event">
                        <button class="btn-sm accordion-btn" onclick="tg.showAlert('Скоро будет доступно')">+ Создать событие</button>
                    </div>
                </div>
            `;
                
            
            // Отображаем услуги в списке
            const servicesContainer = document.getElementById('services-list');
            if (servicesContainer) {{
                if (servicesList.length) {{
                    servicesContainer.innerHTML = servicesList.map(serviceCardHtml).join('');
                }} else {{
                    servicesContainer.innerHTML = '<div class="empty">Услуги пока не созданы</div>';
                }}
            }}
            loadLinkedChat();
        }}

        // Функция для открытия/закрытия аккордеона
        function toggleAccordion(id) {{
            const content = document.getElementById('content-' + id);
            const arrow = document.getElementById('arrow-' + id);
            if (content.style.display === 'block') {{
                content.style.display = 'none';
                arrow.innerHTML = '▶';
            }} else {{
                content.style.display = 'block';
                arrow.innerHTML = '▼';
            }}
        }}

        function renderStats() {{
            const s = statsData || {{ total_requests:0, successful_requests:0, cancelled_requests:0 }};
            const name = tgUser?.username ? '@' + tgUser.username : (tgUser?.first_name || 'Пользователь');
            const accountNumber = 'TIP-' + Math.random().toString(36).substring(2, 10).toUpperCase();
            
            const adsCount = s.ads_count || 0;

            // Данные для заглушек
            const servicesCount = 2;
            const bookingsCount = 218;
            const confirmedBookings = 198;
            const cancelledBookings = 20;
            const earnedMoney = 25680;
            
            document.getElementById('main-content').innerHTML = `
                <!-- Единый блок с фоном #003A81 -->
                <div class="stats-header-block">
                    <div class="home-user-inline">
                        <span class="home-user-role">Основатель</span>
                        <span class="home-user-name">${{name}}</span>
                    </div>
                    
                    <div class="balance-card-flat">
                        
                        <div class="account-row-flat">
                            <span class="account-label-flat">Номер аккаунта:</span>
                        </div>
                        <div class="account-number-flat">
                            ${{accountNumber}}
                        </div>
                        <div class="balance-row-flat">
                            <span class="balance-label-flat">Баланс:</span>
                            <span class="balance-amount-flat">2000.0 ₽</span>
                        </div>
                        
                    </div>
                    <div class="profile-divider-stats"></div>
                </div>
                
        
                
                <!-- ОДИН БОЛЬШОЙ БЕЛЫЙ БЛОК ДЛЯ СТАТИСТИКИ -->
                <div class="menu-container-stats">
                    <!-- Объявления -->
                    <div class="menu-card accordion-header" onclick="toggleStatsAccordion('ads-detail')">
                        <div class="left">
                            <span class="label">Объявления</span>
                            <span style="background: #003A81; padding: 2px 10px; border-radius: 12px; font-size: 12px; color: #FFFFFF;">${{adsCount}}</span>
                        </div>
                        <span class="accordion-arrow" id="stats-arrow-ads-detail">▶</span>
                    </div>
                    <div class="accordion-content" id="stats-content-ads-detail">
                        <div class="stats-detail">
                            <div class="stats-row"><span>Активных объявлений:</span><span class="stats-value">${{adsCount}}</span></div>
                            <div class="stats-row"><span>Всего просмотров:</span><span class="stats-value">2 847</span></div>
                            <div class="stats-row"><span>Кликов:</span><span class="stats-value">126</span></div>
                            <div class="stats-row"><span>Заявок с объявлений:</span><span class="stats-value">19</span></div>
                            <div class="stats-row"><span>Конверсия:</span><span class="stats-value">15%</span></div>
                        </div>
                    </div>
                    <!-- Услуги -->
                    <div class="menu-card accordion-header" onclick="toggleStatsAccordion('services-detail')">
                        <div class="left">
                            <span class="label">Услуги</span>
                        </div>
                        <span class="accordion-arrow" id="stats-arrow-services-detail">▶</span>
                    </div>
                    <div class="accordion-content" id="stats-content-services-detail">
                        <div class="stats-detail">
                            <div class="stats-row"><span>Количество услуг:</span><span class="stats-value">2</span></div>
                            <div class="stats-row"><span>Количество заявок:</span><span class="stats-value">218</span></div>
                            <div class="stats-row"><span>Подтверждённые заявки:</span><span class="stats-value">198</span></div>
                            <div class="stats-row"><span>Отменённые заявки:</span><span class="stats-value">20</span></div>
                            <div class="stats-row"><span>Заработано денег:</span><span class="stats-value">25 680 ₽</span></div>
                        </div>
                    </div>
                    
                    <!-- Товары -->
                    <div class="menu-card accordion-header" onclick="toggleStatsAccordion('products-detail')">
                        <div class="left">
                            <span class="label">Товары</span>
                        </div>
                        <span class="accordion-arrow" id="stats-arrow-products-detail">▶</span>
                    </div>
                    <div class="accordion-content" id="stats-content-products-detail">
                        <div class="stats-detail">
                            <div class="stats-row"><span>Количество товаров:</span><span class="stats-value">5</span></div>
                            <div class="stats-row"><span>Количество заказов:</span><span class="stats-value">47</span></div>
                            <div class="stats-row"><span>Выполненные заказы:</span><span class="stats-value">42</span></div>
                            <div class="stats-row"><span>Возвраты:</span><span class="stats-value">5</span></div>
                            <div class="stats-row"><span>Выручка:</span><span class="stats-value">12 350 ₽</span></div>
                        </div>
                    </div>
                    
                    <!-- Аренда -->
                    <div class="menu-card accordion-header" onclick="toggleStatsAccordion('rentals-detail')">
                        <div class="left">
                            <span class="label">Аренда</span>
                        </div>
                        <span class="accordion-arrow" id="stats-arrow-rentals-detail">▶</span>
                    </div>
                    <div class="accordion-content" id="stats-content-rentals-detail">
                        <div class="stats-detail">
                            <div class="stats-row"><span>Предметов в аренду:</span><span class="stats-value">8</span></div>
                            <div class="stats-row"><span>Активных аренд:</span><span class="stats-value">12</span></div>
                            <div class="stats-row"><span>Завершённых аренд:</span><span class="stats-value">34</span></div>
                            <div class="stats-row"><span>Отменённых аренд:</span><span class="stats-value">3</span></div>
                            <div class="stats-row"><span>Заработано:</span><span class="stats-value">8 420 ₽</span></div>
                        </div>
                    </div>
                    
                    <!-- События -->
                    <div class="menu-card accordion-header" onclick="toggleStatsAccordion('events-detail')">
                        <div class="left">
                            <span class="label">События</span>
                        </div>
                        <span class="accordion-arrow" id="stats-arrow-events-detail">▶</span>
                    </div>
                    <div class="accordion-content" id="stats-content-events-detail">
                        <div class="stats-detail">
                            <div class="stats-row"><span>Создано событий:</span><span class="stats-value">3</span></div>
                            <div class="stats-row"><span>Участников (всего):</span><span class="stats-value">156</span></div>
                            <div class="stats-row"><span>Подтверждённых записей:</span><span class="stats-value">142</span></div>
                            <div class="stats-row"><span>Отменённых записей:</span><span class="stats-value">14</span></div>
                            <div class="stats-row"><span>Сбор с билетов:</span><span class="stats-value">31 200 ₽</span></div>
                        </div>
                    </div>
                    
                    
                </div>
            `;
        }}



        // Функция для открытия/закрытия аккордеона в статистике
        function toggleStatsAccordion(id) {{
            const content = document.getElementById('stats-content-' + id);
            const arrow = document.getElementById('stats-arrow-' + id);
            if (content.style.display === 'block') {{
                content.style.display = 'none';
                arrow.innerHTML = '▶';
            }} else {{
                content.style.display = 'block';
                arrow.innerHTML = '▼';
            }}
        }}

        function renderServices() {{
            document.getElementById('main-content').innerHTML = `
                <div class="page-title">Мои услуги</div>
                <button class="btn" onclick="goCreateService()">+ Создать услугу</button>
                <div style="margin-top:16px">${{servicesList.length ? servicesList.map(serviceCardHtml).join('') : '<div class="empty">Услуги пока не созданы</div>'}}</div>
            `;
        }}

        function statusBadge(status) {{
            const labels = {{pending:'Ожидает',confirmed:'Подтверждена',cancelled:'Отменена'}};
            return `<span class="status-badge status-${{status}}">${{labels[status] || status}}</span>`;
        }}

        // Вспомогательная функция
        function generateBookingsList() {{
            if (bookingsList && bookingsList.length) {{
                return bookingsList.map(b => `
                    <div class="booking-card">
                        <div class="bk-title">${{b.service_title}}</div>
                        <div class="bk-meta">
                            👤 ${{b.client_name}}<br>
                            📅 ${{b.booking_day_label}}, ${{b.booking_time}}
                        </div>
                        ${{statusBadge(b.status)}}
                    </div>
                `).join('');
            }} else {{
                return '<div class="empty">Бронирований пока нет</div>';
            }}
        }}

       function renderBookings() {{
            const name = tgUser?.username ? '@' + tgUser.username : (tgUser?.first_name || 'Пользователь');
            
            document.getElementById('main-content').innerHTML = `
                <!-- Синий блок с содержимым внутри -->
                <div class="stats-header-block">
                    <div class="home-user-inline">
                        <span class="home-user-role">Основатель</span>
                        <span class="home-user-name">${{name}}</span>
                    </div>
                    
                    <div class="books-stats">
                        <div class="bookings-menu-grid">
                            <div class="bookings-menu-item" onclick="filterBookings('ads')">
                                <span class="bookings-menu-label">Объявления</span>
                            </div>
                            <div class="bookings-menu-item" onclick="filterBookings('all')">
                                <span class="bookings-menu-label">Услуги</span>
                            </div>
                            <div class="bookings-menu-item" onclick="filterBookings('products')">
                                <span class="bookings-menu-label">Товары</span>
                            </div>
                            <div class="bookings-menu-item" onclick="filterBookings('rent')">
                                <span class="bookings-menu-label">Аренда</span>
                            </div>
                            <div class="bookings-menu-item" onclick="filterBookings('events')">
                                <span class="bookings-menu-label">События</span>
                            </div>
                        </div>
                        
                        <div class="bookings-filter-buttons">
                            <button class="booking-filter-btn" onclick="filterByStatus('new')">Новые</button>
                            <button class="booking-filter-btn" onclick="filterByStatus('confirmed')">Подтверждённые</button>
                            <button class="booking-filter-btn" onclick="filterByStatus('completed')">Завершённые</button>
                            <button class="booking-filter-btn" onclick="filterByStatus('cancelled')">Отменённые</button>
                        </div>
                    </div>
                    
                    <div class="page-title">📋 Заявки</div>
                    <div id="bookings-list-container">
                        ${{generateBookingsList()}}
                    </div>
                </div>
            `;
        }}


        // Функции для фильтрации (только один раз!)
        function filterBookings(category) {{
            tg.showAlert(`Фильтр по категории: ${{category}} в разработке`);
        }}

        function filterByStatus(status) {{
            tg.showAlert(`Фильтр по статусу: ${{status}} в разработке`);
        }}

        function renderProfile() {{

            // Определяем тему Telegram
            const tg = window.Telegram?.WebApp;
            const isDark = tg?.colorScheme === 'dark';
            
            // Выбираем цвет фона
            const bgColor = isDark 
                ? '#2b2b2b'  // Темная тема — темно-серый
                : '#FFFFFF'; // Светлая тема — БЕЛЫЙ!        
            
            const b = businessData || {{}};
            const photo = b.business_photo_url
                ? `<img src="${{b.business_photo_url}}" id="profile-photo-preview" class="photo-preview" alt="">`
                : `<div class="photo-upload-box" id="profile-photo-box" onclick="document.getElementById('biz-photo-input').click()">📷</div>`;
            const name = tgUser?.username ? '@' + tgUser.username : (tgUser?.first_name || 'Пользователь');
            document.getElementById('main-content').innerHTML = `
                <div class="home-header-block">
                
                
                    <div class="profile-card">
                        <div class="profile-photo-section">
                            <div onclick="document.getElementById('biz-photo-input').click()" style="cursor:pointer; text-align:center;">
                                ${{photo}}
                            </div>
                            <input type="file" id="biz-photo-input" accept="image/*" onchange="onBizPhotoSelect(this)">
                            <div style="font-size:12px;color:var(--tg-theme-hint-color,#999);margin-top:6px; text-align:center;">Нажмите, чтобы загрузить фото</div>
                        </div>
                        
                        <div class="profile-info-section">
                            <div class="profile-business-name">${{b.business_name || 'Название маркета'}}</div>
                          
                            <div class="profile-business-address">📍 ${{b.business_address || 'Адрес не указан'}}</div>
                        </div>
                        
                        
                        
                        
                        <button class="btn btn-edit-profile" onclick="window.location.href='/profile'">Редактировать профиль</button>
                        <button class="btn btn-edit-profile" onclick="window.location.href='/profile'">Настройки</button>
                        <div class="profile-divider"></div>
                    </div>
                </div>



                 <!-- Меню профиля с теми же стилями, что и menu-container-home -->
                <div class="profile-menu-container">
                    <div class="profile-menu-card" onclick="toggleProfileMenu('wallet')">
                        <div class="left">
                            <span class="label">Кошелёк</span>
                        </div>
                        <span class="accordion-arrow" id="arrow-wallet">
                            <svg width="11" height="19" viewBox="0 0 11 19" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M1.12 18.4798L1.19209e-07 17.3998L8.16 9.23984L1.19209e-07 1.07984L1.12 -0.000156403L10.36 9.23984L1.12 18.4798Z" fill="#003A81"/>
                            </svg>

                        </span>
                    </div>
                    
                    <div class="profile-menu-card" onclick="window.location.href='/subscription'">
                        <div class="left">
                            <span class="label">Подписка</span>
                        </div>
                        <span class="accordion-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-card" onclick="window.location.href='/clients?from=profile'">
                        <div class="left">
                            <span class="label">Клиентская база</span>
                        </div>
                        <span class="accordion-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-card" onclick="window.location.href='/services-extra?from=profile'">
                        <div class="left">
                            <span class="label">Дополнительные сервисы</span>
                        </div>
                        <span class="accordion-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-card" onclick="window.location.href='/settings?from=profile'">
                        <div class="left">
                            <span class="label">Настройки</span>
                        </div>
                        <span class="accordion-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-card" onclick="window.location.href='/privacy?from=profile'">
                        <div class="left">
                            <span class="label">Политика и конфиденциальность</span>
                        </div>
                        <span class="accordion-arrow">▶</span>
                    </div>
                    <button class="btn btn-delete-market" onclick="deleteMarket()">Удалить маркет</button>
                </div>
                

            `;
        }}

        // Функция для удаления маркета
        function deleteMarket() {{
            tg.showAlert('Вы уверены, что хотите удалить маркет?', () => {{
                tg.showAlert('Функция в разработке');
            }});
        }}

        function toggleProfileMenu(id) {{
            const content = document.getElementById('content-' + id);
            const arrow = document.getElementById('arrow-' + id);
            
            if (!content || !arrow) return; // Если элемент не найден — выходим
            
            if (content.style.display === 'block') {{
                content.style.display = 'none';
                arrow.classList.remove('open');
            }} else {{
                content.style.display = 'block';
                arrow.classList.add('open');
            }}
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

        async function loadLinkedChat() {{
            const el = document.getElementById('linked-chat-info');
            if (!el || !tgUser) return;
            try {{
                const res = await fetch(`/api/user/${{tgUser.id}}/channel`);
                const data = await res.json();
                if (data.linked) {{
                    const typeLabel = data.chat_type === 'channel' ? 'Канал' : 'Группа';
                    el.textContent = `✅ ${{typeLabel}} подключена: ${{data.chat_title}}`;
                }} else {{
                    el.textContent = 'Бот не подключён к группе или каналу';
                }}
            }} catch(e) {{
                el.textContent = '';
            }}
        }}

        async function addBotToGroup() {{
            try {{
                const res = await fetch('/api/bot/username');
                const data = await res.json();
                if (!data.username) {{
                    tg.showAlert('Не удалось получить имя бота');
                    return;
                }}
                tg.showPopup({{
                    title: 'Подключение бота',
                    message: 'Выберите, куда добавить бота:',
                    buttons: [
                        {{id: 'group', type: 'default', text: 'В группу'}},
                        {{id: 'channel', type: 'default', text: 'В канал'}},
                        {{type: 'cancel'}}
                    ]
                }}, (btnId) => {{
                    if (btnId === 'group') {{
                        tg.openTelegramLink(`https://t.me/${{data.username}}?startgroup=connect`);
                    }} else if (btnId === 'channel') {{
                        tg.openTelegramLink(`https://t.me/${{data.username}}?startchannel&admin=post_messages`);
                    }}
                }});
            }} catch(e) {{
                tg.showAlert('Ошибка: ' + e.message);
            }}
        }}

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
            try {{
                console.log('🔄 Загружаем данные с сервера...');
                
                const [biz, svc, stats, bookings] = await Promise.all([
                    fetch(`/api/business/${{tgUser.id}}`).then(r => r.json()),
                    fetch(`/api/services/${{tgUser.id}}`).then(r => r.json()),
                    fetch(`/api/stats/${{tgUser.id}}`).then(r => r.json()),
                    fetch(`/api/bookings/${{tgUser.id}}`).then(r => r.json()),
                ]);
                
                // Проверяем: есть ли бизнес на сервере
                if (biz && biz.has_business === true) {{
                    console.log('✅ Бизнес найден на сервере:', biz.business_name);
                    businessData = biz;
                    servicesList = svc.services || [];
                    statsData = stats;
                    bookingsList = bookings.bookings || [];
                }} else {{
                    console.log('ℹ️ Бизнес НЕ найден на сервере, будут созданы тестовые данные');
                    businessData = null;
                    servicesList = [];
                    statsData = null;
                    bookingsList = [];
                }}
            }} catch(e) {{
                console.warn('⚠️ Ошибка загрузки с сервера:', e.message);
                businessData = null;
                servicesList = [];
                statsData = null;
                bookingsList = [];
            }}
        }}

        // ===================== ФУНКЦИЯ СОЗДАНИЯ ТЕСТОВОГО БИЗНЕСА =====================
        function createTestBusiness() {{
            console.log('🔧 СОЗДАЕМ ТЕСТОВЫЙ БИЗНЕС...');
            
            // ТЕСТОВЫЙ БИЗНЕС
            businessData = {{
                has_business: true,
                business_name: "Тестовый Маркет",
                business_photo_url: null,
                business_rating: 4.8,
                business_address: "Москва, ул. Тестовая, д. 1",
                business_country: "Россия",
                business_region: "Москва",
                business_city: "Москва",
                username: tgUser?.username || "test_user",
                market_created_at: new Date().toISOString()
            }};
            
            // ТЕСТОВЫЕ УСЛУГИ
            servicesList = [
                {{
                    id: 1,
                    title: "Персональная тренировка",
                    description: "Индивидуальное занятие с профессиональным тренером",
                    price: 1500,
                    category: "Персональные тренировки",
                    training_duration: 60,
                    booking_format: "online",
                    working_days_label: "Пн, Ср, Пт",
                    photo_url: null,
                    created_at: new Date().toISOString()
                }},
                {{
                    id: 2,
                    title: "Групповая йога",
                    description: "Занятия йогой в группе до 10 человек",
                    price: 800,
                    category: "Йога",
                    training_duration: 45,
                    booking_format: "offline",
                    working_days_label: "Вт, Чт",
                    photo_url: null,
                    created_at: new Date().toISOString()
                }},
                {{
                    id: 3,
                    title: "Кроссфит",
                    description: "Интенсивные функциональные тренировки",
                    price: 1200,
                    category: "Кроссфит",
                    training_duration: 50,
                    booking_format: "online",
                    working_days_label: "Пн, Вт, Чт, Пт",
                    photo_url: null,
                    created_at: new Date().toISOString()
                }}
            ];
            
            // ТЕСТОВАЯ СТАТИСТИКА
            statsData = {{
                total_requests: 25,
                successful_requests: 20,
                cancelled_requests: 5
            }};
            
            // ТЕСТОВЫЕ БРОНИРОВАНИЯ
            bookingsList = [
                {{
                    id: 1,
                    service_id: 1,
                    service_title: "Персональная тренировка",
                    client_name: "Иван Петров",
                    booking_day: "mon",
                    booking_day_label: "Пн",
                    booking_time: "10:00",
                    status: "confirmed",
                    created_at: new Date().toISOString()
                }},
                {{
                    id: 2,
                    service_id: 2,
                    service_title: "Групповая йога",
                    client_name: "Мария Смирнова",
                    booking_day: "wed",
                    booking_day_label: "Ср",
                    booking_time: "18:30",
                    status: "pending",
                    created_at: new Date().toISOString()
                }},
                {{
                    id: 3,
                    service_id: 3,
                    service_title: "Кроссфит",
                    client_name: "Алексей Иванов",
                    booking_day: "fri",
                    booking_day_label: "Пт",
                    booking_time: "09:00",
                    status: "confirmed",
                    created_at: new Date().toISOString()
                }}
            ];
            
            console.log('✅ Тестовый бизнес создан!');
        }}

        async function init() {{
            // ============ ТЕСТОВЫЙ РЕЖИМ ============
            // Если нет пользователя - создаем тестового
            if (!tgUser) {{
                console.log('🔧 Создаем тестового пользователя...');
                
                // Создаем тестового пользователя
                tgUser = {{
                    id: 123456789,
                    username: 'test_user',
                    first_name: 'Тестовый',
                    last_name: 'Пользователь'
                }};
                
                // Показываем предупреждение о тестовом режиме
                const mainContent = document.getElementById('main-content');
                if (mainContent) {{
                    mainContent.innerHTML = `
                        <div style="background: #fff3cd; color: #856404; padding: 12px; border-radius: 8px; margin-bottom: 16px; text-align: center; font-weight: 600; border: 2px solid #ffc107;">
                            ⚠️ РЕЖИМ ТЕСТИРОВАНИЯ: Данные пользователя заглушка
                        </div>
                    `;
                }}
            }}
            // ========================================
            
            try {{
                // Загружаем данные с сервера
                await loadAll();
                
                // ============ СОЗДАЕМ ТЕСТОВЫЙ БИЗНЕС ============
                // Если бизнес не найден - создаем тестовый
                if (!businessData || !businessData.has_business) {{
                    console.log('🔧 Создаем тестовый бизнес...');
                    
                    // Тестовые данные бизнеса
                    businessData = {{
                        has_business: true,
                        business_name: "Тестовый Маркет",
                        business_photo_url: null,
                        business_rating: 4.8,
                        business_address: "Москва, ул. Тестовая, д. 1",
                        business_country: "Россия",
                        business_region: "Москва",
                        business_city: "Москва",
                        username: tgUser?.username || "test_user",
                        market_created_at: new Date().toISOString()
                    }};
                    
                    // Тестовые услуги
                    servicesList = [
                        {{
                            id: 1,
                            title: "Персональная тренировка",
                            description: "Индивидуальное занятие с профессиональным тренером",
                            price: 1500,
                            category: "Персональные тренировки",
                            training_duration: 60,
                            booking_format: "online",
                            working_days_label: "Пн, Ср, Пт",
                            photo_url: null,
                            created_at: new Date().toISOString()
                        }},
                        {{
                            id: 2,
                            title: "Групповая йога",
                            description: "Занятия йогой в группе до 10 человек",
                            price: 800,
                            category: "Йога",
                            training_duration: 45,
                            booking_format: "offline",
                            working_days_label: "Вт, Чт",
                            photo_url: null,
                            created_at: new Date().toISOString()
                        }},
                        {{
                            id: 3,
                            title: "Кроссфит",
                            description: "Интенсивные функциональные тренировки",
                            price: 1200,
                            category: "Кроссфит",
                            training_duration: 50,
                            booking_format: "online",
                            working_days_label: "Пн, Вт, Чт, Пт",
                            photo_url: null,
                            created_at: new Date().toISOString()
                        }}
                    ];
                    
                    // Тестовая статистика
                    statsData = {{
                        total_requests: 25,
                        successful_requests: 20,
                        cancelled_requests: 5
                    }};
                    
                    // Тестовые бронирования
                    bookingsList = [
                        {{
                            id: 1,
                            service_id: 1,
                            service_title: "Персональная тренировка",
                            client_name: "Иван Петров",
                            booking_day: "mon",
                            booking_day_label: "Пн",
                            booking_time: "10:00",
                            status: "confirmed",
                            created_at: new Date().toISOString()
                        }},
                        {{
                            id: 2,
                            service_id: 2,
                            service_title: "Групповая йога",
                            client_name: "Мария Смирнова",
                            booking_day: "wed",
                            booking_day_label: "Ср",
                            booking_time: "18:30",
                            status: "pending",
                            created_at: new Date().toISOString()
                        }},
                        {{
                            id: 3,
                            service_id: 3,
                            service_title: "Кроссфит",
                            client_name: "Алексей Иванов",
                            booking_day: "fri",
                            booking_day_label: "Пт",
                            booking_time: "09:00",
                            status: "confirmed",
                            created_at: new Date().toISOString()
                        }}
                    ];
                    
                    // Убираем предупреждение о тестовом режиме, если оно было
                    const mainContent = document.getElementById('main-content');
                    if (mainContent && mainContent.innerHTML.includes('РЕЖИМ ТЕСТИРОВАНИЯ')) {{
                        mainContent.innerHTML = '';
                    }}
                }}
                // ================================================
                
                // Проверяем параметр tab в URL
                const urlParams = new URLSearchParams(window.location.search);
                const tab = urlParams.get('tab') || 'home';
                switchTab(tab);
                
            }} catch(e) {{
                console.error('❌ Ошибка:', e);
                // При ошибке тоже создаем тестовые данные
                if (!businessData) {{
                    businessData = {{
                        has_business: true,
                        business_name: "Тестовый Маркет (оффлайн)",
                        business_photo_url: null,
                        business_rating: 4.5,
                        business_address: "Москва, ул. Тестовая, д. 1",
                        username: tgUser?.username || "test_user"
                    }};
                }}
                if (!servicesList || servicesList.length === 0) {{
                    servicesList = [
                        {{
                            id: 1,
                            title: "Тестовая услуга",
                            description: "Описание тестовой услуги",
                            price: 1000,
                            category: "Персональные тренировки",
                            training_duration: 60,
                            booking_format: "online",
                            working_days_label: "Пн, Ср, Пт",
                            photo_url: null
                        }}
                    ];
                }}
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
#                 <button class="back-link" onclick="window.location.href='/?tab=home'">← Назад</button>
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
                <button class="back-link" onclick="history.back()">← Назад</button>
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
                <button class="back-link" onclick="history.back()">← Назад</button>
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


@app.get("/wallet", response_class=HTMLResponse)
async def wallet_page():
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>{COMMON_STYLES}</style>
        <title>Кошелёк</title>
    </head>
    <body>
        <div class="app">
            <div class="content">
               <button class="back-link" onclick="history.back()">← Назад</button>
                
                <!-- Пустой синий блок -->
                <div class="wallet-header-block"></div>
                
                <div class="page-title">💰 Кошелёк</div>
                
                <div class="profile-card">
                    <div class="profile-info-section">
                        <div style="font-size:48px; margin-bottom:16px;">💳</div>
                        <div class="profile-business-name">Баланс: 2000.0 ₽</div>
                        <div class="profile-business-address" style="margin-top:8px;">Номер аккаунта: TIP-XXXX-XXXX</div>
                    </div>
                </div>
                
                <div class="profile-menu-section">
                    <div class="section-title">Операции</div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('История операций в разработке')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">📊 История операций</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Пополнить баланс в разработке')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">➕ Пополнить</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Вывод средств в разработке')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">➖ Вывести</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                </div>
            </div>
        </div>
        <script>
        {WEBAPP_INIT}
        </script>
    </body>
    </html>
    """


@app.get("/subscription", response_class=HTMLResponse)
async def subscription_page():
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>{COMMON_STYLES}</style>
        <title>Подписка</title>
    </head>
    <body>
        <div class="app">
            <div class="content">
                <!-- Синий блок с кнопкой назад внутри -->
                <div class="subscription-header-block">
                    <button class="back-link-white" onclick="history.back()">← Назад</button>
                    <div class="subscription-title">📋 Подписка</div>
                </div>
                
                <div class="profile-card">
                    <div class="profile-info-section">
                        <div style="font-size:48px; margin-bottom:16px;">⭐</div>
                        <div class="profile-business-name">Базовый тариф</div>
                        <div class="profile-business-address" style="margin-top:8px;">До 5 услуг · Базовая статистика</div>
                    </div>
                </div>
                
                <div class="profile-menu-section">
                    <div class="section-title">Доступные тарифы</div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Базовый тариф - 0 ₽/мес')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">📦 Базовый</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">Бесплатно</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Про тариф - 499 ₽/мес')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">🚀 Про</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">499 ₽/мес</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Бизнес тариф - 999 ₽/мес')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">💼 Бизнес</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">999 ₽/мес</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                </div>
            </div>
        </div>
        <script>
        {WEBAPP_INIT}
        </script>
    </body>
    </html>
    """


@app.get("/clients", response_class=HTMLResponse)
async def clients_page():
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>{COMMON_STYLES}</style>
        <title>Клиентская база</title>
    </head>
    <body>
        <div class="app">
            <div class="content" style="padding-top: 0;">
                <!-- Синий блок с кнопкой назад внутри, прижат к верху -->
                <div class="clients-header-block">
                    <button class="back-link-white" onclick="window.location.href='/?tab=profile'">← Назад</button>
                    <div class="clients-title">👥 Клиентская база</div>
                    <div class="clients-count">Всего клиентов: 156</div>
                </div>
                
                <div class="profile-card" style="margin-top: 20px;">
                    <div class="profile-info-section">
                        <div style="font-size:48px; margin-bottom:16px;">📊</div>
                        <div class="profile-business-name">Активных клиентов: 89</div>
                        <div class="profile-business-address" style="margin-top:8px;">Новых за месяц: 24</div>
                    </div>
                </div>
                
                <div class="profile-menu-section">
                    <div class="section-title">Список клиентов</div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Иван Петров - +7 999 123-45-67')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">👤 Иван Петров</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">3 записи</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Мария Смирнова - +7 999 234-56-78')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">👤 Мария Смирнова</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">5 записей</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Алексей Иванов - +7 999 345-67-89')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">👤 Алексей Иванов</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">2 записи</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Екатерина Козлова - +7 999 456-78-90')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">👤 Екатерина Козлова</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">7 записей</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Дмитрий Сидоров - +7 999 567-89-01')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">👤 Дмитрий Сидоров</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">1 запись</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                </div>
            </div>
        </div>
        <script>
        {WEBAPP_INIT}
        
        function goBack() {{
            const urlParams = new URLSearchParams(window.location.search);
            const from = urlParams.get('from');
            
            if (from === 'profile') {{
                window.location.href = '/?tab=profile';
            }} else {{
                history.back();
            }}
        }}
        </script>
    </body>
    </html>
    """


@app.get("/services-extra", response_class=HTMLResponse)
async def services_extra_page():
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>{COMMON_STYLES}</style>
        <title>Дополнительные сервисы</title>
    </head>
    <body>
        <div class="app">
            <div class="content" style="padding-top: 0;">
                <!-- Синий блок с кнопкой назад внутри, прижат к верху -->
                <div class="services-extra-header-block">
                    <button class="back-link-white" onclick="window.location.href='/?tab=profile'">← Назад</button>
                    <div class="services-extra-title">⚡ Дополнительные сервисы</div>
                    <div class="services-extra-subtitle">Расширьте возможности вашего бизнеса</div>
                </div>
                
                <div class="profile-card" style="margin-top: 20px;">
                    <div class="profile-info-section">
                        <div style="font-size:48px; margin-bottom:16px;">🚀</div>
                        <div class="profile-business-name">Подключено сервисов: 3</div>
                        <div class="profile-business-address" style="margin-top:8px;">Доступно: 7</div>
                    </div>
                </div>
                
                <div class="profile-menu-section">
                    <div class="section-title">Доступные сервисы</div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('СМС-уведомления - 299 ₽/мес')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">📱 СМС-уведомления</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">299 ₽/мес</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Email-рассылка - 199 ₽/мес')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">📧 Email-рассылка</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">199 ₽/мес</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Чат-бот для записи - 499 ₽/мес')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">🤖 Чат-бот для записи</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">499 ₽/мес</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Аналитика и отчёты - 399 ₽/мес')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">📊 Аналитика и отчёты</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">399 ₽/мес</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Интеграция с соцсетями - 249 ₽/мес')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">🌐 Интеграция с соцсетями</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">249 ₽/мес</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('VIP-поддержка - 599 ₽/мес')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">👑 VIP-поддержка 24/7</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">599 ₽/мес</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Своя CRM-система - 799 ₽/мес')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">💼 Своя CRM-система</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">799 ₽/мес</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                </div>
            </div>
        </div>
        <script>
        {WEBAPP_INIT}
        
        function goBack() {{
            const urlParams = new URLSearchParams(window.location.search);
            const from = urlParams.get('from');
            
            if (from === 'profile') {{
                window.location.href = '/?tab=profile';
            }} else {{
                history.back();
            }}
        }}
        </script>
    </body>
    </html>
    """


@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>{COMMON_STYLES}</style>
        <title>Настройки</title>
    </head>
    <body>
        <div class="app">
            <div class="content" style="padding-top: 0;">
                <!-- Синий блок с кнопкой назад внутри, прижат к верху -->
                <div class="settings-header-block">
                    <button class="back-link-white" onclick="window.location.href='/?tab=profile'">← Назад</button>
                    <div class="settings-title">⚙️ Настройки</div>
                    <div class="settings-subtitle">Управление параметрами аккаунта</div>
                </div>
                
                <div class="profile-card" style="margin-top: 20px;">
                    <div class="profile-info-section">
                        <div style="font-size:48px; margin-bottom:16px;">🔐</div>
                        <div class="profile-business-name">Безопасность</div>
                        <div class="profile-business-address" style="margin-top:8px;">Двухфакторная аутентификация: <span style="color:#4caf50;">Включена</span></div>
                    </div>
                </div>
                
                <div class="profile-menu-section">
                    <div class="section-title">Общие настройки</div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Язык: Русский')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">🌍 Язык</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">Русский</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Тема: Светлая')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">🎨 Тема оформления</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">Светлая</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Уведомления: Включены')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">🔔 Уведомления</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">Включены</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                </div>
                
                <div class="profile-menu-section">
                    <div class="section-title">Приватность</div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Профиль: Виден всем')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">👁️ Видимость профиля</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">Виден всем</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Показывать номер телефона: Нет')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">📱 Показывать номер телефона</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">Нет</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                </div>
                
                <div class="profile-menu-section">
                    <div class="section-title">Конфиденциальность</div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Политика конфиденциальности')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">📄 Политика конфиденциальности</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Удалить все данные')" style="border: 1px solid #ff3b30;">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label" style="color: #ff3b30;">🗑️ Удалить все данные</span>
                        </div>
                        <span class="profile-menu-arrow" style="color: #ff3b30;">▶</span>
                    </div>
                </div>
            </div>
        </div>
        <script>
        {WEBAPP_INIT}
        
        function goBack() {{
            const urlParams = new URLSearchParams(window.location.search);
            const from = urlParams.get('from');
            
            if (from === 'profile') {{
                window.location.href = '/?tab=profile';
            }} else {{
                history.back();
            }}
        }}
        </script>
    </body>
    </html>
    """


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page():
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>{COMMON_STYLES}</style>
        <title>Политика и конфиденциальность</title>
    </head>
    <body>
        <div class="app">
            <div class="content" style="padding-top: 0;">
                <!-- Синий блок с кнопкой назад внутри, прижат к верху -->
                <div class="privacy-header-block">
                    <button class="back-link-white" onclick="window.location.href='/?tab=profile'">← Назад</button>
                    <div class="privacy-title">🔒 Политика и конфиденциальность</div>
                    <div class="privacy-subtitle">Ваша безопасность — наш приоритет</div>
                </div>
                
                <div class="profile-card" style="margin-top: 20px;">
                    <div class="profile-info-section">
                        <div style="font-size:48px; margin-bottom:16px;">🛡️</div>
                        <div class="profile-business-name">Защита данных</div>
                        <div class="profile-business-address" style="margin-top:8px;">Все данные защищены шифрованием</div>
                    </div>
                </div>
                
                <div class="profile-menu-section">
                    <div class="section-title">Основные положения</div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Мы собираем только необходимые данные для работы сервиса')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">📋 Сбор данных</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Ваши данные используются только для предоставления услуг')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">🔐 Использование данных</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Мы не передаём ваши данные третьим лицам без вашего согласия')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">🤝 Передача данных</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Вы можете запросить удаление всех ваших данных в любое время')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">🗑️ Удаление данных</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                </div>
                
                <div class="profile-menu-section">
                    <div class="section-title">Ваши права</div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Вы имеете право на доступ к вашим данным')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">👁️ Право на доступ</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Вы имеете право на исправление неточных данных')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">✏️ Право на исправление</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Вы имеете право на удаление ваших данных')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">🗑️ Право на удаление</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                </div>
                
                <div class="profile-menu-section">
                    <div class="section-title">Контакты</div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('support@tipster-market.com')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">📧 По вопросам конфиденциальности</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                    
                    <div class="profile-menu-item" onclick="tg.showAlert('Последнее обновление: 15 июня 2026 г.')">
                        <div class="profile-menu-left">
                            <span class="profile-menu-label">📅 Дата обновления</span>
                            <span style="font-size:12px;color:var(--tg-theme-hint-color,#707579);">15.06.2026</span>
                        </div>
                        <span class="profile-menu-arrow">▶</span>
                    </div>
                </div>
            </div>
        </div>
        <script>
        {WEBAPP_INIT}
        
        function goBack() {{
            const urlParams = new URLSearchParams(window.location.search);
            const from = urlParams.get('from');
            
            if (from === 'profile') {{
                window.location.href = '/?tab=profile';
            }} else {{
                history.back();
            }}
        }}
        </script>
    </body>
    </html>
    """

@app.get("/market/{telegram_id}", response_class=HTMLResponse)
async def public_market_page(telegram_id: int):
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>{COMMON_STYLES}</style>
        <title>Мой Маркет</title>
    </head>
    <body>
        <div class="app">
            <div class="content" id="main-content"></div>
        </div>
        <script>
        {WEBAPP_INIT}
        {SERVICE_HELPERS_JS}

        const MARKETPLACE = "{MARKETPLACE_NAME}";
        let businessData = null;
        let servicesList = [];
        let adsList = [];
        let currentTab = 'services';
        let telegramId = {telegram_id};

        // ТЕСТОВЫЕ ОБЪЯВЛЕНИЯ
        const TEST_ADS = [
            {{
                id: 1,
                title: "Скидка на персональные тренировки",
                description: "Персональные тренировки со скидкой 20%\\nАкция действует до конца месяца!\\nУспейте записаться!\\n\\nПодробности:\\n- Индивидуальный подход\\n- Профессиональный тренер\\n- Современное оборудование",
                rating: 4.5,
                created_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
                photo_url: null
            }},
            {{
                id: 2,
                title: "Новый курс по йоге",
                description: "Набор в группу по хатха-йоге\\nЗанятия 3 раза в неделю\\nПервый урок бесплатно!\\n\\nДля начинающих и продолжающих",
                rating: 4.8,
                created_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
                photo_url: null
            }},
            {{
                id: 3,
                title: "Спецпредложение",
                description: "Абонемент на месяц со скидкой 30%\\nТолько до конца недели!\\n\\nВключает:\\n- Неограниченные тренировки\\n- Доступ к тренажерному залу\\n- Консультация тренера",
                rating: 4.2,
                created_at: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(),
                photo_url: null
            }}
        ];

        // Данные для оценок (хранятся в localStorage)
        function getAdRating(adId) {{
            const ratings = JSON.parse(localStorage.getItem('ad_ratings') || '{{}}');
            return ratings[adId] || null;
        }}

        function setAdRating(adId, rating) {{
            const ratings = JSON.parse(localStorage.getItem('ad_ratings') || '{{}}');
            ratings[adId] = rating;
            localStorage.setItem('ad_ratings', JSON.stringify(ratings));
        }}

        function renderStars(rating) {{
            const full = Math.floor(rating);
            let s = '';
            for (let i = 0; i < 5; i++) s += i < full ? '★' : '☆';
            return s + ' ' + rating.toFixed(1);
        }}

        function renderStarsHtml(rating, interactive = false, adId = null) {{
            const full = Math.floor(rating);
            const hasHalf = rating % 1 >= 0.5;
            let html = '';
            for (let i = 1; i <= 5; i++) {{
                let star = '☆';
                if (i <= full) {{
                    star = '★';
                }} else if (i === full + 1 && hasHalf) {{
                    star = '★';
                }}
                if (interactive && adId) {{
                    html += `<button class="ad-detail-star ${{i <= (getAdRating(adId) || 0) ? 'active' : ''}}" onclick="setRating(${{adId}}, ${{i}})">★</button>`;
                }} else {{
                    html += `<span class="ad-detail-star ${{i <= rating ? 'active' : ''}}">★</span>`;
                }}
            }}
            return html;
        }}

        function renderPublicPage() {{
            if (!businessData) {{
                document.getElementById('main-content').innerHTML =
                    '<div class="error">Бизнес не найден</div>';
                return;
            }}

            const photo = businessData.business_photo_url
                ? `<img class="market-photo" src="${{businessData.business_photo_url}}" alt="">`
                : '<div class="market-photo-placeholder">🏪</div>';

            document.getElementById('main-content').innerHTML = `
                <button class="back-link-white"
                        onclick="goBack()"
                        style="position:absolute; top:16px; left:16px; z-index:10; background:rgba(0,0,0,0.5); padding:8px 12px; border-radius:12px;">
                    ← Назад
                </button>
                <div class="market-header-block">
                    <div class="market-info-row">
                        <div class="market-photo-wrapper">
                            ${{photo}}
                        </div>
                        <div class="market-info-wrapper">
                            <div class="market-name">${{businessData.business_name}}</div>
                            <div class="market-username">@${{businessData.username || 'Пользователь'}}</div>
                            <div class="market-rating">${{renderStars(businessData.business_rating)}}</div>
                        </div>
                    </div>
                    <div class="market-address">📍 ${{businessData.business_address}}</div>
                </div>

                <div class="market-menu-grid">
                    <div class="market-menu-item" data-tab="ads" onclick="switchMarketTab('ads')">
                        <span class="market-menu-label">Посты</span>
                    </div>
                    <div class="market-menu-item active" data-tab="services" onclick="switchMarketTab('services')">
                        <span class="market-menu-label">Услуги</span>
                    </div>
                    <div class="market-menu-item" data-tab="products" onclick="switchMarketTab('products')">
                        <span class="market-menu-label">Товары</span>
                    </div>
                    <div class="market-menu-item" data-tab="rent" onclick="switchMarketTab('rent')">
                        <span class="market-menu-label">Аренда</span>
                    </div>
                    <div class="market-menu-item" data-tab="events" onclick="switchMarketTab('events')">
                        <span class="market-menu-label">События</span>
                    </div>
                </div>

                <div id="market-content">
                    ${{renderTabContent('services')}}
                </div>
            `;
        }}

        function renderTabContent(tab) {{
            if (tab === 'services') {{
                if (servicesList && servicesList.length) {{
                    return servicesList.map(serviceCardHtml).join('');
                }} else {{
                    return '<div class="empty">Услуги пока не созданы</div>';
                }}
            }} else if (tab === 'products') {{
                return '<div class="empty">Товары временно не доступны</div>';
            }} else if (tab === 'rent') {{
                return '<div class="empty">Аренда временно не доступна</div>';
            }} else if (tab === 'events') {{
                return '<div class="empty">События временно не доступны</div>';
            }} else if (tab === 'ads') {{
                if (adsList && adsList.length) {{
                    return `
                        <div class="market-ads-container">
                            ${{adsList.map(post => {{
                                const createdDate = post.created_at ? new Date(post.created_at).toLocaleDateString('ru-RU') : '';
                                const subtitle = post.subtitle || 'Без подзаголовка';
                                return `
                                    <div class="market-ad-card">
                                        <div class="market-ad-card-body">
                                            <div class="market-ad-card-title">${{post.title}}</div>
                                            <div class="market-ad-card-subtitle">${{subtitle}}</div>
                                            <div class="market-ad-card-footer">
                                                <span class="market-ad-card-date">📅 ${{createdDate}}</span>
                                                <button class="market-ad-card-btn" onclick="viewAd(${{post.id}})">Посмотреть</button>
                                            </div>
                                        </div>
                                    </div>
                                `;
                            }}).join('')}}
                        </div>
                    `;
                }} else {{
                    return '<div class="empty">Постов пока нет</div>';
                }}
            }}
            return '';
        }}

        function viewAd(adId) {{
            window.location.href = `/market/ad/${{telegramId}}/${{adId}}`;
        }}

        function switchMarketTab(tab) {{
            currentTab = tab;
            document.querySelectorAll('.market-menu-item').forEach(el =>
                el.classList.toggle('active', el.dataset.tab === tab));
            document.getElementById('market-content').innerHTML = renderTabContent(tab);
        }}

        async function loadMarketData() {{
            try {{
                const [biz, svc, ads] = await Promise.all([
                    fetch(`/api/business/${{telegramId}}`).then(r => r.json()),
                    fetch(`/api/services/${{telegramId}}`).then(r => r.json()),
                    fetch(`/api/market/posts/${{telegramId}}`).then(r => r.json()),
                ]);
                
                if (!biz || !biz.has_business) {{
                    console.log('🔧 Создаем тестовый бизнес...');
                    businessData = {{
                        has_business: true,
                        business_name: "Тестовый Маркет",
                        business_photo_url: null,
                        business_rating: 4.8,
                        business_address: "Москва, ул. Тестовая, д. 1",
                        business_country: "Россия",
                        business_region: "Москва",
                        business_city: "Москва",
                        username: "test_user"
                    }};
                    
                    servicesList = [
                        {{
                            id: 1,
                            title: "Персональная тренировка",
                            description: "Индивидуальное занятие с профессиональным тренером",
                            price: 1500,
                            category: "Персональные тренировки",
                            training_duration: 60,
                            booking_format: "online",
                            working_days_label: "Пн, Ср, Пт",
                            photo_url: null,
                            created_at: new Date().toISOString()
                        }},
                        {{
                            id: 2,
                            title: "Групповая йога",
                            description: "Занятия йогой в группе до 10 человек",
                            price: 800,
                            category: "Йога",
                            training_duration: 45,
                            booking_format: "offline",
                            working_days_label: "Вт, Чт",
                            photo_url: null,
                            created_at: new Date().toISOString()
                        }}
                    ];
                }} else {{
                    businessData = biz;
                    servicesList = svc.services || [];
                }}

                if (ads.posts && ads.posts.length > 0) {{
                    adsList = ads.posts;
                }} else {{
                    adsList = [];
                }}

            }} catch(e) {{
                console.error('Ошибка загрузки:', e);
                businessData = {{
                    has_business: true,
                    business_name: "Тестовый Маркет (оффлайн)",
                    business_photo_url: null,
                    business_rating: 4.5,
                    business_address: "Москва, ул. Тестовая, д. 1",
                    username: "test_user"
                }};
                servicesList = [
                    {{
                        id: 1,
                        title: "Тестовая услуга",
                        description: "Описание тестовой услуги",
                        price: 1000,
                        category: "Персональные тренировки",
                        training_duration: 60,
                        booking_format: "online",
                        working_days_label: "Пн, Ср, Пт",
                        photo_url: null
                    }}
                ];
                adsList = [];
            }}
        }}

        async function init() {{
            await loadMarketData();
            renderPublicPage();
        }}

        function goBack() {{
            if (history.length > 1) {{
                history.back();
            }} else {{
                window.location.href = `/main/${{telegramId}}`;
            }}
        }}
        init();
        </script>
    </body>
    </html>
    """


# Legacy ad routes moved to posts_router.py

@app.get("/market/ad/{telegram_id}/{ad_id}", response_class=HTMLResponse)
async def view_ad_page(telegram_id: int, ad_id: int):
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>{COMMON_STYLES}</style>
        <title>Объявление</title>
    </head>
    <body>
        <div class="app">
            <div class="content" id="main-content" style="padding-top: 0;"></div>
        </div>
        <script>
        {WEBAPP_INIT}
        {SERVICE_HELPERS_JS}

        const telegramId = {telegram_id};
        const adId = {ad_id};

        // ТЕСТОВЫЕ ДАННЫЕ
        const TEST_ADS = [
            {{
                id: 1,
                title: "Скидка на персональные тренировки",
                description: "Персональные тренировки со скидкой 20%\\nАкция действует до конца месяца!\\nУспейте записаться!\\n\\nПодробности:\\n- Индивидуальный подход\\n- Профессиональный тренер\\n- Современное оборудование",
                rating: 4.5,
                created_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
                photo_url: null
            }},
            {{
                id: 2,
                title: "Новый курс по йоге",
                description: "Набор в группу по хатха-йоге\\nЗанятия 3 раза в неделю\\nПервый урок бесплатно!\\n\\nДля начинающих и продолжающих",
                rating: 4.8,
                created_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
                photo_url: null
            }},
            {{
                id: 3,
                title: "Спецпредложение",
                description: "Абонемент на месяц со скидкой 30%\\nТолько до конца недели!\\n\\nВключает:\\n- Неограниченные тренировки\\n- Доступ к тренажерному залу\\n- Консультация тренера",
                rating: 4.2,
                created_at: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(),
                photo_url: null
            }}
        ];

        let adData = null;
        let userRating = 0;

        function getAdRating(adId) {{
            const ratings = JSON.parse(localStorage.getItem('ad_ratings') || '{{}}');
            return ratings[adId] || null;
        }}

        function setAdRating(adId, rating) {{
            const ratings = JSON.parse(localStorage.getItem('ad_ratings') || '{{}}');
            ratings[adId] = rating;
            localStorage.setItem('ad_ratings', JSON.stringify(ratings));
            userRating = rating;
            renderAdDetail();
        }}

        function renderAdDetail() {{
            if (!adData) {{
                document.getElementById('main-content').innerHTML = 
                    '<div class="error">Объявление не найдено</div>';
                return;
            }}

            const createdDate = adData.created_at ? new Date(adData.created_at).toLocaleDateString('ru-RU') : new Date().toLocaleDateString('ru-RU');
            const rating = adData.rating || 0;
            const userRatingValue = getAdRating(adId) || 0;
            
            // Фото
            const photoHtml = adData.photo_url 
                ? `<img class="ad-detail-image" src="${{adData.photo_url}}" alt="${{adData.title}}">`
                : `<div class="ad-detail-image-placeholder">📷</div>`;
            
            // Звезды для оценки
            let starsHtml = '';
            for (let i = 1; i <= 5; i++) {{
                const isActive = i <= userRatingValue ? 'active' : '';
                starsHtml += `<button class="ad-detail-star ${{isActive}}" onclick="setRating(${{adId}}, ${{i}})">★</button>`;
            }}

            document.getElementById('main-content').innerHTML = `
                <button class="back-link-white" onclick="window.location.href='/market/${{telegramId}}'" style="position:absolute; top:16px; left:16px; z-index:10; background:rgba(0,0,0,0.5); padding:8px 12px; border-radius:12px;">
                    ← Назад
                </button>
                <div class="ad-detail-page">
                    ${{photoHtml}}
                    <div class="ad-detail-content">
                        <div class="ad-detail-title">${{adData.title}}</div>
                        <div class="ad-detail-meta">
                            <span class="ad-detail-date">📅 ${{createdDate}}</span>
                            <span class="ad-detail-rating">${{renderStars(rating)}}</span>
                        </div>
                        <div class="ad-detail-description">${{adData.description || 'Описание отсутствует'}}</div>
                        <div class="ad-detail-rating-section">
                            <span class="ad-detail-rating-label">Оцените объявление:</span>
                            <div class="ad-detail-stars">
                                ${{starsHtml}}
                            </div>
                            ${{userRatingValue > 0 ? `<span class="ad-detail-rating-value">${{userRatingValue}}.0</span>` : ''}}
                        </div>
                    </div>
                </div>
            `;
        }}

        function setRating(adId, rating) {{
            setAdRating(adId, rating);
            tg.showAlert(`Вы поставили оценку ${{rating}} из 5!`);
        }}

        function renderStars(rating) {{
            const full = Math.floor(rating);
            let s = '';
            for (let i = 0; i < 5; i++) s += i < full ? '★' : '☆';
            return s + ' ' + rating.toFixed(1);
        }}

        async function loadAdData() {{
            try {{
                const response = await fetch(`/api/ads/get/${{adId}}`);
                if (response.ok) {{
                    const data = await response.json();
                    if (data.ad) {{
                        adData = data.ad;
                        console.log('✅ Загружено реальное объявление');
                        renderAdDetail();
                        return;
                    }}
                }}
                
                const found = TEST_ADS.find(a => a.id === adId);
                if (found) {{
                    adData = found;
                    console.log('📢 Используем тестовое объявление');
                }} else {{
                    adData = TEST_ADS[0];
                    console.log('📢 Используем первое тестовое объявление');
                }}
            }} catch(e) {{
                console.error('Ошибка загрузки:', e);
                adData = TEST_ADS[0];
            }}
            renderAdDetail();
        }}


        async function init() {{
            await loadAdData();
        }}
        init();
        </script>
    </body>
    </html>
    """



@app.get("/api/market/ads/{telegram_id}")
async def get_market_ads(telegram_id: int):
    try:
        async with AsyncSessionLocal() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id)

            if not user:
                return JSONResponse({"ads": []})

            ad_repo = AdRepository(session)
            ads = await ad_repo.get_active_by_user_id(user.id)

            return JSONResponse({
                "ads": [_ad_to_dict(ad) for ad in ads]
            })

    except Exception as e:
        return JSONResponse({"ads": [], "error": str(e)})


from app.api.posts_router import router as posts_router, register_post_pages

app.include_router(posts_router)
register_post_pages(app, COMMON_STYLES, WEBAPP_INIT)