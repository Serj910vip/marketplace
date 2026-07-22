import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.bot.bot import bot
from app.database.session import AsyncSessionLocal
from app.models.user import User
from app.repositories.ad_repository import AdRepository, photos_from_ad
from app.repositories.user_repository import UserRepository
from app.services.file_service import save_file
from app.services.post_publisher import send_post_to_chat

router = APIRouter()

POST_PHOTOS_CSS = """
    .post-photo-slot {
        margin-bottom: 16px;
    }
    .post-photo-slot .slot-label {
        font-size: 13px;
        font-weight: 600;
        color: #8A9593;
        margin-bottom: 8px;
    }
    .post-photo-box {
        width: 100%;
        height: 140px;
        background: rgba(0, 58, 129, 0.3);
        border: 0.5px solid #0073FF;
        border-radius: 16px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 32px;
        cursor: pointer;
        overflow: hidden;
        color: #8A9593;
    }
    .post-photo-box img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }
    .post-photo-remove {
        margin-top: 6px;
        background: none;
        border: none;
        color: #FF8282;
        font-size: 13px;
        cursor: pointer;
        padding: 0;
    }
    .posts-secondary-btn {
        width: 110px;
        padding: 14px;
        margin-top: 10px;
        background: rgba(0, 58, 129, 0.3);
        border: 0.5px solid #0073FF;
        border-radius: 10px;
        color: #FFFFFF;
        font-size: 10px;
        font-weight: 500;
        cursor: pointer;
    }
    .posts-secondary-btn.active {
        background: #003A81;
    }
    .posts-secondary-btn:hover {
        background: #003A81;
    }

    .ads-filter-tabs {
        display: flex;
        justify-content: space-around;
        margin-bottom: 19px;
    }

    .ads-filter-tab {
        width: 110px;
        padding: 14px;
        margin-top: 10px;
        background: rgba(0, 58, 129, 0.3);
        border: 0.5px solid #0073FF;
        border-radius: 10px;
        color: #FFFFFF;
        font-size: 10px;
        font-weight: 500;
        cursor: pointer;
    }

    .ads-filter-tab.active {
        background: #003A81;
        border: 0.5px solid #0073FF;
        color: #FFFFFF;
    }


    .ads-filter-tab:hover {
        background: #003A81;
    }



    .market-ad-card-image-full {
        width: 100%;
        height: 180px;
        object-fit: cover;
        border-radius: 12px 12px 0 0;
        display: block;
    }
    .market-ad-card-image-placeholder-full {
        width: 100%;
        height: 120px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 40px;
        background: rgba(0,58,129,0.2);
        border-radius: 12px 12px 0 0;
    }

    /* Стили для ползунка планирования */
    .schedule-toggle-container {
        display: flex;
        align-items: center;
        justify-content: space-between; 
        border-radius: 12px;
        margin-bottom: 16px;
    }

    .schedule-toggle-label {
        font-size: 14px;
        color: #FFFFFF;
        font-weight: 500;
    }

    .schedule-toggle-status {
        font-size: 13px;
        color: #8A9593;
    }

    .schedule-toggle-status.active {
        color: #4caf50;
    }

    .schedule-toggle-status.inactive {
        color: #ff6b6b;
    }

    .switch-schedule {
        position: relative;
        display: inline-block;
        width: 58px;
        height: 25px;
        flex-shrink: 0;
    }

    .switch-schedule input {
        opacity: 0;
        width: 0;
        height: 0;
    }

    .switch-schedule .slider {
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

    .switch-schedule .slider:before {
        position: absolute;
        content: "";
        height: 21px;
        width: 27px;
        bottom: 0.55px;
        background: #0073FF;
        transition: 0.3s;
        border-radius: 25%;
    }

    .switch-schedule input:checked + .slider {
        background: #003A81;
    }

    .switch-schedule input:checked + .slider:before {
        transform: translateX(24px);
    }

    /* Стили для полей даты и времени */
    .schedule-fields {
        display: none;
        gap: 12px;
        margin-top: 12px;
        border-radius: 12px;
    }

    .schedule-fields.visible {
        display: block;
    }

    .schedule-field-group {
        display: flex;
        justify-content: space-between;
        flex: 1;
    }

    .schedule-field-group label {
        display: block;
        font-size: 12px;
        width: 130px;
        text-align: center;
        padding: 8px 8px 8px 8px;
        color: #ffffff;
        margin-bottom: 4px;
        background: #003A81;
        border: 0.5px solid #0073FF;
        border-radius: 10px;
    }


    .schedule-field-group input:focus {
        border-color: #4a9eff;
    }

    .schedule-field-group input[type="date"]::-webkit-calendar-picker-indicator,
    .schedule-field-group input[type="time"]::-webkit-calendar-picker-indicator {
        filter: invert(1);
        cursor: pointer;
    }



    /* Новые стили для полей даты и времени */
    .schedule-fields {
        display: none;
        margin-top: 12px;
        border-radius: 12px;
    }

    .schedule-fields.visible {
        display: block;
    }

    .schedule-field-group {
        margin-bottom: 12px;
    }

    .schedule-field-group label {
        display: block;
        font-size: 12px;
        color: #FFFFFF;
        margin-bottom: 4px;
    }

    .schedule-field-group input {
        width: 140px;
        height: 38px;
        margin-left: 39px;
        padding: 0 12px;
        background: rgba(0, 58, 129, 0.3);
        border: 0.5px solid #0073FF;
        border-radius: 10px;
        color: #FFFFFF;
        font-size: 14px;
        outline: none;
        box-sizing: border-box;
        float: right;
    }

    .schedule-field-group input:focus {
        border-color: #4a9eff;
    }

    .schedule-field-group input[type="date"]::-webkit-calendar-picker-indicator,
    .schedule-field-group input[type="time"]::-webkit-calendar-picker-indicator {
        filter: invert(1);
        cursor: pointer;
    }

    /* Очистка float */
    .schedule-field-group::after {
        content: "";
        display: table;
        clear: both;
    }
"""

POST_PHOTOS_JS = """
    const MAX_POST_PHOTOS = 3;
    const photoSlots = [null, null, null];

    function renderPhotoSlots() {
        const container = document.getElementById('photo-slots');
        if (!container) return;
        container.innerHTML = [0, 1, 2].map(index => {
            const slot = photoSlots[index];
            const preview = slot
                ? (slot.kind === 'existing'
                    ? `<img src="${slot.url}" alt="">`
                    : `<img src="${slot.preview}" alt="">`)
                : '➕';
            const removeBtn = slot
                ? `<button type="button" class="post-photo-remove" onclick="removePhotoSlot(${index})">Удалить фото ${index + 1}</button>`
                : '';
            return `
                <div class="post-photo-slot">
                    <div class="slot-label">Фото ${index + 1}</div>
                    <div class="post-photo-box" onclick="pickPhoto(${index})">${preview}</div>
                    ${removeBtn}
                </div>
            `;
        }).join('');
    }

    function pickPhoto(index) {
        window._photoPickIndex = index;
        document.getElementById('photo-file-input').click();
    }

    function removePhotoSlot(index) {
        photoSlots[index] = null;
        renderPhotoSlots();
    }

    function fileFingerprint(file) {
        return `${file.name}_${file.size}_${file.lastModified}`;
    }

    function isDuplicateFile(file) {
        const fp = fileFingerprint(file);
        return photoSlots.some(slot => {
            if (!slot || slot.kind !== 'new') return false;
            return fileFingerprint(slot.file) === fp;
        });
    }

    function onPhotoFileSelected(input) {
        const file = input.files[0];
        input.value = '';
        if (!file) return;
        if (!file.type.startsWith('image/')) {
            tg.showAlert('Можно загружать только изображения');
            return;
        }
        if (file.size > 3 * 1024 * 1024) {
            tg.showAlert('Фото не больше 3 МБ');
            return;
        }
        if (isDuplicateFile(file)) {
            tg.showAlert('Это фото уже добавлено');
            return;
        }
        const index = window._photoPickIndex;
        const reader = new FileReader();
        reader.onload = e => {
            photoSlots[index] = { kind: 'new', file, preview: e.target.result };
            renderPhotoSlots();
        };
        reader.readAsDataURL(file);
    }

    function initPhotoSlotsFromUrls(urls) {
        photoSlots[0] = null;
        photoSlots[1] = null;
        photoSlots[2] = null;
        (urls || []).slice(0, 3).forEach((url, i) => {
            photoSlots[i] = { kind: 'existing', url };
        });
        renderPhotoSlots();
    }

    function appendPhotosToFormData(formData) {
        const kept = photoSlots
            .filter(s => s && s.kind === 'existing')
            .map(s => s.url);
        formData.append('existing_photos', JSON.stringify(kept));
        photoSlots.forEach((slot, index) => {
            if (slot && slot.kind === 'new') {
                formData.append('files', slot.file, slot.file.name || `photo${index + 1}.jpg`);
            }
        });
    }
"""


def post_to_dict(post) -> dict:
    photo_list = photos_from_ad(post)
    return {
        "id": post.id,
        "title": post.title,
        "subtitle": post.subtitle,
        "content": post.description,
        "photos": photo_list,
        "photo_url": photo_list[0] if photo_list else None,
        "status": post.status or "published",
        "hidden": post.hidden,
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "created_at": post.created_at.isoformat() if post.created_at else None,
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
    return urls[:3]


async def _publish_post(user: User, post) -> None:
    if not user.linked_chat_id:
        raise HTTPException(
            status_code=400,
            detail="Сначала добавьте бота в группу или канал",
        )
    await send_post_to_chat(bot, user.linked_chat_id, post)


def register_post_pages(app, common_styles: str, webapp_init: str):
    styles = common_styles + POST_PHOTOS_CSS

    @app.get("/posts", response_class=HTMLResponse)
    async def posts_list_page():
        return f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
            <style>{styles}</style>
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
                    <div class="divider-line-posts"></div>
                    <div class="container-post">
                        <div class="ads-create-btn-wrapper">
                            <button class="ads-create-btn" onclick="window.location.href='/post/create'">Создать пост</button>
                            
                        </div>
                    </div>
                    
                   
                    <div class="ads-filter-tabs" id="status-tabs">
                        <button class="ads-filter-tab active" id="filter-published" onclick="filterPosts('published')">Активные</button>
                        <button class="ads-filter-tab" id="filter-scheduled" onclick="filterPosts('scheduled')">Запланированные</button>
                        <button class="ads-filter-tab" id="filter-hidden" onclick="filterPosts('hidden')">Скрытые</button>
                    </div>
                    <div class="ads-count" id="posts-count">Посты: 0</div>
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
                
                document.getElementById('filter-published').classList.remove('active');
                document.getElementById('filter-scheduled').classList.remove('active');
                document.getElementById('filter-hidden').classList.remove('active');
                
                // Добавляем active на нужную кнопку
                if (type === 'published') {{
                    document.getElementById('filter-published').classList.add('active');
                }} else if (type === 'scheduled') {{
                    document.getElementById('filter-scheduled').classList.add('active');
                }} else if (type === 'hidden') {{
                    document.getElementById('filter-hidden').classList.add('active');
                }}
                renderPosts();
            }}

            function renderPosts() {{
                let filtered;
                if (currentFilter === 'published') {{
                    filtered = allPosts.filter(p => !p.hidden && p.status === 'published');
                }} else if (currentFilter === 'scheduled') {{
                    filtered = allPosts.filter(p => !p.hidden && p.status === 'scheduled');
                }} else if (currentFilter === 'hidden') {{
                    filtered = allPosts.filter(p => p.hidden === true);
                }}
                
                const container = document.getElementById('posts-list');
                const labels = {{
                    published: 'опубликованных',
                    scheduled: 'запланированных',
                    hidden: 'скрытых',
                }};
                document.getElementById('posts-count').textContent = `Посты: ${{filtered.length}}`;
                
                if (!filtered.length) {{
                    container.innerHTML = `<div class="ads-empty">Нет ${{labels[currentFilter]}} постов</div>`;
                    return;
                }}
                
                container.innerHTML = filtered.map((post, index) => {{
                    const num = String(index + 1).padStart(3, '0');
                    const date = post.created_at
                        ? new Date(post.created_at).toLocaleString('ru-RU')
                        : '';
                    const scheduleInfo = post.scheduled_at
                        ? `<br>Опубликуется: ${{new Date(post.scheduled_at).toLocaleString('ru-RU')}}`
                        : '';
                    return `
                        <div class="add-item">
                            <div class="add-item-date-block">
                                <div class="add-item-number">#${{num}}</div>
                                <div class="add-item-date">Создано: ${{date}}${{scheduleInfo}}</div>
                            </div>
                            <div class="add-item-title-block">
                                    <div class="add-item-title">${{post.title}}</div>
                                    <div class="add-item-subtitle">${{post.subtitle || 'Без подзаголовка'}}</div>
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
            <style>{styles}</style>
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
                    <div class="divider-line-posts"></div>
                    <div class="ad-create-main-block" style="margin-top:15px;">
                        <div class="ad-field-group">
                            <label class="ad-field-label">Заголовок поста:</label>
                            <input class="ad-field-input" id="post-title" maxlength="200" placeholder="Заголовок поста">
                        </div>
                        <div class="ad-field-group">
                            <label class="ad-field-label">Подзаголовок поста:</label>
                            <input class="ad-field-input" id="post-subtitle" maxlength="200" placeholder="Краткое описание">
                        </div>
                        <div class="ad-field-group">
                            <label class="ad-field-label">Содержание поста:</label>
                            <textarea class="ad-field-input" id="post-content" maxlength="2000" placeholder="Текст поста"></textarea>
                        </div>
                        <div class="ad-field-group">
                            <label class="ad-field-label">Загрузите фотографии (до 3 шт., до 3 МБ каждая)</label>
                            <div id="photo-slots"></div>
                            <input type="file" id="photo-file-input" class="ad-input-file" accept="image/*" onchange="onPhotoFileSelected(this)">
                        </div>

                    
                        <!-- Ползунок планирования -->
                        <div class="schedule-toggle-container">
                            <span class="schedule-toggle-label">Запланировать публикацию</span>
                            <label class="switch-schedule">
                                <input type="checkbox" id="schedule-toggle" onchange="toggleScheduleFields(this.checked)">
                                <span class="slider"></span>
                            </label>
                        </div>

                        <!-- Поля даты и времени -->
                        <div class="schedule-fields" id="schedule-fields">
                            <div class="schedule-field-group">
                                <label>Дата</label>
                                <input type="date" id="schedule-date">
                            </div>
                            <div class="schedule-field-group">
                                <label>Время</label>
                                <input type="time" id="schedule-time" step="60">
                            </div>
                        </div>

                        <!-- Кнопка Опубликовать -->
                        <button class="ad-btn-create" onclick="submitPost()">Опубликовать</button>
                    </div>
                </div>
            </div>
            <script>
            {webapp_init}
            {POST_PHOTOS_JS}
            let scheduleVisible = false;

          

            // Функция для переключения полей планирования
            function toggleScheduleFields(checked) {{
                const fields = document.getElementById('schedule-fields');

                
                if (checked) {{
                    fields.classList.add('visible');

                    // Устанавливаем дату по умолчанию - завтра
                    const tomorrow = new Date();
                    tomorrow.setDate(tomorrow.getDate() + 1);
                    document.getElementById('schedule-date').value = tomorrow.toISOString().split('T')[0];
                    // Устанавливаем время по умолчанию - 10:00
                    document.getElementById('schedule-time').value = '10:00';
                }} else {{
                    fields.classList.remove('visible');

                }}
            }}

            async function submitPost() {{
                const title = document.getElementById('post-title').value.trim();
                if (!title) {{ tg.showAlert('Введите заголовок'); return; }}

                const subtitle = document.getElementById('post-subtitle').value.trim();
                const content = document.getElementById('post-content').value.trim();

                // Проверяем, включено ли планирование
                const isScheduled = document.getElementById('schedule-toggle').checked;
                let scheduled_at = null;
                let action = 'publish';

                if (isScheduled) {{
                    const date = document.getElementById('schedule-date').value;
                    const time = document.getElementById('schedule-time').value;
                    
                    if (!date || !time) {{
                        tg.showAlert('Выберите дату и время публикации');
                        return;
                    }}
                    
                    scheduled_at = `${{date}}T${{time}}:00`;
                    action = 'schedule';
                }}

                const formData = new FormData();
                formData.append('telegram_id', tgUser.id);
                formData.append('title', title);
                formData.append('subtitle', subtitle);
                formData.append('content', content);
                formData.append('action', action);
                if (scheduled_at) formData.append('scheduled_at', scheduled_at);
                appendPhotosToFormData(formData);

                try {{
                    const res = await fetch('/api/posts/create', {{ method: 'POST', body: formData }});
                    const data = await res.json().catch(() => ({{}}));
                    if (!res.ok) throw new Error(data.detail || 'Ошибка');
                    const msg = action === 'publish' ? '✅ Пост опубликован!' : '✅ Пост запланирован!';
                    tg.showAlert(msg, () => {{ window.location.href = '/posts'; }});
                }} catch(e) {{ tg.showAlert('❌ ' + e.message); }}
            }}

            initPhotoSlotsFromUrls([]);

            
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
            <style>{styles}</style>
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
                    <div class="divider-line-posts"></div>
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
                            <div class="ad-field-group">
                                <label class="ad-field-label">Фотографии</label>
                                <div id="photo-slots"></div>
                                <input type="file" id="photo-file-input" class="ad-input-file" accept="image/*" onchange="onPhotoFileSelected(this)">
                            </div>
                            <div class="ad-field-group" style="margin-top:20px;">
                            <div class="toggle-container" style="display:flex;align-items:center;justify-content:space-between;">
                                <label class="ad-field-label-hid" style="margin-bottom:0;">Скрыть пост</label>
                                <label class="switch">
                                    <input type="checkbox" id="post-hidden-toggle" onchange="onHiddenToggle(this.checked)">
                                    <span class="slider"></span>
                                </label>
                            </div>
                            <div style="display:flex;gap:12px;margin-top:8px;">
                                <button class="ad-btn-create-posts" id="delete-btn" style="flex:1;background:rgba(0, 58, 129, 0.3);border-color:#0073FF;" onclick="deletePost()">Удалить пост</button>
                                <button class="ad-btn-create-posts" style="flex:2;" onclick="savePost()">Сохранить изменения</button>
                                
                            </div>
                            
                        </div>
                        </div>
                    </div>
                </div>
            </div>
            <script>
            {webapp_init}
            {POST_PHOTOS_JS}
            const postId = {post_id};
            let isHidden = false;

            function onHiddenToggle(checked) {{
                isHidden = checked;

            }}

            async function loadPost() {{
                const res = await fetch(`/api/posts/get/${{postId}}`);
                if (!res.ok) {{ 
                    if (tg && tg.showAlert) tg.showAlert('Пост не найден');
                    else alert('Пост не найден');
                    return; 
                }}
                const data = await res.json();
                const p = data.post;
                document.getElementById('post-title').value = p.title || '';
                document.getElementById('post-subtitle').value = p.subtitle || '';
                document.getElementById('post-content').value = p.content || '';
                initPhotoSlotsFromUrls(p.photos || []);
                isHidden = !!p.hidden;
                document.getElementById('post-hidden-toggle').checked = isHidden;
                onHiddenToggle(isHidden);
                document.getElementById('loading').classList.add('hidden');
                document.getElementById('form-container').classList.remove('hidden');
            }}

            async function savePost() {{
                const title = document.getElementById('post-title').value.trim();
                if (!title) {{ 
                    if (tg && tg.showAlert) tg.showAlert('Введите заголовок'); 
                    else alert('Введите заголовок');
                    return; 
                }}
                const formData = new FormData();
                formData.append('title', title);
                formData.append('subtitle', document.getElementById('post-subtitle').value.trim());
                formData.append('content', document.getElementById('post-content').value.trim());
                formData.append('hidden', isHidden ? 'true' : 'false');
                appendPhotosToFormData(formData);
                const res = await fetch(`/api/posts/update/${{postId}}`, {{
                    method: 'PUT',
                    body: formData,
                }});
                const data = await res.json().catch(() => ({{}}));
                if (!res.ok) {{ 
                    if (tg && tg.showAlert) tg.showAlert(data.detail || 'Ошибка сохранения'); 
                    else alert(data.detail || 'Ошибка сохранения');
                    return; 
                }}
                if (tg && tg.showAlert) {{
                    tg.showAlert('✅ Сохранено!', () => {{ window.location.href = '/posts'; }});
                }} else {{
                    alert('✅ Сохранено!');
                    window.location.href = '/posts';
                }}
            }}

            // ИСПРАВЛЕННАЯ ФУНКЦИЯ УДАЛЕНИЯ
            function deletePost() {{
                // Проверяем, доступен ли Telegram WebApp
                const tg = window.Telegram?.WebApp;
                
                // Функция выполнения удаления
                const performDelete = async () => {{
                    const btn = document.getElementById('delete-btn');
                    btn.disabled = true;
                    btn.textContent = 'Удаление...';
                    
                    try {{
                        const res = await fetch(`/api/posts/${{postId}}`, {{
                            method: 'DELETE'
                        }});
                        
                        if (!res.ok) {{
                            const data = await res.json().catch(() => ({{}}));
                            throw new Error(data.detail || 'Ошибка удаления');
                        }}
                        
                        // Успешно удалено
                        if (tg && tg.showAlert) {{
                            tg.showAlert('✅ Пост удалён', () => {{ 
                                window.location.href = '/posts'; 
                            }});
                        }} else {{
                            alert('✅ Пост удалён');
                            window.location.href = '/posts';
                        }}
                    }} catch (e) {{
                        if (tg && tg.showAlert) {{
                            tg.showAlert('❌ ' + e.message);
                        }} else {{
                            alert('❌ ' + e.message);
                        }}
                        btn.disabled = false;
                        btn.textContent = 'Удалить';
                    }}
                }};

                // Показываем диалог подтверждения
                if (tg && tg.showConfirmPopup) {{
                    // Используем нативный диалог Telegram
                    tg.showConfirmPopup({{
                        title: 'Удаление',
                        message: 'Удалить этот пост навсегда?',
                        buttons: [
                            {{ type: 'cancel' }},
                            {{ id: 'delete', type: 'destructive', text: 'Удалить' }}
                        ]
                    }}, (btnId) => {{
                        if (btnId === 'delete') {{
                            performDelete();
                        }}
                    }});
                }} else {{
                    // Fallback для обычного браузера
                    if (confirm('Удалить этот пост навсегда?')) {{
                        performDelete();
                    }}
                }}
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
async def create_post(
    telegram_id: int = Form(...),
    title: str = Form(...),
    subtitle: str = Form(""),
    content: str = Form(""),
    action: str = Form(...),
    scheduled_at: Optional[str] = Form(None),
    existing_photos: str = Form("[]"),
    files: list[UploadFile] = File(default=[]),
):
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        photo_urls = await _save_upload_files(files)
        if len(photo_urls) > 3:
            raise HTTPException(status_code=400, detail="Максимум 3 фотографии")

        parsed_schedule = None
        if action == "schedule":
            if not scheduled_at:
                raise HTTPException(status_code=400, detail="Укажите дату публикации")
            parsed_schedule = datetime.fromisoformat(scheduled_at)
            if parsed_schedule <= datetime.utcnow():
                raise HTTPException(status_code=400, detail="Дата должна быть в будущем")

        ad_repo = AdRepository(session)
        if action == "publish":
            post = await ad_repo.create(
                user_id=user.id,
                title=title.strip(),
                subtitle=subtitle or None,
                description=content or None,
                photos=photo_urls,
                status="published",
                hidden=False,
                published_at=datetime.utcnow(),
            )
            await _publish_post(user, post)
        else:
            post = await ad_repo.create(
                user_id=user.id,
                title=title.strip(),
                subtitle=subtitle or None,
                description=content or None,
                photos=photo_urls,
                status="scheduled",
                hidden=False,
                scheduled_at=parsed_schedule,
            )

        return JSONResponse({"success": True, "post": post_to_dict(post)})


@router.put("/api/posts/update/{post_id}")
async def update_post(
    post_id: int,
    title: str = Form(...),
    subtitle: str = Form(""),
    content: str = Form(""),
    hidden: str = Form("false"),
    existing_photos: str = Form("[]"),
    files: list[UploadFile] = File(default=[]),
):
    async with AsyncSessionLocal() as session:
        ad_repo = AdRepository(session)
        post = await ad_repo.get_by_id(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Пост не найден")

        try:
            kept = json.loads(existing_photos)
            if not isinstance(kept, list):
                kept = []
        except json.JSONDecodeError:
            kept = []

        new_photos = await _save_upload_files(files)
        final_photos = (kept + new_photos)[:3]

        updated = await ad_repo.update(post_id, {
            "title": title.strip(),
            "subtitle": subtitle or None,
            "description": content or None,
            "hidden": _parse_hidden(hidden),
            "photos": final_photos,
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
