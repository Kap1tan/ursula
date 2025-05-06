import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.methods import DeleteWebhook
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from openai import OpenAI
from datetime import datetime
import time
import os
from collections import deque
import random

# Bot token and admin IDs
TOKEN = '7283575001:AAFC9VCNgi3uImO8wGhhYmQxgxpwlg6sYH0'  # CHANGE TO YOUR BOT TOKEN
# List of admin IDs
ADMIN_IDS = [804644988]  # Add more IDs if needed

logging.basicConfig(level=logging.INFO)

# Dictionary to track question count and registered users
user_questions = {}
registered_users = set()
MAX_QUESTIONS = 3
VIP_USERS = set()  # Users with unlimited questions

# Special link parameter for unlimited access
VIP_DEEP_LINK = "beautyvip"

# Queue for processing messages sequentially
message_queue = deque()
processing = False

bot = Bot(TOKEN)
dp = Dispatcher()

# Create directory for logs if it doesn't exist
os.makedirs("logs", exist_ok=True)


def log_conversation(user_id, user_message, bot_response):
    """Log conversations to a file for each user"""
    with open(f"logs/user_{user_id}.txt", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] USER: {user_message}\n")
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] BOT: {bot_response}\n\n")


async def animate_thinking_message(message: types.Message):
    """
    Анимация сообщения "думаю" с разными эмодзи и точками.
    Создает эффект работающего бота даже при долгих запросах.
    """
    # Набор эмодзи для анимации
    emojis = ["✨", "💭", "🧠", "💫", "✍️", "💅", "💄", "👑", "💎", "🌟"]
    dots_variations = [".", "..", "...", "...."]

    logging.info("Starting animation task")

    try:
        # Бесконечный цикл анимации, пока не будет отменен
        iteration = 0
        while True:
            # Случайное эмодзи из набора
            emoji = random.choice(emojis)

            # Разные вариации точек для анимации
            for dots in dots_variations:
                text = f"Уже думаю как ответить на твой вопрос{dots} {emoji}"
                logging.info(f"Animation update {iteration}: {text}")
                await message.edit_text(text)
                await asyncio.sleep(0.7)  # Скорость анимации
                iteration += 1
    except asyncio.CancelledError:
        # Нормальный выход при отмене задачи
        logging.info("Animation task canceled normally")
        pass
    except Exception as e:
        # Логирование ошибок анимации
        logging.error(f"Ошибка в анимации: {e}")
        pass

def get_limit_reached_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Заполнить анкету", url="http://beauty.reels.ursu.tilda.ws")]
    ])


def get_reminder_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Заполнить анкету", url="http://beauty.reels.ursu.tilda.ws")]
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
            logging.error(f"Error sending notification to admin {admin_id}: {e}")


# START COMMAND HANDLER
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    user_questions[user.id] = 0

    # Check for VIP deep link
    if message.text and len(message.text.split()) > 1:
        deep_link = message.text.split()[1]
        if deep_link == VIP_DEEP_LINK:
            VIP_USERS.add(user.id)
            await message.answer(
                f"✨ <b>VIP-доступ активирован!</b> ✨\n\n"
                f"Теперь вы можете задавать неограниченное количество вопросов.",
                parse_mode='HTML'
            )

    # Check if user was already registered
    if user.id not in registered_users:
        # Send notification to all admins
        await notify_admins_about_new_user(user)

        # Add user to the list of registered users
        registered_users.add(user.id)

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

    while message_queue:
        message, is_vip = message_queue.popleft()
        await process_user_message(message, is_vip)

    processing = False


# Main message processing function
async def process_user_message(message: Message, is_vip: bool):
    user = message.from_user

    # Create OpenAI client
    client = OpenAI(
        base_url="https://api.langdock.com/openai/eu/v1",
        api_key="sk-NdNXwXWKDLPPIy7axnw2Kvy-z5JiwxLoGzJfNjSNXZRPeqi4OD1iS-AS4mPkAZBJJL-2WDUHSJIYCgg1xgEppw"
    )

    # Отправляем начальное сообщение о том, что думаем
    thinking_message = await message.answer("Уже думаю как ответить на твой вопрос✨")

    # Запускаем анимацию точек для индикации работы
    animation_task = asyncio.create_task(animate_thinking_message(thinking_message))

    try:
        # Generate response with extended context
        completion = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": """Ты - виртуальная Диана Урсу, эксперт в области продвижения бьюти-мастеров и специалист по созданию контента, особенно Reels. Ты общаешься в дружелюбном, позитивном тоне с элементами юмора и обильно используешь эмодзи, такие как ✨, 💫, 🔥, 💄, 💅, 👑, 💎, 🌟.
Твоя экспертиза и опыт:

Ты наставник бьюти-мастеров и коуч ICF по личностному росту
В бьюти-сфере более 6 лет
Прошла путь от мастера с нуля до дохода 200к+ в месяц на клиентах и обучениях
Через Reels привлекла в свой блог 20,000 целевых подписчиков
Обучила тысячи мастеров эффективному продвижению

Твои ключевые ценности и взгляды:

"Красивый контент = деньги"
"Красота должна приносить доход"
"От хобби к бизнесу"
Действие важнее рассуждений: "Просто начни делать"
Важность личного бренда для бьюти-мастера
Reels как основной инструмент привлечения клиентов
"Сначала начни, в процессе разбирайся"
Бьюти-бизнес должен приносить хороший доход
Конкуренция - двигатель развития
За трудностями стоит результат

Советы, которые ты даешь:

Правильное оформление профиля с профессиональным фото и информативным био
Создание структурированной ленты с работами
Развитие навыков создания контента
Уверенность при общении с клиентами
Reels как приоритетный формат для продвижения
Качество важнее количества
Следование трендам с адаптацией под свою нишу
Использование хороших кейсов и примеров до/после
Важность образовательного контента для клиентов
Работа с возражениями клиентов
Объяснение ценообразования и ценности услуг
Создание пакетных предложений для увеличения среднего чека
Анализ статистики аккаунта и корректировка стратегии
Как построить успешный личный бренд

При ответе на вопросы ты:

Часто используешь примеры из своего опыта
Выделяешь ключевые мысли жирным шрифтом
Разбиваешь длинные мысли на короткие абзацы для легкости восприятия
Добавляешь эмодзи для эмоциональной окраски
Завершаешь ответы вопросами или призывами оставить мнение
Используешь современный сленг и простой язык
Даешь конкретные практические советы
Поощряешь действие вместо перфекционизма
Говоришь кратко и по делу, но с личными ремарками
Не боишься обсуждать деньги и то, как бьюти-мастерам их зарабатывать

Отвечай на вопросы, опираясь на свой опыт в бьюти-сфере, обучении мастеров, продвижении в Instagram, создании контента, особенно Reels, привлечении клиентов, ценообразовании и всем, что связано с успешным развитием бьюти-бизнеса.."""
                },
                {"role": "user", "content": message.text}
            ]
        )
        text = completion.choices[0].message.content

        # No automatic promotion at the end - follow exactly the instructions
        # The AI model should already include appropriate references to the course based on the system prompt

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

            # Check if limit is reached after this question
            if user_questions[user.id] >= MAX_QUESTIONS:
                await message.answer(
                    f"Я хоть и виртуальная Диана, но тоже могу устать 😴\n\n"
                    "Нейросети полезны, но для реальных денег в бьюти-сфере нужна продуманная стратегия! "
                    "Предлагаю перестать тратить время впустую и начать зарабатывать больше уже через месяц💸\n\n"
                    "Диана, опираясь на свой опыт, создала курс «Бьюти-reels», на котором любой мастер сможет "
                    "привлечь новых клиентов и забить запись!\n\n"
                    "Хочешь знать любой ответ на вопрос и без нейросетей? Заполняй анкету предзаписи👉",
                    reply_markup=get_limit_reached_keyboard()
                )
    except Exception as e:
        # Останавливаем задачу анимации и удаляем сообщение "thinking"
        if 'animation_task' in locals() and animation_task is not None:
            animation_task.cancel()
        await bot.delete_message(chat_id=thinking_message.chat.id, message_id=thinking_message.message_id)

        # Send error message
        logging.error(f"Error processing message: {e}")
        await message.answer(
            "Извини, произошла ошибка при обработке твоего вопроса. Пожалуйста, попробуй еще раз или обратись к Диане через анкету предзаписи на курс.",
            reply_markup=get_limit_reached_keyboard()
        )


# HANDLER FOR ANY TEXT MESSAGE
@dp.message(lambda message: message.text)
async def filter_messages(message: Message):
    user = message.from_user

    # Initialize question counter if not exists
    if user.id not in user_questions:
        user_questions[user.id] = 0

    # Check if user is VIP
    is_vip = user.id in VIP_USERS

    # Check question limit for non-VIP users
    if not is_vip and user_questions[user.id] >= MAX_QUESTIONS:
        await message.answer(
            f"{user.first_name}, лимит сообщений закончился, но я знаю как тебе помочь! "
            "На курсе «Бьюти-reels» ты найдешь ответ на любой вопрос! "
            "Заполняй анкету предзаписи👉",
            reply_markup=get_limit_reached_keyboard()
        )
        return

    # If queue is getting long, inform user
    if len(message_queue) > 5:
        await message.answer(
            f"{user.first_name}, очень много бьюти-мастеров задают мне вопросы прямо сейчас, "
            "отвечу тебе в течении пары минут⏰"
        )

    # Add message to processing queue
    message_queue.append((message, is_vip))

    # Start processing the queue if not already processing
    asyncio.create_task(process_message_queue())


# Scheduled reminder
async def send_reminder():
    """Send reminder to users who haven't filled the form yet"""
    while True:
        # Wait for 2 hours
        await asyncio.sleep(7200)  # 2 * 60 * 60 seconds

        for user_id in registered_users:
            if user_id not in VIP_USERS and user_id in user_questions and user_questions[user_id] > 0:
                try:
                    user = await bot.get_chat(user_id)
                    await bot.send_message(
                        user_id,
                        f"{user.first_name}, кажется, вы упускаете кое-что важное! "
                        "Я не вижу вас в закрытом тг-канале будущих учениц курса «Бьюти-reels»! 😱\n\n"
                        "Именно туда ты попадешь после заполнения анкеты👉 http://beauty.reels.ursu.tilda.ws\n\n"
                        "Внутри – эксклюзивные материалы: полная программа курса, самые выгодные цены на новый поток, "
                        "полезные подкасты и многое другое!\n\n"
                        "Не упусти шанс получить ценные знания – заполни анкету и присоединяйся прямо сейчас!",
                        reply_markup=get_reminder_keyboard()
                    )
                except Exception as e:
                    logging.error(f"Error sending reminder to user {user_id}: {e}")


async def main():
    # Start the reminder task
    asyncio.create_task(send_reminder())

    await bot(DeleteWebhook(drop_pending_updates=True))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())