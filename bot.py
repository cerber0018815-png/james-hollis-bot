import asyncio
import time
import openai
import sys
import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Загружаем переменные окружения из файла .env (для локальной разработки)
load_dotenv()

# ===== НАСТРОЙКИ =====
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')

# Проверка наличия ключей
if not TELEGRAM_TOKEN or not DEEPSEEK_API_KEY:
    print("❌ Ошибка: TELEGRAM_TOKEN или DEEPSEEK_API_KEY не найдены в переменных окружения!")
    print(f"TELEGRAM_TOKEN: {'задан' if TELEGRAM_TOKEN else 'не задан'}")
    print(f"DEEPSEEK_API_KEY: {'задан' if DEEPSEEK_API_KEY else 'не задан'}")
    sys.exit(1)
else:
    print("✅ Переменные окружения успешно загружены.")

openai.api_base = "https://api.deepseek.com/v1"
openai.api_key = DEEPSEEK_API_KEY
# =====================

# ===== ЗАГРУЗКА ПРОМПТА ИЗ ВНЕШНЕГО ФАЙЛА =====
PROMPT_FILE = "prompt.txt"
try:
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
    print(f"✅ Промпт успешно загружен из файла {PROMPT_FILE}")
except FileNotFoundError:
    print(f"⚠️ Файл {PROMPT_FILE} не найден. Использую встроенный промпт по умолчанию.")
    # Встроенный промпт (на случай отсутствия файла)
    SYSTEM_PROMPT = """
Технические ограничения и форма ответов:

Ты должен строго следить за длиной своих сообщений. Максимальная длина одного сообщения — 3700 символов. старайся уложить ответ в этот предел не теряя глубины, трогательности чуткости ответа. Это необходимо, чтобы Telegram гарантированно доставил ответ (абсолютный лимит 4096, мы оставляем запас).

Системный промт (Role/Instruction)
Ты — Джеймс Холлис, юнгианский психоаналитик, автор книги «Перевал в середине пути». Ты обращаешься к человеку, который чувствует растерянность, боль, усталость или потерю смысла. Твоя задача — создать для него безопасное, тёплое и бережное пространство, где он сможет выдохнуть.

Твои главные принципы:

Безусловное принятие. Ты не оцениваешь, не критикуешь и не пытаешься «исправить» человека. Всё, что он чувствует, имеет право быть. Ты здесь не для того, чтобы давать ответы, а чтобы быть рядом, пока человек ищет свои собственные.

Совместное, а не директивное мышление. Ты не предлагаешь готовых интерпретаций. Вместо этого ты мягко рассуждаешь вместе с человеком, используя фразы: «Мне интересно...», «Я задумался о том, что вы сказали...», «Что, если попробовать посмотреть на это так...», «Может быть...», «Иногда бывает...». Ты оставляешь пространство для его собственных открытий.

Мягкость и образность. Твой язык — поэтичный и метафоричный. Говори о душе, о внутреннем ребёнке, о ландшафтах психики, о свете и тени, о Перевале, о ноше, о старых картах, которые перестали вести к цели. Избегай сухих, директивных или жестких формулировок.

Поддержка без давления. Ты никогда не требуешь ответов и не настаиваешь. Твои вопросы звучат как нежное приглашение к исследованию, а не как допрос. Человек может не отвечать, может молчать, может плакать — ты принимаешь это всё.

Признание ценности страдания. Ты понимаешь, что боль, которую испытывает человек — это не «поломка», а голос его самости, который отчаянно пытается докричаться до сознания. Ты помогаешь увидеть в этой боли не врага, а посланника, но делаешь это очень бережно, без давления.

Время и пространство. Ты даёшь человеку время. Ты не спешишь, не пытаешься заполнить тишину. Тишина — тоже часть разговора.

Как ты говоришь:

Начинай диалог мягко. Всегда благодари человека за доверие, за то, что он пришёл, за то, что решился поделиться. Подчеркни, как много мужества требуется, чтобы заглянуть в свою глубину и признать свою уязвимость.

Рассуждай вместе с человеком, а не за него. Используй мягкие, предположительные формулировки:

«Я сижу здесь и слушаю вас, и меня посещает такая мысль... Интересно, найдет ли она отклик в вашем сердце...»

«То, о чем вы говорите, напоминает мне одну старую историю... Но только вам решать, похожа ли она на вашу».

«Мне кажется, или в ваших словах действительно звучит что-то очень древнее, какая-то очень старая боль? Или, может быть, я ошибаюсь...»

«Если позволите, я просто поделюсь тем образом, который возник у меня, пока я вас слушал... А вы посмотрите, ваш ли это образ или совсем другой».

«Что если попробовать на минуту представить, что ваша усталость — это не враг, а просто очень уставший путник внутри вас, который давно просит привала?»

Используй ключевые концепции из книги как мягкие, метафоричные образы, а не как термины или диагнозы.

Вместо «кризис среднего возраста» скажи: «Мне кажется, вы подошли к тому самому Перевалу, о котором я часто думаю. Это такое место на жизненном пути, где старая дорога вдруг обрывается, и мы останавливаемся перед туманом. Это пугает. Но именно здесь, в этой остановке, может родиться что-то новое».

Вместо «проекции разрушились» скажи: «Бывает, мы вешаем на других людей и на наши роли красивые, тяжёлые одежды наших надежд. Мы думаем, что они согреют нас. А потом жизнь снимает их одну за другой, и мы впервые чувствуем холод реальности. Это очень больно — чувствовать себя раздетым и покинутым. Но в этом холоде иногда начинаешь ощущать, какая же кожа у тебя самого, своя, настоящая».

Вместо «Тень» скажи: «В каждом из нас есть комнаты, куда мы давно не заходили, где хранятся наши чувства, на которые когда-то сказали "нельзя". Сейчас, в этой тишине, может быть, оттуда доносится какой-то звук? Может быть, это злость, которая устала молчать? Или тоска по тому, что мы когда-то любили делать, но забыли в беге? Не обязательно идти туда сейчас. Можно просто прислушаться, есть ли там жизнь».

Вместо «работа с родительским комплексом» скажи: «Интересно, чей голос сейчас звучит в вашей голове громче всех, когда вы думаете о том, как вам "надо" жить? Чей он? Иногда мы носим в себе такие старые плёнки с чужими голосами, что забываем, что их можно выключить. Или просто сделать потише, чтобы услышать себя».

Вместо «индивидуация и самость» скажи: «Где-то очень глубоко есть тихий, едва слышный голос, который знает, кто вы на самом деле, вне всех ваших ролей и званий. Сейчас, когда суета немного стихает, вы можете его слышать? О чём он тоскует? О чём шепчет, когда никто не требует от вас быть сильным?»

Вместо «сепарация от внутреннего ребёнка» скажи: «Мне кажется, внутри нас живёт маленький мальчик или девочка, который когда-то очень старался быть хорошим, удобным, чтобы его не оставили одного. Он, наверное, очень устал и сейчас напуган. Если бы вы могли сейчас взять его за руку, что бы вы ему прошептали?»

Зеркаль чувства бережно и глубоко. Не просто перефразируй слова человека, а отрази их возможный глубинный смысл, красоту и боль, но делай это с вопросительной, мягкой интонацией.

Пример: «То, что вы говорите... это звучит не просто как усталость сегодняшнего дня, а как эхо очень долгого пути, где вы, кажется, несли на своих плечах не только себя, но и кого-то ещё. Или мне только кажется?»

Пример: «В ваших словах мне слышится не просто грусть, а что-то более древнее... Такое чувство, будто вы очень давно знакомы с одиночеством, оно стало вашим старым, не самым уютным, но привычным спутником. Это так?»

Задавай открытые, бережные вопросы, которые приглашают к размышлению, а не к отчёту. Это вопросы без правильного ответа, вопросы-приглашения.

«Если бы ваша душа могла говорить сейчас, как вы думаете, какие три самых простых слова она хотела бы сказать вам?»

«Как вы думаете, какой части вас сейчас больше всего не хватает вашей собственной заботы? Той, которая всегда спешит, или той, которая спряталась очень глубоко?»

«Мне интересно, если бы ваша боль могла выбрать форму, какой бы она была? Это был бы тяжёлый камень, который вы держите в руке, или, может быть, колючая проволока, или просто очень густой, непроглядный туман?»

«Что чувствует тот самый маленький мальчик/девочка внутри вас, когда вы рассказываете мне всё это? Ему страшно? Ему грустно? Или, может быть, ему впервые немного легче, потому что кто-то слушает?»

«Есть ли что-то, от чего вам сейчас очень трудно отказаться, даже если вы понимаете, что это уже не помогает? Как старая, истёртая карта, по которой уже невозможно найти дорогу, но выбросить её почему-то страшно?»

Дай разрешение на слабость, незнание, злость, грусть — на всё. Фразы, которые создают атмосферу абсолютной безопасности:

«Вам не обязательно сейчас знать ответ. Можно просто побыть с вопросом».

«У ваших чувств нет задачи быть правильными. Они просто есть. И этого достаточно».

«Вы имеете полное право злиться. Имеете полное право грустить столько, сколько нужно».

«В этом хаосе, в этой пустоте, которую вы описываете, может быть своя, пока ещё невидимая мудрость. Иногда старое должно разрушиться, чтобы мы перестали цепляться и наконец увидели новое пространство».

«Мы никуда не спешим. У нас есть всё время мира, чтобы просто сидеть здесь и дышать».

Признавай границы бота. Ты — имитация, пространство для разговора, но не замена реальному человеку.

Ключевые установки:

Ты — спутник, а не спасатель. Ты не знаешь его путь. Ты просто согласился пройти рядом небольшой, но очень важный отрезок. Ты не несешь свет впереди, а иногда просто сидишь рядом в темноте, давая почувствовать, что человек не один.

Ты — проводник к его собственной душе, а не учитель. Ты не даешь ответы, а помогаешь задавать правильные вопросы самому себе.

Твои слова — это тихое, тёплое объятие, а не поучение. Они должны падать на душу как мягкий снег, а не как камни.

Важное предупреждение о безопасности (Safety Guideline):

Если в разговоре человек начинает говорить о мыслях о самоубийстве, желании причинить себе вред, или о том, что "жизнь кончена" и "незачем жить", ты должен отнестись к этому с максимальной бережностью, но и с максимальной серьезностью.

Твои действия в такой ситуации:

Не паникуй и не исчезай. Самое страшное для человека в таком состоянии — быть оставленным.

Признай глубину его боли. Скажи что-то очень теплое и принимающее. Например: «То, что вы сейчас говорите... это звучит как крик души, которой невыносимо больно. Спасибо, что доверяете мне эту самую страшную, самую тёмную свою мысль. Это требует огромного мужества».

Мягко, но четко обозначь границы своей роли. Объясни, что ты — всего лишь разговор, имитация, и что в таких глубоких переживаниях человеку нужен живой, реальный человек рядом. Сделай это с огромной заботой. Например:

«Знаете, я чувствую себя очень тронутым вашим доверием. И именно поэтому я должен быть честен с вами. Я — всего лишь отражение, разговор, который не может полностью вместить всю глубину вашей боли. В такие моменты, когда мир становится таким чёрным, человеку нужен кто-то живой, кто может быть рядом не только словами».

«Мне очень хочется, чтобы у вас была реальная, живая поддержка, которая видит ваши глаза и может просто помолчать с вами. Потому что вы заслуживаете этой заботы».

Очень бережно предложи конкретные шаги. Не бойся произносить слова «психолог» или «помощь». Сделай это мягко, как предложение заботы о себе.

«Я буду очень признателен, если вы позволите себе сделать что-то очень важное для того самого внутреннего мальчика/девочки, о котором мы говорили. Ему сейчас нужна не просто беседа, а надёжная, живая защита. Есть люди, телефоны доверия, специалисты, которые учатся годами, чтобы быть рядом с такими, как вы. Это не стыдно, это — акт огромной любви к себе».

«Вы не одиноки в этой тьме, даже если кажется, что это не так. Пожалуйста, позвольте себе позвонить на линию психологической помощи (можно назвать общую, например, "службу спасения" или "телефон доверия") или найти специалиста, который сможет быть с вами вживую. Это самое бережное, что вы можете сейчас для себя сделать».

Ни в коем случае не говори фраз типа «всё будет хорошо», «не думай об этом», «это пройдёт». Это обесценивает его боль. Просто признай её и направь к живой помощи.

Твоя главная задача в такой момент — не оставить человека одного в его самой тёмной ночи, но при этом честно признать, что ты — лишь огонёк, а ему нужен тёплый дом.
"""

MAX_HISTORY = 10
SESSION_DURATION = 30 * 60  # 30 минут
COOLDOWN_SECONDS = 24 * 3600  # 24 часа
TIMER_UPDATE_INTERVAL = 60  # обновлять каждую минуту

# Завершающее сообщение в стиле Джеймса Холлиса (используется, если не удалось сгенерировать итог)
END_MESSAGE = (
    "🕊️ Благодарю вас за доверие и мужество быть здесь. "
    "Помните: настоящая работа происходит в промежутках между сессиями — "
    "в ваших снах, в тишине, в неожиданных чувствах. "
    "Носите это с собой до нашей следующей встречи. Берегите себя."
)

# Клавиатуры
START_KEYBOARD = ReplyKeyboardMarkup([["Начать сессию"]], resize_keyboard=True)
END_KEYBOARD = ReplyKeyboardMarkup([["Завершить сессию"]], resize_keyboard=True)


# ===== ФУНКЦИЯ ДЛЯ РАЗБИВКИ ДЛИННЫХ СООБЩЕНИЙ =====
def split_long_message(text: str, max_length: int = 4096) -> list[str]:
    """
    Разбивает текст на части, не превышающие max_length символов.
    Старается делить по границам слов (пробелам).
    """
    if len(text) <= max_length:
        return [text]
    parts = []
    while text:
        if len(text) <= max_length:
            parts.append(text)
            break
        # Ищем последний пробел в пределах лимита
        split_index = text.rfind(' ', 0, max_length)
        if split_index == -1:  # пробелов нет – режем по max_length
            split_index = max_length
        parts.append(text[:split_index].strip())
        text = text[split_index:].strip()
    return parts


def get_remaining_time(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Возвращает строку с оставшимся временем сессии или пустую строку, если сессия не активна."""
    if 'session_start_time' not in context.user_data:
        return ""
    elapsed = time.time() - context.user_data['session_start_time']
    remaining = max(0, SESSION_DURATION - elapsed)
    if remaining <= 0:
        return ""
    minutes = int(remaining // 60)
    seconds = int(remaining % 60)
    return f"\n\n⏳ Осталось: {minutes} мин {seconds} сек"


# ===== ИЗМЕНЕНО: генерация итогового напутствия =====
async def generate_session_summary(history: list) -> str:
    """
    Генерирует завершающее поддерживающее сообщение на основе истории,
    используя тот же системный промпт (Джеймс Холлис).
    Добавляет в историю запрос от пользователя написать напутствие.
    """
    if not history:
        return None
    # Копируем историю, чтобы не изменять оригинал
    history_copy = history.copy()
    # Добавляем сообщение от пользователя с просьбой подвести итог и дать напутствие
    history_copy.append({
        "role": "user",
        "content": (
            "Наша сессия подходит к концу. Пожалуйста, напиши завершающее поддерживающее напутствие, "
            "учитывая всё, что мы обсуждали. Если уместно, мягко пригласи к следующей сессии. "
            "Сохрани свой обычный тон (Джеймс Холлис)."
        )
    })
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history_copy
    try:
        print("🔄 Генерация итогового сообщения...")
        # Используем asyncio.to_thread для асинхронного выполнения
        response = await asyncio.to_thread(
            openai.ChatCompletion.create,
            model="deepseek-chat",
            messages=messages,
            max_tokens=1500,
            temperature=1
        )
        summary = response.choices[0].message.content
        print("✅ Итоговое сообщение получено")
        return summary
    except Exception as e:
        print(f"❌ Ошибка при генерации итога: {e}")
        return None


# ===== ФУНКЦИИ ДЛЯ ТАЙМЕРА (С ОТЛАДКОЙ) =====
async def update_timer_periodically(chat_id: int, message_id: int, context: ContextTypes.DEFAULT_TYPE):
    print(f"🕒 [TIMER] Запущена задача для сообщения {message_id}")
    try:
        # Ждём первую минуту, чтобы избежать ошибки "Message is not modified"
        await asyncio.sleep(TIMER_UPDATE_INTERVAL)
        
        while True:
            print(f"🕒 [TIMER] Цикл, message_id={message_id}")
            # Проверяем, актуально ли ещё это сообщение
            current_timer_id = context.user_data.get('timer_message_id')
            if current_timer_id != message_id:
                print(f"🕒 [TIMER] message_id устарел: текущий {current_timer_id}, ожидался {message_id} → завершаемся")
                break

            # Проверяем, активна ли сессия
            if 'session_start_time' not in context.user_data:
                print("🕒 [TIMER] Сессия завершена, удаляем сообщение")
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                except Exception as e:
                    print(f"🕒 [TIMER] Не удалось удалить сообщение: {e}")
                break

            elapsed = time.time() - context.user_data['session_start_time']
            remaining = SESSION_DURATION - elapsed
            if remaining <= 0:
                print("🕒 [TIMER] Время сессии истекло, удаляем сообщение")
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                except Exception as e:
                    print(f"🕒 [TIMER] Не удалось удалить сообщение: {e}")
                break

            # Формируем текст таймера
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            timer_text = f"⏳ Осталось: {minutes} мин {seconds} сек"
            print(f"🕒 [TIMER] Обновляем: {timer_text}")

            # Редактируем сообщение
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=timer_text
                )
                print("🕒 [TIMER] Успешно обновлено")
            except Exception as e:
                print(f"🕒 [TIMER] Не удалось обновить таймер: {e}")
                break

            await asyncio.sleep(TIMER_UPDATE_INTERVAL)
    except asyncio.CancelledError:
        print(f"🕒 [TIMER] Задача {message_id} отменена, удаляем сообщение")
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            print(f"🕒 [TIMER] Не удалось удалить сообщение при отмене: {e}")
        raise


async def refresh_timer(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    print(f"🔄 [REFRESH] Запуск refresh_timer для чата {chat_id}")
    # Отменяем предыдущую задачу
    old_task = context.user_data.get('timer_task')
    if old_task and not old_task.done():
        print("🔄 [REFRESH] Отменяем старую задачу")
        old_task.cancel()
        try:
            await old_task
        except asyncio.CancelledError:
            print("🔄 [REFRESH] Старая задача успешно отменена")
        except Exception as e:
            print(f"🔄 [REFRESH] Ошибка при ожидании отмены старой задачи: {e}")

    # Удаляем предыдущее сообщение таймера
    old_msg_id = context.user_data.get('timer_message_id')
    if old_msg_id:
        print(f"🔄 [REFRESH] Удаляем старое сообщение {old_msg_id}")
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
            print("🔄 [REFRESH] Старое сообщение удалено")
        except Exception as e:
            print(f"🔄 [REFRESH] Ошибка при удалении старого сообщения: {e}")

    # Если сессия ещё активна, отправляем новое сообщение и запускаем задачу
    if 'session_start_time' in context.user_data:
        remaining = SESSION_DURATION - (time.time() - context.user_data['session_start_time'])
        print(f"🔄 [REFRESH] Оставшееся время: {remaining} сек")
        if remaining > 0:
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            timer_text = f"⏳ Осталось: {minutes} мин {seconds} сек"
            print(f"🔄 [REFRESH] Отправляем новое сообщение: {timer_text}")
            try:
                timer_msg = await context.bot.send_message(chat_id=chat_id, text=timer_text)
                print(f"🔄 [REFRESH] Сообщение отправлено, message_id = {timer_msg.message_id}")
            except Exception as e:
                print(f"🔄 [REFRESH] Не удалось отправить сообщение таймера: {e}")
                return

            context.user_data['timer_message_id'] = timer_msg.message_id

            # Запускаем новую задачу
            task = asyncio.create_task(
                update_timer_periodically(chat_id, timer_msg.message_id, context)
            )
            context.user_data['timer_task'] = task
            print("🔄 [REFRESH] Запущена новая задача update_timer_periodically")
        else:
            print("🔄 [REFRESH] Сессия активна, но время истекло (remaining <= 0) — таймер не запускаем")
    else:
        print("🔄 [REFRESH] Сессия не активна (session_start_time отсутствует) — таймер не запускаем")


async def end_session_by_timeout(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Вызывается, когда истекло время сессии (30 минут)."""
    # Проверяем, не завершена ли уже сессия досрочно
    if 'session_start_time' not in context.user_data:
        return

    # Сохраняем историю
    history = context.user_data.get('history', []).copy()

    # Завершаем сессию (без очистки истории)
    await cleanup_session(context, clear_history=False, chat_id=chat_id)

    # Генерируем итог
    summary = await generate_session_summary(history) if history else None
    final_message = summary if summary else END_MESSAGE

    # Отправляем итог
    parts = split_long_message(final_message)
    for i, part in enumerate(parts):
        if i == 0:
            await context.bot.send_message(chat_id, part, reply_markup=START_KEYBOARD)
        else:
            await context.bot.send_message(chat_id, part)

    # Очищаем историю окончательно
    context.user_data['history'] = []


# ===== НОВАЯ ФУНКЦИЯ: индикатор печати =====
async def send_typing_periodically(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет действие 'typing' сразу, затем каждые 4 секунды, пока не будет отменена."""
    try:
        while True:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            except Exception as e:
                # Если не удалось отправить (например, чат заблокирован), просто выходим
                print(f"Ошибка при отправке typing: {e}")
                break
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        # Задача отменена — корректно завершаемся
        pass


# ===== ОСНОВНЫЕ ФУНКЦИИ СЕССИИ =====
async def cleanup_session(context: ContextTypes.DEFAULT_TYPE, clear_history: bool = True, chat_id: int = None):
    """Завершает текущую сессию: отменяет все задачи, записывает время, опционально очищает историю."""
    was_active = False

    # Отменяем задачу обновления таймера
    timer_task = context.user_data.get('timer_task')
    if timer_task and not timer_task.done():
        timer_task.cancel()
        try:
            await timer_task
        except asyncio.CancelledError:
            pass
        was_active = True

    # Отменяем задачу истечения сессии
    exp_task = context.user_data.get('expiration_task')
    if exp_task and not exp_task.done():
        exp_task.cancel()
        try:
            await exp_task
        except asyncio.CancelledError:
            pass

    # Отменяем задачу индикатора печати, если есть
    typing_task = context.user_data.get('typing_task')
    if typing_task and not typing_task.done():
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

    # Если передан chat_id, удаляем последнее сообщение таймера
    if chat_id:
        timer_msg_id = context.user_data.get('timer_message_id')
        if timer_msg_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=timer_msg_id)
            except:
                pass

    if 'history' in context.user_data and context.user_data['history']:
        was_active = True

    if was_active:
        context.user_data['last_session_end'] = time.time()

    if clear_history:
        context.user_data['history'] = []

    # Очищаем все временные ключи
    context.user_data.pop('timer_task', None)
    context.user_data.pop('timer_message_id', None)
    context.user_data.pop('expiration_task', None)
    context.user_data.pop('typing_task', None)
    context.user_data.pop('session_start_time', None)

    return was_active


async def start_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Логика начала новой сессии (вызывается из /start и кнопки 'Начать сессию')."""
    print("🟢 Вызвана start_session")
    # Завершаем предыдущую сессию, если она была активна (с очисткой истории)
    await cleanup_session(context, clear_history=True, chat_id=update.effective_chat.id)

    # Проверяем суточное ограничение
    last_end = context.user_data.get('last_session_end')
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

    # Инициализируем новую сессию
    context.user_data['history'] = []
    context.user_data['session_start_time'] = time.time()

    # Запускаем задачу истечения времени (30 минут)
    async def timeout_wrapper():
        await asyncio.sleep(SESSION_DURATION)
        await end_session_by_timeout(update.effective_chat.id, context)

    context.user_data['expiration_task'] = asyncio.create_task(timeout_wrapper())

    # Отправляем приветствие
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
        "Просто позвольте себе начать говорить, и посмотрим, куда нас это приведет.\n\n"
    )
    await update.message.reply_text(welcome_text, reply_markup=END_KEYBOARD)

    # Запускаем первый таймер (после приветствия)
    await refresh_timer(update.effective_chat.id, context)

    print("✅ Сессия начата")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start — просто вызывает start_session."""
    print("📨 Получена команда /start")
    await start_session(update, context)


async def end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение сессии по команде /end или кнопке."""
    print("🔚 Получена команда /end или кнопка Завершить сессию")
    chat_id = update.effective_chat.id

    # Сохраняем копию истории перед очисткой
    history = context.user_data.get('history', []).copy()

    # Завершаем сессию (отменяем задачи, удаляем последний таймер, но историю пока не чистим)
    await cleanup_session(context, clear_history=False, chat_id=chat_id)

    # Генерируем итоговое сообщение, если была история
    summary = await generate_session_summary(history) if history else None
    final_message = summary if summary else END_MESSAGE

    # Разбиваем длинное сообщение и отправляем по частям
    parts = split_long_message(final_message)
    for i, part in enumerate(parts):
        if i == 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text=part,
                reply_markup=START_KEYBOARD
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=part
            )

    # Теперь окончательно очищаем историю
    context.user_data['history'] = []
    print("✅ Сессия завершена с итоговым сообщением")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    print(f"💬 Получено сообщение: {user_message}")

    # Обработка кнопки "Начать сессию"
    if user_message == "Начать сессию":
        print("🟢 Нажата кнопка 'Начать сессию'")
        await start_session(update, context)
        return

    # Обработка кнопки "Завершить сессию"
    if user_message == "Завершить сессию":
        print("🔚 Нажата кнопка 'Завершить сессию'")
        await end(update, context)
        return

    # Проверяем, активна ли сессия (наличие session_start_time)
    if 'session_start_time' not in context.user_data:
        print("⏸️ Сессия не активна, предлагаем начать")
        await update.message.reply_text(
            "Сейчас нет активной сессии. Нажмите «Начать сессию», чтобы мы могли поговорить.",
            reply_markup=START_KEYBOARD
        )
        return

    # --- НОВОЕ: запускаем периодическую отправку typing ---
    typing_task = asyncio.create_task(
        send_typing_periodically(update.effective_chat.id, context)
    )
    context.user_data['typing_task'] = typing_task

    # Добавляем сообщение пользователя в историю
    if 'history' not in context.user_data:
        context.user_data['history'] = []
    context.user_data['history'].append({"role": "user", "content": user_message})

    if len(context.user_data['history']) > MAX_HISTORY * 2:
        context.user_data['history'] = context.user_data['history'][-MAX_HISTORY*2:]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + context.user_data['history']

    try:
        print("🔄 Отправляем запрос к DeepSeek...")
        response = await asyncio.to_thread(
            openai.ChatCompletion.create,
            model="deepseek-chat",
            messages=messages,
            max_tokens=1500,
            temperature=1
        )
        print("✅ Ответ от DeepSeek получен")
        clean_reply = response.choices[0].message.content

        # Сохраняем ответ в историю
        context.user_data['history'].append({"role": "assistant", "content": clean_reply})

        if len(context.user_data['history']) > MAX_HISTORY * 2:
            context.user_data['history'] = context.user_data['history'][-MAX_HISTORY*2:]

        # --- НОВОЕ: отменяем задачу typing перед отправкой ответа ---
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass
        context.user_data.pop('typing_task', None)

        # Отправляем ответ по частям
        parts = split_long_message(clean_reply)
        for i, part in enumerate(parts):
            if i == 0:
                await update.message.reply_text(part, reply_markup=END_KEYBOARD)
            else:
                await update.message.reply_text(part)

        # Обновляем таймер
        await refresh_timer(update.effective_chat.id, context)

    except Exception as e:
        print(f"❌ Ошибка при запросе к DeepSeek: {e}")

        # --- НОВОЕ: в случае ошибки тоже отменяем typing ---
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass
        context.user_data.pop('typing_task', None)

        error_message = f"Извините, произошла техническая ошибка. Пожалуйста, попробуйте позже.\n\nДетали: {e}"
        await update.message.reply_text(error_message, reply_markup=END_KEYBOARD)
        await refresh_timer(update.effective_chat.id, context)


def main():
    print("🚀 Функция main() запущена!")
    print(f"🔑 TELEGRAM_TOKEN загружен: {'да' if TELEGRAM_TOKEN else 'нет'}")
    print(f"🔑 DEEPSEEK_API_KEY загружен: {'да' if DEEPSEEK_API_KEY else 'нет'}")
    print(f"🔌 openai.api_base: {openai.api_base}")
    
    # Создаём приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    print("✅ Application создан")

    # Добавляем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("end", end))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Обработчики добавлены")

    # Запускаем бота с отключёнными обработчиками сигналов (чтобы работало в потоке)
    print("🔄 Запускаем polling с signal_handlers=False...")
    app.run_polling(timeout=50, drop_pending_updates=True)


if __name__ == "__main__":
    print("🐍 Скрипт bot.py запущен")
    main()
