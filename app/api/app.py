from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select
from app.database.session import AsyncSessionLocal
from app.models.user import User

app = FastAPI()


# ========== API ЭНДПОИНТЫ ==========

@app.get("/api/business/{telegram_id}")
async def get_business_info(telegram_id: int):
    """Получить данные бизнеса по telegram_id"""
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

            # Возвращаем данные для админки
            return JSONResponse({
                "has_business": bool(user.market_name),
                "business_name": user.market_name or "Не указан",
                "telegram_id": user.telegram_id,
                "username": user.username,
                "created_at": user.market_created_at.isoformat() if user.market_created_at else None
            })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== HTML СТРАНИЦЫ ==========

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <head>
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                    padding: 20px;
                    margin: 0;
                    background: var(--tg-theme-bg-color, #ffffff);
                    color: var(--tg-theme-text-color, #000000);
                }
                .container {
                    max-width: 600px;
                    margin: 0 auto;
                }
                .header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                }
                .refresh-btn {
                    background: var(--tg-theme-secondary-bg-color, #e0e0e0);
                    color: var(--tg-theme-text-color, #000000);
                    border: none;
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    font-size: 20px;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0;
                    padding: 0;
                }
                .refresh-btn:hover {
                    opacity: 0.8;
                }
                .user-card {
                    background: var(--tg-theme-secondary-bg-color, #f0f0f0);
                    padding: 20px;
                    border-radius: 12px;
                    margin-bottom: 20px;
                }
                .business-name {
                    font-size: 24px;
                    font-weight: bold;
                    margin: 10px 0;
                    color: var(--tg-theme-button-color, #2481cc);
                }
                .stat {
                    background: var(--tg-theme-bg-color, #ffffff);
                    padding: 15px;
                    border-radius: 10px;
                    margin-bottom: 10px;
                    border: 1px solid var(--tg-theme-hint-color, #ddd);
                }
                button {
                    width: 100%;
                    background: var(--tg-theme-button-color, #2481cc);
                    color: var(--tg-theme-button-text-color, #ffffff);
                    border: none;
                    padding: 15px;
                    border-radius: 10px;
                    font-size: 16px;
                    font-weight: 600;
                    cursor: pointer;
                    margin-top: 10px;
                }
                .loading {
                    text-align: center;
                    padding: 50px;
                    color: var(--tg-theme-hint-color, #999);
                }
                .error {
                    background: #f44336;
                    color: white;
                    padding: 15px;
                    border-radius: 10px;
                    text-align: center;
                }
                .last-updated {
                    text-align: center;
                    font-size: 12px;
                    color: var(--tg-theme-hint-color, #999);
                    margin-top: 20px;
                }
            </style>
            <title>Панель управления бизнесом</title>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div style="font-size: 18px; font-weight: bold;">🏪 Мой бизнес</div>
                    <button class="refresh-btn" onclick="forceRefresh()">🔄</button>
                </div>
                <div id="content" class="loading">Загрузка данных...</div>
                <div id="lastUpdated" class="last-updated"></div>
            </div>

            <script>
                const tg = window.Telegram.WebApp;
                tg.ready();
                tg.expand();

                const user = tg.initDataUnsafe.user;

                // Функция принудительного обновления
                function forceRefresh() {
                    tg.showPopup({
                        title: 'Обновление',
                        message: 'Обновить данные?',
                        buttons: [
                            {type: 'cancel'},
                            {type: 'default', text: 'Обновить'}
                        ]
                    }, (buttonId) => {
                        if (buttonId === 'default') {
                            // Показываем индикатор загрузки
                            document.getElementById('content').innerHTML = '<div class="loading">Обновление...</div>';
                            // Принудительно загружаем данные с сервера
                            loadBusinessData(true);
                        }
                    });
                }

                async function loadBusinessData(force = false) {
                    if (!user) {
                        document.getElementById('content').innerHTML = '<div class="error">Ошибка: не удалось получить данные пользователя</div>';
                        return;
                    }

                    try {
                        // Добавляем timestamp для предотвращения кэширования
                        const url = force ? `/api/business/${user.id}?_=${Date.now()}` : `/api/business/${user.id}`;
                        const response = await fetch(url);
                        const data = await response.json();

                        // Обновляем время последнего обновления
                        const now = new Date();
                        document.getElementById('lastUpdated').innerHTML = `Последнее обновление: ${now.toLocaleTimeString()}`;

                        if (data.has_business) {
                            // Показываем админку с данными бизнеса
                            document.getElementById('content').innerHTML = `
                                <div class="user-card">
                                    <div>👋 Здравствуйте, ${user.first_name} ${user.last_name || ''}</div>
                                    <div class="business-name">🏪 ${data.business_name}</div>
                                    <div>Telegram ID: ${data.telegram_id}</div>
                                    <div>Username: @${user.username || 'не указан'}</div>
                                </div>

                                <div class="stat">
                                    <strong>📊 Статистика маркета</strong><br>
                                    Создан: ${data.created_at ? new Date(data.created_at).toLocaleDateString() : 'только что'}<br>
                                    Статус: ✅ Активен
                                </div>

                                <div class="stat">
                                    <strong>🛍️ Товары и услуги</strong><br>
                                    Пока нет добавленных товаров
                                </div>

                                <div class="stat">
                                    <strong>📈 За сегодня</strong><br>
                                    Просмотров: 0<br>
                                    Заказов: 0<br>
                                    Доход: 0 ₽
                                </div>

                                <button onclick="addProduct()">➕ Добавить товар/услугу</button>
                                <button onclick="showOrders()" style="background: #4caf50;">📦 Заказы</button>
                                <button onclick="showSettings()">⚙️ Настройки</button>
                            `;
                        } else {
                            // Бизнес не зарегистрирован
                            document.getElementById('content').innerHTML = `
                                <div class="error">
                                    ⚠️ Бизнес не зарегистрирован<br><br>
                                    Закройте это окно и в боте нажмите "Создать маркет"
                                </div>
                                <button onclick="tg.close()">Закрыть</button>
                            `;
                        }
                    } catch (error) {
                        document.getElementById('content').innerHTML = `<div class="error">Ошибка загрузки: ${error.message}<br><br><button onclick="location.reload()">Повторить</button></div>`;
                    }
                }

                function addProduct() {
                    tg.showAlert('Форма добавления товара будет здесь');
                    // Здесь можно открыть форму добавления
                }

                function showOrders() {
                    tg.showAlert('Список заказов');
                }

                function showSettings() {
                    tg.showAlert('Настройки бизнеса');
                }

                // Автоматическое обновление при открытии страницы
                loadBusinessData();

                    // Автообновление каждые 30 секунд (опционально)
                    setInterval(() => loadBusinessData(true), 30000);
                </script>
            </body>
        </html>
        """