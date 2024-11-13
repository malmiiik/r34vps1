from keep_alive import keep_alive
import os
import sqlite3
import aiohttp
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode

# Загрузка токена и URL API
TOKEN = os.getenv("TELEGRAM_TOKEN")
RULE34_API_URL = "https://api.rule34.xxx/index.php?page=dapi&s=post&q=index&json=1"

# Списки для хранения данных
post_cache = []
current_post_index = 0
favorites_cache = []
favorite_index = 0

# Подключение к базе данных SQLite
def get_db_connection(user_id):
    db_file = f"favorites_{user_id}.db"
    return sqlite3.connect(db_file)

# Создание таблицы для избранного
def create_favorites_table(user_id):
    with get_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_url TEXT NOT NULL,
                tags TEXT
            )
        ''')
        conn.commit()

# Кнопки навигации
def get_navigation_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад", callback_data='previous_post'),
         InlineKeyboardButton("Вперед ➡️", callback_data='next_post')],
        [InlineKeyboardButton("🎁 Добавить в избранное", callback_data='add_to_favorites')],
        [InlineKeyboardButton("🏠 Главное меню 🎉", callback_data='main_menu')]
    ])

def get_favorites_navigation_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад", callback_data='previous_favorite'),
         InlineKeyboardButton("Вперед ➡️", callback_data='next_favorite')],
        [InlineKeyboardButton("❌ Удалить из избранного", callback_data='remove_from_favorites')],
        [InlineKeyboardButton("🏠 Главное меню 🎉", callback_data='main_menu')]
    ])

def get_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎄 Случайный пост 🎉", callback_data='random_post')],
        [InlineKeyboardButton("🎁 Поиск по тегу 🎅", callback_data='search_by_tag')],
        [InlineKeyboardButton("❄️ Избранное ⭐", callback_data='view_favorites')],
        [InlineKeyboardButton("🎆 О боте 🧣", callback_data='about_bot')],
        [InlineKeyboardButton("📜 Пользовательское соглашение 🎊", callback_data='user_agreement')]
    ])

# Экранирование текста для MarkdownV2
def escape_markdown_v2(text):
    escape_chars = ['\\', '`', '*', '_', '{', '}', '[', ']', '(', ')', '#', '+', '-', '.', '!', ' ']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text

# Функция для извлечения расширения файла
def get_file_extension(url):
    return os.path.splitext(url)[1][1:].upper()  # Получаем расширение файла

# Обновленная функция для замены сообщения с постом
async def update_post_message(update: Update, post, tags, buttons):
    post_url = post['file_url']
    file_extension = get_file_extension(post_url)
    tags_text = ", ".join(tags).replace(",", " ") if isinstance(tags, list) else tags.replace(",", " ")
    
    # Добавляем новогоднюю атмосферу в текст
    message_text = f"🎄✨ {escape_markdown_v2(tags_text)} ✨🎄\n\n[🎁 Открыть пост]({post_url})\n*Формат файла: {file_extension}*"
    
    await update.effective_message.edit_text(message_text, reply_markup=buttons, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=False)


# Функция отправки медиа как ссылки
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Проверяем и создаем базу данных для пользователя
    create_favorites_table(user_id)

    await update.message.reply_text(
        "🎄❄️ Привет! Я бот для поиска новогодних постов на Rule34. ❄️🎄\n\n"
        "Выберите одно из действий:\n"
        "1. 🎄 Случайный пост 🎉\n"
        "2. 🎁 Поиск по тегу 🎅\n"
        "3. ❄️ Избранное ⭐\n",
        reply_markup=get_main_menu()
    )


# Получение данных с API Rule34
async def fetch_posts(session, params=None):
    async with session.get(RULE34_API_URL, params=params) as response:
        response.raise_for_status()
        return await response.json() if response.status == 200 else None

# Обработчик случайного поста
async def random_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loading_message = await update.effective_message.reply_text("⏳ Загрузка... Пожалуйста, подождите.")
    async with aiohttp.ClientSession() as session:
        posts = await fetch_posts(session)
        await loading_message.delete()
        if posts:
            global post_cache, current_post_index
            post_cache = posts
            random.shuffle(post_cache)  # Перемешиваем список постов для случайности
            current_post_index = 0
            post_tags = post_cache[current_post_index].get("tags", "Случайный пост").replace(",", " ").split()  # Заменяем запятые на пробелы и разделяем
            post_url = post_cache[current_post_index]['file_url']
            message_text = f"🎄✨ {escape_markdown_v2(' '.join(post_tags))} ✨🎄\n\n[🎁 Открыть пост]({post_url})"
            
            # Используем update_post_message вместо send_large_file_link
            await update_post_message(update, post_cache[current_post_index], post_tags, get_navigation_buttons())
        else:
            await update.effective_message.reply_text("❌ Не удалось найти случайный пост.", reply_markup=get_main_menu())


async def handle_tag_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        user_input = update.message.text
        if not user_input:
            await update.message.reply_text("❌ Пожалуйста, введите хотя бы один тег для поиска.", reply_markup=get_main_menu())
            return

        tags = [tag.strip() for tag in user_input.replace(",", " ").split()]  # Заменяем запятые на пробелы и разделяем по пробелам
        params = {'tags': ' '.join(tags)}  # Форматируем теги как строку с пробелами

        loading_message = await update.effective_message.reply_text("⏳ Загрузка... Пожалуйста, подождите.")

        try:
            async with aiohttp.ClientSession() as session:
                posts = await fetch_posts(session, params)
        except Exception as e:
            await loading_message.delete()
            await update.effective_message.reply_text(f"❌ Ошибка при поиске постов: {str(e)}", reply_markup=get_main_menu())
            return

        await loading_message.delete()

        if posts:
            global post_cache, current_post_index
            post_cache = posts
            random.shuffle(post_cache)  # Перемешиваем список постов для случайности
            current_post_index = 0  # Начинаем с первого поста в списке
            post_tags = post_cache[current_post_index].get("tags", "Поиск по тегам").replace(",", " ").split()  # Заменяем запятые на пробелы и разделяем
            post_url = post_cache[current_post_index]['file_url']
            message_text = f"✨ {escape_markdown_v2(' '.join(post_tags))} \\✨\n\n[Открыть пост]({post_url})"

            # Вместо редактирования отправим новое сообщение
            await update.effective_message.reply_text(
                message_text, 
                reply_markup=get_navigation_buttons(), 
                parse_mode=ParseMode.MARKDOWN_V2, 
                disable_web_page_preview=False
            )
        else:
            await update.effective_message.reply_text("❌ Посты с такими тегами не найдены.", reply_markup=get_main_menu())

# Обработчик нажатий на кнопки
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == 'random_post':
        await random_post(update, context)
    elif data == 'search_by_tag':
        await query.message.reply_text("🔍 Введите теги для поиска.")
    elif data == 'view_favorites':
        await view_favorites(update, context)
    elif data == 'previous_post':
        await previous_post(update)
    elif data == 'next_post':
        await next_post(update)
    elif data == 'previous_favorite':
        await previous_favorite(update, context)  # Передаем context
    elif data == 'next_favorite':
        await next_favorite(update, context)  # Передаем context
    elif data == 'add_to_favorites':
        await add_to_favorites(update, context)
    elif data == 'remove_from_favorites':
        await remove_from_favorites(update, context)
    elif data == 'about_bot':
        await about_bot(update, context)
    elif data == 'user_agreement':
        await user_agreement(update, context)
    elif data == 'main_menu':
        await query.message.edit_text(
            "🎉 Привет! Я бот для поиска постов на Rule34.\n\n"
            "Выберите одно из действий:\n"
            "1. 🎲 Случайный пост\n"
            "2. 🔍 Поиск по тегу\n"
            "3. ⭐ Избранное\n",
            reply_markup=get_main_menu()
        )

# Переход к следующему посту
async def next_post(update: Update):
    global current_post_index
    if post_cache:
        # Переход к следующему посту в списке
        next_index = current_post_index + 1
        if next_index < len(post_cache):  # Проверяем, есть ли следующий пост
            current_post_index = next_index
            post = post_cache[current_post_index]
            post_tags = post.get("tags", "").replace(",", " ").split()  # Получаем теги поста
            # Если контент изменился, обновляем сообщение
            message_text = f"✨ {escape_markdown_v2(' '.join(post_tags))} \\✨\n\n[Открыть пост]({post['file_url']})"
            await update_post_message(update, post, post_tags, get_navigation_buttons())  # Обновляем сообщение с новым постом
        else:
            await update.callback_query.answer("❌ Это последний пост.")
    else:
        await update.callback_query.answer("❌ Нет доступных постов.")

# Переход к предыдущему посту
async def previous_post(update: Update):
    global current_post_index
    if post_cache:
        # Переход к предыдущему посту в списке
        prev_index = current_post_index - 1
        if prev_index >= 0:  # Проверяем, есть ли предыдущий пост
            current_post_index = prev_index
            post = post_cache[current_post_index]
            post_tags = post.get("tags", "").replace(",", " ").split()  # Получаем теги поста
            # Если контент изменился, обновляем сообщение
            message_text = f"✨ {escape_markdown_v2(' '.join(post_tags))} \\✨\n\n[Открыть пост]({post['file_url']})"
            await update_post_message(update, post, post_tags, get_navigation_buttons())  # Обновляем сообщение с новым постом
        else:
            await update.callback_query.answer("❌ Это первый пост.")
    else:
        await update.callback_query.answer("❌ Нет доступных постов.")

# Просмотр избранных постов
async def view_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global favorites_cache, favorite_index
    user_id = update.effective_user.id
    with get_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_url, tags FROM favorites")
        favorites_cache = cursor.fetchall()
    if favorites_cache:
        favorite_index = 0
        await show_favorite(update)
    else:
        await update.callback_query.answer("❌ Избранное пусто.")

# Отображение поста из избранного
async def show_favorite(update: Update):
    if favorites_cache:
        post_url, post_tags = favorites_cache[favorite_index]
        
        # Заменяем запятые на пробелы в тегах и убираем лишние пробелы
        post_tags = post_tags.replace(",", " ").strip()
        
        # Экранируем теги для безопасного отображения в MarkdownV2
        escaped_tags = escape_markdown_v2(post_tags)
        
        # Формируем сообщение с постом и его тегами
        message_text = f"✨ {escaped_tags} \\✨\n\n[Открыть пост]({post_url})"
        
        # Отправляем или редактируем сообщение с постом
        await update.effective_message.edit_text(
            message_text, 
            reply_markup=get_favorites_navigation_buttons(), 
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.callback_query.answer("❌ Избранное пусто!")  # Уведомление пользователю


# Переход к следующему посту в избранном
async def next_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global favorite_index
    if favorites_cache:
        if favorite_index + 1 < len(favorites_cache):  # Проверяем, есть ли следующий пост
            favorite_index += 1
            await show_favorite(update)
        else:
            favorite_index = 0  # Переход к первому посту
            if update.callback_query:
                await update.callback_query.answer("❌ Это последний пост. Перехожу к первому посту.")
                await update.callback_query.edit_message_text(
                    "❌ Это последний пост. Перехожу к первому посту.",
                    reply_markup=get_favorites_navigation_buttons()
                )
            await show_favorite(update)  # Показываем первый пост
    else:
        if update.callback_query:
            await update.callback_query.answer("❌ Избранное пусто!")
        else:
            await update.message.reply("❌ Избранное пусто!")


# Переход к предыдущему посту в избранном
async def previous_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global favorite_index
    if favorites_cache:
        if favorite_index - 1 >= 0:  # Проверяем, есть ли предыдущий пост
            favorite_index -= 1
            await show_favorite(update)
        else:
            favorite_index = len(favorites_cache) - 1  # Переход к последнему посту
            if update.callback_query:
                await update.callback_query.answer("❌ Это первый пост. Перехожу к последнему посту.")
            await show_favorite(update)  # Показываем последний пост
    else:
        if update.callback_query:
            await update.callback_query.answer("❌ Избранное пусто!")
        else:
            await update.message.reply("❌ Избранное пусто!")




# Отображение поста из избранного
async def show_favorite(update: Update):
    if favorites_cache:
        post_url, post_tags = favorites_cache[favorite_index]
        
        # Заменяем запятые на пробелы и убираем лишние пробелы
        post_tags = post_tags.replace(",", " ").strip()
        
        # Экранируем теги для безопасного отображения в MarkdownV2
        escaped_tags = escape_markdown_v2(post_tags)
        
        # Формируем сообщение с постом и его тегами
        message_text = f"✨ {escaped_tags} \\✨\n\n[Открыть пост]({post_url})"
        
        # Отправляем или редактируем сообщение с постом
        await update.effective_message.edit_text(
            message_text, 
            reply_markup=get_favorites_navigation_buttons(), 
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.callback_query.answer("❌ Избранное пусто!")  # Уведомление пользователю



# Добавление поста в избранное
async def add_to_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    post = post_cache[current_post_index]
    create_favorites_table(user_id)
    post_tags = post.get("tags", "Случайный пост").split(" ")
    with get_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM favorites WHERE file_url = ?", (post['file_url'],))
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO favorites (file_url, tags) VALUES (?, ?)", (post['file_url'], ", ".join(post_tags)))
            conn.commit()
            await update.callback_query.answer("Добавлено в избранное!")
        else:
            await update.callback_query.answer("Этот пост уже в избранном!")

# Удаление поста из избранного
async def remove_from_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global favorite_index
    user_id = update.effective_user.id
    post_url = favorites_cache[favorite_index][0]
    with get_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM favorites WHERE file_url = ?", (post_url,))
        conn.commit()
    await update.callback_query.answer("Удалено из избранного!")
    del favorites_cache[favorite_index]
    if favorite_index >= len(favorites_cache):
        favorite_index = max(favorite_index - 1, 0)
    if favorites_cache:
        await show_favorite(update)
    else:
        await update.callback_query.message.reply_text("Избранное пусто.", reply_markup=get_main_menu())

# О боте
async def about_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "🎉 Привет! Я — бот, созданный для поиска интересных постов на Rule34."
    await update.callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')]]))

# Пользовательское соглашение
async def user_agreement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📜 Пользовательское соглашение:\n\n"
        "1. Используйте бота только для законных целей.\n"
        "2. Мы не несем ответственности за контент, найденный через API Rule34.\n"
    )
    await update.callback_query.message.edit_text(
        text, 
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')]])
    )

# Основная функция
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tag_search))
    application.add_handler(CallbackQueryHandler(button))
    application.run_polling()

if __name__ == "__main__":
    keep_alive()
    main()  # Запуск без asyncio.run
