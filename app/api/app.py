from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Literal, Optional
from sqlalchemy import select
from app.database.session import AsyncSessionLocal
from app.models.user import User
from app.repositories.user_repository import UserRepository

app = FastAPI()

COMMON_STYLES = """
    * { box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        padding: 16px;
        margin: 0;
        background: var(--tg-theme-bg-color, #ffffff);
        color: var(--tg-theme-text-color, #000000);
    }
    .container { max-width: 480px; margin: 0 auto; }
    .page-title {
        font-size: 22px;
        font-weight: 700;
        text-align: center;
        margin-bottom: 20px;
    }
    .username {
        text-align: center;
        font-size: 16px;
        color: var(--tg-theme-hint-color, #707579);
        margin-bottom: 16px;
    }
    .photo-frame {
        border: 2px solid var(--tg-theme-hint-color, #c8c8c8);
        border-radius: 16px;
        overflow: hidden;
        margin: 0 auto 16px;
        width: 100%;
        max-width: 280px;
        aspect-ratio: 4 / 3;
        background: var(--tg-theme-secondary-bg-color, #f0f0f0);
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .photo-frame img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }
    .photo-placeholder {
        font-size: 48px;
        color: var(--tg-theme-hint-color, #999);
    }
    .business-name {
        text-align: center;
        font-size: 20px;
        font-weight: 700;
        margin-bottom: 12px;
    }
    .info-row {
        display: flex;
        justify-content: center;
        gap: 20px;
        margin-bottom: 24px;
        flex-wrap: wrap;
    }
    .info-item {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 15px;
        background: var(--tg-theme-secondary-bg-color, #f0f0f0);
        padding: 8px 14px;
        border-radius: 20px;
    }
    .btn {
        width: 100%;
        background: var(--tg-theme-button-color, #2481cc);
        color: var(--tg-theme-button-text-color, #ffffff);
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
        color: var(--tg-theme-text-color, #000000);
    }
    .loading, .error {
        text-align: center;
        padding: 40px 20px;
    }
    .error {
        background: #ffebee;
        color: #c62828;
        border-radius: 12px;
    }
    .tabs {
        display: flex;
        gap: 8px;
        margin-bottom: 24px;
    }
    .tab {
        flex: 1;
        padding: 12px 8px;
        border: none;
        border-radius: 10px;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        background: var(--tg-theme-secondary-bg-color, #e8e8e8);
        color: var(--tg-theme-text-color, #000000);
    }
    .tab.active {
        background: var(--tg-theme-button-color, #2481cc);
        color: var(--tg-theme-button-text-color, #ffffff);
    }
    .step-indicator {
        text-align: center;
        font-size: 13px;
        color: var(--tg-theme-hint-color, #707579);
        margin-bottom: 8px;
    }
    .step-title {
        font-size: 18px;
        font-weight: 600;
        margin-bottom: 16px;
        text-align: center;
    }
    select, input[type="text"] {
        width: 100%;
        padding: 14px;
        border-radius: 10px;
        border: 1px solid var(--tg-theme-hint-color, #ccc);
        font-size: 16px;
        background: var(--tg-theme-bg-color, #fff);
        color: var(--tg-theme-text-color, #000);
        margin-bottom: 16px;
    }
    .back-link {
        display: inline-block;
        margin-bottom: 16px;
        color: var(--tg-theme-link-color, #2481cc);
        text-decoration: none;
        font-size: 15px;
        cursor: pointer;
        border: none;
        background: none;
        padding: 0;
    }
"""

WEBAPP_SCRIPT = """
    const tg = window.Telegram.WebApp;
    tg.ready();
    tg.expand();
    const user = tg.initDataUnsafe.user;
"""


class ProfileUpdateRequest(BaseModel):
    profile_type: Literal["business", "personal"]
    country: Optional[str] = None
    region: Optional[str] = None


# ========== API ЭНДПОИНТЫ ==========

@app.get("/api/business/{telegram_id}")
async def get_business_info(telegram_id: int):
    try:
        async with AsyncSessionLocal() as session:
            query = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(query)
            user = result.scalar_one_or_none()

            if not user:
                return JSONResponse({
                    "has_business": False,
                    "error": "Пользователь не найден"
                })

            location_label = _format_location(user.business_region, user.business_country)

            return JSONResponse({
                "has_business": bool(user.market_name),
                "business_name": user.market_name or "Не указан",
                "telegram_id": user.telegram_id,
                "username": user.username,
                "created_at": user.market_created_at.isoformat() if user.market_created_at else None,
                "business_photo_url": user.business_photo_url,
                "business_rating": user.business_rating or 0.0,
                "latitude": user.latitude,
                "longitude": user.longitude,
                "location_label": location_label,
                "business_country": user.business_country,
                "business_region": user.business_region,
                "personal_country": user.personal_country,
                "personal_region": user.personal_region,
            })

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
            )

            return JSONResponse({"success": True})

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _format_location(region: str | None, country: str | None) -> str:
    parts = [p for p in (region, country) if p]
    return ", ".join(parts) if parts else "Не указана"


# ========== HTML СТРАНИЦЫ ==========

@app.get("/", response_class=HTMLResponse)
async def admin_panel():
    return f"""
    <html>
        <head>
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
            <style>{COMMON_STYLES}</style>
            <title>Админ панель</title>
        </head>
        <body>
            <div class="container">
                <div id="content" class="loading">Загрузка...</div>
            </div>
            <script>
                {WEBAPP_SCRIPT}

                function openProfile() {{
                    window.location.href = '/profile';
                }}

                function renderStars(rating) {{
                    const full = Math.floor(rating);
                    const half = rating % 1 >= 0.5;
                    let stars = '';
                    for (let i = 0; i < 5; i++) {{
                        if (i < full) stars += '⭐';
                        else if (i === full && half) stars += '✨';
                        else stars += '☆';
                    }}
                    return stars + ' ' + rating.toFixed(1);
                }}

                function renderMapLink(data) {{
                    if (data.latitude && data.longitude) {{
                        const url = `https://maps.google.com/?q=${{data.latitude}},${{data.longitude}}`;
                        return `<a href="${{url}}" target="_blank" style="color:inherit;text-decoration:none;">📍 На карте</a>`;
                    }}
                    return `📍 ${{data.location_label}}`;
                }}

                async function loadAdmin() {{
                    if (!user) {{
                        document.getElementById('content').innerHTML =
                            '<div class="error">Не удалось получить данные пользователя</div>';
                        return;
                    }}

                    try {{
                        const response = await fetch(`/api/business/${{user.id}}`);
                        const data = await response.json();

                        if (!data.has_business) {{
                            document.getElementById('content').innerHTML = `
                                <div class="error">
                                    Бизнес не зарегистрирован.<br>
                                    Закройте окно и создайте бизнес в боте.
                                </div>
                            `;
                            return;
                        }}

                        const photoHtml = data.business_photo_url
                            ? `<img src="${{data.business_photo_url}}" alt="Фото бизнеса">`
                            : '<div class="photo-placeholder">🏪</div>';

                        const displayName = user.username
                            ? '@' + user.username
                            : (user.first_name || 'Пользователь');

                        document.getElementById('content').innerHTML = `
                            <div class="page-title">Админ панель</div>
                            <div class="username">${{displayName}}</div>
                            <div class="photo-frame">${{photoHtml}}</div>
                            <div class="business-name">${{data.business_name}}</div>
                            <div class="info-row">
                                <div class="info-item">${{renderStars(data.business_rating)}}</div>
                                <div class="info-item">${{renderMapLink(data)}}</div>
                            </div>
                            <button class="btn" onclick="openProfile()">📝 Заполнить профиль</button>
                        `;
                    }} catch (error) {{
                        document.getElementById('content').innerHTML =
                            `<div class="error">Ошибка: ${{error.message}}</div>`;
                    }}
                }}

                loadAdmin();
            </script>
        </body>
    </html>
    """


@app.get("/profile", response_class=HTMLResponse)
async def profile_page():
    return f"""
    <html>
        <head>
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
            <style>{COMMON_STYLES}</style>
            <title>Заполнение профиля</title>
        </head>
        <body>
            <div class="container">
                <button class="back-link" onclick="window.location.href='/'">← Назад в админку</button>
                <div class="tabs">
                    <button class="tab active" id="tab-business" onclick="switchTab('business')">Бизнес профиль</button>
                    <button class="tab" id="tab-personal" onclick="switchTab('personal')">Личный профиль</button>
                </div>
                <div id="content"></div>
            </div>
            <script>
                {WEBAPP_SCRIPT}

                const COUNTRIES = [
                    'Россия', 'Беларусь', 'Казахстан', 'Украина',
                    'Узбекистан', 'Армения', 'Грузия', 'Азербайджан',
                    'Кыргызстан', 'Молдова', 'Таджикистан', 'Туркменистан'
                ];

                const REGIONS = {{
                    'Россия': [
                        'Москва', 'Московская область', 'Санкт-Петербург', 'Ленинградская область',
                        'Краснодарский край', 'Свердловская область', 'Новосибирская область',
                        'Ростовская область', 'Татарстан', 'Башкортостан', 'Другая область'
                    ],
                    'Беларусь': ['Минск', 'Минская область', 'Гомельская область', 'Брестская область', 'Другая область'],
                    'Казахстан': ['Алматы', 'Астана', 'Шымкент', 'Карагандинская область', 'Другая область'],
                    'Украина': ['Киев', 'Киевская область', 'Львовская область', 'Одесская область', 'Другая область'],
                }};

                let activeTab = 'business';
                let currentStep = 1;
                let selectedCountry = '';
                let selectedRegion = '';
                let profileData = {{}};

                function switchTab(tab) {{
                    activeTab = tab;
                    currentStep = 1;
                    selectedCountry = '';
                    selectedRegion = '';
                    document.getElementById('tab-business').classList.toggle('active', tab === 'business');
                    document.getElementById('tab-personal').classList.toggle('active', tab === 'personal');
                    renderStep();
                }}

                function getRegions(country) {{
                    return REGIONS[country] || ['Другая область'];
                }}

                function renderStep() {{
                    const tabLabel = activeTab === 'business' ? 'бизнеса' : 'личного профиля';
                    const savedCountry = activeTab === 'business'
                        ? profileData.business_country
                        : profileData.personal_country;
                    const savedRegion = activeTab === 'business'
                        ? profileData.business_region
                        : profileData.personal_region;

                    if (currentStep === 1) {{
                        const options = COUNTRIES.map(c =>
                            `<option value="${{c}}" ${{c === (selectedCountry || savedCountry) ? 'selected' : ''}}>${{c}}</option>`
                        ).join('');

                        document.getElementById('content').innerHTML = `
                            <div class="step-indicator">Шаг 1 из 2</div>
                            <div class="step-title">Страна ${{tabLabel}}</div>
                            <select id="countrySelect">
                                <option value="">Выберите страну</option>
                                ${{options}}
                            </select>
                            <button class="btn" onclick="nextStep()">Далее →</button>
                        `;
                    }} else {{
                        const country = selectedCountry || savedCountry;
                        const regions = getRegions(country);
                        const options = regions.map(r =>
                            `<option value="${{r}}" ${{r === (selectedRegion || savedRegion) ? 'selected' : ''}}>${{r}}</option>`
                        ).join('');

                        document.getElementById('content').innerHTML = `
                            <div class="step-indicator">Шаг 2 из 2</div>
                            <div class="step-title">Область ${{tabLabel}}</div>
                            <p style="text-align:center;color:var(--tg-theme-hint-color,#707579);margin-bottom:16px;">
                                Страна: <strong>${{country}}</strong>
                            </p>
                            <select id="regionSelect">
                                <option value="">Выберите область</option>
                                ${{options}}
                            </select>
                            <button class="btn btn-secondary" onclick="prevStep()">← Назад</button>
                            <button class="btn" onclick="saveProfile()">Сохранить</button>
                        `;
                    }}
                }}

                function nextStep() {{
                    const country = document.getElementById('countrySelect').value;
                    if (!country) {{
                        tg.showAlert('Выберите страну');
                        return;
                    }}
                    selectedCountry = country;
                    currentStep = 2;
                    renderStep();
                }}

                function prevStep() {{
                    currentStep = 1;
                    renderStep();
                }}

                async function saveProfile() {{
                    const region = document.getElementById('regionSelect').value;
                    if (!region) {{
                        tg.showAlert('Выберите область');
                        return;
                    }}

                    try {{
                        const response = await fetch(`/api/profile/${{user.id}}`, {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{
                                profile_type: activeTab,
                                country: selectedCountry,
                                region: region,
                            }}),
                        }});

                        if (!response.ok) throw new Error('Ошибка сохранения');

                        tg.showAlert('Профиль сохранён!', () => {{
                            window.location.href = '/';
                        }});
                    }} catch (error) {{
                        tg.showAlert('Ошибка: ' + error.message);
                    }}
                }}

                async function init() {{
                    if (!user) {{
                        document.getElementById('content').innerHTML =
                            '<div class="error">Не удалось получить данные пользователя</div>';
                        return;
                    }}

                    try {{
                        const response = await fetch(`/api/business/${{user.id}}`);
                        profileData = await response.json();
                        renderStep();
                    }} catch (error) {{
                        document.getElementById('content').innerHTML =
                            `<div class="error">Ошибка: ${{error.message}}</div>`;
                    }}
                }}

                init();
            </script>
        </body>
    </html>
    """
