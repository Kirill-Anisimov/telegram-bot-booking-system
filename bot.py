# bot.py
import asyncio
import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from config import BOT_TOKEN, WORK_HOURS
from database import SessionLocal, engine
from models import Base, User, Slot

Base.metadata.create_all(bind=engine)
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- Вспомогательные функции ---

def get_free_slots(date):
    session = SessionLocal()
    slots = session.query(Slot).filter(Slot.date == date).all()
    session.close()

    taken = {s.time for s in slots if s.is_booked}
    all_slots = [f"{h:02d}:00" for h in WORK_HOURS]
    return [t for t in all_slots if t not in taken]

def book_slot(user_id, date, time):
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=user_id).first()
    if not user:
        return False, "Пользователь не найден."

    # Проверка, не занят ли слот
    existing = session.query(Slot).filter_by(date=date, time=time).first()
    if existing and existing.is_booked:
        session.close()
        return False, "Этот слот уже занят 😞"

    if not existing:
        existing = Slot(date=date, time=time)

    existing.is_booked = True
    existing.booked_by = user
    session.add(existing)
    session.commit()
    session.close()
    return True, f"✅ Вы успешно забронировали {time} на {date.strftime('%d.%m.%Y')}"

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
        [InlineKeyboardButton(text="📋 Мои брони", callback_data="my_bookings")]
    ])
    await message.answer("🎵 Добро пожаловать в школу музыки!\nВыберите действие:", reply_markup=kb)


@dp.callback_query(F.data == "book")
async def choose_date(callback: types.CallbackQuery):
    today = datetime.date.today()
    kb = InlineKeyboardBuilder()
    for i in range(5):  # ближайшие 5 дней
        date = today + datetime.timedelta(days=i)
        kb.button(
            text=date.strftime("%d.%m.%Y"), callback_data=f"date_{date}"
        )
    kb.adjust(1)
    await callback.message.edit_text("Выберите дату:", reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("date_"))
async def choose_time(callback: types.CallbackQuery):
    date_str = callback.data.split("_")[1]
    date = datetime.date.fromisoformat(date_str)
    free_slots = get_free_slots(date)

    if not free_slots:
        await callback.message.edit_text("На эту дату нет свободных слотов 😞")
        return

    kb = InlineKeyboardBuilder()
    for t in free_slots:
        kb.button(text=t, callback_data=f"time_{date}_{t}")
    kb.adjust(3)
    await callback.message.edit_text(f"Свободные слоты на {date.strftime('%d.%m.%Y')}:", reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("time_"))
async def confirm_booking(callback: types.CallbackQuery):
    _, date_str, time = callback.data.split("_")
    date = datetime.date.fromisoformat(date_str)

    ok, msg = book_slot(callback.from_user.id, date, time)
    await callback.message.edit_text(msg)


@dp.callback_query(F.data == "my_bookings")
async def my_bookings(callback: types.CallbackQuery):
    bookings = get_user_bookings(callback.from_user.id)

    if not bookings:
        await callback.message.edit_text("У вас нет активных броней 🎶")
        return

    kb = InlineKeyboardBuilder()
    for b in bookings:
        label = f"{b.date.strftime('%d.%m.%Y')} {b.time}"
        kb.button(text=f"❌ Отменить {label}", callback_data=f"cancel_{b.id}")
    kb.adjust(1)

    text = "📋 Ваши брони:\n" + "\n".join(
        [f"• {b.date.strftime('%d.%m.%Y')} {b.time}" for b in bookings]
    )
    await callback.message.edit_text(text, reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("cancel_"))
async def cancel(callback: types.CallbackQuery):
    slot_id = int(callback.data.split("_")[1])
    msg = cancel_booking(callback.from_user.id, slot_id)
    await callback.message.edit_text(msg)


# --- Запуск ---
async def main():
    print("Бот запущен 🚀")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
