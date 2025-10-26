# bot.py
import asyncio
import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import BOT_TOKEN, WORK_HOURS
from database import SessionLocal, engine
from models import Base, User, Slot, RoomType

Base.metadata.create_all(bind=engine)
bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# --- Вспомогательные функции ---

def get_free_slots(date, room):
    session = SessionLocal()
    slots = session.query(Slot).filter(Slot.date == date, Slot.room == room).all()
    session.close()

    taken = {s.time for s in slots if s.is_booked}
    all_slots = [f"{h:02d}:00" for h in WORK_HOURS]
    return [t for t in all_slots if t not in taken]


def book_slot(user_id, date, time, room):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=user_id).first()
    if not user:
        return False, "Пользователь не найден."

    # Проверка, не занят ли слот
    existing = session.query(Slot).filter_by(date=date, time=time, room=room).first()
    if existing and existing.is_booked:
        session.close()
        return False, "Этот слот уже занят 😞"

    if not existing:
        existing = Slot(date=date, time=time, room=room)

    existing.is_booked = True
    existing.booked_by = user
    session.add(existing)
    session.commit()
    session.close()
    return True, f"✅ Вы успешно забронировали {time} ({room.value}) на {date.strftime('%d.%m.%Y')}"


def get_user_bookings(user_id):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=user_id).first()
    if not user:
        return []
    bookings = (
        session.query(Slot)
        .filter(Slot.booked_by_id == user.id)
        .order_by(Slot.date, Slot.time)
        .all()
    )
    session.close()
    return bookings


def cancel_booking(user_id, slot_id):
    session = SessionLocal()
    slot = session.query(Slot).filter_by(id=slot_id).first()
    if not slot or not slot.is_booked:
        session.close()
        return "Бронь не найдена."
    slot.is_booked = False
    slot.booked_by_id = None
    session.commit()
    session.close()
    return "❌ Бронь отменена."


# --- Хендлеры ---

@dp.message(F.text == "/start")
async def start(message: types.Message):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
    if not user:
        user = User(telegram_id=message.from_user.id, full_name=message.from_user.full_name)
        session.add(user)
        session.commit()
    session.close()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Забронировать", callback_data="book")],
        [InlineKeyboardButton(text="📋 Мои брони", callback_data="show_my_bookings")],
        [InlineKeyboardButton(text="❌ Отменить бронь", callback_data="cancel_menu")]
    ])
    await message.answer(
        text="🎵 Добро пожаловать в школу музыки!\nВыберите действие:",
        reply_markup=kb,
    )


# --- 1️⃣ Выбор комнаты ---
@dp.callback_query(F.data == "book")
async def choose_room(callback: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    for room in RoomType:
        emoji = {
            RoomType.DRUMS: "🥁",
            RoomType.BASS: "🎸",
            RoomType.VOCAL: "🎤",
            RoomType.GUITAR: "🎶"
        }[room]
        kb.button(text=f"{emoji} {room.value}", callback_data=f"room_{room.value}")
    kb.adjust(2)
    await callback.message.edit_text("Выберите комнату:", reply_markup=kb.as_markup())


# --- 2️⃣ Выбор даты ---
@dp.callback_query(F.data.startswith("room_"))
async def choose_date(callback: types.CallbackQuery):
    room_value = callback.data.split("_")[1]
    today = datetime.date.today()
    kb = InlineKeyboardBuilder()
    for i in range(5):  # ближайшие 5 дней
        date = today + datetime.timedelta(days=i)
        kb.button(
            text=date.strftime("%d.%m.%Y"),
            callback_data=f"date_{room_value}_{date}"
        )
    kb.adjust(1)
    await callback.message.edit_text(f"Вы выбрали {room_value}. Теперь выберите дату:", reply_markup=kb.as_markup())


# --- 3️⃣ Выбор времени ---
@dp.callback_query(F.data.startswith("date_"))
async def choose_time(callback: types.CallbackQuery):
    _, room_value, date_str = callback.data.split("_")
    date = datetime.date.fromisoformat(date_str)
    room = RoomType(room_value)
    free_slots = get_free_slots(date, room)

    if not free_slots:
        await callback.message.edit_text(f"На {date.strftime('%d.%m.%Y')} нет свободных слотов для {room_value} 😞")
        return

    kb = InlineKeyboardBuilder()
    for t in free_slots:
        kb.button(text=t, callback_data=f"time_{room_value}_{date}_{t}")
    kb.adjust(3)
    await callback.message.edit_text(f"Свободные слоты ({room_value}) на {date.strftime('%d.%m.%Y')}:",
                                     reply_markup=kb.as_markup())


# --- 4️⃣ Подтверждение брони ---
@dp.callback_query(F.data.startswith("time_"))
async def confirm_booking(callback: types.CallbackQuery):
    _, room_value, date_str, time = callback.data.split("_")
    date = datetime.date.fromisoformat(date_str)
    room = RoomType(room_value)

    ok, msg = book_slot(callback.from_user.id, date, time, room)
    await callback.message.edit_text(msg)


# --- 5️⃣ Просмотр своих броней ---
@dp.callback_query(F.data == "show_my_bookings")
async def show_my_bookings(callback: types.CallbackQuery):
    bookings = get_user_bookings(callback.from_user.id)

    if not bookings:
        await callback.message.edit_text("У вас нет активных броней 🎶")
        return

    text = "📋 Ваши брони:\n" + "\n".join(
        [f"• {b.room.value} | {b.date.strftime('%d.%m.%Y')} {b.time}" for b in bookings]
    )
    await callback.message.edit_text(text)


# --- 6️⃣ Меню отмены брони ---
@dp.callback_query(F.data == "cancel_menu")
async def cancel_menu(callback: types.CallbackQuery):
    bookings = get_user_bookings(callback.from_user.id)

    if not bookings:
        await callback.message.edit_text("У вас нет активных броней для отмены 🎶")
        return

    kb = InlineKeyboardBuilder()
    for b in bookings:
        label = f"{b.room.value} | {b.date.strftime('%d.%m.%Y')} {b.time}"
        kb.button(text=f"❌ Отменить {label}", callback_data=f"cancel_{b.id}")
    kb.button(text="◀️ Назад", callback_data="back_to_menu")
    kb.adjust(1)

    await callback.message.edit_text(
        "Выберите бронь, которую хотите отменить:",
        reply_markup=kb.as_markup()
    )


# --- 7️⃣ Отмена брони ---
@dp.callback_query(F.data.startswith("cancel_"))
async def cancel(callback: types.CallbackQuery):
    slot_id = int(callback.data.split("_")[1])
    msg = cancel_booking(callback.from_user.id, slot_id)
    await callback.message.edit_text(msg)


# --- 8️⃣ Возврат в меню start ---
@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await start(callback.message)


# --- Запуск ---
async def main():
    print("Бот запущен 🚀")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
