# bot_categories_moderators.py
import asyncio
import sqlite3
import uuid
from datetime import datetime
from typing import Optional, Dict

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ------------------ Настройки ------------------
TOKEN = "8537204507:AAG7DJpZPgCVVrlNkVCPXk_1U9uVobgn7h8"
# Укажи реальные Telegram ID модераторов (по одному на категорию)
MODERATORS: Dict[str, int] = {
    "Backend": 8077275072,           # <- замените на реальный id
    "Frontend": 8077275072,
    "Grafik dizayner": 8077275072,
    "Kiberxavfsizlik": 8077275072
}
CATEGORIES = list(MODERATORS.keys())
DB_PATH = "orders.db"
PAGE_SIZE = 5
# ------------------------------------------------

bot = Bot(token=TOKEN)
dp = Dispatcher()

# временные состояния в памяти
temp_state = {
    "awaiting_order_from": {},    # user_id -> category (когда ждем описание после выбора категории)
    "awaiting_send_from_mod": {}, # mod_id -> order_id (когда ждем от модератора результат для отправки)
}

# ------------------ SQLite helpers ------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        username TEXT,
        category TEXT,
        description TEXT,
        status TEXT,          -- pending, in_progress, done, rejected
        assigned_mod INTEGER, -- id модератора
        result_text TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """)
    conn.commit()
    conn.close()

def create_order_row(user: types.User, description: str, category: str):
    conn = get_conn()
    cur = conn.cursor()
    oid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO orders(order_id, user_id, username, category, description, status, assigned_mod, result_text, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', NULL, NULL, ?, ?)",
        (oid, user.id, user.username or "", category, description, now, now)
    )
    conn.commit()
    conn.close()
    return oid

def get_pending_orders_by_category(category: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE status = 'pending' AND category = ? ORDER BY created_at DESC", (category,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_order(order_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = cur.fetchone()
    conn.close()
    return row

def update_order_status(order_id: str, status: str, assigned_mod: Optional[int] = None, result_text: Optional[str] = None):
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute(
        "UPDATE orders SET status = ?, assigned_mod = ?, result_text = ?, updated_at = ? WHERE order_id = ?",
        (status, assigned_mod, result_text, now, order_id)
    )
    conn.commit()
    conn.close()

def delete_order(order_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
    conn.commit()
    conn.close()

def get_user_orders(user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_orders_by_status(status: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC", (status,))
    rows = cur.fetchall()
    conn.close()
    return rows

# init db
init_db()

# ------------------ Keyboards ------------------
def categories_kb():
    kb = InlineKeyboardBuilder()
    for c in CATEGORIES:
        kb.button(text=c, callback_data=f"cat_{c}")
    kb.adjust(2)
    return kb.as_markup()

def start_kb(user: types.User):
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Buyurtma berish", callback_data="make_order")
    kb.button(text="📄 Mening zakazlarim", callback_data="my_orders")
    # если пользователь является модератор — показать кнопку "My tasks"
    if user.id in MODERATORS.values():
        kb.button(text="🛠️ My tasks", callback_data="my_tasks")
    kb.adjust(2)
    return kb.as_markup()

def mod_notification_kb(order_id: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="👀 Ko'rish", callback_data=f"mod_view_{order_id}")
    kb.button(text="🛠️ Olish (в работу)", callback_data=f"mod_start_{order_id}")
    kb.button(text="📤 Отправить результат", callback_data=f"mod_send_{order_id}")
    kb.button(text="❌ Rad etish", callback_data=f"mod_reject_{order_id}")
    kb.button(text="🗑️ O'chirish", callback_data=f"mod_delete_{order_id}")
    kb.adjust(2)
    return kb.as_markup()

def order_options_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Baholash ⭐️", callback_data="rate")
    kb.button(text="Admin bilan bog'lanish 📩", callback_data="contact_admin")
    kb.button(text="Zakazni bekor qilish ❌", callback_data="cancel_order")
    kb.adjust(2)
    return kb.as_markup()

# ------------------ Пользовательский флоу ------------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Salom! Nima qilmoqchisiz?", reply_markup=start_kb(message.from_user))

@dp.callback_query(lambda c: c.data == "make_order")
async def cb_make_order(callback: types.CallbackQuery):
    await callback.message.answer("Qaysi sohada buyurtma berasiz? Tanlang:", reply_markup=categories_kb())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("cat_"))
async def cb_category_selected(callback: types.CallbackQuery):
    category = callback.data.split("_", 1)[1]
    # Сохраняем в temp_state, ждем описание от пользователя
    temp_state["awaiting_order_from"][callback.from_user.id] = category
    await callback.message.answer(f"Tanlangan: {category}\nIltimos, buyurtma tavsifini yuboring (tekst).")
    await callback.answer()

@dp.message()
async def catch_message_general(message: types.Message):
    uid = message.from_user.id

    # 1) если ждем описание заказа от пользователя
    if uid in temp_state["awaiting_order_from"]:
        category = temp_state["awaiting_order_from"].pop(uid)
        desc = message.text or ""
        order_id = create_order_row(message.from_user, desc, category)
        # отправляем уведомление ответственному модеру
        mod_id = MODERATORS.get(category)
        if mod_id:
            try:
                await bot.send_message(
                    mod_id,
                    f"📩 Yangi buyurtma ({category}):\nID: <code>{order_id}</code>\nFrom: @{message.from_user.username or message.from_user.id} ({message.from_user.id})\n\n{desc}",
                    reply_markup=mod_notification_kb(order_id),
                    parse_mode="HTML"
                )
            except Exception:
                pass
        await message.answer("Buyurtmangiz moderatorga yuborildi. Tez orada tekshiriladi.", reply_markup=order_options_kb())
        return

    # 2) если модератор должен прислать результат (ждем файл/фото/док/текст)
    if uid in temp_state["awaiting_send_from_mod"]:
        order_id = temp_state["awaiting_send_from_mod"].pop(uid)
        order = get_order(order_id)
        if not order:
            await message.answer("Order topilmadi yoki allaqachon ishlangan.")
            return
        user_id = order["user_id"]
        # Попробуем переслать (копировать) любое сообщение модератора заказчику
        try:
            await bot.copy_message(chat_id=user_id, from_chat_id=uid, message_id=message.message_id)
        except Exception:
            # если не получилось копировать, отправим текст
            if message.text:
                await bot.send_message(user_id, f"📤 Moderator прислал результат:\n\n{message.text}")
            else:
                await message.answer("Не удалось переслать сообщение. Попробуйте отправить как документ/фото или текст ещё раз.")
                return
        # обновим статус заказа
        res_text = message.text if message.text else "[media]"
        update_order_status(order_id, "done", assigned_mod=uid, result_text=res_text)
        await message.answer("Natija yuborildi va zakaz belgilandi: DONE ✅")
        return

    # иначе — проверка команды просмотра своих заказов у пользователя/модератора (если кликали кнопку)
    # просто игнорируем свободные сообщения
    return

# ------------------ Модераторские callback'ы ------------------
@dp.callback_query(lambda c: c.data.startswith("mod_view_"))
async def mod_view(callback: types.CallbackQuery):
    mod_id = callback.from_user.id
    order_id = callback.data.split("_", 2)[2]
    # проверка прав: модератор должен соответствовать категории заказа
    row = get_order(order_id)
    if not row:
        await callback.answer("Order topilmadi.", show_alert=True)
        return
    cat = row["category"]
    expected_mod = MODERATORS.get(cat)
    if mod_id != expected_mod:
        await callback.answer("Bu buyurtma sizga tegishli emas.", show_alert=True)
        return
    text = (
        f"📝 Order\nID: <code>{row['order_id']}</code>\nUser: @{row['username']} ({row['user_id']})\n"
        f"Kategoriya: {row['category']}\nDescription: {row['description']}\nStatus: {row['status']}\nCreated: {row['created_at']}"
    )
    kb = InlineKeyboardBuilder()
    if row["status"] == "pending":
        kb.button(text="🛠️ Olish (в работу)", callback_data=f"mod_start_{order_id}")
    if row["status"] in ("pending", "in_progress"):
        kb.button(text="📤 Отправить результат", callback_data=f"mod_send_{order_id}")
        kb.button(text="❌ Rad etish", callback_data=f"mod_reject_{order_id}")
    kb.button(text="🗑️ O'chirish", callback_data=f"mod_delete_{order_id}")
    kb.adjust(2)
    await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("mod_start_"))
async def mod_start(callback: types.CallbackQuery):
    mod_id = callback.from_user.id
    order_id = callback.data.split("_", 2)[2]
    row = get_order(order_id)
    if not row:
        await callback.answer("Order topilmadi.", show_alert=True)
        return
    # проверка прав
    if MODERATORS.get(row["category"]) != mod_id:
        await callback.answer("Bu buyurtma sizga tegishli emas.", show_alert=True)
        return
    update_order_status(order_id, "in_progress", assigned_mod=mod_id)
    await callback.message.answer(f"Zakaz {order_id} olindi в работу ✅. Endi 'Отправить результат' tugmasini bosing va fayl/tekst yuboring.")
    await callback.answer("Olingan в работу.")

@dp.callback_query(lambda c: c.data.startswith("mod_send_"))
async def mod_send(callback: types.CallbackQuery):
    mod_id = callback.from_user.id
    order_id = callback.data.split("_", 2)[2]
    row = get_order(order_id)
    if not row:
        await callback.answer("Order topilmadi.", show_alert=True)
        return
    if MODERATORS.get(row["category"]) != mod_id:
        await callback.answer("Bu buyurtma sizga tegishli emas.", show_alert=True)
        return
    # ставим ожидание: следующий message от модератора будет переслан заказчику
    temp_state["awaiting_send_from_mod"][mod_id] = order_id
    await callback.message.answer("Iltimos, natijani (fayl/rasm/dokument/video yoki tekst) yuboring — u avtomatik tarzda mijozga yuboriladi.")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("mod_reject_"))
async def mod_reject(callback: types.CallbackQuery):
    mod_id = callback.from_user.id
    order_id = callback.data.split("_", 2)[2]
    row = get_order(order_id)
    if not row:
        await callback.answer("Order topilmadi.", show_alert=True)
        return
    if MODERATORS.get(row["category"]) != mod_id:
        await callback.answer("Bu buyurtma sizga tegishli emas.", show_alert=True)
        return
    update_order_status(order_id, "rejected", assigned_mod=mod_id, result_text="rejected_by_mod")
    # уведомляем заказчика
    try:
        await bot.send_message(row["user_id"], f"❌ Sizning buyurtmangiz (ID: {order_id}) moderator tomonidan rad etildi.")
    except Exception:
        pass
    await callback.message.answer("Zakaz rad etildi va mijozga xabar yuborildi.")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("mod_delete_"))
async def mod_delete(callback: types.CallbackQuery):
    mod_id = callback.from_user.id
    order_id = callback.data.split("_", 2)[2]
    row = get_order(order_id)
    if not row:
        await callback.answer("Order topilmadi.", show_alert=True)
        return
    # Только модератор категории или админ (в нашем случае модераторы только свои) может удалить
    if MODERATORS.get(row["category"]) != mod_id:
        await callback.answer("Bu buyurtma sizga tegishli emas.", show_alert=True)
        return
    delete_order(order_id)
    await callback.message.answer("Zakaz o'chirildi.")
    await callback.answer()

# ------------------ Просмотр задач модератора ------------------
@dp.callback_query(lambda c: c.data == "my_tasks")
async def cb_my_tasks(callback: types.CallbackQuery):
    mod_id = callback.from_user.id
    if mod_id not in MODERATORS.values():
        await callback.answer("Siz moderatorsiz emas.", show_alert=True)
        return
    # найдём категорию(и) за которую отвечает этот модератор (в нашем случае 1)
    cats = [k for k, v in MODERATORS.items() if v == mod_id]
    text = ""
    any_found = False
    for cat in cats:
        pending = get_pending_orders_by_category(cat)
        if pending:
            any_found = True
            text += f"📂 {cat} — {len(pending)} pending:\n\n"
            for o in pending:
                text += f"ID: <code>{o['order_id']}</code>\nUser: @{o['username']} ({o['user_id']})\n{ o['description'] }\n\n"
    if not any_found:
        await callback.message.answer("Hozircha sizga tegishli pending yo'q.")
    else:
        await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

# ------------------ Пользователь: мои заказы ------------------
@dp.callback_query(lambda c: c.data == "my_orders")
async def cb_my_orders(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    rows = get_user_orders(user_id)
    if not rows:
        await callback.message.answer("Sizda hech qanday zakaz yo'q.")
        await callback.answer()
        return
    text = "Sizning zakazlaringiz:\n\n"
    for r in rows:
        text += f"ID: <code>{r['order_id']}</code>\nKategoriya: {r['category']}\nStatus: {r['status']}\nResult: {r['result_text'] or '—'}\n\n"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

# ------------------ Запуск ------------------
async def main():
    print("Bot running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
