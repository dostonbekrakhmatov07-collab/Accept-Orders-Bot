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
MODERATORS: Dict[str, int] = {
    "Backend": 8077275072,           
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

# временные состояния
temp_state = {
    "awaiting_order_from": {},    # user_id -> category
    "awaiting_send_from_mod": {}, # mod_id -> order_id
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
        status TEXT,
        assigned_mod INTEGER,
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
    kb.button(text="📦 Сделать заказ", callback_data="make_order")
    kb.button(text="📄 Мои заказы", callback_data="my_orders")
    if user.id in MODERATORS.values():
        kb.button(text="🛠️ Мои задачи", callback_data="my_tasks")
    kb.adjust(2)
    return kb.as_markup()

def mod_notification_kb(order_id: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="👀 Просмотреть", callback_data=f"mod_view_{order_id}")
    kb.button(text="🛠️ В работу", callback_data=f"mod_start_{order_id}")
    kb.button(text="📤 Отправить результат", callback_data=f"mod_send_{order_id}")
    kb.button(text="❌ Отклонить", callback_data=f"mod_reject_{order_id}")
    kb.button(text="🗑️ Удалить", callback_data=f"mod_delete_{order_id}")
    kb.adjust(2)
    return kb.as_markup()

def order_options_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Оценить ⭐️", callback_data="rate")
    kb.button(text="Связь с админом 📩", callback_data="contact_admin")
    kb.button(text="Отменить заказ ❌", callback_data="cancel_order")
    kb.adjust(2)
    return kb.as_markup()

# ------------------ Пользовательский флоу ------------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привет! Что хотите сделать?", reply_markup=start_kb(message.from_user))

@dp.callback_query(lambda c: c.data == "make_order")
async def cb_make_order(callback: types.CallbackQuery):
    await callback.message.answer("В какой сфере хотите сделать заказ? Выберите:", reply_markup=categories_kb())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("cat_"))
async def cb_category_selected(callback: types.CallbackQuery):
    category = callback.data.split("_", 1)[1]
    temp_state["awaiting_order_from"][callback.from_user.id] = category
    await callback.message.answer(f"Выбрано: {category}\nПожалуйста, отправьте описание заказа (текст).")
    await callback.answer()

@dp.message()
async def catch_message_general(message: types.Message):
    uid = message.from_user.id

    if uid in temp_state["awaiting_order_from"]:
        category = temp_state["awaiting_order_from"].pop(uid)
        desc = message.text or ""
        order_id = create_order_row(message.from_user, desc, category)
        mod_id = MODERATORS.get(category)
        if mod_id:
            try:
                await bot.send_message(
                    mod_id,
                    f"📩 Новый заказ ({category}):\nID: <code>{order_id}</code>\nОт: @{message.from_user.username or message.from_user.id} ({message.from_user.id})\n\n{desc}",
                    reply_markup=mod_notification_kb(order_id),
                    parse_mode="HTML"
                )
            except Exception:
                pass
        await message.answer("Ваш заказ отправлен модератору. Скоро будет проверен.", reply_markup=order_options_kb())
        return

    if uid in temp_state["awaiting_send_from_mod"]:
        order_id = temp_state["awaiting_send_from_mod"].pop(uid)
        order = get_order(order_id)
        if not order:
            await message.answer("Заказ не найден или уже обработан.")
            return
        user_id = order["user_id"]
        try:
            await bot.copy_message(chat_id=user_id, from_chat_id=uid, message_id=message.message_id)
        except Exception:
            if message.text:
                await bot.send_message(user_id, f"📤 Модератор прислал результат:\n\n{message.text}")
            else:
                await message.answer("Не удалось переслать сообщение. Попробуйте другой формат.")
                return
        res_text = message.text if message.text else "[media]"
        update_order_status(order_id, "done", assigned_mod=uid, result_text=res_text)
        await message.answer("Результат отправлен ✅")
        return

# ------------------ Обработчики пользовательских кнопок ------------------
@dp.callback_query(lambda c: c.data == "rate")
async def cb_rate(callback: types.CallbackQuery):
    await callback.message.answer("Спасибо за вашу оценку!")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "contact_admin")
async def cb_contact_admin(callback: types.CallbackQuery):
    await callback.message.answer("Вы можете написать администратору: @admin_username")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "cancel_order")
async def cb_cancel_order(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    rows = get_user_orders(user_id)
    if not rows:
        await callback.answer("У вас нет заказов для отмены.", show_alert=True)
        return
    last_order_id = rows[0]['order_id']
    update_order_status(last_order_id, "rejected")
    await callback.message.answer(f"Ваш заказ {last_order_id} отменён ❌")
    await callback.answer()

# ------------------ Модераторские callback'ы ------------------
@dp.callback_query(lambda c: c.data.startswith("mod_view_"))
async def mod_view(callback: types.CallbackQuery):
    mod_id = callback.from_user.id
    order_id = callback.data.split("_", 2)[2]
    row = get_order(order_id)
    if not row:
        await callback.answer("Заказ не найден.", show_alert=True)
        return
    if mod_id != MODERATORS.get(row["category"]):
        await callback.answer("Этот заказ вам не принадлежит.", show_alert=True)
        return
    text = (
        f"📝 Заказ\nID: <code>{row['order_id']}</code>\nUser: @{row['username']} ({row['user_id']})\n"
        f"Категория: {row['category']}\nОписание: {row['description']}\nСтатус: {row['status']}\nСоздано: {row['created_at']}"
    )
    kb = InlineKeyboardBuilder()
    if row["status"] == "pending":
        kb.button(text="🛠️ В работу", callback_data=f"mod_start_{order_id}")
    if row["status"] in ("pending", "in_progress"):
        kb.button(text="📤 Отправить результат", callback_data=f"mod_send_{order_id}")
        kb.button(text="❌ Отклонить", callback_data=f"mod_reject_{order_id}")
    kb.button(text="🗑️ Удалить", callback_data=f"mod_delete_{order_id}")
    kb.adjust(2)
    await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("mod_start_"))
async def mod_start(callback: types.CallbackQuery):
    mod_id = callback.from_user.id
    order_id = callback.data.split("_", 2)[2]
    row = get_order(order_id)
    if not row or MODERATORS.get(row["category"]) != mod_id:
        await callback.answer("Этот заказ вам не принадлежит.", show_alert=True)
        return
    update_order_status(order_id, "in_progress", assigned_mod=mod_id)
    await callback.message.answer(f"Заказ {order_id} взят в работу ✅. Отправьте результат кнопкой 'Отправить результат'.")
    await callback.answer("В работу.")

@dp.callback_query(lambda c: c.data.startswith("mod_send_"))
async def mod_send(callback: types.CallbackQuery):
    mod_id = callback.from_user.id
    order_id = callback.data.split("_", 2)[2]
    row = get_order(order_id)
    if not row or MODERATORS.get(row["category"]) != mod_id:
        await callback.answer("Этот заказ вам не принадлежит.", show_alert=True)
        return
    temp_state["awaiting_send_from_mod"][mod_id] = order_id
    await callback.message.answer("Отправьте результат (файл/текст), он автоматически будет отправлен клиенту.")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("mod_reject_"))
async def mod_reject(callback: types.CallbackQuery):
    mod_id = callback.from_user.id
    order_id = callback.data.split("_", 2)[2]
    row = get_order(order_id)
    if not row or MODERATORS.get(row["category"]) != mod_id:
        await callback.answer("Этот заказ вам не принадлежит.", show_alert=True)
        return
    update_order_status(order_id, "rejected", assigned_mod=mod_id, result_text="rejected_by_mod")
    try:
        await bot.send_message(row["user_id"], f"❌ Ваш заказ (ID: {order_id}) отклонён модератором.")
    except Exception:
        pass
    await callback.message.answer("Заказ отклонён и клиенту отправлено уведомление.")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("mod_delete_"))
async def mod_delete(callback: types.CallbackQuery):
    mod_id = callback.from_user.id
    order_id = callback.data.split("_", 2)[2]
    row = get_order(order_id)
    if not row or MODERATORS.get(row["category"]) != mod_id:
        await callback.answer("Этот заказ вам не принадлежит.", show_alert=True)
        return
    delete_order(order_id)
    await callback.message.answer("Заказ удалён.")
    await callback.answer()

# ------------------ Просмотр задач модератора ------------------
@dp.callback_query(lambda c: c.data == "my_tasks")
async def cb_my_tasks(callback: types.CallbackQuery):
    mod_id = callback.from_user.id
    if mod_id not in MODERATORS.values():
        await callback.answer("Вы не модератор.", show_alert=True)
        return
    cats = [k for k, v in MODERATORS.items() if v == mod_id]
    text = ""
    any_found = False
    for cat in cats:
        pending = get_pending_orders_by_category(cat)
        if pending:
            any_found = True
            text += f"📂 {cat} — {len(pending)} заказов в ожидании:\n\n"
            for o in pending:
                text += f"ID: <code>{o['order_id']}</code>\nUser: @{o['username']} ({o['user_id']})\n{o['description']}\n\n"
    if not any_found:
        await callback.message.answer("Пока нет заказов в ожидании.")
    else:
        await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

# ------------------ Пользователь: мои заказы ------------------
@dp.callback_query(lambda c: c.data == "my_orders")
async def cb_my_orders(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    rows = get_user_orders(user_id)
    if not rows:
        await callback.message.answer("У вас нет заказов.")
        await callback.answer()
        return
    text = "Ваши заказы:\n\n"
    for r in rows:
        text += f"ID: <code>{r['order_id']}</code>\nКатегория: {r['category']}\nСтатус: {r['status']}\nРезультат: {r['result_text'] or '—'}\n\n"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

# ------------------ Запуск ------------------
async def main():
    print("Bot running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
