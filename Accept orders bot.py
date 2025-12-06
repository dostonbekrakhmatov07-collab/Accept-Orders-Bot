from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.state import StateFilter
import random
import json

TOKEN = "8537204507:AAG7DJpZPgCVVrlNkVCPXk_1U9uVobgn7h8"
ADMIN_ID = 8077275072

# Bot va dispatcher
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

categories = ["Backend", "Frontend", "Kiberxavfsizlik", "Flutter", "Grafik dizayner", "Kompyuter savodxonligi"]

# FSM states
class OrderStates(StatesGroup):
    choosing_category = State()
    entering_budget = State()
    entering_order_name = State()
    contacting_admin = State()  # admin bilan bog'lanish uchun state

# Inline keyboards
def categories_keyboard():
    kb = InlineKeyboardBuilder()
    for c in categories:
        kb.button(text=c, callback_data=f"cat_{c}")
    kb.adjust(2)
    return kb.as_markup()

def order_options_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Baholash ⭐️", callback_data="rate")
    kb.button(text="Admin bilan bog'lanish 📩", callback_data="contact_admin")
    kb.button(text="Zakazni bekor qilish ❌", callback_data="cancel_order")
    kb.adjust(2)
    return kb.as_markup()

def rating_keyboard():
    kb = InlineKeyboardBuilder()
    for i in range(1,6):
        kb.button(text=f"{i}⭐", callback_data=f"rate_{i}")
    kb.adjust(5)
    return kb.as_markup()

# Start command
@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    kb = InlineKeyboardBuilder()
    kb.button(text="Buyurtma berish", callback_data="order")
    kb.adjust(1)
    await message.answer("Salom! Nima qilmoqchisiz?", reply_markup=kb.as_markup())
    await state.clear()

# Order callback
@dp.callback_query(F.data=="order")
async def order_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Qaysi sohada zakaz olmoqchisiz?", reply_markup=categories_keyboard())
    await state.set_state(OrderStates.choosing_category)
    await callback.answer()

# Category selected
@dp.callback_query(F.data.startswith("cat_"), StateFilter(OrderStates.choosing_category))
async def category_selected(callback: CallbackQuery, state: FSMContext):
    category = callback.data[4:]
    await state.update_data(category=category)
    await callback.message.answer(f"{category} tanlandi. Mablag'ingizni kiriting (raqam bilan):")
    await state.set_state(OrderStates.entering_budget)
    await callback.answer()

# Enter budget
@dp.message(StateFilter(OrderStates.entering_budget))
async def enter_budget(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting!")
        return
    await state.update_data(budget=int(message.text))
    await message.answer("Nima buyurtma qilmoqchisiz? (masalan: logo, bot, website)")
    await state.set_state(OrderStates.entering_order_name)

# Enter order name
@dp.message(StateFilter(OrderStates.entering_order_name))
async def enter_order_name(message: Message, state: FSMContext):
    order_name = message.text
    data = await state.get_data()
    category = data["category"]
    budget = data["budget"]
    random_price = random.randint(int(budget*0.7), int(budget*1.3))

    user_data = {
        "id": message.from_user.id,
        "category": category,
        "budget": budget,
        "order_title": order_name,
        "random_price": random_price
    }

    try:
        with open("orders.json", "r") as f:
            orders = json.load(f)
    except:
        orders = {"users": []}

    orders["users"].append(user_data)

    with open("orders.json", "w") as f:
        json.dump(orders, f, indent=4)

    await message.answer(
        f"Zakazingiz qabul qilindi!\nRandom narx: {random_price} so'm",
        reply_markup=order_options_keyboard()
    )
    await state.clear()

# Order options: Rate, Contact admin, Cancel
@dp.callback_query(F.data.in_(["rate","contact_admin","cancel_order"]))
async def order_option_selected(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if callback.data == "rate":
        await callback.message.answer("Bahoni tanlang:", reply_markup=rating_keyboard())
    elif callback.data == "contact_admin":
        await callback.message.answer("Iltimos, adminga yuboradigan xabaringizni kiriting:")
        await state.set_state(OrderStates.contacting_admin)
    elif callback.data == "cancel_order":
        try:
            with open("orders.json", "r") as f:
                data = json.load(f)
            data["users"] = [u for u in data["users"] if u["id"] != user_id]
            with open("orders.json", "w") as f:
                json.dump(data, f, indent=4)
            await callback.message.answer("Zakazingiz bekor qilindi ❌")
        except:
            await callback.message.answer("Zakaz topilmadi.")
    await callback.answer()

# Adminga xabar jo'natish (FSMContact)
@dp.message(StateFilter(OrderStates.contacting_admin))
async def send_admin_message(message: Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"Foydalanuvchi @{message.from_user.username} xabar yubordi:\n\n{message.text}")
    await message.answer("Xabaringiz adminga yuborildi 📩")
    await state.clear()

# Rating selected
@dp.callback_query(F.data.startswith("rate_"))
async def rating_selected(callback: CallbackQuery):
    rate = int(callback.data[5:])
    user_id = callback.from_user.id
    try:
        with open("orders.json", "r") as f:
            data = json.load(f)
        for u in data["users"]:
            if u["id"] == user_id:
                u["rating"] = rate
        with open("orders.json", "w") as f:
            json.dump(data, f, indent=4)
    except:
        pass
    await callback.message.answer(f"Siz {rate}⭐ bilan baholadingiz. Rahmat!")
    await callback.answer()

# Run bot
if __name__ == "__main__":
    dp.run_polling(bot)
