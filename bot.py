import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- Конфигурация ---
BOT_TOKEN = "8666743714:AAFICSeqAaaahFg5hZ0c7lmZHeKYPFdDN8k"
ADMIN_ID = 2032012311
COOLDOWN_MINUTES = 3

# --- Хранилища данных (в памяти) ---
# В реальном проекте лучше использовать базу данных (SQLite/PostgreSQL)
banned_users = set()
last_message_time = {}

# --- Инициализация ---
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- FSM (Состояния) ---
class AdminStates(StatesGroup):
    waiting_for_ban_id = State()

# --- Клавиатуры ---
def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Забанить пользователя", callback_data="admin_ban")]
    ])

# --- Хэндлеры ---

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id in banned_users:
        return
    
    if message.from_user.id == ADMIN_ID:
        await message.answer("👋 Добро пожаловать в админ-панель, Макс!", reply_markup=get_admin_keyboard())
    else:
        await message.answer(
            "Привет! Напиши свое обращение/предложение сюда, и я передам его администратору.\n\n"
            f"⏳ Обратите внимание: отправлять сообщения можно не чаще, чем раз в {COOLDOWN_MINUTES} минуты."
        )

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🔧 Админ-панель", reply_markup=get_admin_keyboard())

# --- Логика Админа ---

@dp.callback_query(F.data == "admin_ban")
async def process_ban_button(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    
    await callback.message.answer("Введите ID пользователя, которого хотите забанить (только цифры):")
    await state.set_state(AdminStates.waiting_for_ban_id)
    await callback.answer()

@dp.message(AdminStates.waiting_for_ban_id)
async def process_ban_id(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        user_id_to_ban = int(message.text.strip())
        banned_users.add(user_id_to_ban)
        await message.answer(f"✅ Пользователь с ID {user_id_to_ban} успешно забанен. Он больше не сможет отправлять сообщения.")
    except ValueError:
        await message.answer("❌ Ошибка! ID должен состоять только из цифр. Попробуйте снова нажать кнопку бана.")
    
    await state.clear()

# --- Логика приема сообщений от пользователей ---

@dp.message(F.text)
async def handle_user_message(message: Message):
    user_id = message.from_user.id

    # Проверка на бан
    if user_id in banned_users:
        return # Игнорируем забаненных молча

    # Игнорируем сообщения от админа (чтобы он сам себе не отправлял предложку)
    if user_id == ADMIN_ID:
        return

    # Проверка кулдауна (3 минуты)
    now = datetime.now()
    if user_id in last_message_time:
        time_passed = now - last_message_time[user_id]
        if time_passed < timedelta(minutes=COOLDOWN_MINUTES):
            wait_time = timedelta(minutes=COOLDOWN_MINUTES) - time_passed
            minutes_left = int(wait_time.total_seconds() // 60)
            seconds_left = int(wait_time.total_seconds() % 60)
            await message.answer(f"⏳ Подождите! Следующее сообщение можно будет отправить через {minutes_left} мин. {seconds_left} сек.")
            return

    # Отправка сообщения админу
    text_to_admin = (
        f"📩 <b>Новое обращение!</b>\n\n"
        f"<b>От кого:</b> @{message.from_user.username or 'Без username'}\n"
        f"<b>ID:</b> <code>{user_id}</code>\n"
        f"<b>Сообщение:</b>\n{message.text}"
    )

    try:
        await bot.send_message(chat_id=ADMIN_ID, text=text_to_admin, parse_mode="HTML")
        # Обновляем время последнего сообщения только после успешной отправки
        last_message_time[user_id] = now
        await message.answer("✅ Ваше сообщение успешно отправлено администратору!")
    except Exception as e:
        logging.error(f"Failed to send message to admin: {e}")
        await message.answer("❌ Произошла ошибка при отправке. Попробуйте позже.")


# --- Запуск ---
async def main():
    # Пропускаем накопившиеся апдейты
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
