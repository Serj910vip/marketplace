from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.bot.bot import bot
from app.database.session import AsyncSessionLocal
from app.models.user import User
from app.repositories.ad_repository import AdRepository
from app.repositories.user_repository import UserRepository
from app.services.post_publisher import send_post_to_chat

router = APIRouter()


class PostCreateRequest(BaseModel):
    telegram_id: int
    title: str
    subtitle: Optional[str] = None
    content: Optional[str] = None
    action: Literal["publish", "schedule"]
    scheduled_at: Optional[str] = None


class PostUpdateRequest(BaseModel):
    title: str
    subtitle: Optional[str] = None
    content: Optional[str] = None


def post_to_dict(post) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "subtitle": post.subtitle,
        "content": post.description,
        "status": post.status or "published",
        "hidden": post.hidden,
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "created_at": post.created_at.isoformat() if post.created_at else None,
    }


def _status_label(status: str) -> str:
    return {
        "published": "🟢 Опубликован",
        "scheduled": "🕐 Запланирован",
    }.get(status, status)


async def _publish_post(user: User, post) -> None:
    if not user.linked_chat_id:
        raise HTTPException(
            status_code=400,
            detail="Сначала добавьте бота в группу или канал",
        )
    await send_post_to_chat(bot, user.linked_chat_id, post)


def register_post_pages(app, common_styles: str, webapp_init: str):
    @app.get("/posts", response_class=HTMLResponse)
    async def posts_list_page():
        return f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
            <style>{common_styles}</style>
            <title>Посты</title>
        </head>
        <body>
            <div class="app">
                <div class="content" style="padding-top:0;">
                    <div class="ad-header-block">
                        <div class="ad-header-row">
                            <button class="back-link-white" onclick="window.location.href='/'">← Назад</button>
                            <span class="ads-header-title">Посты</span>
                        </div>
                    </div>
                    <div class="ads-create-btn-wrapper">
                        <button class="ads-create-btn" onclick="window.location.href='/post/create'">Создать пост</button>
                    </div>
                    <div class="ads-filter-tabs">
                        <button class="ads-filter-tab active" id="filter-published" onclick="filterPosts('published')">Опубликованные</button>
                        <button class="ads-filter-tab" id="filter-scheduled" onclick="filterPosts('scheduled')">Запланированные</button>
                    </div>
                    <div class="ads-count" id="posts-count">У вас 0 постов</div>
                    <div class="ads-list-container" id="posts-list">
                        <div class="ads-empty">Список постов пуст</div>
                    </div>
                </div>
            </div>
            <script>
            {webapp_init}
            let allPosts = [];
            let currentFilter = 'published';
            let telegramId = tgUser?.id;

            function filterPosts(type) {{
                currentFilter = type;
                document.getElementById('filter-published').classList.toggle('active', type === 'published');
                document.getElementById('filter-scheduled').classList.toggle('active', type === 'scheduled');
                renderPosts();
            }}

            function renderPosts() {{
                const filtered = allPosts.filter(p => p.status === currentFilter);
                const container = document.getElementById('posts-list');
                document.getElementById('posts-count').textContent = `У вас ${{filtered.length}} постов`;
                if (!filtered.length) {{
                    container.innerHTML = `<div class="ads-empty">${{currentFilter === 'published' ? 'Опубликованных' : 'Запланированных'}} постов нет</div>`;
                    return;
                }}
                container.innerHTML = filtered.map((post, index) => {{
                    const num = String(index + 1).padStart(3, '0');
                    const date = post.created_at 
                        ? new Date(post.created_at).toLocaleString('ru-RU', {{
                            timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                            day: '2-digit',
                            month: '2-digit',
                            year: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit'
                        }})
                        : '';

                    const scheduleInfo = post.scheduled_at 
                        ? `<br>🕐 ${{new Date(post.scheduled_at).toLocaleString('ru-RU', {{
                            timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                            day: '2-digit',
                            month: '2-digit',
                            year: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit'
                        }})}}`
                        : '';
                    
                    return `
                        <div class="add-item">
                            <div class="add-item-header">
                                <div class="add-item-title-block">
                                    <div class="add-item-title">${{post.title}}</div>
                                    <div class="add-item-subtitle">${{post.subtitle || 'Без подзаголовка'}}</div>
                                </div>
                                <div class="add-item-title-block">
                                    <div class="add-item-number">#${{num}}</div>
                                    <div class="add-item-date">${{date}}${{scheduleInfo}}</div>
                                </div>
                            </div>
                            <div class="add-item-actions">
                                <button class="add-item-btn add-item-btn-edit" onclick="editPost(${{post.id}})">Редактировать</button>
                            </div>
                        </div>`;
                }}).join('');
            }}

            function editPost(id) {{ window.location.href = `/post/edit/${{id}}`; }}

            async function loadPosts() {{
                if (!telegramId) return;
                const res = await fetch(`/api/posts/${{telegramId}}`);
                const data = await res.json();
                allPosts = data.posts || [];
                renderPosts();
            }}
            loadPosts();
            </script>
        </body>
        </html>
        """

    @app.get("/post/create", response_class=HTMLResponse)
    async def post_create_page():
        return f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
            <style>{common_styles}</style>
            <title>Создание поста</title>
        </head>
        <body>
            <div class="app">
                <div class="content" style="padding-top:0;">
                    <div class="ad-header-block">
                        <div class="ad-header-row">
                            <button class="back-link-white" onclick="window.location.href='/posts'">← Назад</button>
                            <span class="ad-header-title">Создание поста</span>
                        </div>
                    </div>
                    <div class="ad-create-main-block" style="margin-top:20px;">
                        <div class="ad-field-group">
                            <label class="ad-field-label">Заголовок</label>
                            <input class="ad-field-input" id="post-title" maxlength="200" placeholder="Заголовок поста">
                        </div>
                        <div class="ad-field-group">
                            <label class="ad-field-label">Подзаголовок</label>
                            <input class="ad-field-input" id="post-subtitle" maxlength="200" placeholder="Краткое описание">
                        </div>
                        <div class="ad-field-group">
                            <label class="ad-field-label">Содержание</label>
                            <textarea class="ad-field-input" id="post-content" maxlength="2000" placeholder="Текст поста"></textarea>
                        </div>
                        <div id="schedule-block" class="ad-field-group hidden">
                            <label class="ad-field-label">Дата и время публикации</label>
                            <input class="ad-field-input" type="datetime-local" id="schedule-datetime">
                        </div>
                        <div class="post-actions-row">
                            <button class="ad-btn-create" onclick="submitPost('publish')">Опубликовать</button>
                            <button class="ad-btn-create ad-btn-secondary" onclick="toggleSchedule()">Запланировать</button>
                        </div>
                        <button id="confirm-schedule-btn" class="ad-btn-create hidden" onclick="submitPost('schedule')">Подтвердить планирование</button>
                    </div>
                </div>
            </div>
            <script>
            {webapp_init}
            let scheduleVisible = false;

            function toggleSchedule() {{
                scheduleVisible = !scheduleVisible;
                document.getElementById('schedule-block').classList.toggle('hidden', !scheduleVisible);
                document.getElementById('confirm-schedule-btn').classList.toggle('hidden', !scheduleVisible);
            }}

            async function submitPost(action) {{
                const title = document.getElementById('post-title').value.trim();
                if (!title) {{ tg.showAlert('Введите заголовок'); return; }}
                const subtitle = document.getElementById('post-subtitle').value.trim();
                const content = document.getElementById('post-content').value.trim();
                let scheduled_at = null;
                if (action === 'schedule') {{
                    scheduled_at = document.getElementById('schedule-datetime').value;
                    if (!scheduled_at) {{ tg.showAlert('Выберите дату и время'); return; }}
                }}
                try {{
                    const res = await fetch('/api/posts/create', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{
                            telegram_id: tgUser.id,
                            title, subtitle, content, action, scheduled_at
                        }}),
                    }});
                    const data = await res.json().catch(() => ({{}}));
                    if (!res.ok) throw new Error(data.detail || 'Ошибка');
                    const msg = action === 'publish' ? '✅ Пост опубликован!' : '✅ Пост запланирован!';
                    tg.showAlert(msg, () => {{ window.location.href = '/posts'; }});
                }} catch(e) {{ tg.showAlert('❌ ' + e.message); }}
            }}
            </script>
        </body>
        </html>
        """

    @app.get("/post/edit/{post_id}", response_class=HTMLResponse)
    async def post_edit_page(post_id: int):
        return f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
            <style>{common_styles}</style>
            <title>Редактирование поста</title>
        </head>
        <body>
            <div class="app">
                <div class="content" style="padding-top:0;">
                    <div class="ad-header-block">
                        <div class="ad-header-row">
                            <button class="back-link-white" onclick="window.location.href='/posts'">← Назад</button>
                            <span class="ad-header-title">Редактирование поста</span>
                        </div>
                    </div>
                    <div class="ad-create-main-block" style="margin-top:20px;">
                        <div id="loading" style="text-align:center;padding:40px 0;color:#8A9593;">Загрузка...</div>
                        <div id="form-container" class="hidden">
                            <div class="ad-field-group">
                                <label class="ad-field-label">Заголовок</label>
                                <input class="ad-field-input" id="post-title" maxlength="200">
                            </div>
                            <div class="ad-field-group">
                                <label class="ad-field-label">Подзаголовок</label>
                                <input class="ad-field-input" id="post-subtitle" maxlength="200">
                            </div>
                            <div class="ad-field-group">
                                <label class="ad-field-label">Содержание</label>
                                <textarea class="ad-field-input" id="post-content" maxlength="2000"></textarea>
                            </div>
                            <div style="display:flex;gap:12px;margin-top:8px;">
                                <button class="ad-btn-create" style="flex:2;" onclick="savePost()">Сохранить</button>
                                <button class="ad-btn-create" style="flex:1;background:#FF8282;border-color:#FF8282;" onclick="deletePost()">Удалить</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <script>
            {webapp_init}
            const postId = {post_id};

            async function loadPost() {{
                const res = await fetch(`/api/posts/get/${{postId}}`);
                if (!res.ok) {{ tg.showAlert('Пост не найден'); return; }}
                const data = await res.json();
                const p = data.post;
                document.getElementById('post-title').value = p.title || '';
                document.getElementById('post-subtitle').value = p.subtitle || '';
                document.getElementById('post-content').value = p.content || '';
                document.getElementById('loading').classList.add('hidden');
                document.getElementById('form-container').classList.remove('hidden');
            }}

            async function savePost() {{
                const body = {{
                    title: document.getElementById('post-title').value.trim(),
                    subtitle: document.getElementById('post-subtitle').value.trim(),
                    content: document.getElementById('post-content').value.trim(),
                }};
                if (!body.title) {{ tg.showAlert('Введите заголовок'); return; }}
                const res = await fetch(`/api/posts/update/${{postId}}`, {{
                    method: 'PUT',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify(body),
                }});
                if (!res.ok) {{ tg.showAlert('Ошибка сохранения'); return; }}
                tg.showAlert('✅ Сохранено!', () => {{ window.location.href = '/posts'; }});
            }}

            function deletePost() {{
                tg.showConfirmPopup({{
                    title: 'Удаление',
                    message: 'Удалить этот пост?',
                    buttons: [{{type:'cancel'}}, {{id:'delete', type:'destructive', text:'Удалить'}}]
                }}, async (btnId) => {{
                    if (btnId !== 'delete') return;
                    await fetch(`/api/posts/${{postId}}`, {{method:'DELETE'}});
                    tg.showAlert('✅ Удалено', () => {{ window.location.href = '/posts'; }});
                }});
            }}
            loadPost();
            </script>
        </body>
        </html>
        """

    @app.get("/ads")
    async def redirect_ads():
        return RedirectResponse(url="/posts", status_code=302)

    @app.get("/ad/create")
    async def redirect_ad_create():
        return RedirectResponse(url="/post/create", status_code=302)

    @app.get("/ad/edit/{ad_id}")
    async def redirect_ad_edit(ad_id: int):
        return RedirectResponse(url=f"/post/edit/{ad_id}", status_code=302)


@router.get("/api/bot/username")
async def get_bot_username():
    me = await bot.get_me()
    return JSONResponse({"username": me.username})


@router.get("/api/user/{telegram_id}/channel")
async def get_linked_channel(telegram_id: int):
    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_id)
        if not user:
            return JSONResponse({"linked": False})
        return JSONResponse({
            "linked": bool(user.linked_chat_id),
            "chat_title": user.linked_chat_title,
            "chat_type": user.linked_chat_type,
        })


@router.get("/api/posts/{telegram_id}")
async def get_posts(telegram_id: int):
    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_id)
        if not user:
            return JSONResponse({"posts": []})
        posts = await AdRepository(session).get_by_user_id(user.id)
        return JSONResponse({"posts": [post_to_dict(p) for p in posts]})


@router.get("/api/posts/get/{post_id}")
async def get_post(post_id: int):
    async with AsyncSessionLocal() as session:
        post = await AdRepository(session).get_by_id(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Пост не найден")
        return JSONResponse({"post": post_to_dict(post)})


@router.post("/api/posts/create")
async def create_post(body: PostCreateRequest):
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(body.telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        scheduled_at = None
        if body.action == "schedule":
            if not body.scheduled_at:
                raise HTTPException(status_code=400, detail="Укажите дату публикации")
            scheduled_at = datetime.fromisoformat(body.scheduled_at)
            if scheduled_at <= datetime.utcnow():
                raise HTTPException(status_code=400, detail="Дата должна быть в будущем")

        ad_repo = AdRepository(session)
        if body.action == "publish":
            post = await ad_repo.create(
                user_id=user.id,
                title=body.title.strip(),
                subtitle=body.subtitle,
                description=body.content,
                status="published",
                hidden=False,
                published_at=datetime.utcnow(),
            )
            await _publish_post(user, post)
        else:
            post = await ad_repo.create(
                user_id=user.id,
                title=body.title.strip(),
                subtitle=body.subtitle,
                description=body.content,
                status="scheduled",
                hidden=True,
                scheduled_at=scheduled_at,
            )

        return JSONResponse({"success": True, "post": post_to_dict(post)})


@router.put("/api/posts/update/{post_id}")
async def update_post(post_id: int, body: PostUpdateRequest):
    async with AsyncSessionLocal() as session:
        ad_repo = AdRepository(session)
        post = await ad_repo.get_by_id(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Пост не найден")

        updated = await ad_repo.update(post_id, {
            "title": body.title.strip(),
            "subtitle": body.subtitle,
            "description": body.content,
        })
        return JSONResponse({"success": True, "post": post_to_dict(updated)})


@router.delete("/api/posts/{post_id}")
async def delete_post(post_id: int):
    async with AsyncSessionLocal() as session:
        ok = await AdRepository(session).delete(post_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Пост не найден")
        return JSONResponse({"success": True})


@router.get("/api/market/posts/{telegram_id}")
async def get_market_posts(telegram_id: int):
    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_id)
        if not user:
            return JSONResponse({"posts": []})
        posts = await AdRepository(session).get_active_by_user_id(user.id)
        return JSONResponse({"posts": [post_to_dict(p) for p in posts]})
