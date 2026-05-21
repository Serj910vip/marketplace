from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>

        <head>

            <script src="https://telegram.org/js/telegram-web-app.js"></script>

        </head>

        <body>

            <h1>Кто вы?</h1>

            <div id="user-info"></div>

            <br>

            <a href="/customer">
                <button>
                    👤 Я клиент
                </button>
            </a>

            <br><br>

            <a href="/business">
                <button>
                    🏢 Я бизнес
                </button>
            </a>

            <script>

                const tg = window.Telegram.WebApp;

                tg.expand();

                const user = tg.initDataUnsafe.user;

                if (user) {

                    document.getElementById("user-info").innerHTML = `
                        <p>
                            Привет, ${user.first_name}
                        </p>

                        <p>
                            Ваш Telegram ID: ${user.id}
                        </p>
                    `;
                }

            </script>

        </body>

    </html>
    """


@app.get("/customer", response_class=HTMLResponse)
async def customer_page():
    return """
    <html>
        <body>
            <h1>Добро пожаловать в marketplace</h1>

            <p>
                Здесь будут:
            </p>

            <ul>
                <li>Категории</li>
                <li>Рекомендации</li>
                <li>Поиск услуг</li>
            </ul>

        </body>
    </html>
    """


@app.get("/business", response_class=HTMLResponse)
async def business_page():
    return """
    <html>
        <body>
            <h1>Регистрация бизнеса</h1>

            <p>
                Создайте свой бизнес-профиль
            </p>

        </body>
    </html>
    """