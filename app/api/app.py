from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Literal, Optional
from sqlalchemy import select
from app.database.session import AsyncSessionLocal
from app.models.user import User
from app.models.service import Service
from app.repositories.user_repository import UserRepository
from app.repositories.service_repository import ServiceRepository

app = FastAPI()

MARKETPLACE_NAME = "Tipster my market"


class ProfileUpdateRequest(BaseModel):
    profile_type: Literal["business", "personal"]
    country: str
    region: str
    city: str


class ServiceCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    price: Optional[float] = None


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
                "services": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "description": s.description,
                        "price": s.price,
                        "created_at": s.created_at.isoformat(),
                    }
                    for s in services
                ]
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
                price=body.price,
            )
            return JSONResponse({
                "success": True,
                "service": {
                    "id": service.id,
                    "title": service.title,
                    "description": service.description,
                    "price": service.price,
                    "created_at": service.created_at.isoformat(),
                },
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

            return JSONResponse({
                "total_requests": 0,
                "successful_requests": 0,
                "cancelled_requests": 0,
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
    .content { flex: 1; padding: 16px 16px 80px; overflow-y: auto; }
    .hidden { display: none !important; }

    .market-title {
        text-align: center;
        font-size: 20px;
        font-weight: 800;
        color: var(--tg-theme-button-color, #2481cc);
        margin-bottom: 6px;
        letter-spacing: 0.3px;
    }
    .user-name {
        text-align: center;
        font-size: 15px;
        color: var(--tg-theme-hint-color, #707579);
        margin-bottom: 16px;
    }

    .business-card {
        background: var(--tg-theme-secondary-bg-color, #fff);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        text-align: center;
    }
    .business-photo {
        width: 90px;
        height: 90px;
        border-radius: 50%;
        object-fit: cover;
        margin: 0 auto 12px;
        display: block;
        background: var(--tg-theme-bg-color, #eee);
        border: 3px solid var(--tg-theme-button-color, #2481cc);
    }
    .photo-placeholder {
        width: 90px;
        height: 90px;
        border-radius: 50%;
        margin: 0 auto 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 36px;
        background: var(--tg-theme-bg-color, #eee);
        border: 3px solid var(--tg-theme-button-color, #2481cc);
    }
    .business-card .name { font-size: 18px; font-weight: 700; margin-bottom: 6px; }
    .business-card .rating { font-size: 14px; margin-bottom: 6px; color: #f5a623; }
    .business-card .address { font-size: 13px; color: var(--tg-theme-hint-color, #707579); }

    .section-title {
        font-size: 16px;
        font-weight: 700;
        margin-bottom: 12px;
        padding-bottom: 8px;
        border-bottom: 2px solid var(--tg-theme-button-color, #2481cc);
    }

    .menu-card {
        background: var(--tg-theme-secondary-bg-color, #fff);
        border-radius: 12px;
        padding: 14px 16px;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }
    .menu-card .left { display: flex; align-items: center; gap: 10px; }
    .menu-card .icon { font-size: 22px; }
    .menu-card .label { font-size: 15px; font-weight: 600; }
    .badge {
        font-size: 11px;
        padding: 4px 8px;
        border-radius: 8px;
        background: #fff3cd;
        color: #856404;
        font-weight: 600;
        white-space: nowrap;
    }
    .btn-sm {
        background: var(--tg-theme-button-color, #2481cc);
        color: var(--tg-theme-button-text-color, #fff);
        border: none;
        padding: 8px 14px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
    }
    .btn {
        width: 100%;
        background: var(--tg-theme-button-color, #2481cc);
        color: var(--tg-theme-button-text-color, #fff);
        border: none;
        padding: 14px;
        border-radius: 12px;
        font-size: 16px;
        font-weight: 600;
        cursor: pointer;
        margin-top: 10px;
    }
    .btn-secondary {
        background: var(--tg-theme-secondary-bg-color, #e8e8e8);
        color: var(--tg-theme-text-color, #000);
    }

    .service-item {
        background: var(--tg-theme-secondary-bg-color, #fff);
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 8px;
        font-size: 14px;
    }
    .service-item .title { font-weight: 600; margin-bottom: 4px; }
    .service-item .meta { font-size: 12px; color: var(--tg-theme-hint-color, #707579); }
    .empty { text-align: center; color: var(--tg-theme-hint-color, #999); padding: 30px 10px; font-size: 14px; }

    .stat-card {
        background: var(--tg-theme-secondary-bg-color, #fff);
        border-radius: 14px;
        padding: 20px;
        margin-bottom: 12px;
        text-align: center;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }
    .stat-card .number { font-size: 32px; font-weight: 800; color: var(--tg-theme-button-color, #2481cc); }
    .stat-card .label { font-size: 14px; color: var(--tg-theme-hint-color, #707579); margin-top: 4px; }
    .stat-card.success .number { color: #4caf50; }
    .stat-card.cancel .number { color: #f44336; }

    .bottom-nav {
        position: fixed;
        bottom: 0;
        left: 50%;
        transform: translateX(-50%);
        width: 100%;
        max-width: 480px;
        display: flex;
        background: var(--tg-theme-secondary-bg-color, #fff);
        border-top: 1px solid rgba(0,0,0,0.08);
        z-index: 100;
        padding: 6px 0 env(safe-area-inset-bottom, 0);
    }
    .nav-item {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 2px;
        padding: 8px 4px;
        border: none;
        background: none;
        cursor: pointer;
        color: var(--tg-theme-hint-color, #999);
        font-size: 10px;
        font-weight: 600;
    }
    .nav-item .nav-icon { font-size: 22px; }
    .nav-item.active { color: var(--tg-theme-button-color, #2481cc); }

    .page-title { font-size: 20px; font-weight: 700; text-align: center; margin-bottom: 20px; }
    .tabs { display: flex; gap: 8px; margin-bottom: 20px; }
    .tab {
        flex: 1; padding: 12px 8px; border: none; border-radius: 10px;
        font-size: 14px; font-weight: 600; cursor: pointer;
        background: var(--tg-theme-secondary-bg-color, #e8e8e8);
        color: var(--tg-theme-text-color, #000);
    }
    .tab.active {
        background: var(--tg-theme-button-color, #2481cc);
        color: var(--tg-theme-button-text-color, #fff);
    }
    .field-label { font-size: 13px; font-weight: 600; margin-bottom: 6px; color: var(--tg-theme-hint-color, #707579); }
    .field-group { margin-bottom: 16px; }
    select, input[type="text"], input[type="number"], textarea {
        width: 100%; padding: 12px; border-radius: 10px;
        border: 1px solid var(--tg-theme-hint-color, #ccc);
        font-size: 15px;
        background: var(--tg-theme-bg-color, #fff);
        color: var(--tg-theme-text-color, #000);
    }
    textarea { resize: vertical; min-height: 70px; }
    .back-link {
        display: inline-block; margin-bottom: 16px;
        color: var(--tg-theme-link-color, #2481cc);
        font-size: 15px; cursor: pointer; border: none; background: none;
    }
    .modal-overlay {
        position: fixed; inset: 0; background: rgba(0,0,0,0.5);
        display: flex; align-items: flex-end; justify-content: center;
        z-index: 200;
    }
    .modal {
        background: var(--tg-theme-bg-color, #fff);
        border-radius: 16px 16px 0 0;
        padding: 20px;
        width: 100%; max-width: 480px;
        max-height: 80vh; overflow-y: auto;
    }
    .modal h3 { margin-bottom: 16px; font-size: 18px; }
    .error { background: #ffebee; color: #c62828; padding: 16px; border-radius: 12px; text-align: center; }
    .profile-info { background: var(--tg-theme-secondary-bg-color, #fff); border-radius: 12px; padding: 16px; margin-bottom: 16px; }
    .profile-info .row { margin-bottom: 8px; font-size: 14px; }
    .profile-info .row strong { color: var(--tg-theme-hint-color, #707579); }
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
        'Москва': ['Москва'],
        'Московская область': ['Химки','Подольск','Мытищи','Королёв','Балашиха','Другой город'],
        'Санкт-Петербург': ['Санкт-Петербург'],
        'Ленинградская область': ['Гатчина','Выборг','Всеволожск','Другой город'],
        'Краснодарский край': ['Краснодар','Сочи','Новороссийск','Анапа','Другой город'],
        'Свердловская область': ['Екатеринбург','Нижний Тагил','Другой город'],
        'Новосибирская область': ['Новосибирск','Бердск','Другой город'],
        'Ростовская область': ['Ростов-на-Дону','Таганрог','Другой город'],
        'Татарстан': ['Казань','Набережные Челны','Другой город'],
        'Башкортостан': ['Уфа','Стерлитамак','Другой город'],
        'Минск': ['Минск'],
        'Минская область': ['Борисов','Солигорск','Другой город'],
        'Алматы': ['Алматы'],
        'Астана': ['Астана'],
        'Киев': ['Киев'],
    };
    function getRegions(country) { return REGIONS[country] || []; }
    function getCities(region) { return CITIES[region] || ['Другой город']; }
    function fillSelect(el, items, placeholder, selected) {
        el.innerHTML = `<option value="">${placeholder}</option>` +
            items.map(i => `<option value="${i}" ${i===selected?'selected':''}>${i}</option>`).join('');
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
                    <span class="nav-icon">🏠</span>Home
                </button>
                <button class="nav-item" data-tab="stats" onclick="switchTab('stats')">
                    <span class="nav-icon">📊</span>Статистика
                </button>
                <button class="nav-item" data-tab="services" onclick="switchTab('services')">
                    <span class="nav-icon">🛠️</span>Услуги
                </button>
                <button class="nav-item" data-tab="profile" onclick="switchTab('profile')">
                    <span class="nav-icon">👤</span>Профиль
                </button>
            </nav>
        </div>
        <div id="modal-root"></div>
        <script>
        {WEBAPP_INIT}
        {LOCATION_DATA_JS}

        const MARKETPLACE = "{MARKETPLACE_NAME}";
        let businessData = null;
        let servicesList = [];
        let statsData = null;
        let currentTab = 'home';

        function renderStars(rating) {{
            const full = Math.floor(rating);
            let s = '';
            for (let i = 0; i < 5; i++) s += i < full ? '★' : '☆';
            return s + ' ' + rating.toFixed(1);
        }}

        function serviceItemsHtml(services, compact) {{
            if (!services.length) return '<div class="empty">Услуги пока не созданы</div>';
            return services.map(s => `
                <div class="service-item">
                    <div class="title">${{s.title}}</div>
                    <div class="meta">${{s.description || 'Без описания'}}${{s.price ? ' · ' + s.price + ' ₽' : ''}}</div>
                </div>
            `).join('');
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
            const name = tgUser?.username ? '@' + tgUser.username
                : (tgUser?.first_name || 'Пользователь');

            document.getElementById('main-content').innerHTML = `
                <div class="market-title">${{MARKETPLACE}}</div>
                <div class="user-name">${{name}}</div>
                <div class="business-card">
                    ${{photo}}
                    <div class="name">${{businessData.business_name}}</div>
                    <div class="rating">${{renderStars(businessData.business_rating)}}</div>
                    <div class="address">📍 ${{businessData.business_address}}</div>
                </div>

                <div class="section-title">Главное меню</div>

                <div class="menu-card">
                    <div class="left"><span class="icon">🛠️</span><span class="label">Услуга</span></div>
                    <button class="btn-sm" onclick="openCreateService()">+ Создать</button>
                </div>
                <div id="home-services">${{serviceItemsHtml(servicesList.slice(0,3), true)}}</div>

                <div class="menu-card">
                    <div class="left"><span class="icon">📦</span><span class="label">Товар</span></div>
                    <span class="badge">Функция временно не работает</span>
                </div>
                <div class="menu-card">
                    <div class="left"><span class="icon">📅</span><span class="label">Событие</span></div>
                    <button class="btn-sm" onclick="tg.showAlert('Создание события скоро будет доступно')">+ Создать</button>
                </div>
                <div class="menu-card">
                    <div class="left"><span class="icon">📢</span><span class="label">Объявление</span></div>
                    <button class="btn-sm" onclick="tg.showAlert('Создание объявления скоро будет доступно')">+ Создать</button>
                </div>
                <div class="menu-card">
                    <div class="left"><span class="icon">🏠</span><span class="label">Аренда</span></div>
                    <span class="badge">Функция временно не работает</span>
                </div>
            `;
        }}

        function renderStats() {{
            const s = statsData || {{ total_requests: 0, successful_requests: 0, cancelled_requests: 0 }};
            document.getElementById('main-content').innerHTML = `
                <div class="page-title">📊 Статистика</div>
                <div class="stat-card">
                    <div class="number">${{s.total_requests}}</div>
                    <div class="label">Заявки</div>
                </div>
                <div class="stat-card success">
                    <div class="number">${{s.successful_requests}}</div>
                    <div class="label">Успешные заявки</div>
                </div>
                <div class="stat-card cancel">
                    <div class="number">${{s.cancelled_requests}}</div>
                    <div class="label">Отменённые заявки</div>
                </div>
            `;
        }}

        function renderServices() {{
            document.getElementById('main-content').innerHTML = `
                <div class="page-title">🛠️ Мои услуги</div>
                <button class="btn" onclick="openCreateService()">+ Создать услугу</button>
                <div style="margin-top:16px" id="services-list">${{serviceItemsHtml(servicesList)}}</div>
            `;
        }}

        function renderProfile() {{
            const b = businessData || {{}};
            document.getElementById('main-content').innerHTML = `
                <div class="page-title">👤 Профиль</div>
                <div class="profile-info">
                    <div class="row"><strong>Бизнес:</strong> ${{b.business_name || '—'}}</div>
                    <div class="row"><strong>Адрес бизнеса:</strong> ${{b.business_address || '—'}}</div>
                    <div class="row"><strong>Личный адрес:</strong> ${{b.personal_address || '—'}}</div>
                </div>
                <button class="btn" onclick="window.location.href='/profile'">📝 Заполнить профиль</button>
            `;
        }}

        function switchTab(tab) {{
            currentTab = tab;
            document.querySelectorAll('.nav-item').forEach(el => {{
                el.classList.toggle('active', el.dataset.tab === tab);
            }});
            if (tab === 'home') renderHome();
            else if (tab === 'stats') renderStats();
            else if (tab === 'services') renderServices();
            else if (tab === 'profile') renderProfile();
        }}

        function openCreateService() {{
            document.getElementById('modal-root').innerHTML = `
                <div class="modal-overlay" onclick="if(event.target===this)closeModal()">
                    <div class="modal">
                        <h3>Новая услуга</h3>
                        <div class="field-group">
                            <div class="field-label">Название *</div>
                            <input type="text" id="svc-title" placeholder="Например: Ремонт телефонов">
                        </div>
                        <div class="field-group">
                            <div class="field-label">Описание</div>
                            <textarea id="svc-desc" placeholder="Краткое описание"></textarea>
                        </div>
                        <div class="field-group">
                            <div class="field-label">Цена (₽)</div>
                            <input type="number" id="svc-price" placeholder="0">
                        </div>
                        <button class="btn" onclick="saveService()">Сохранить</button>
                        <button class="btn btn-secondary" onclick="closeModal()">Отмена</button>
                    </div>
                </div>
            `;
        }}

        function closeModal() {{
            document.getElementById('modal-root').innerHTML = '';
        }}

        async function saveService() {{
            const title = document.getElementById('svc-title').value.trim();
            if (!title) {{ tg.showAlert('Введите название услуги'); return; }}
            const desc = document.getElementById('svc-desc').value.trim();
            const priceVal = document.getElementById('svc-price').value;
            const price = priceVal ? parseFloat(priceVal) : null;
            try {{
                const res = await fetch(`/api/services/${{tgUser.id}}`, {{
                    method: 'POST',
                    headers: {{'Content-Type':'application/json'}},
                    body: JSON.stringify({{ title, description: desc || null, price }}),
                }});
                if (!res.ok) throw new Error('Ошибка сохранения');
                closeModal();
                await loadServices();
                await loadStats();
                tg.showAlert('Услуга создана!');
                switchTab(currentTab === 'services' ? 'services' : 'home');
            }} catch(e) {{ tg.showAlert('Ошибка: ' + e.message); }}
        }}

        async function loadBusiness() {{
            const res = await fetch(`/api/business/${{tgUser.id}}`);
            businessData = await res.json();
        }}

        async function loadServices() {{
            const res = await fetch(`/api/services/${{tgUser.id}}`);
            const data = await res.json();
            servicesList = data.services || [];
        }}

        async function loadStats() {{
            const res = await fetch(`/api/stats/${{tgUser.id}}`);
            statsData = await res.json();
        }}

        async function init() {{
            if (!tgUser) {{
                document.getElementById('main-content').innerHTML =
                    '<div class="error">Не удалось получить данные пользователя</div>';
                document.getElementById('bottom-nav').classList.add('hidden');
                return;
            }}
            try {{
                await Promise.all([loadBusiness(), loadServices(), loadStats()]);
                switchTab('home');
            }} catch(e) {{
                document.getElementById('main-content').innerHTML =
                    `<div class="error">Ошибка загрузки: ${{e.message}}</div>`;
            }}
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

        let activeTab = 'business';
        let profileData = {{}};

        function switchTab(tab) {{
            activeTab = tab;
            document.getElementById('tab-business').classList.toggle('active', tab === 'business');
            document.getElementById('tab-personal').classList.toggle('active', tab === 'personal');
            renderForm();
        }}

        function onCountryChange() {{
            const country = document.getElementById('country').value;
            fillSelect(document.getElementById('region'), getRegions(country), 'Выберите область/край', '');
            fillSelect(document.getElementById('city'), [], 'Сначала выберите область', '');
        }}

        function onRegionChange() {{
            const region = document.getElementById('region').value;
            fillSelect(document.getElementById('city'), getCities(region), 'Выберите город', '');
        }}

        function renderForm() {{
            const isBusiness = activeTab === 'business';
            const prefix = isBusiness ? 'business' : 'personal';
            const saved = {{
                country: profileData[prefix + '_country'] || '',
                region: profileData[prefix + '_region'] || '',
                city: profileData[prefix + '_city'] || '',
            }};
            const label = isBusiness ? 'бизнеса' : 'личного профиля';

            document.getElementById('form-area').innerHTML = `
                <div class="field-group">
                    <div class="field-label">Страна ${{label}}</div>
                    <select id="country" onchange="onCountryChange()"></select>
                </div>
                <div class="field-group">
                    <div class="field-label">Область / край</div>
                    <select id="region" onchange="onRegionChange()"></select>
                </div>
                <div class="field-group">
                    <div class="field-label">Город</div>
                    <select id="city"></select>
                </div>
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
            if (!country) {{ tg.showAlert('Выберите страну'); return; }}
            if (!region) {{ tg.showAlert('Выберите область/край'); return; }}
            if (!city) {{ tg.showAlert('Выберите город'); return; }}

            try {{
                const res = await fetch(`/api/profile/${{tgUser.id}}`, {{
                    method: 'POST',
                    headers: {{'Content-Type':'application/json'}},
                    body: JSON.stringify({{ profile_type: activeTab, country, region, city }}),
                }});
                if (!res.ok) throw new Error('Ошибка сохранения');
                tg.showAlert('Профиль сохранён!', () => {{ window.location.href = '/'; }});
            }} catch(e) {{ tg.showAlert('Ошибка: ' + e.message); }}
        }}

        async function init() {{
            if (!tgUser) {{
                document.getElementById('form-area').innerHTML =
                    '<div class="error">Не удалось получить данные пользователя</div>';
                return;
            }}
            const res = await fetch(`/api/business/${{tgUser.id}}`);
            profileData = await res.json();
            renderForm();
        }}

        init();
        </script>
    </body>
    </html>
    """
