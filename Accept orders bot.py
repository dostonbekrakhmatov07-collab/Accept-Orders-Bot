import asyncio
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN = "8537204507:AAG7DJpZPgCVVrlNkVCPXk_1U9uVobgn7h8"

# ID админов
ADMINS = [8077275072]

bot = Bot(TOKEN)
dp = Dispatcher()


# ------------------------------
# ФУНКЦИЯ СОХРАНЕНИЯ В JSON
# ------------------------------
def save_order(user_id, text):
    try:
        with open("orders.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except:
        data = []

    data.append({"user_id": user_id, "order": text})

    with open("orders.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# ------------------------------
# СТАРТ МЕНЮ
# ------------------------------
@dp.message(Command("start"))
async def start(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Buyurtma berish", callback_data="make_order")
    kb.adjust(1)

    await message.answer(
        "Assalomu alaykum!\nQuyidan buyurtma berishingiz mumkin.",
        reply_markup=kb.as_markup()
    )


# ------------------------------
# ПОЛЬЗОВАТЕЛЬ НАЖАЛ "СДЕЛАТЬ ЗАКАЗ"
# ------------------------------
@dp.callback_query(lambda c: c.data == "make_order")
async def make_order(callback: types.CallbackQuery):
    await callback.message.answer("Buyurtma matnini yuboring:")
    await callback.answer()
    dp["waiting_for_order"] = callback.from_user.id


# ------------------------------
# ПОЛЬЗОВАТЕЛЬ ОТПРАВИЛ ТЕКСТ ЗАКАЗА
# ------------------------------
@dp.message()
async def catch_order(message: types.Message):

    # Проверяем, ждём ли мы от него заказ
    if dp.get("waiting_for_order") == message.from_user.id:

        order_text = message.text

        # Кнопки для админа
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Qabul qilish", callback_data=f"accept_{message.from_user.id}")
        kb.button(text="❌ Rad etish", callback_data=f"decline_{message.from_user.id}")
        kb.adjust(2)

        # Отправляем админу
        for admin in ADMINS:
            await bot.send_message(
                admin,
                f"📩 Yangi buyurtma!\n\n📌 User: {message.from_user.id}\n\n📝 Buyurtma:\n{order_text}",
                reply_markup=kb.as_markup()
            )

        await message.answer("Buyurtmangiz moderatorga yuborildi!")
        dp["waiting_for_order"] = None


# ------------------------------
# АДМИН ПРИНЯЛ ЗАКАЗ
# ------------------------------
@dp.callback_query(lambda c: c.data.startswith("accept_"))
async def accept_order(callback: types.CallbackQuery):

    if callback.from_user.id not in ADMINS:
        return await callback.answer("Siz admin emassiz!", show_alert=True)

    user_id = int(callback.data.split("_")[1])
    text = callback.message.text.split("📝 Buyurtma:\n")[1]

    save_order(user_id, text)

    await bot.send_message(user_id, "✅ Buyurtmangiz qabul qilindi!")
    await callback.message.edit_text("Buyurtma qabul qilindi ✓")
    await callback.answer()


# ------------------------------
# АДМИН ОТКЛОНИЛ ЗАКАЗ
# ------------------------------
@dp.callback_query(lambda c: c.data.startswith("decline_"))
async def decline_order(callback: types.CallbackQuery):

    if callback.from_user.id not in ADMINS:
        return await callback.answer("Siz admin emassiz!", show_alert=True)

    user_id = int(callback.data.split("_")[1])

    await bot.send_message(user_id, "❌ Buyurtmangiz rad etildi.")
    await callback.message.edit_text("Buyurtma rad etildi ✗")
    await callback.answer()


# ------------------------------
# ЗАПУСК БОТА
# ------------------------------
async def main():
    print("Bot ishga tushdi...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
