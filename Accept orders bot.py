"""
Admin panel bot (aiogram 3.22)
Функции:
- /start - обычное меню пользователя
- Отправка заказа пользователем -> уходит в pending и админам
- /admin - открывает админ-панель (только для id из ADMINS)
- Просмотр pending с пагинацией, просмотр approved, принятие/отклонение/удаление
- Поиск по user_id
- Статистика
- /broadcast - следующий текст отправится всем users с approved заказами
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, date

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ---------- Настройки ----------
TOKEN = "8537204507:AAG7DJpZPgCVVrlNkVCPXk_1U9uVobgn7h8"
ADMINS = [8077275072]  # <- вставь сюда id админов

PENDING_FILE = "pending_orders.json"
ORDERS_FILE = "orders.json"
# --------------------------------

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Временное хранилище состояний (для простоты)
temp_state = {
    "awaiting_order_from": {},   # user_id -> True (когда ждем текст заказа)
    "awaiting_search_from": {},  # admin_id -> True (когда ждем id для поиска)
    "awaiting_broadcast_from": {},# admin_id -> True (когда ждем текст для рассылки)
}

# ---------- Утилиты работы с файлами ----------
def load_json(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def ensure_files():
    if not os.path.exists(PENDING_FILE):
        save_json(PENDING_FILE, {"orders": []})
    if not os.path.exists(ORDERS_FILE):
        save_json(ORDERS_FILE, {"orders": []})

ensure_files()

# ---------- Вспомогательные функции ----------
def create_order_entry(user: types.User, category: str, budget: int, title: str, attachments=None):
    return {
        "order_id": str(uuid.uuid4()),
        "user_id": user.id,
        "username": user.username or "",
        "first_name": user.first_name or "",
        "category": category,
        "budget": budget,
        "order_title": title,
        "attachments": attachments or [],
        "random_price": None,
        "created_at": datetime.utcnow().isoformat()
    }

def get_stats():
    pending = load_json(PENDING_FILE, {"orders": []})["orders"]
    orders = load_json(ORDERS_FILE, {"orders": []})["orders"]
    total = len(pending) + len(orders)
    approved = len([o for o in orders if o.get("status") == "approved"])
    rejected = len([o for o in orders if o.get("status") == "rejected"])
    pending_cnt = len(pending)
    return {"total": total, "approved": approved, "rejected": rejected, "pending": pending_cnt}

# ---------- Меню /start ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Buyurtma berish", callback_data="make_order")
    if message.from_user.id in ADMINS:
        kb.button(text="🔐 Admin panel", callback_data="open_admin")
    kb.adjust(1)
    await message.answer("Assalomu alaykum! Tanlang:", reply_markup=kb.as_markup())

# ---------- Пользователь: начать заказ ----------
@dp.callback_query(lambda c: c.data == "make_order")
async def on_make_order(callback: types.CallbackQuery):
    await callback.message.answer("Yubormoqchi bo'lgan buyurtma matnini kiriting (sodda matn).")
    temp_state["awaiting_order_from"][callback.from_user.id] = True
    await callback.answer()

# ---------- Прием текста заказа от пользователя ----------
@dp.message()
async def catch_user_order(message: types.Message):
    user_id = message.from_user.id
    # если ждем заказ от пользователя
    if temp_state["awaiting_order_from"].get(user_id):
        # Для простоты: не используем категории/бюджет — можно расширить
        title = message.text.strip()
        pending = load_json(PENDING_FILE, {"orders": []})
        entry = {
            "order_id": str(uuid.uuid4()),
            "user_id": user_id,
            "username": message.from_user.username or "",
            "first_name": message.from_user.first_name or "",
            "category": "—",
            "budget": 0,
            "order_title": title,
            "attachments": [],
            "created_at": datetime.utcnow().isoformat()
        }
        pending["orders"].append(entry)
        save_json(PENDING_FILE, pending)

        # отправим всем админам уведомление с кнопками принять/отклонить
        for admin in ADMINS:
            kb = InlineKeyboardBuilder()
            kb.button(text="✅ Qabul qilish", callback_data=f"admin_accept_{entry['order_id']}")
            kb.button(text="❌ Rad etish", callback_data=f"admin_reject_{entry['order_id']}")
            kb.button(text="🗑️ O'chirish", callback_data=f"admin_delete_{entry['order_id']}")
            kb.adjust(2)
            await bot.send_message(admin,
                                   f"📩 Yangi buyurtma (pending):\n\nID: <code>{entry['order_id']}</code>\nUser: @{entry['username']} ({entry['user_id']})\nBuyurtma: {entry['order_title']}\nVaqt: {entry['created_at']}",
                                   reply_markup=kb.as_markup(), parse_mode="HTML")
        await message.answer("Buyurtmangiz moderatorlarga yuborildi. Tez orada ko'rib chiqiladi.")
        temp_state["awaiting_order_from"].pop(user_id, None)
        return

    # если ждем ввод ID для поиска (админ)
    if temp_state["awaiting_search_from"].get(user_id):
        try:
            search_id = int(message.text.strip())
        except:
            await message.answer("Iltimos, haqiqiy numeric user_id kiriting.")
            return
        # ищем
        orders_db = load_json(ORDERS_FILE, {"orders": []})["orders"]
        user_orders = [o for o in orders_db if o.get("user_id") == search_id]
        if not user_orders:
            await message.answer("Bu foydalanuvchiga oid tasdiqlangan zakazlar topilmadi.")
        else:
            text = f"Foydalanuvchi {search_id} bo'yicha {len(user_orders)} zakaz:\n\n"
            for o in user_orders:
                text += f"ID: {o.get('order_id')}\nTitle: {o.get('order_title')}\nStatus: {o.get('status')}\n\n"
            await message.answer(text)
        temp_state["awaiting_search_from"].pop(user_id, None)
        return

    # если ждем текст для broadcast
    if temp_state["awaiting_broadcast_from"].get(user_id):
        text = message.text
        # получаем всех пользователей с approved заказами
        orders_db = load_json(ORDERS_FILE, {"orders": []})["orders"]
        user_ids = set(o.get("user_id") for o in orders_db if o.get("status") == "approved")
        sent = 0
        for uid in user_ids:
            try:
                await bot.send_message(uid, f"📢 Admin рассылка:\n\n{text}")
                sent += 1
            except Exception:
                pass
        await message.answer(f"Рассылка отправлена {sent} пользователям (approved orders).")
        temp_state["awaiting_broadcast_from"].pop(user_id, None)
        return

    # иначе — простое сообщение (игнорируем)
    # можно добавить логику обычных сообщений
    return

# ---------- Открыть админ-панель ----------
@dp.callback_query(lambda c: c.data == "open_admin")
async def open_admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return await callback.answer("Siz admin emassiz!", show_alert=True)
    kb = InlineKeyboardBuilder()
    kb.button(text="📂 Pending zakazlar", callback_data="admin_pending_list")
    kb.button(text="📚 Tasdiqlangan zakazlar", callback_data="admin_approved_list")
    kb.button(text="🔎 Qidiruv user_id bo'yicha", callback_data="admin_search_user")
    kb.button(text="📊 Statistik", callback_data="admin_stats")
    kb.button(text="✉️ Broadcast (approved users)", callback_data="admin_broadcast")
    kb.adjust(2)
    await callback.message.answer("🔐 Admin panel:", reply_markup=kb.as_markup())
    await callback.answer()

# ---------- Пагинация: вспомогательная сборка клавиатур ----------
PAGE_SIZE = 3

def paginate_list(items, page):
    total = len(items)
    max_page = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if page < 1: page = 1
    if page > max_page: page = max_page
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    return items[start:end], page, max_page

def nav_kb(prefix, page, max_page):
    kb = InlineKeyboardBuilder()
    if page > 1:
        kb.button(text="⬅ Oldingi", callback_data=f"{prefix}_page_{page-1}")
    if page < max_page:
        kb.button(text="Keyingi ➡", callback_data=f"{prefix}_page_{page+1}")
    kb.adjust(2)
    return kb.as_markup()

# ---------- Admin: список pending (страница) ----------
@dp.callback_query(lambda c: c.data == "admin_pending_list")
async def admin_pending_list(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return await callback.answer("Siz admin emassiz!", show_alert=True)
    pending = load_json(PENDING_FILE, {"orders": []})["orders"]
    if not pending:
        return await callback.message.answer("Hozircha pending zakaz yo'q.")
    page_items, page, max_page = paginate_list(pending, 1)
    text = f"📂 Pending zakazlar — {len(pending)} ta\n\n"
    for o in page_items:
        text += f"ID: <code>{o['order_id']}</code>\nUser: @{o.get('username')} ({o.get('user_id')})\nTitle: {o.get('order_title')}\n\n"
    kb = nav_kb("admin_pending", page, max_page)
    # для быстрого просмотра деталей — добавим кнопку посмотреть первый элемент
    kb2 = InlineKeyboardBuilder()
    kb2.button(text="Ko'rish (1)", callback_data=f"admin_view_{page_items[0]['order_id']}")
    kb2.adjust(1)
    await callback.message.answer(text, reply_markup=kb)
    await callback.message.answer("Tezkor:", reply_markup=kb2.as_markup())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_pending_page_"))
async def admin_pending_page(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return await callback.answer("Siz admin emassiz!", show_alert=True)
    parts = callback.data.split("_")
    page = int(parts[-1])
    pending = load_json(PENDING_FILE, {"orders": []})["orders"]
    page_items, page, max_page = paginate_list(pending, page)
    text = f"📂 Pending zakazlar — {len(pending)} ta\n\n"
    for o in page_items:
        text += f"ID: <code>{o['order_id']}</code>\nUser: @{o.get('username')} ({o.get('user_id')})\nTitle: {o.get('order_title')}\n\n"
    kb = nav_kb("admin_pending", page, max_page)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# ---------- Admin: список approved ----------
@dp.callback_query(lambda c: c.data == "admin_approved_list")
async def admin_approved_list(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return await callback.answer("Siz admin emassiz!", show_alert=True)
    orders = load_json(ORDERS_FILE, {"orders": []})["orders"]
    if not orders:
        return await callback.message.answer("Tasdiqlangan zakazlar topilmadi.")
    page_items, page, max_page = paginate_list(orders, 1)
    text = f"📚 Tasdiqlangan zakazlar — {len(orders)} ta\n\n"
    for o in page_items:
        text += f"ID: <code>{o['order_id']}</code>\nUser: @{o.get('username')} ({o.get('user_id')})\nTitle: {o.get('order_title')}\nStatus: {o.get('status')}\n\n"
    kb = nav_kb("admin_approved", page, max_page)
    await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_approved_page_"))
async def admin_approved_page(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return await callback.answer("Siz admin emassiz!", show_alert=True)
    page = int(callback.data.split("_")[-1])
    orders = load_json(ORDERS_FILE, {"orders": []})["orders"]
    page_items, page, max_page = paginate_list(orders, page)
    text = f"📚 Tasdiqlangan zakazlar — {len(orders)} ta\n\n"
    for o in page_items:
        text += f"ID: <code>{o['order_id']}</code>\nUser: @{o.get('username')} ({o.get('user_id')})\nTitle: {o.get('order_title')}\nStatus: {o.get('status')}\n\n"
    kb = nav_kb("admin_approved", page, max_page)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# ---------- Admin: view single order details ----------
@dp.callback_query(lambda c: c.data.startswith("admin_view_"))
async def admin_view_order(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return await callback.answer("Siz admin emassiz!", show_alert=True)
    order_id = callback.data.split("_", 2)[2]
    pending = load_json(PENDING_FILE, {"orders": []})["orders"]
    orders = load_json(ORDERS_FILE, {"orders": []})["orders"]
    found = None
    where = None
    for o in pending:
        if o["order_id"] == order_id:
            found = o
            where = "pending"
            break
    if not found:
        for o in orders:
            if o["order_id"] == order_id:
                found = o
                where = "approved"
                break
    if not found:
        await callback.answer("Order topilmadi.", show_alert=True)
        return
    text = f"📝 Detal: \nID: <code>{found['order_id']}</code>\nUser: @{found.get('username')} ({found.get('user_id')})\nTitle: {found.get('order_title')}\nCategory: {found.get('category')}\nBudget: {found.get('budget')}\nCreated: {found.get('created_at')}\nStatus: {found.get('status','pending')}"
    # buttons: accept/reject/delete (depend on where)
    kb = InlineKeyboardBuilder()
    if where == "pending":
        kb.button(text="✅ Qabul", callback_data=f"admin_accept_{found['order_id']}")
        kb.button(text="❌ Rad etish", callback_data=f"admin_reject_{found['order_id']}")
    kb.button(text="🗑️ O'chirish", callback_data=f"admin_delete_{found['order_id']}")
    kb.adjust(2)
    await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()

# ---------- Admin: принять заказ ----------
@dp.callback_query(lambda c: c.data.startswith("admin_accept_"))
async def admin_accept(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return await callback.answer("Siz admin emassiz!", show_alert=True)
    order_id = callback.data.split("_", 2)[2]
    pending = load_json(PENDING_FILE, {"orders": []})["orders"]
    orders_db = load_json(ORDERS_FILE, {"orders": []})["orders"]
    # найти и переместить
    found = None
    for o in pending:
        if o["order_id"] == order_id:
            found = o
            break
    if not found:
        return await callback.answer("Order topilmadi (yoki allaqachon ishlangan).", show_alert=True)
    # пометим approved
    found["status"] = "approved"
    found["approved_at"] = datetime.utcnow().isoformat()
    orders_db.append(found)
    # удалим из pending
    pending = [o for o in pending if o["order_id"] != order_id]
    save_json(PENDING_FILE, {"orders": pending})
    save_json(ORDERS_FILE, {"orders": orders_db})
    # уведомить пользователя
    try:
        await bot.send_message(found["user_id"], f"✅ Sizning buyurtmangiz (ID: {found['order_id']}) qabul qilindi.")
    except Exception:
        pass
    await callback.message.edit_text("✅ Zakaz qabul qilindi va saqlandi.")
    await callback.answer("Qabul qilindi.")

# ---------- Admin: отклонить заказ ----------
@dp.callback_query(lambda c: c.data.startswith("admin_reject_"))
async def admin_reject(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return await callback.answer("Siz admin emassiz!", show_alert=True)
    order_id = callback.data.split("_", 2)[2]
    pending = load_json(PENDING_FILE, {"orders": []})["orders"]
    found = None
    for o in pending:
        if o["order_id"] == order_id:
            found = o
            break
    if not found:
        return await callback.answer("Order topilmadi.", show_alert=True)
    # удалить и уведомить
    pending = [o for o in pending if o["order_id"] != order_id]
    save_json(PENDING_FILE, {"orders": pending})
    try:
        await bot.send_message(found["user_id"], f"❌ Sizning buyurtmangiz (ID: {found['order_id']}) moderator tomonidan rad etildi.")
    except Exception:
        pass
    await callback.message.edit_text("❌ Zakaz rad etildi.")
    await callback.answer("Rad etildi.")

# ---------- Admin: удалить заказ (из approved или pending) ----------
@dp.callback_query(lambda c: c.data.startswith("admin_delete_"))
async def admin_delete(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return await callback.answer("Siz admin emassiz!", show_alert=True)
    order_id = callback.data.split("_", 2)[2]
    pending = load_json(PENDING_FILE, {"orders": []})["orders"]
    orders_db = load_json(ORDERS_FILE, {"orders": []})["orders"]
    new_pending = [o for o in pending if o["order_id"] != order_id]
    new_orders = [o for o in orders_db if o["order_id"] != order_id]
    save_json(PENDING_FILE, {"orders": new_pending})
    save_json(ORDERS_FILE, {"orders": new_orders})
    await callback.message.edit_text("🗑️ Zakaz o'chirildi.")
    await callback.answer("O'chirildi.")

# ---------- Admin: статистика ----------
@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return await callback.answer("Siz admin emassiz!", show_alert=True)
    s = get_stats()
    text = (
        f"📊 Statistika:\n\n"
        f"Umumiy zakazlar (pending+approved): {s['total']}\n"
        f"✅ Tasdiqlangan: {s['approved']}\n"
        f"❌ Rad etilgan: {s['rejected']}\n"
        f"⏳ Pending: {s['pending']}\n"
    )
    await callback.message.answer(text)
    await callback.answer()

# ---------- Admin: поиск по user_id ----------
@dp.callback_query(lambda c: c.data == "admin_search_user")
async def admin_search_user(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return await callback.answer("Siz admin emassiz!", show_alert=True)
    temp_state["awaiting_search_from"][callback.from_user.id] = True
    await callback.message.answer("Qidiriladigan user_id ni kiriting (raqam):")
    await callback.answer()

# ---------- Admin: broadcast (следующее сообщение станет рассылкой) ----------
@dp.callback_query(lambda c: c.data == "admin_broadcast")
async def admin_broadcast(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return await callback.answer("Siz admin emassiz!", show_alert=True)
    temp_state["awaiting_broadcast_from"][callback.from_user.id] = True
    await callback.message.answer("Yubormoqchi bo'lgan xabar matnini kiriting — u barcha approved foydalanuvchilarga jo'natiladi.")
    await callback.answer()

# ---------- Запуск ----------
async def main():
    print("Bot started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
