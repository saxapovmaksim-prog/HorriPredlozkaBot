import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- Конфигурация ---
BOT_TOKEN = "8666743714:AAFICSeqAaaahFg5hZ0c7lmZHeKYPFdDN8k"
ADMIN_ID = 2032012311
COOLDOWN_MINUTES = 3

# --- Хранилища данных (в памяти) ---
banned_users = set()
last_message_time = {}
all_users = set()  # Множество для хранения ID всех пользователей бота

# --- Инициализация ---
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- FSM (Состояния) ---
class AdminStates(StatesGroup):
    waiting_for_ban_id = State()
    waiting_for_broadcast = State() # Новое состояние для рассылки

# --- Клавиатуры ---
def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Опубликовать сообщение", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🚫 Забанить пользователя", callback_data="admin_ban")]
    ])

# --- Хэндлеры ---

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    all_users.add(user_id) # Запоминаем пользователя
    
    if user_id in banned_users:
        return
    
    if user_id == ADMIN_ID:
        await message.answer("👋 Добро пожаловать в админ-панель!", reply_markup=get_admin_keyboard())
    else:
        await message.answer(
            "Привет! Напиши свое обращение/предложение сюда, и я передам его администратору.\n\n"
            f"⏳ Обратите внимание: отправлять сообщения можно не чаще, чем раз в {COOLDOWN_MINUTES} минуты."
        )

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🔧 Админ-панель", reply_markup=get_admin_keyboard())

# --- Логика Админа: БАН ---

@dp.callback_query(F.data == "admin_ban")
async def process_ban_button(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    
    await callback.message.answer("Введите ID пользователя, которого хотите забанить (только цифры):\nДля отмены напишите /cancel")
    await state.set_state(AdminStates.waiting_for_ban_id)
    await callback.answer()

@dp.message(AdminStates.waiting_for_ban_id)
async def process_ban_id(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    if message.text == "/cancel":
        await message.answer("Действие отменено.", reply_markup=get_admin_keyboard())
        await state.clear()
        return

    try:
        user_id_to_ban = int(message.text.strip())
        banned_users.add(user_id_to_ban)
        await message.answer(f"✅ Пользователь с ID {user_id_to_ban} успешно забанен.")
    except ValueError:
        await message.answer("❌ Ошибка! ID должен состоять только из цифр. Попробуйте снова.")
    
    await state.clear()

# --- Логика Админа: РАССЫЛКА ---

@dp.callback_query(F.data == "admin_broadcast")
async def process_broadcast_button(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    
    await callback.message.answer(
        "📝 Отправьте сообщение, которое хотите разослать всем пользователям бота.\n"
        "Вы можете отправить текст, фото, видео или голосовое сообщение.\n\n"
        "Для отмены напишите /cancel"
    )
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.answer()

@dp.message(AdminStates.waiting_for_broadcast)
async def process_broadcast_message(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    if message.text == "/cancel":
        await message.answer("Рассылка отменена.", reply_markup=get_admin_keyboard())
        await state.clear()
        return

    # Защита от случайной рассылки пустого списка (если кроме админа никого нет)
    users_to_send = [uid for uid in all_users if uid != ADMIN_ID]
    if not users_to_send:
        await message.answer("❌ В базе пока нет пользователей для рассылки (кроме вас).")
        await state.clear()
        return

    await message.answer(f"⏳ Начинаю рассылку для {len(users_to_send)} пользователей...")
    success_count = 0

    for user_id in users_to_send:
        try:
            # copy_to позволяет скопировать сообщение 1 в 1 (включая фото/видео)
            await message.copy_to(chat_id=user_id)
            success_count += 1
            await asyncio.sleep(0.05) # Небольшая задержка, чтобы Telegram не заблокировал за спам
        except Exception as e:
            logging.info(f"Не удалось отправить пользователю {user_id}: {e}")

    await message.answer(f"✅ Рассылка успешно завершена!\nДоставлено: {success_count} из {len(users_to_send)}.", reply_markup=get_admin_keyboard())
    await state.clear()

# --- Логика приема сообщений от пользователей ---

@dp.message()
async def handle_user_message(message: Message, state: FSMContext):
    user_id = message.from_user.id
    all_users.add(user_id) # На всякий случай запоминаем и тут

    # Если мы находимся в каком-то состоянии админа, не обрабатываем это как предложку
    current_state = await state.get_state()
    if current_state is not None:
        return

    # Проверка на бан
    if user_id in banned_users:
        return 

    # Игнорируем сообщения от админа вне состояний
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

    # Формируем текст
    text_to_admin = (
        f"📩 <b>Новое обращение!</b>\n\n"
        f"<b>От кого:</b> @{message.from_user.username or 'Без username'}\n"
        f"<b>ID:</b> <code>{user_id}</code>\n"
    )

    try:
        # Сначала отправляем информацию о пользователе
        await bot.send_message(chat_id=ADMIN_ID, text=text_to_admin, parse_mode="HTML")
        # Затем пересылаем само сообщение пользователя (сохраняются фото, видео, документы)
        await message.copy_to(chat_id=ADMIN_ID)
        
        last_message_time[user_id] = now
        await message.answer("✅ Ваше сообщение успешно отправлено администратору!")
    except Exception as e:
        logging.error(f"Failed to send message to admin: {e}")
        await message.answer("❌ Произошла ошибка при отправке. Попробуйте позже.")


# --- Запуск ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
