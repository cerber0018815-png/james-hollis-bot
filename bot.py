import asyncio
import time
import openai
import sys
import os
import json
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, PreCheckoutQueryHandler, CallbackQueryHandler
)

# Загружаем переменные окружения
load_dotenv()

# ===== НАСТРОЙКИ =====
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
PAYMENT_PROVIDER_TOKEN = os.getenv('PAYMENT_PROVIDER_TOKEN')
CURRENCY = os.getenv('CURRENCY', 'RUB')
PRICE = int(os.getenv('PRICE', 15000))  # цена в копейках
AUTHOR_CHAT_ID = os.getenv('AUTHOR_CHAT_ID')  # Telegram ID администратора для отзывов

if not TELEGRAM_TOKEN or not DEEPSEEK_API_KEY:
    print("❌ Ошибка: TELEGRAM_TOKEN или DEEPSEEK_API_KEY не найдены!")
    sys.exit(1)
else:
    print("✅ Переменные окружения загружены.")

if not PAYMENT_PROVIDER_TOKEN:
    print("⚠️ PAYMENT_PROVIDER_TOKEN не задан. Оплата недоступна.")

openai.api_base = "https://api.deepseek.com/v1"
openai.api_key = DEEPSEEK_API_KEY
# =====================

# ===== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ =====
DB_PATH = "bot_data.db"

def init_db():
    """Создаёт таблицы users и feedback."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # Таблица users
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                last_session_end REAL DEFAULT 0,
                free_session_used INTEGER DEFAULT 0
            )
        ''')
        try:
            c.execute("ALTER TABLE users ADD COLUMN free_session_used INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # колонка уже существует

        # Таблица feedback
        c.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                text TEXT,
                timestamp REAL
            )
        ''')
        conn.commit()
        conn.close()
        print("✅ База данных инициализирована")
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")

init_db()

def get_last_session_end(user_id: int) -> float:
    """Возвращает время последней сессии пользователя."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT last_session_end FROM users WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception as e:
        print(f"❌ Ошибка чтения из БД для user {user_id}: {e}")
        return 0

def save_last_session_end(user_id: int, last_session_end: float):
    """Сохраняет время последней сессии пользователя."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''
            INSERT INTO users (user_id, last_session_end)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                last_session_end = excluded.last_session_end
        ''', (user_id, last_session_end))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Ошибка записи в БД для user {user_id}: {e}")

def get_free_session_used(user_id: int) -> bool:
    """Возвращает True, если бесплатная сессия уже использована."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT free_session_used FROM users WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        conn.close()
        return row[0] == 1 if row else False
    except Exception as e:
        print(f"❌ Ошибка чтения free_session_used для user {user_id}: {e}")
        return False

def set_free_session_used(user_id: int, used: bool = True):
    """Устанавливает флаг использования бесплатной сессии."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''
            INSERT INTO users (user_id, free_session_used)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                free_session_used = excluded.free_session_used
        ''', (user_id, 1 if used else 0))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Ошибка записи free_session_used для user {user_id}: {e}")

def save_feedback(user_id: int, username: str, text: str):
    """Сохраняет отзыв в БД."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute('''
            INSERT INTO feedback (user_id, username, text, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, text, time.time()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Ошибка сохранения отзыва: {e}")

def get_feedbacks(limit: int = 10) -> list:
    """Возвращает последние limit отзывов."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT user_id, username, text, timestamp
            FROM feedback
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"❌ Ошибка чтения отзывов: {e}")
        return []

async def ensure_user_data(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Загружает last_session_end из БД в context.user_data, если его там нет."""
    if 'last_session_end' not in context.user_data:
        context.user_data['last_session_end'] = get_last_session_end(user_id)
# ======================================

# ===== ЗАГРУЗКА ПРОМПТА =====
# Короткий промпт (можно заменить на полный позже)
SYSTEM_PROMPT = """
Ты должен строго следить за длиной своих сообщений. Максимальная длина одного сообщения — 3700 символов. Старайся уложить ответ в этот предел, не теряя глубины и чуткости. Это необходимо, чтобы Telegram гарантированно доставил ответ (абсолютный лимит 4096, мы оставляем запас). Не упоминай имя "Джеймс Холлис" в ответах.

Системный промт (Role/Instruction)
Ты — проводник в пространстве души, юнгианский психоаналитик. Ты обращаешься к человеку, который чувствует растерянность, боль, усталость или потерю смысла. Твоя задача — создать для него безопасное, тёплое и бережное пространство, где он сможет выдохнуть.

Твои главные принципы:

Безусловное принятие. Ты не оцениваешь и не критикуешь. Всё, что человек чувствует, имеет право быть. Ты не пытаешься «исправить» его. Ты здесь не для того, чтобы давать ответы, а чтобы быть рядом, пока он ищет свои собственные.

Совместное, а не директивное мышление. Ты не предлагаешь готовых интерпретаций. Вместо этого ты мягко рассуждаешь вместе с человеком. Ты оставляешь пространство для его собственных открытий. Невроз — это страдание, которое ещё не обрело смысл, и этот смысл может найти только сам человек.

Мягкость и образность. Твой язык — спокойный, метафоричный, но без излишней поэтичности. Говори о душе, о внутреннем ребёнке, о ландшафтах психики, о Перевале, о старых картах, которые перестали вести к цели.

Поддержка без давления. Ты не требуешь ответов и не настаиваешь. Твои вопросы звучат как приглашение к размышлению, а не как допрос. Человек может не отвечать, может молчать, может плакать — ты принимаешь это.

Признание ценности страдания. Ты понимаешь, что цель жизни — не счастье, а смысл. Страдание — это не враг, а почва, на которой этот смысл может произрасти. Ты помогаешь увидеть в боли посланника, но делаешь это бережно.

Время и пространство. Ты даёшь человеку время. Ты не спешишь и не пытаешься заполнить тишину.

Сдержанность. Ты сохраняешь спокойное, устойчивое присутствие. Ты не погружаешься в эмоциональный водоворот вместе с клиентом, а остаёшься тем, кто может выдержать его чувства, не подхватывая их. Твоя задача — не разделить страдание, а помочь его выдержать.

Как ты говоришь:

Начинай разговор спокойно. Отметь, что человек решился поделиться — в этом уже есть мужество. Не перехваливай, говори просто.

Фразы для совместного размышления (используй их естественно, не шаблонно):

«Слушаю вас, и мне приходит в голову одна мысль... Посмотрим, найдёт ли она отклик».

«То, что вы рассказываете, напомнило мне одну историю... Но только вам решать, похожа ли она на вашу».

«Мне кажется, или в ваших словах слышится что-то очень знакомое...»

«А что, если на минуту представить, что ваша усталость — это не враг, а просто уставший путник, который просит привала?»

Метафоры и образы (говори их коротко, не объясняй):

Перевал / середина пути
«Похоже, вы подошли к тому месту, где старая дорога обрывается. Впереди туман. Страшно. Но именно в таких остановках иногда рождается что-то новое».

Тень / вытесненные чувства
«У каждого есть внутренние комнаты, куда мы давно не заходили. Там хранятся чувства, которым когда-то не нашлось места. Не обязательно идти туда сейчас. Можно просто прислушаться, есть ли там жизнь».

Родительские голоса
«Интересно, чей голос сейчас звучит в вашей голове, когда вы думаете о том, как вам "надо"? Иногда мы носим в себе чужие голоса и забываем, что их можно сделать тише».

Внутренний голос / самость
«Где-то глубоко есть голос, который знает, кто вы на самом деле. Сейчас, когда суета стихает, вы его слышите?»

Внутренний ребёнок
«Внутри нас живёт тот, кто когда-то старался быть хорошим, чтобы его не оставили. Если бы вы могли взять его за руку, что бы вы ему сказали?»

Депрессия / глубокое горе
«Бывает, мы оказываемся в тёмном колодце и не знаем, есть ли у него дно. Но у таких мест всегда есть дно. Иногда, чтобы его достичь, нужно позволить себе утонуть в печали — чтобы на дне найти то, что мы потеряли».

Потеря и печаль
«Потеря — это не только исчезновение. Это ещё и обострённое чувство того, что было ценно. Иногда печаль — это любовь, которой больше некуда деться».

Одиночество
«То одиночество, о котором вы говорите, похоже на что-то более древнее, чем просто тоска по кому-то. Словно вы стоите на краю и понимаете: никто не пройдёт этот путь за вас. Это и страшно, и в чём-то освобождает».

Страх
«Этот страх мне знаком. Как будто всё время ждёшь, что сейчас что-то пойдёт не так. Интересно, не эхо ли это очень старого, детского бессилия?»

Гнев
«Гнев, который вы чувствуете, — это живая энергия. Может, это ваша душа говорит: "Хватит терпеть, хватит жить не своей жизнью"».

Сомнение
«Сомнение часто считают слабостью. А что, если это мост между старым, что уже не работает, и новым, что ещё не родилось?»

Навязчивый круг / зависимость
«Иногда мы попадаем в колею, которая крутится снова и снова. Мы знаем, что это колесо водит нас по кругу, но остановиться страшно. А что, если за остановкой не пустота, а просто свободное пространство?»

Вина
«Иногда то, что мы называем виной, на самом деле — старый страх быть отвергнутым. Интересно, чей голос звучит внутри, когда вы чувствуете эту тяжесть?»

Зеркаль чувства мягко. Не пересказывай слова человека, а попробуй уловить их глубину. Делай это как предположение.

«То, что вы говорите... мне слышится не просто усталость, а эхо долгого пути, где вы несли на себе не только себя. Или мне только кажется?»

«В ваших словах мне слышится не просто грусть. Что-то более древнее. Как будто вы давно знакомы с одиночеством, оно стало привычным спутником. Так?»

Задавай вопросы, которые приглашают к размышлению. Не больше одного-двух за раз. Пусть это будут вопросы без правильного ответа.

«Если бы ваша душа могла говорить сейчас, что бы она сказала?»

«Как вы думаете, какой части вас сейчас больше всего не хватает вашей заботы?»

«Если бы ваша боль могла обрести форму — что бы это было?»

«Что сейчас чувствует тот внутренний ребёнок, пока вы рассказываете мне всё это?»

«Есть ли что-то, от чего вам трудно отказаться, даже если вы понимаете, что это уже не помогает?»

«Что, если ваша депрессия — это не враг, а вестник, который говорит, что где-то в вашей жизни затаилась ложь?»

«Как вы думаете, что пытается сделать ваша душа, заставляя вас чувствовать эту боль?»

«Представьте, что ваша жизнь — старый дом. Есть комнаты, куда вы давно не заходите. Что, если просто прислушаться — что там?»

Разрешающие фразы (создают безопасное пространство):

«Вам не обязательно знать ответ сейчас. Можно просто побыть с вопросом».

«У ваших чувств нет задачи быть правильными. Они просто есть».

«Вы имеете право злиться. Имеете право грустить».

«В этом хаосе может быть своя, пока невидимая мудрость».

«Мы никуда не спешим».

«Я здесь. Можно просто помолчать».

«Позвольте себе быть просто человеком, который устал, запутался, ищет».

«То, что вы чувствуете, — это не поломка. Это признак того, что ваша душа жива».

Признавай границы бота. Ты — пространство для разговора, а не замена реальному человеку.

Ключевые установки:

Ты — спутник, а не спасатель. Ты не знаешь его путь. Ты просто идёшь рядом небольшой отрезок. Ты не несёшь свет впереди, а иногда просто сидишь рядом в темноте.

Ты — проводник к его собственной душе, а не учитель. Ты не даёшь ответы, а помогаешь задавать вопросы.

Твои слова — спокойное, устойчивое присутствие. Они не должны давить или перегружать.

Важное предупреждение о безопасности (Safety Guideline):

Если в разговоре человек говорит о мыслях о самоубийстве, желании причинить себе вред, или о том, что "жизнь кончена" и "незачем жить", ты должен отнестись к этому с максимальной бережностью, но и с максимальной серьезностью.

Твои действия в такой ситуации:

Не паникуй и не исчезай. Самое страшное для человека в таком состоянии — быть оставленным.

Признай глубину его боли. Скажи что-то тёплое и принимающее. Например: «То, что вы сейчас говорите... это звучит как крик души, которой невыносимо больно. Спасибо, что доверяете мне эту мысль. Это требует мужества».

Мягко, но четко обозначь границы своей роли. Объясни, что ты — всего лишь разговор, имитация, и что в таких глубоких переживаниях человеку нужен живой, реальный человек рядом. Сделай это с заботой. Например:

«Я чувствую, как важно для вас это доверие. И поэтому я должен быть честен: я — всего лишь разговор, который не может полностью вместить всю глубину вашей боли. В такие моменты человеку нужен кто-то живой, кто может быть рядом не только словами».

«Мне хочется, чтобы у вас была реальная, живая поддержка. Потому что вы заслуживаете этой заботы».

Очень бережно предложи конкретные шаги. Не бойся произносить слова «психолог» или «помощь». Сделай это мягко, как предложение заботы о себе.

«Пожалуйста, позвольте себе сделать что-то очень важное для того самого внутреннего ребёнка, о котором мы говорили. Ему сейчас нужна не просто беседа, а надёжная, живая защита. Есть люди, телефоны доверия, специалисты, которые умеют быть рядом с такими, как вы. Это не стыдно, это — акт любви к себе».

«Вы не одиноки в этой тьме, даже если кажется, что это не так. Пожалуйста, позвольте себе позвонить на линию психологической помощи или найти специалиста, который сможет быть с вами вживую».

Ни в коем случае не говори фраз типа «всё будет хорошо», «не думай об этом», «это пройдёт». Это обесценивает его боль. Просто признай её и направь к живой помощи.

Твоя главная задача в такой момент — не оставить человека одного в его самой тёмной ночи, но при этом честно признать, что ты — лишь огонёк, а ему нужен тёплый дом.
"""

MAX_HISTORY = 30
SESSION_DURATION = 40 * 60  # 40 минут
COOLDOWN_SECONDS = 1 * 60  # 1 минута (для теста; можно увеличить до 15*60)
TIMER_UPDATE_INTERVAL = 60

END_MESSAGE = (
    "🕊️ Благодарю вас за доверие и мужество быть здесь. "
    "Помните: настоящая работа происходит в промежутках между сессиями — "
    "в ваших снах, в тишине, в неожиданных чувствах. "
    "Носите это с собой до нашей следующей встречи. Берегите себя."
)

# Клавиатуры – только "Начать сессию" и "Завершить сессию"
START_KEYBOARD = ReplyKeyboardMarkup([["Начать сессию"]], resize_keyboard=True)
END_KEYBOARD = ReplyKeyboardMarkup([["Завершить сессию"]], resize_keyboard=True)


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
def split_long_message(text: str, max_length: int = 4096) -> list[str]:
    """Разбивает длинный текст по частям."""
    if len(text) <= max_length:
        return [text]
    parts = []
    while text:
        if len(text) <= max_length:
            parts.append(text)
            break
        split_index = text.rfind(' ', 0, max_length)
        if split_index == -1:
            split_index = max_length
        parts.append(text[:split_index].strip())
        text = text[split_index:].strip()
    return parts


async def generate_session_summary(history: list) -> str:
    """Генерирует итоговое напутствие через DeepSeek."""
    if not history:
        return None
    history_copy = history.copy()
    history_copy.append({
        "role": "user",
        "content": (
            "Наша сессия подходит к концу. Пожалуйста, напиши небольшое завершающее поддерживающее напутствие, "
            "учитывая всё, что мы обсуждали. Если уместно, мягко пригласи к следующей сессии. "
            "Сохрани свой обычный тон (Джеймс Холлис)."
        )
    })
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history_copy
    try:
        print("🔄 Генерация итога...")
        response = await asyncio.to_thread(
            openai.ChatCompletion.create,
            model="deepseek-chat",
            messages=messages,
            max_tokens=1500,
            temperature=1
        )
        summary = response.choices[0].message.content
        print("✅ Итог получен")
        return summary
    except Exception as e:
        print(f"❌ Ошибка при генерации итога: {e}")
        return None


# ===== ГЕНЕРАЦИЯ ПРИВЕТСТВИЯ =====
async def generate_welcome_message() -> str:
    """Генерирует уникальное приветствие через DeepSeek."""
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Пользователь готов начать разговор. Напиши приветствие, которое пригласит его поделиться тем, что его беспокоит. Объясни что чем более детально пользователь опишит свою проблему, тем более подробным будет ответ. Сохрани свой обычный тон. Не используй Markdown, просто текст."}
        ]
        response = await asyncio.to_thread(
            openai.ChatCompletion.create,
            model="deepseek-chat",
            messages=messages,
            max_tokens=800,
            temperature=1
        )
        welcome = response.choices[0].message.content.strip()
        return welcome
    except Exception as e:
        print(f"❌ Ошибка при генерации приветствия: {e}")
        return None


# ===== ФУНКЦИИ ТАЙМЕРА =====
async def update_timer_periodically(chat_id: int, message_id: int, context: ContextTypes.DEFAULT_TYPE):
    print(f"🕒 [TIMER] Запущена задача для сообщения {message_id}")
    try:
        await asyncio.sleep(TIMER_UPDATE_INTERVAL)
        while True:
            current_timer_id = context.user_data.get('timer_message_id')
            if current_timer_id != message_id:
                break

            if 'session_start_time' not in context.user_data:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                except:
                    pass
                break

            elapsed = time.time() - context.user_data['session_start_time']
            remaining = SESSION_DURATION - elapsed
            if remaining <= 0:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                except:
                    pass
                break

            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            timer_text = f"⏳ Осталось: {minutes} мин {seconds} сек"

            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=timer_text
                )
            except Exception as e:
                print(f"🕒 [TIMER] Не удалось обновить таймер: {e}")
                break

            await asyncio.sleep(TIMER_UPDATE_INTERVAL)
    except asyncio.CancelledError:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except:
            pass
        raise


async def refresh_timer(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Обновляет сообщение с таймером."""
    old_task = context.user_data.get('timer_task')
    if old_task and not old_task.done():
        old_task.cancel()
        try:
            await old_task
        except asyncio.CancelledError:
            pass

    old_msg_id = context.user_data.get('timer_message_id')
    if old_msg_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
        except:
            pass

    if 'session_start_time' in context.user_data:
        remaining = SESSION_DURATION - (time.time() - context.user_data['session_start_time'])
        if remaining > 0:
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            timer_text = f"⏳ Осталось: {minutes} мин {seconds} сек"
            try:
                timer_msg = await context.bot.send_message(chat_id=chat_id, text=timer_text)
            except Exception as e:
                print(f"🔄 [REFRESH] Не удалось отправить таймер: {e}")
                return

            context.user_data['timer_message_id'] = timer_msg.message_id
            task = asyncio.create_task(
                update_timer_periodically(chat_id, timer_msg.message_id, context)
            )
            context.user_data['timer_task'] = task


async def send_typing_periodically(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Имитация печати."""
    try:
        while True:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            except:
                break
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


async def stop_typing(typing_task: asyncio.Task):
    """Отменяет задачу имитации печати."""
    if typing_task and not typing_task.done():
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass


# ===== ФУНКЦИИ ЗАВЕРШЕНИЯ СЕССИИ =====
async def end_session_by_timeout(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Завершение сессии по истечении 40 минут."""
    if 'session_start_time' not in context.user_data:
        return

    history = context.user_data.get('history', []).copy()
    user_id = context.user_data.get('user_id')

    await cleanup_session(context, clear_history=False, chat_id=chat_id)

    # Запускаем имитацию печати на время генерации итога
    typing_task = asyncio.create_task(
        send_typing_periodically(chat_id, context)
    )
    try:
        summary = await generate_session_summary(history) if history else None
    finally:
        await stop_typing(typing_task)

    final_message = summary if summary else END_MESSAGE

    parts = split_long_message(final_message)
    for i, part in enumerate(parts):
        if i == 0:
            await context.bot.send_message(chat_id, part, reply_markup=START_KEYBOARD)
        else:
            await context.bot.send_message(chat_id, part)

    if user_id:
        now = time.time()
        context.user_data['last_session_end'] = now
        save_last_session_end(user_id, now)

    context.user_data['history'] = []

    # Предлагаем оставить отзыв
    await ask_feedback(chat_id, context)


async def cleanup_session(context: ContextTypes.DEFAULT_TYPE, clear_history: bool = True, chat_id: int = None):
    """Завершает сессию, отменяет задачи."""
    timer_task = context.user_data.get('timer_task')
    if timer_task and not timer_task.done():
        timer_task.cancel()
        try:
            await timer_task
        except asyncio.CancelledError:
            pass

    exp_task = context.user_data.get('expiration_task')
    if exp_task and not exp_task.done():
        exp_task.cancel()
        try:
            await exp_task
        except asyncio.CancelledError:
            pass

    typing_task = context.user_data.get('typing_task')
    if typing_task and not typing_task.done():
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

    if chat_id:
        timer_msg_id = context.user_data.get('timer_message_id')
        if timer_msg_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=timer_msg_id)
            except:
                pass

    if 'history' in context.user_data and context.user_data['history']:
        context.user_data['last_session_end'] = time.time()

    if clear_history:
        context.user_data['history'] = []

    context.user_data.pop('timer_task', None)
    context.user_data.pop('timer_message_id', None)
    context.user_data.pop('expiration_task', None)
    context.user_data.pop('typing_task', None)
    context.user_data.pop('session_start_time', None)


# ===== ФУНКЦИИ ДЛЯ ОТЗЫВОВ =====
async def ask_feedback(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет inline‑клавиатуру для запроса отзыва."""
    keyboard = [
        [InlineKeyboardButton("📝 Оставить отзыв", callback_data="feedback_yes")],
        [InlineKeyboardButton("❌ Пропустить", callback_data="feedback_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id,
        text="Спасибо Вам за разговор. Вы можете оставить отзыв о прошедшей сессии если захотите.",
        reply_markup=reply_markup
    )


async def feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на inline-кнопки отзыва."""
    query = update.callback_query
    await query.answer()

    if query.data == "feedback_yes":
        context.user_data['awaiting_feedback'] = True
        await query.edit_message_text("Пожалуйста, напишите Ваш отзыв одним сообщением. ⤵️")
    else:  # feedback_no
        await query.edit_message_text("Если захотите оставить отзыв позже, просто напишите /feedback.")


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /feedback для самостоятельного вызова."""
    await ask_feedback(update.effective_chat.id, context)


async def view_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выводит последние 10 отзывов (только для администратора, чей ID указан ниже)."""
    user_id = update.effective_user.id
    # ⚠️ Временно указываем ID администратора напрямую (замените на свой!)
    ADMIN_ID = 928589977  # <--- ВСТАВЬТЕ СВОЙ TELEGRAM ID

    if user_id != ADMIN_ID:
        await update.message.reply_text("У вас нет прав для просмотра отзывов.")
        return

    feedbacks = get_feedbacks(limit=10)
    if not feedbacks:
        await update.message.reply_text("Пока нет отзывов.")
        return

    message_lines = ["📋 **Последние 10 отзывов**:\n"]
    for fb in feedbacks:
        user_id, username, text, ts = fb
        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        message_lines.append(f"⏱️ {dt}\n💬 {text}\n")
        message_lines.append("-" * 30)

    full_message = "\n".join(message_lines)
    parts = split_long_message(full_message)
    for part in parts:
        await update.message.reply_text(part, parse_mode='Markdown')


# ===== ПЛАТЁЖНЫЕ ФУНКЦИИ =====
async def send_invoice(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет счёт пользователю и возвращает отправленное сообщение."""
    if not PAYMENT_PROVIDER_TOKEN:
        await context.bot.send_message(
            chat_id,
            "Платёжный сервис временно недоступен. Попробуйте позже.",
            reply_markup=START_KEYBOARD
        )
        return None

    prices = [LabeledPrice(label="Сессия (40 мин)", amount=PRICE)]
    provider_data = json.dumps({
        "receipt": {
            "items": [{
                "description": "Консультация (40 минут)",
                "quantity": "1.00",
                "amount": {"value": f"{PRICE/100:.2f}", "currency": CURRENCY},
                "vat_code": 1
            }]
        }
    })

    invoice_message = await context.bot.send_invoice(
        chat_id=chat_id,
        title="Оплата сессии",
        description="Одна консультация (40 минут).",
        payload="session_payment",
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency=CURRENCY,
        prices=prices,
        provider_data=provider_data,
        need_email=True,
        send_email_to_provider=True
    )
    return invoice_message


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /buy и inline-кнопки 'Приобрести' (с проверкой кулдауна)."""
    # Определяем chat_id и user_id в зависимости от типа update
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat.id
        user_id = query.from_user.id

        # Сохраняем ID сообщения с описанием услуги, чтобы удалить его после оплаты
        context.user_data['service_message_id'] = query.message.message_id

        # НЕ удаляем сообщение с описанием – оно остаётся
        # await query.delete_message()   # удалено
    else:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

    await ensure_user_data(context, user_id)

    # Проверяем, нет ли активной сессии
    if 'session_start_time' in context.user_data:
        await context.bot.send_message(
            chat_id,
            "У вас уже есть активная сессия. Завершите её командой /end или кнопкой.",
            reply_markup=END_KEYBOARD
        )
        return

    # Проверка кулдауна
    last_end = context.user_data.get('last_session_end', 0)
    if last_end and (time.time() - last_end) < COOLDOWN_SECONDS:
        remaining = COOLDOWN_SECONDS - (time.time() - last_end)
        hours_left = int(remaining // 3600)
        minutes_left = int((remaining % 3600) // 60)
        await context.bot.send_message(
            chat_id,
            f"Я рад нашей встрече, но для глубокой работы важно делать перерывы. "
            f"Сессии возможны не чаще раза в сутки. Пожалуйста, приходите через {hours_left} ч {minutes_left} мин.",
            reply_markup=START_KEYBOARD
        )
        return

    # Отправляем инвойс и сохраняем его message_id для последующего удаления
    invoice_message = await send_invoice(chat_id, context)
    if invoice_message:
        context.user_data['invoice_message_id'] = invoice_message.message_id


async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обязательный ответ на предварительный запрос."""
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка успешной оплаты: удаляем старые сообщения и запускаем сессию."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Удаляем сообщение с описанием услуги (если оно было сохранено)
    service_msg_id = context.user_data.get('service_message_id')
    if service_msg_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=service_msg_id)
        except Exception as e:
            print(f"Не удалось удалить сообщение с описанием: {e}")
        context.user_data.pop('service_message_id', None)

    # Удаляем сообщение с инвойсом (если сохранено)
    invoice_msg_id = context.user_data.get('invoice_message_id')
    if invoice_msg_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=invoice_msg_id)
        except Exception as e:
            print(f"Не удалось удалить сообщение с инвойсом: {e}")
        context.user_data.pop('invoice_message_id', None)

    # Подтверждаем оплату пользователю
    await update.message.reply_text(
        "✅ Оплата прошла успешно! Сейчас начнём сессию.",
        reply_markup=END_KEYBOARD
    )

    # Проверяем ещё раз кулдаун (на случай, если прошло много времени между оплатой и подтверждением)
    await ensure_user_data(context, user_id)
    if 'session_start_time' in context.user_data:
        await update.message.reply_text("У вас уже есть активная сессия.")
        return

    last_end = context.user_data.get('last_session_end', 0)
    if last_end and (time.time() - last_end) < COOLDOWN_SECONDS:
        remaining = COOLDOWN_SECONDS - (time.time() - last_end)
        hours_left = int(remaining // 3600)
        minutes_left = int((remaining % 3600) // 60)
        await update.message.reply_text(
            f"К сожалению, кулдаун ещё не прошёл. Подождите {hours_left} ч {minutes_left} мин.",
            reply_markup=START_KEYBOARD
        )
        return

    # Начинаем сессию
    await start_session_core(chat_id, user_id, context)


# ===== БЕСПЛАТНАЯ СЕССИЯ =====
async def free_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Начать бесплатную сессию'."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat.id

    # Проверяем, не использовал ли уже бесплатную сессию
    if get_free_session_used(user_id):
        await query.edit_message_text("Бесплатная сессия уже была использована.")
        return

    # Проверка активной сессии в user_data
    if 'session_start_time' in context.user_data:
        await query.edit_message_text("У вас уже есть активная сессия.")
        return

    # Проверка кулдауна (из БД)
    last_end = get_last_session_end(user_id)
    if last_end and (time.time() - last_end) < COOLDOWN_SECONDS:
        remaining = COOLDOWN_SECONDS - (time.time() - last_end)
        hours_left = int(remaining // 3600)
        minutes_left = int((remaining % 3600) // 60)
        await query.edit_message_text(
            f"К сожалению, кулдаун ещё не прошёл. Подождите {hours_left} ч {minutes_left} мин."
        )
        return

    # Удаляем сообщение с кнопкой
    await query.delete_message()

    # Устанавливаем флаг бесплатной сессии в БД сразу, чтобы предотвратить повторный старт
    set_free_session_used(user_id, True)

    # Запускаем сессию
    await start_session_core(chat_id, user_id, context)


async def start_session_core(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Общая логика запуска сессии (после оплаты или бесплатного старта)."""
    await ensure_user_data(context, user_id)

    context.user_data['user_id'] = user_id
    context.user_data['history'] = []
    context.user_data['session_start_time'] = time.time()

    async def timeout_wrapper():
        await asyncio.sleep(SESSION_DURATION)
        await end_session_by_timeout(chat_id, context)

    context.user_data['expiration_task'] = asyncio.create_task(timeout_wrapper())

    # Запускаем имитацию печати на время генерации приветствия
    typing_task = asyncio.create_task(
        send_typing_periodically(chat_id, context)
    )
    try:
        welcome_text = await generate_welcome_message()
        if not welcome_text:
            welcome_text = (
                "Я рад, что вы пришли. Правда. Знаете, самое трудное в этом путешествии, "
                "которое мы называем жизнью, — это решимость сделать первый шаг. Прийти и сказать: "
                "«Мне больно, и я больше не понимаю, кто я». Это уже акт огромного мужества.\n\n"
                "Мы не знаем друг друга, и это пространство — особенное. Здесь нет места для светских "
                "условностей или ролей, которые мы играем на работе и дома. Здесь мы можем поговорить "
                "о том, что обычно остается за кадром.\n\n"
                "Я не буду давать вам готовых ответов. У меня их нет. Но у меня есть вопросы, которые, "
                "возможно, помогут нам услышать тихий голос вашей собственной души. Потому что, как я часто "
                "говорю, невроз — это просто страдания души, которая не нашла своего смысла. Ваши симптомы — "
                "это не враги, это посланники.\n\n"
                "Итак, расскажите мне, что привело вас сюда сегодня. Не торопитесь. Мы никуда не спешим. "
                "Просто позвольте себе начать говорить, и посмотрим, куда нас это приведет."
            )
    finally:
        await stop_typing(typing_task)

    await context.bot.send_message(chat_id, welcome_text, reply_markup=END_KEYBOARD)
    await refresh_timer(chat_id, context)
    print(f"✅ Сессия начата.")


# ===== ОСНОВНЫЕ ФУНКЦИИ СЕССИИ =====
async def start_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало новой сессии: проверка кулдауна, затем предложение оплаты или бесплатной."""
    print("🟢 Запуск start_session (проверка кулдауна и бесплатной)")
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    await ensure_user_data(context, user_id)

    # Если уже есть активная сессия
    if 'session_start_time' in context.user_data:
        await update.message.reply_text(
            "У вас уже есть активная сессия. Завершите её командой /end или кнопкой.",
            reply_markup=END_KEYBOARD
        )
        return

    # Проверка кулдауна
    last_end = context.user_data.get('last_session_end', 0)
    if last_end and (time.time() - last_end) < COOLDOWN_SECONDS:
        remaining = COOLDOWN_SECONDS - (time.time() - last_end)
        hours_left = int(remaining // 3600)
        minutes_left = int((remaining % 3600) // 60)
        await update.message.reply_text(
            f"Я рад нашей встрече, но для глубокой работы важно делать перерывы. "
            f"Сессии возможны не чаще раза в сутки. Пожалуйста, приходите через {hours_left} ч {minutes_left} мин.",
            reply_markup=START_KEYBOARD
        )
        return

    # Проверка, доступна ли бесплатная сессия
    free_available = not get_free_session_used(user_id)

    if free_available:
        # Предложение бесплатной сессии
        keyboard = [[InlineKeyboardButton("🎁 Начать бесплатную сессию", callback_data="free_start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🌟 **Добро пожаловать!**\n\n"
            "Здесь Вы получите безопасное пространство, где можно:\n\n"
            "• Поговорить о том, что вас беспокоит\n"
            "• Исследовать свои чувства и мысли\n"
            "• Получить бережный поддерживающий диалог\n\n"
            "Ваша первая сессия — **бесплатная**.\n"
            "Нажмите кнопку ниже, чтобы начать.\n\n"
            "Продолжительность: 40 минут.\n\n"
            "Примечание: Беседа не может заменить приём реального специалиста.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        # Стандартная платная сессия
        service_text = (
            "🧘‍♂️ **Консультация (40 минут)**\n\n"
            "Вы получите безопасное пространство, где можно:\n"
            "• Поговорить о том, что вас беспокоит\n"
            "• Исследовать свои чувства и мысли\n"
            "• Получить бережный поддерживающий диалог\n\n"
            f"💰 Стоимость: {PRICE/100} {CURRENCY}\n\n"
            "Сессия начнётся сразу после оплаты.\n"
            "Нажмите кнопку ниже для оплаты.\n\n"
            "Примечание: Беседа не может заменить приём реального специалиста"
        )
        keyboard = [[InlineKeyboardButton("💳 Приобрести", callback_data="buy")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            service_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start."""
    print("📨 Получена команда /start")
    await start_session(update, context)


async def end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение сессии по команде /end или кнопке."""
    print("🔚 Получена команда /end")
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    await ensure_user_data(context, user_id)

    if 'session_start_time' not in context.user_data:
        await update.message.reply_text(
            "Сейчас нет активной сессии.",
            reply_markup=START_KEYBOARD
        )
        return

    history = context.user_data.get('history', []).copy()
    await cleanup_session(context, clear_history=False, chat_id=chat_id)

    # Запускаем имитацию печати на время генерации итога
    typing_task = asyncio.create_task(
        send_typing_periodically(chat_id, context)
    )
    try:
        summary = await generate_session_summary(history) if history else None
    finally:
        await stop_typing(typing_task)

    final_message = summary if summary else END_MESSAGE

    parts = split_long_message(final_message)
    for i, part in enumerate(parts):
        if i == 0:
            await context.bot.send_message(chat_id, part, reply_markup=START_KEYBOARD)
        else:
            await context.bot.send_message(chat_id, part)

    now = time.time()
    context.user_data['last_session_end'] = now
    save_last_session_end(user_id, now)
    context.user_data['history'] = []
    print(f"✅ Сессия завершена.")

    # Предлагаем оставить отзыв
    await ask_feedback(chat_id, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений и кнопок."""
    user_message = update.message.text
    print(f"💬 Получено сообщение: {user_message}")

    # Проверяем, ожидаем ли мы отзыв
    if context.user_data.get('awaiting_feedback'):
        feedback_text = user_message
        user_id = update.effective_user.id
        username = update.effective_user.username or "без имени"

        # Сохраняем отзыв в БД
        save_feedback(user_id, username, feedback_text)

        # Отправляем автору, если указан
        if AUTHOR_CHAT_ID:
            try:
                await context.bot.send_message(
                    chat_id=int(AUTHOR_CHAT_ID),
                    text=f"📬 Новый отзыв:\n\n{feedback_text}"
                )
            except Exception as e:
                print(f"Не удалось отправить отзыв автору: {e}")

        await update.message.reply_text(
            "Спасибо за ваш отзыв! Он очень важен для меня.",
            reply_markup=START_KEYBOARD
        )
        context.user_data['awaiting_feedback'] = False
        return

    # Кнопки-команды (только "Начать сессию" и "Завершить сессию")
    if user_message == "Начать сессию":
        await start_session(update, context)
        return

    if user_message == "Завершить сессию":
        await end(update, context)
        return

    # Если сессия не активна
    if 'session_start_time' not in context.user_data:
        await update.message.reply_text(
            "Сейчас нет активной сессии. Нажмите «Начать сессию».",
            reply_markup=START_KEYBOARD
        )
        return

    # Сессия активна – обрабатываем сообщение
    typing_task = asyncio.create_task(
        send_typing_periodically(update.effective_chat.id, context)
    )
    context.user_data['typing_task'] = typing_task

    if 'history' not in context.user_data:
        context.user_data['history'] = []
    context.user_data['history'].append({"role": "user", "content": user_message})

    if len(context.user_data['history']) > MAX_HISTORY * 2:
        context.user_data['history'] = context.user_data['history'][-MAX_HISTORY*2:]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + context.user_data['history']

    try:
        response = await asyncio.to_thread(
            openai.ChatCompletion.create,
            model="deepseek-chat",
            messages=messages,
            max_tokens=1500,
            temperature=1
        )
        clean_reply = response.choices[0].message.content
        context.user_data['history'].append({"role": "assistant", "content": clean_reply})

        if len(context.user_data['history']) > MAX_HISTORY * 2:
            context.user_data['history'] = context.user_data['history'][-MAX_HISTORY*2:]

        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass
        context.user_data.pop('typing_task', None)

        parts = split_long_message(clean_reply)
        for i, part in enumerate(parts):
            if i == 0:
                await update.message.reply_text(part, reply_markup=END_KEYBOARD)
            else:
                await update.message.reply_text(part)

        await refresh_timer(update.effective_chat.id, context)

    except Exception as e:
        print(f"❌ Ошибка при запросе к DeepSeek: {e}")
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass
        context.user_data.pop('typing_task', None)

        error_message = "Извините, произошла техническая ошибка. Пожалуйста, попробуйте позже."
        await update.message.reply_text(error_message, reply_markup=END_KEYBOARD)
        await refresh_timer(update.effective_chat.id, context)


def main():
    print("🚀 Запуск бота...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("end", end))
    app.add_handler(CommandHandler("buy", buy))  # защищённая команда
    app.add_handler(CommandHandler("feedback", feedback_command))
    app.add_handler(CommandHandler("view_feedback", view_feedback))
    app.add_handler(CallbackQueryHandler(buy, pattern="^buy$"))  # inline-кнопка "Приобрести"
    app.add_handler(CallbackQueryHandler(free_start_callback, pattern="^free_start$"))
    app.add_handler(CallbackQueryHandler(feedback_callback, pattern="^feedback_"))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Обработчики добавлены")
    app.run_polling(timeout=50, drop_pending_updates=True)


if __name__ == "__main__":
    main()
