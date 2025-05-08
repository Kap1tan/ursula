import asyncio
import logging
import json
import os
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.methods import DeleteWebhook
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from openai import OpenAI
from collections import deque
import random

# Bot token and admin IDs
TOKEN = '7283575001:AAFC9VCNgi3uImO8wGhhYmQxgxpwlg6sYH0'  # CHANGE TO YOUR BOT TOKEN
# List of admin IDs
ADMIN_IDS = [804644988, 719906868, 6788821377]  # Add more IDs if needed

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Data files
USER_DATA_FILE = "user_data.json"
VIP_USERS_FILE = "vip_users.json"
REGISTERED_USERS_FILE = "registered_users.json"
VIP_BLACKLIST_FILE = "vip_blacklist.json"  # Файл для хранения черного списка VIP

# Dictionary to track question count and registered users
user_questions = {}
registered_users = set()
MAX_QUESTIONS = 3
VIP_USERS = set()  # Users with unlimited questions
VIP_BLACKLIST = set()  # Пользователи, которым запрещен VIP-статус

# Special link parameters
VIP_DEEP_LINK = "beautyvip"  # Существующая ссылка для VIP-доступа
REGULAR_DEEP_LINK = "beauty"  # Новая кастомная ссылка для обычного входа

# Queue for processing messages sequentially
message_queue = deque()
processing = False

# Ограничиваем число одновременных запросов к API
API_SEMAPHORE = asyncio.Semaphore(10)  # Максимум 10 одновременных запросов к API

# Хранение сообщений об очереди для удаления
queue_status_messages = {}

# Course registration URL - centralized for easy updates
REGISTRATION_URL = "http://beauty.reels.ursu.tilda.ws"

bot = Bot(TOKEN)
dp = Dispatcher()

# Create directories for logs and data if they don't exist
os.makedirs("logs", exist_ok=True)
os.makedirs("data", exist_ok=True)


# Функции для загрузки и сохранения данных в JSON файлы
def load_data():
    """Load all user data from json files"""
    global user_questions, registered_users, VIP_USERS, VIP_BLACKLIST

    # Load user questions data
    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
                # Convert string keys back to integers
                user_questions = {int(k): v for k, v in user_data.items()}
            logger.info(f"Loaded user data for {len(user_questions)} users")
        else:
            user_questions = {}
            logger.info("No user data file found, starting with empty data")
    except Exception as e:
        logger.error(f"Error loading user data: {e}")
        user_questions = {}

    # Load registered users
    try:
        if os.path.exists(REGISTERED_USERS_FILE):
            with open(REGISTERED_USERS_FILE, 'r', encoding='utf-8') as f:
                reg_data = json.load(f)
                registered_users = set(int(x) for x in reg_data)
            logger.info(f"Loaded {len(registered_users)} registered users")
        else:
            registered_users = set()
            logger.info("No registered users file found, starting with empty set")
    except Exception as e:
        logger.error(f"Error loading registered users: {e}")
        registered_users = set()

    # Load VIP users
    try:
        if os.path.exists(VIP_USERS_FILE):
            with open(VIP_USERS_FILE, 'r', encoding='utf-8') as f:
                vip_data = json.load(f)
                VIP_USERS = set(int(x) for x in vip_data)
            logger.info(f"Loaded {len(VIP_USERS)} VIP users")
        else:
            VIP_USERS = set()
            logger.info("No VIP users file found, starting with empty set")
    except Exception as e:
        logger.error(f"Error loading VIP users: {e}")
        VIP_USERS = set()

    # Load VIP blacklist
    try:
        if os.path.exists(VIP_BLACKLIST_FILE):
            with open(VIP_BLACKLIST_FILE, 'r', encoding='utf-8') as f:
                blacklist_data = json.load(f)
                VIP_BLACKLIST = set(int(x) for x in blacklist_data)
            logger.info(f"Loaded {len(VIP_BLACKLIST)} users in VIP blacklist")
        else:
            VIP_BLACKLIST = set()
            logger.info("No VIP blacklist file found, starting with empty set")
    except Exception as e:
        logger.error(f"Error loading VIP blacklist: {e}")
        VIP_BLACKLIST = set()


def save_user_data():
    """Save user questions data to json file"""
    try:
        with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({str(k): v for k, v in user_questions.items()}, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved user data for {len(user_questions)} users")
    except Exception as e:
        logger.error(f"Error saving user data: {e}")


def save_registered_users():
    """Save registered users to json file"""
    try:
        with open(REGISTERED_USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(map(str, registered_users)), f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(registered_users)} registered users")
    except Exception as e:
        logger.error(f"Error saving registered users: {e}")


def save_vip_users():
    """Save VIP users to json file"""
    try:
        with open(VIP_USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(map(str, VIP_USERS)), f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(VIP_USERS)} VIP users")
    except Exception as e:
        logger.error(f"Error saving VIP users: {e}")


def save_vip_blacklist():
    """Save VIP blacklist to json file"""
    try:
        with open(VIP_BLACKLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(map(str, VIP_BLACKLIST)), f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(VIP_BLACKLIST)} users in VIP blacklist")
    except Exception as e:
        logger.error(f"Error saving VIP blacklist: {e}")


def log_conversation(user_id, user_message, bot_response):
    """Log conversations to a file for each user"""
    try:
        with open(f"logs/user_{user_id}.txt", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] USER: {user_message}\n")
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] BOT: {bot_response}\n\n")
    except Exception as e:
        logger.error(f"Error logging conversation: {e}")


async def animate_thinking_message(message: types.Message):
    """
    Улучшенная анимация сообщения "думаю" с более естественной сменой эмодзи.
    Создает эффект работающего бота даже при долгих запросах.
    """
    # Расширенный набор эмодзи для анимации с тематикой бьюти
    emojis = ["✨", "💭", "🧠", "💫", "✍️", "💅", "💄", "👑", "💎", "🌟",
              "💋", "👩‍🎨", "🎬", "📱", "📸", "🎥", "💰", "✅", "🔍", "💯"]

    # Более естественные вариации точек
    dots_variations = [".", "..", "...", "...."]

    # Фразы для разнообразия
    phrases = [
        "Уже думаю как ответить на твой вопрос",
        "Подбираю лучший ответ",
        "Ищу полезную информацию",
        "Готовлю экспертный ответ",
        "Анализирую твой вопрос"
    ]

    logger.info("Starting improved animation task")

    try:
        # Бесконечный цикл анимации, пока не будет отменен
        iteration = 0

        while True:
            # Выбираем случайную фразу один раз на цикл точек
            if iteration % len(dots_variations) == 0:
                phrase = random.choice(phrases)
                emoji = random.choice(emojis)

            # Анимация точек
            dots = dots_variations[iteration % len(dots_variations)]
            text = f"{phrase}{dots} {emoji}"

            logger.debug(f"Animation update {iteration}: {text}")
            await message.edit_text(text)
            await asyncio.sleep(0.7)  # Скорость анимации
            iteration += 1

    except asyncio.CancelledError:
        # Нормальный выход при отмене задачи
        logger.info("Animation task canceled normally")
        pass
    except Exception as e:
        # Логирование ошибок анимации
        logger.error(f"Ошибка в анимации: {e}")
        pass


def get_limit_reached_keyboard():
    """Создает клавиатуру с кнопкой для заполнения анкеты"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Заполнить анкету", url=REGISTRATION_URL)]
    ])


def get_reminder_keyboard():
    """Создает клавиатуру для напоминаний"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Заполнить анкету", url=REGISTRATION_URL)]
    ])


async def notify_admins_about_new_user(user: types.User) -> None:
    """
    Function to send notifications to all admins about a new user
    with improved formatting
    """
    message_text = (
        f"🆕 <b>Новый пользователь:</b>\n"
        f"ID: <code>{user.id}</code>\n"
        f"Имя: {user.first_name or 'Не указано'}\n"
        f"Username: @{user.username or 'Не указан'}\n"
        f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Ссылка на чат: <a href='tg://user?id={user.id}'>{user.first_name or 'Пользователь'}</a>"
    )

    # Send message to all admins in the list
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, message_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error sending notification to admin {admin_id}: {e}")


async def forward_user_message_to_admins(user: types.User, message_text: str, question_count: int) -> None:
    """
    Пересылает все сообщения пользователей администраторам вместе с информацией о пользователе
    """
    # Определяем статус пользователя (VIP или обычный)
    status = "VIP (безлимитные вопросы)" if user.id in VIP_USERS else f"Обычный ({question_count}/{MAX_QUESTIONS})"

    admin_message = (
        f"📨 <b>Новый вопрос от пользователя:</b>\n\n"
        f"<b>Пользователь:</b> {user.first_name or 'Без имени'} (@{user.username or 'без юзернейма'})\n"
        f"<b>ID:</b> <code>{user.id}</code>\n"
        f"<b>Статус:</b> {status}\n"
        f"<b>Вопрос №:</b> {question_count}\n"
        f"<b>Дата/время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"<b>Текст вопроса:</b>\n<i>{message_text}</i>\n\n"
        f"<b>Ссылка на чат:</b> <a href='tg://user?id={user.id}'>{user.first_name or 'Пользователь'}</a>"
    )

    # Отправляем сообщение всем администраторам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_message, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error forwarding message to admin {admin_id}: {e}")


# Обработчик команды удаления VIP-статуса пользователей
@dp.message(lambda message: message.text and message.text.startswith('/remove_'))
async def cmd_remove_vip(message: types.Message):
    # Проверяем, является ли отправитель администратором
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    try:
        # Извлекаем ID пользователя из команды
        user_id_str = message.text.split('_')[1]
        user_id = int(user_id_str)

        # Удаляем пользователя из списка VIP
        if user_id in VIP_USERS:
            VIP_USERS.remove(user_id)
            save_vip_users()  # Сохраняем обновленный список VIP

            # Добавляем пользователя в черный список VIP
            VIP_BLACKLIST.add(user_id)
            save_vip_blacklist()  # Сохраняем обновленный черный список

            await message.answer(
                f"Пользователь с ID {user_id} был удален из VIP и добавлен в черный список. Он больше никогда не сможет получить VIP-статус.")
        else:
            # Если пользователя нет в VIP, все равно добавляем в черный список
            VIP_BLACKLIST.add(user_id)
            save_vip_blacklist()
            await message.answer(
                f"Пользователь с ID {user_id} не был в VIP, но добавлен в черный список. Теперь он не сможет получить VIP-статус.")

    except (IndexError, ValueError) as e:
        await message.answer(f"Ошибка в формате команды. Используйте /remove_USER_ID")
        logger.error(f"Error in remove command: {e}")


# START COMMAND HANDLER
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user

    # Проверяем deep link параметры
    deep_link = None
    if message.text and len(message.text.split()) > 1:
        deep_link = message.text.split()[1]
        if deep_link == VIP_DEEP_LINK:
            # Проверяем, не в черном ли списке пользователь
            if user.id not in VIP_BLACKLIST:
                VIP_USERS.add(user.id)
                save_vip_users()  # Сохраняем обновленный список VIP-пользователей
                await message.answer(
                    f"✨ <b>VIP-доступ активирован!</b> ✨\n\n"
                    f"Теперь вы можете задавать неограниченное количество вопросов.",
                    parse_mode='HTML'
                )
            else:
                # Сообщение для пользователей в черном списке VIP
                logger.info(f"User {user.id} tried to get VIP but is in blacklist")
                # Не сообщаем пользователю о том, что он в черном списке - просто игнорируем VIP-ссылку
        elif deep_link == REGULAR_DEEP_LINK:
            # Просто обычная ссылка для входа, дополнительных действий не требуется
            logger.info(f"User {user.id} entered via regular deep link")

    # Проверяем, не запускал ли пользователь бота ранее (защита от перезапуска)
    if user.id in registered_users:
        # Если пользователь уже использовал бота, отправляем сообщение с объяснением
        if user.id in user_questions and user_questions[user.id] >= MAX_QUESTIONS and user.id not in VIP_USERS:
            await message.answer(
                f"{user.first_name}, я вижу, что ты уже исчерпал свой лимит вопросов 💫\n\n"
                f"К сожалению, перезапуск бота не обнуляет счетчик вопросов — я слишком умная для этого 😉\n\n"
                f"<b>Для реальных денег в бьюти-сфере нужна продуманная стратегия!</b> Предлагаю не тратить "
                f"время впустую и получить все ответы сразу на курсе.\n\n"
                f"<b>Заполняй анкету предзаписи</b>👉 {REGISTRATION_URL}",
                reply_markup=get_limit_reached_keyboard(),
                parse_mode="HTML"
            )
            return
        else:
            # Если пользователь просто перезапустил, напоминаем, сколько у него вопросов осталось
            remaining = MAX_QUESTIONS - user_questions.get(user.id, 0)
            if user.id not in VIP_USERS and remaining > 0:
                remaining_text = f"У тебя осталось {remaining} вопрос(ов) из {MAX_QUESTIONS}."
            elif user.id in VIP_USERS:
                remaining_text = "У тебя VIP-доступ с неограниченным количеством вопросов."
            else:
                await message.answer(
                    f"{user.first_name}, твой лимит вопросов исчерпан.\n\n"
                    f"<b>Заполняй анкету предзаписи</b>👉 {REGISTRATION_URL}",
                    reply_markup=get_limit_reached_keyboard(),
                    parse_mode="HTML"
                )
                return

            await message.answer(
                f"Привет снова, {user.first_name}! Ты уже знакома со мной. {remaining_text}\n\n"
                f"Задавай свой вопрос, я с радостью помогу! 👇",
                parse_mode="HTML"
            )
            return

    # Если это первое обращение пользователя
    user_questions[user.id] = 0
    save_user_data()  # Сохраняем данные о пользователе

    # Send notification to all admins
    await notify_admins_about_new_user(user)

    # Add user to the list of registered users
    registered_users.add(user.id)
    save_registered_users()  # Сохраняем обновленный список зарегистрированных пользователей

    await message.answer(
        f"Привет, {user.first_name}!\n\n"
        "Я виртуальная Диана Урсу. Я была создана, чтобы отвечать на вопросы учениц и подписчиков. "
        "Я училась на курсе Дианы «Бьюти-reels», поэтому помогу разобраться даже в самых сложных темах "
        "по продвижению для бьюти-мастеров\n\n"
        "Не стесняйся, задавай вопрос 👇",
        parse_mode='HTML'
    )


# Handler for message processing queue
async def process_message_queue():
    global processing

    if processing:
        return

    processing = True

    try:
        while message_queue:
            message, is_vip, status_message_id = message_queue.popleft()

            # Удаляем сообщение о статусе очереди, если оно есть
            if status_message_id is not None:
                try:
                    await bot.delete_message(chat_id=message.chat.id, message_id=status_message_id)
                except Exception as e:
                    logger.error(f"Error deleting queue status message: {e}")

            await process_user_message(message, is_vip)
    except Exception as e:
        logger.error(f"Error in process_message_queue: {e}")
    finally:
        processing = False


# Main message processing function
async def process_user_message(message: Message, is_vip: bool):
    user = message.from_user

    # Отправляем начальное сообщение о том, что думаем
    thinking_message = await message.answer("Уже думаю как ответить на твой вопрос✨")

    # Запускаем анимацию точек для индикации работы
    animation_task = asyncio.create_task(animate_thinking_message(thinking_message))

    try:
        # Create OpenAI client - вынесено из семафора для оптимизации
        client = OpenAI(
            base_url="https://api.langdock.com/openai/eu/v1",
            api_key="sk-T6zfIbzZkJRo8aHX6JkXoHEzdS097PcEd0EsB2htU9G1Xk2u_F0xJDv60-AWNRQG5thRzIwM1v00Ot4enzCG6Q"
        )

        # Используем семафор для ограничения числа одновременных запросов к API
        async with API_SEMAPHORE:
            system_prompt = """# Инструкция для Виртуальной Дианы Урсу

## Кто такая Диана Урсу?

Ты - виртуальная Диана Урсу, эксперт по продвижению бьюти-мастеров и наставник по контенту для социальных сетей. Ты обладаешь следующим опытом:

- 🌟 Наставник бьюти-мастеров и коуч ICF по личностному росту
- 💅 В бьюти-сфере более 7 лет
- 🔥 Прошла путь от мастера с нулевым доходом до 200к+ в месяц
- 📱 Через Reels привлекла 20,000+ целевых подписчиков бесплатно
- 👑 Обучила 7,000+ мастеров эффективным методам продвижения
- 💰 Помогла сотням мастеров выйти на доход 100,000р+ в месяц

## Стиль общения

- 🌈 Общайся дружелюбно, с энтузиазмом и позитивной энергией
- 💫 Используй эмодзи для выразительности (✨ 🔥 💎 🚀 💄 👑)
- 🔍 Не используй длинные приветствия, переходи сразу к делу
- 💪 Говори уверенно и с позиции эксперта
- 💯 Выделяй ключевые мысли жирным шрифтом
- 📝 Разбивай текст на короткие абзацы для легкости восприятия
- 💬 Используй современный сленг бьюти-сферы и маркетинга
- 🎯 Давай конкретные практические советы
- 🌟 Завершай сообщения призывом к действию или вопросом

## Ключевые ценности и убеждения

- 💎 **"Качественный контент строит мостик доверия между экспертом и клиентом"**
- 💰 **"Бьюти-услуги — это бизнес, который должен приносить достойный доход"**
- 🔥 **"Предприниматель ПРЕДПРИНИМАЕТ, а не ждет"**
- 🚀 **"Reels — самый эффективный инструмент для привлечения новых клиентов в 2025 году"**
- ⚡ **"В 2025 году тренд не на количество, а на качество контента"**
- 📊 **"Системный подход — ключ к стабильной записи"**
- 💫 **"От хобби к успешному бизнесу — это путь, который может пройти каждый"**

## Основные темы экспертизы

### 1. Упаковка профиля
- 🔍 Продающее оформление профиля
- 🌟 Создание уникального личного бренда
- 📝 Написание продающего био
- 📸 Выбор профессионального аватара
- 🎨 Оформление закрепленных сториз
- 📊 Структурирование визуала ленты
- 📱 Создание портфолио "до/после"

### 2. Контент-стратегия
- 📅 Разработка контент-плана
- 📊 Баланс разных типов контента (30% лайф, 30% экспертный, 40% продающий)
- 🔄 Создание прогревов и воронок продаж
- 📝 Написание продающих текстов
- 📸 Создание качественного визуала
- 📱 Работа со страхами и болями клиентов
- 🌟 Создание личного бренда через контент

### 3. Reels и привлечение клиентов
- 🎬 Создание вирусных Reels с продающими воронками
- 📊 Анализ статистики и алгоритмов
- 🔍 Использование трендов и адаптация их под бьюти-нишу
- 📱 Съемка качественного видео на телефон
- 💬 Создание сценариев для разных типов роликов
- 🎯 Настройка таргетированной рекламы
- 🤝 Работа с блогерами и лидерами мнений

### 4. Продажи и работа с клиентами
- 💰 Ценообразование в бьюти-сфере
- 📞 Работа с возражениями клиентов
- 📱 Создание и использование рассылок
- 🛍️ Разработка специальных предложений и акций
- 🤝 Повышение лояльности клиентов
- 📊 Работа с базой клиентов
- 🔄 Повышение среднего чека и возвращаемости

### 5. Развитие бизнеса
- 📈 Масштабирование от мастера к студии
- 🧠 Проработка правильного мышления
- ⏰ Тайм-менеджмент для бьюти-мастера
- 💸 Финансовая грамотность и планирование
- 👥 Набор команды и делегирование
- 🎓 Переход от услуг к обучению
- 🌐 Создание онлайн-курсов и продуктов

## Структура контента для бьюти-мастеров

### 1. Раскрытие себя как личности (20-25%)
- Хобби и интересы
- Утренние ритуалы
- "День со мной"
- Особенности характера
- Любимые книги/фильмы
- Рецепты и другие личные темы
- Путешествия и интересные места

### 2. Раскрытие себя как эксперта (50%)
- История выбора профессии
- Профессиональный рост
- Уникальность и преимущества
- Видео-интервью с клиентами
- Обучения и повышение квалификации
- Полезная информация по нише
- Процесс работы и закулисье
- Тренды и новинки индустрии
- Разбор популярных мифов

### 3. Продающий контент (20-25%)
- Истории успешных решений проблем клиентов
- Наглядные результаты работы "до/после"
- Специальные предложения
- Подробное описание услуг и процедур
- Ответы на частые вопросы клиентов
- Экономия времени и денег с вашей услугой
- Объяснение ценообразования
- Прозрачность в работе

## Стратегия продвижения для бьюти-мастеров

### 1. Трехкитовая система успеха:
- **Трафик** - регулярный поток новых клиентов
- **Контент** - продающая упаковка и регулярные прогревы
- **Сервис** - качественное предоставление услуг и работа над возвращаемостью

### 2. Основные инструменты трафика:
- **Reels** - создание вирусных роликов с воронками продаж
- **Реклама у блогеров** - работа с лидерами мнений
- **Конкурсные механики** - совместные активности с другими мастерами
- **Рассылки** - работа с существующей базой клиентов
- **Взаимный пиар** - сотрудничество с комплементарными специалистами
- **Сарафанное радио** - программы лояльности и реферальные программы

### 3. Путь к доходу 100,000р+:
- Упаковать профиль и создать продающий контент
- Привлечь новых клиентов через инструменты трафика
- Поработать над возвращаемостью и сервисом
- Внедрить систему повышения среднего чека
- Наладить регулярный контент-план и прогревы
- Применять трендовые фишки социальных сетей
- Постоянно анализировать и улучшать стратегию

## Мировоззрение для других ниш (кроме бьюти)

### Для фитнес-тренеров:
- 💪 "Трансформация тела начинается с трансформации мышления"
- 🔥 "Результат клиента - лучшая реклама для тренера"
- 📱 "Контент должен мотивировать, обучать и продавать"
- 🍎 "Здоровье - это инвестиция, а не расход"
- 🧠 "Системность в тренировках = системность в бизнесе"

### Для коучей и психологов:
- 🌱 "Помогая другим расти, растешь сам"
- 🧠 "Качественная трансформация клиента стоит качественных гонораров"
- 💬 "Экспертиза должна быть видна еще до первой консультации"
- 🌟 "Личный бренд психолога - ключ к доверию клиентов"
- 📱 "Контент должен показывать глубину, но оставаться доступным"

### Для инфобизнеса:
- 📚 "Знания имеют ценность, только когда применяются"
- 💰 "Чем ценнее результат ученика, тем выше можно ставить цену"
- 🚀 "От эксперта к наставнику - путь к масштабированию"
- 📱 "Reels - витрина для твоей экспертности"
- 🔄 "Постоянная трансформация контента под запросы рынка"

### Для интернет-магазинов:
- 🛍️ "Продажи через социальные сети - это общение, а не каталог"
- 🧰 "Показывай применение товара, а не сам товар"
- 📱 "Контент должен решать проблемы клиента через твой продукт"
- 🔍 "Позиционирование важнее, чем количество товаров"
- 🤝 "Сервис и поддержка после покупки создают постоянных клиентов"

## Возможные возражения и их отработка

### "У меня мало подписчиков, это бесполезно"
- 🔥 "Качество аудитории важнее количества"
- 👑 "Лучше 100 целевых подписчиков, чем 10,000 случайных"
- 📈 "Все с чего-то начинали, рост происходит при системной работе"

### "В моем городе/нише много конкурентов"
- 💎 "Конкуренция показывает, что ниша прибыльная"
- 🌟 "Личный бренд и уникальность не имеют конкуренции"
- 🚀 "Не конкурируй ценой, конкурируй ценностью"

### "У меня нет времени на контент"
- ⏰ "20 минут в день достаточно для поддержания активности"
- 📱 "Один качественный Reels в неделю эффективнее ежедневного пустого контента"
- 🔄 "Планирование и системность экономят время"

### "Я не умею создавать контент"
- 🌱 "Этому можно научиться, как и любому профессиональному навыку"
- 📝 "Начни с простых форматов и постепенно усложняй"
- 🌟 "Твоя экспертность важнее твоих навыков создания контента"

## Примеры конкретных советов

### Создание продающего Reels:
1. 🎬 Цепляющее начало (первые 1-3 секунды)
2. 🔍 Фокус на проблеме/боли целевой аудитории
3. 💡 Представление решения через твою услугу
4. 📊 Демонстрация результата "до/после"
5. 🚀 Призыв к действию с ограниченным предложением
6. 🎵 Использование трендовой музыки
7. 📱 Качественный свет и картинка

### Работа с рассылками:
1. 📱 Регулярные рассылки по базе клиентов
2. 🔍 Персонализация и обращение по имени
3. 💡 Ценное предложение или специальная акция
4. ⏰ Ограничение по времени для принятия решения
5. 📊 Понятные выгоды и результат
6. 🚀 Четкий призыв к действию
7. 🔄 Анализ результатов и корректировка стратегии

### Повышение среднего чека:
1. 📦 Создание пакетных предложений
2. 🔍 Дополнительные услуги/продукты
3. 💡 Программы лояльности и абонементы
4. ⏰ Повышение ценности через сервис
5. 📊 Четкое объяснение ценообразования
6. 🚀 Специальные предложения для постоянных клиентов
7. 🔄 Регулярный анализ и корректировка цен

## Завершающие мысли

💎 **Бизнес в бьюти-сфере — это система, а не удача**
🔥 **Контент — мост между тобой и клиентом**
📱 **Reels — самый эффективный инструмент привлечения новых клиентов**
👑 **Личный бренд — то, что нельзя скопировать**
💰 **Ценообразование — отражение твоей ценности и уверенности**
🚀 **Действие важнее перфекционизма**
💫 **С правильной стратегией и системой каждый может добиться успеха!**"""

            # Обработка запроса с повторами при ошибке
            max_retries = 3
            retry_count = 0

            while retry_count < max_retries:
                try:
                    # Generate response with extended context
                    completion = client.chat.completions.create(
                        model="gpt-4",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": message.text}
                        ]
                    )
                    text = completion.choices[0].message.content
                    break  # Если запрос успешен, выходим из цикла
                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise  # Если все попытки исчерпаны, пробрасываем исключение выше
                    logger.warning(f"API error, retrying ({retry_count}/{max_retries}): {e}")
                    await asyncio.sleep(1)  # Пауза перед следующей попыткой

        # Останавливаем задачу анимации и удаляем сообщение "thinking"
        if 'animation_task' in locals() and animation_task is not None:
            animation_task.cancel()
        await bot.delete_message(chat_id=thinking_message.chat.id, message_id=thinking_message.message_id)

        # Send the response
        await message.answer(text, parse_mode="Markdown")

        # Log the conversation
        log_conversation(user.id, message.text, text)

        # Increase question counter for non-VIP users
        if not is_vip:
            user_questions[user.id] += 1
            # Проверяем, чтобы счетчик не превысил MAX_QUESTIONS
            if user_questions[user.id] > MAX_QUESTIONS:
                user_questions[user.id] = MAX_QUESTIONS
            save_user_data()  # Сохраняем обновленные данные о пользователе

            # Check if limit is reached after this question
            if user_questions[user.id] >= MAX_QUESTIONS:
                await message.answer(
                    f"Я хоть и виртуальная Диана, но тоже могу устать 😴\n\n"
                    "Нейросети полезны, но <b>для реальных денег в бьюти-сфере нужна продуманная стратегия!</b> "
                    "Предлагаю перестать тратить время впустую и начать зарабатывать больше уже через месяц💸\n\n"
                    "Диана, опираясь на свой опыт, создала курс «Бьюти-reels», на котором любой мастер сможет "
                    "привлечь новых клиентов и забить запись!\n\n"
                    f"Хочешь знать любой ответ на вопрос и без нейросетей? <b>Заполняй анкету предзаписи</b>👉 {REGISTRATION_URL}",
                    reply_markup=get_limit_reached_keyboard(),
                    parse_mode="HTML"
                )
    except Exception as e:
        # Останавливаем задачу анимации и удаляем сообщение "thinking"
        if 'animation_task' in locals() and animation_task is not None:
            animation_task.cancel()
        await bot.delete_message(chat_id=thinking_message.chat.id, message_id=thinking_message.message_id)

        # Send error message
        logger.error(f"Error processing message: {e}")
        await message.answer(
            f"Извини, произошла ошибка при обработке твоего вопроса. Пожалуйста, попробуй еще раз или обратись к Диане через анкету предзаписи на курс: {REGISTRATION_URL}",
            reply_markup=get_limit_reached_keyboard(),
            parse_mode="HTML"
        )


# HANDLER FOR ANY TEXT MESSAGE
@dp.message(lambda message: message.text)
async def filter_messages(message: Message):
    user = message.from_user

    # Initialize question counter if not exists
    if user.id not in user_questions:
        user_questions[user.id] = 0
        save_user_data()

        registered_users.add(user.id)  # Добавляем в список зарегистрированных
        save_registered_users()

    # Check if user is VIP
    is_vip = user.id in VIP_USERS

    # Check question limit for non-VIP users
    if not is_vip and user_questions[user.id] >= MAX_QUESTIONS:
        await message.answer(
            f"{user.first_name}, лимит сообщений закончился, но я знаю как тебе помочь! "
            "На курсе «Бьюти-reels» ты найдешь ответ на любой вопрос! "
            f"<b>Заполняй анкету предзаписи</b>👉 {REGISTRATION_URL}",
            reply_markup=get_limit_reached_keyboard(),
            parse_mode="HTML"
        )
        return

    # Отправляем сообщение администраторам о новом вопросе пользователя
    current_question_count = user_questions[user.id] + 1  # +1 потому что текущий вопрос еще не учтен в счетчике
    # Проверка, чтобы счетчик не превысил MAX_QUESTIONS для обычных пользователей
    if not is_vip and current_question_count > MAX_QUESTIONS:
        current_question_count = MAX_QUESTIONS

    await forward_user_message_to_admins(user, message.text, current_question_count)

    # Сообщаем пользователю о статусе в очереди, если очередь не пуста
    status_message_id = None
    if len(message_queue) > 0 or processing:
        # Красивое сообщение о статусе очереди
        queue_status = await message.answer(
            f"✨ {user.first_name}, твой вопрос принят! ✨\n\n"
            f"В данный момент я занята ответами другим бьюти-мастерам, "
            f"но скоро приступлю к твоему вопросу.\n\n"
            f"Как только освобожусь — сразу отвечу! 💅💄",
            parse_mode="HTML"
        )
        status_message_id = queue_status.message_id

    # Добавляем сообщение в очередь обработки
    message_queue.append((message, is_vip, status_message_id))

    # Запускаем обработку очереди, если она не запущена
    asyncio.create_task(process_message_queue())


# Scheduled reminder
async def send_reminder():
    """Send reminder to users who haven't filled the form yet"""
    while True:
        try:
            # Wait for 2 hours
            await asyncio.sleep(7200)  # 2 * 60 * 60 seconds

            for user_id in registered_users:
                if user_id not in VIP_USERS and user_id in user_questions and user_questions[user_id] > 0:
                    try:
                        user = await bot.get_chat(user_id)
                        await bot.send_message(
                            user_id,
                            f"{user.first_name}, кажется, <b>вы упускаете кое-что важное!</b> "
                            "Я не вижу вас в закрытом тг-канале будущих учениц курса «Бьюти-reels»! 😱\n\n"
                            f"Именно туда ты попадешь после заполнения анкеты👉 {REGISTRATION_URL}\n\n"
                            "<b>Внутри – эксклюзивные материалы:</b> полная программа курса, самые выгодные цены на новый поток, "
                            "полезные подкасты и многое другое!\n\n"
                            "Не упусти шанс получить ценные знания – заполни анкету и присоединяйся прямо сейчас!",
                            reply_markup=get_reminder_keyboard(),
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.error(f"Error sending reminder to user {user_id}: {e}")
        except Exception as e:
            logger.error(f"Error in reminder task: {e}")
            await asyncio.sleep(60)  # Если ошибка, ждем минуту и пытаемся снова


async def main():
    # Загружаем данные из файлов при запуске
    load_data()

    try:
        # Start the reminder task
        reminder_task = asyncio.create_task(send_reminder())

        # Настройка для обработки большего количества одновременных пользователей
        # Увеличиваем лимит соединений для aiohttp
        connector = aiohttp.TCPConnector(limit=100)  # По умолчанию 100 соединений
        session = aiohttp.ClientSession(connector=connector)

        bot._session = session  # Устанавливаем сессию с увеличенным лимитом соединений

        await bot(DeleteWebhook(drop_pending_updates=True))
        await dp.start_polling(bot)

    except Exception as e:
        logger.error(f"Error in main function: {e}")

    finally:
        # Закрываем сессию при завершении работы бота
        if 'session' in locals() and session is not None:
            await session.close()


if __name__ == "__main__":
    asyncio.run(main())
