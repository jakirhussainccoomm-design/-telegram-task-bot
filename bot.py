
    import os
import time
import threading
import sqlite3
import random
import logging
from datetime import datetime, timedelta
import pyotp
import requests
import telebot
from telebot import types
import pandas as pd
from flask import Flask

# ==============================
# CONFIGURATION
# ==============================
BOT_TOKEN = "8969651007:AAHOE3jQNIjZKefk51rJg4yCz6WPPYYP4t4"
ADMIN_ID = 7942994648
DB_NAME = "taskbot.db"

# গুগল শিটের ওয়েব অ্যাপ ইউআরএল (প্রয়ोजन হলে বসাবেন)
GOOGLE_SHEET_URL = "আপনার_ওয়েব_অ্যাপ_লিংকটি_এখানে_বসান"

# ফেসবুক ও ইনস্টাগ্রামের পাসওয়ার্ড প্রিফিক্স
FB_IG_PREFIX = "Jihad" 

def get_fb_ig_password():
    bd_time = datetime.utcnow() + timedelta(hours=6)
    if bd_time.hour >= 21:
        target_date = bd_time + timedelta(days=1)
    else:
        target_date = bd_time
    date_str = target_date.strftime("%d") 
    return f"{FB_IG_PREFIX}@{date_str}"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
logging.basicConfig(level=logging.INFO)

user_states = {}
admin_states = {}  # অ্যাডমিন স্টেট ট্র্যাক করার জন্য

# ==============================
# GOOGLE SHEET FUNCTION
# ==============================
def save_to_google_sheet(task_type, user_id, f1, f2, f3=""):
    try:
        payload = {
            "task_type": task_type,
            "user_id": str(user_id),
            "field1": str(f1),
            "field2": str(f2),
            "field3": str(f3)
        }
        requests.post(GOOGLE_SHEET_URL, json=payload, timeout=5)
    except Exception as e:
        print(f"Sheet Error: {e}")

# ==============================
# RENDER-এর জন্য FLASK সার্ভার সেটআপ (24/7 Running)
# ==============================
app = Flask('')

@app.route('/')
def home():
    return "Bot is active and running 24/7!"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

# ==============================
# KEYBOARDS
# ==============================
def main_reply_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📖কাজ ▸", "ব্যালেন্স💰")
    markup.row("📥টাকা উত্তোলন", "My Referrals🎁")
    markup.row("আমি নতুন🥰", "সাপোর্ট📞")
    if user_id == ADMIN_ID:
        markup.row("👑 Admin Panel")
    return markup

def task_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📸 ইনস্টাگرام কাজ >")
    markup.row("📘 Facebook কাজ")
    markup.row("❌ বাতিল")
    return markup

def withdraw_method_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🪙 USDT (BEP20) -> সর্বনিম্ন: ৩০(-৫)")
    markup.row("⬅️ ফিরে যান")
    return markup

# ==============================
# DATA BANK & VALIDATIONS
# ==============================
IG_FIRST_NAMES = ["john", "michael", "david", "james", "robert", "william", "joseph", "thomas", "charles", "daniel", "tanvir", "sakib", "rahim"]
IG_LAST_NAMES = ["smith", "brown", "wilson", "taylor", "johnson", "davis", "miller", "khan", "rahman", "hasan"]

def generate_human_ig_username():
    first = random.choice(IG_FIRST_NAMES)
    last = random.choice(IG_LAST_NAMES)
    num = random.randint(100, 9999)
    return f"{first}{last}{num}"

FB_FIRST_NAMES = ["Md", "Md", "Md", "Tanvir", "Shakil", "Rakib", "Arif", "Faisal", "Kamrul", "Shahin", "Naim", "Alamin"]
FB_LAST_NAMES = ["Khan", "Khan", "Khan", "Rahman", "Hasan", "Ahmed", "Hossain", "Islam", "Chowdhury", "Sheikh", "Uddin", "Ali"]

def is_valid_fb_uid(uid_str):
    uid_str = uid_str.strip()
    return uid_str.isdigit() and len(uid_str) >= 6

def is_valid_fb_cookie(cookie_str):
    cookie_str = cookie_str.strip()
    return "c_user" in cookie_str or "xs=" in cookie_str or ("name" in cookie_str and "value" in cookie_str)

def delete_credentials_msg(chat_id, user_id):
    if user_id in user_states and "cred_msg_id" in user_states[user_id]:
        try:
            bot.delete_message(chat_id, user_states[user_id]["cred_msg_id"])
        except Exception:
            pass

# ==============================
# DATABASE SETUP
# ==============================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0,
            total_income REAL DEFAULT 0,
            referral_income REAL DEFAULT 0,
            referred_by INTEGER
        )
    """)
    try:
        cur.execute("ALTER TABLE users ADD COLUMN referral_income REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_type TEXT,
            proof_data TEXT,
            reward REAL,
            status TEXT DEFAULT 'pending'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            net_amount REAL,
            method TEXT,
            address TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row

def register_user(user_id, username, ref_id=None):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not cur.fetchone():
        referred_by = ref_id if ref_id and ref_id != user_id else None
        cur.execute("INSERT INTO users (user_id, username, referred_by) VALUES (?, ?, ?)",
                    (user_id, username or "", referred_by))
        conn.commit()
    conn.close()

# ==============================
# START COMMAND
# ==============================
@bot.message_handler(commands=["start"])
def start_cmd(message):
    args = message.text.split()
    ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    
    register_user(message.from_user.id, message.from_user.username, ref_id)
    bot.send_message(
        message.chat.id,
        f"<b>🤖 PREMIUM TASK & WORK BOT</b>\n\nস্বাগতম <b>{message.from_user.first_name}</b>!\nনিচের মেনু থেকে আপনার কাঙ্ক্ষিত অপশন বেছে নিন।",
        reply_markup=main_reply_keyboard(message.from_user.id)
    )

# ==============================
# TEXT MESSAGE HANDLERS
# ==============================
@bot.message_handler(func=lambda message: True)
def handle_text_inputs(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text.strip()

    if user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == "waiting_for_broadcast":
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users")
        users = cur.fetchall()
        conn.close()

        success_count = 0
        for u in users:
            try:
                bot.send_message(u[0], text)
                success_count += 1
                time.sleep(0.05)
            except Exception:
                pass

        admin_states[ADMIN_ID] = "none"
        bot.send_message(chat_id, f"✅ <b>ব্রডকাস্ট সফল!</b> মোট {success_count} জন ইউজারের কাছে মেসেজ পাঠানো হয়েছে।", reply_markup=main_reply_keyboard(user_id))
        return

    if text == "❌ বাতিল" or text == "⬅️ ফিরে যান":
        if user_id in user_states:
            delete_credentials_msg(chat_id, user_id)
            del user_states[user_id]
        if user_id == ADMIN_ID:
            admin_states[ADMIN_ID] = "none"
        bot.send_message(chat_id, "❌ মূল মেনুতে ফিরে এসেছেন।", reply_markup=main_reply_keyboard(user_id))
        return

    if user_id == ADMIN_ID and text == "👑 Admin Panel":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📂 টাস্ক ফাইল আপলোড", callback_data="upload_task_file"),
            types.InlineKeyboardButton("📊 স্ট্যাটিস্টিক্স", callback_data="show_stats"),
            types.InlineKeyboardButton("📢 ব্রডকাস্ট মেসেজ", callback_data="broadcast_msg")
        )
        bot.send_message(
            chat_id, 
            "👑 <b>অ্যাডমিন প্যানেল</b>\n\nনিচের অপশনগুলো থেকে আপনার প্রয়োজনীয় কাজ সিলেক্ট করুন:", 
            reply_markup=markup
        )
        return

    if user_id in user_states and "step" in user_states[user_id]:
        state = user_states[user_id].get("step")

        if state == "ig_wait_2fa_key":
            try:
                clean_secret = text.replace(" ", "")
                totp = pyotp.TOTP(clean_secret)
                otp_code = totp.now()
                user_states[user_id]["secret"] = clean_secret
                
                keyboard = types.InlineKeyboardMarkup(row_width=1)
                keyboard.add(
                    types.InlineKeyboardButton("✅ অ্যাকাউন্ট খোলা শেষ", callback_data="ig_finish"),
                    types.InlineKeyboardButton("❌ বাতিল", callback_data="cancel_task")
                )
                bot.send_message(
                    chat_id,
                    f"🔑 <b>অটো জেনারেটেড ২এফএ কোড:</b> <code>{otp_code}</code>\n\nকোডটি নিয়ে ইনস্টাগ্রামে ব্যবহার করুন। কাজ শেষ হলে নিচের বাটনে চাপ দিন:",
                    reply_markup=keyboard
                )
                return
            except Exception:
                bot.send_message(chat_id, "⚠️ সঠিক ২এফএ সিক্রেট কী দিন।")
                return

        elif state == "fb_wait_uid":
            if not is_valid_fb_uid(text):
                bot.send_message(chat_id, "❌ <b>ইউআইডিটি সঠিক নয়!</b> শুধুমাত্র সংখ্যা দিয়ে সঠিক UID দিন:")
                return
            user_states[user_id]["uid"] = text
            user_states[user_id]["step"] = "fb_wait_cookie"
            
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                types.InlineKeyboardButton("🍪 কুকিস সেন্ড করুন", callback_data="fb_click_cookie_btn"),
                types.InlineKeyboardButton("❌ বাতিল", callback_data="cancel_task")
            )
            bot.send_message(chat_id, "✅ UID গ্রহণ করা হয়েছে! এখন কুকিস পাঠান:", reply_markup=keyboard)
            return

        elif state == "fb_wait_cookie":
            if not is_valid_fb_cookie(text):
                bot.send_message(chat_id, "❌ <b>কুকিটি সঠিক নয়!</b> অরিজিনাল কুকি দিন:")
                return
            user_states[user_id]["cookie"] = text
            user_states[user_id]["step"] = "none"

            keyboard = types.InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                types.InlineKeyboardButton("✅ অ্যাকাউন্ট খোলা শেষ", callback_data="fb_finish"),
                types.InlineKeyboardButton("❌ বাতিল", callback_data="cancel_task")
            )
            bot.send_message(chat_id, "✅ কুকিস গ্রহণ করা হয়েছে! কাজ শেষে নিচের বাটনে ক্লিক করুন:", reply_markup=keyboard)
            return

        elif state == "withdraw_address":
            user_states[user_id]["address"] = text
            user_states[user_id]["step"] = "withdraw_amount"
            bot.send_message(chat_id, "💰 <b>কত টাকা উইথড্র করতে চান তা সংখ্যায় লিখুন (মিনিমাম ৩০ টাকা):</b>", reply_markup=withdraw_method_keyboard())
            return

        elif state == "withdraw_amount":
            if not text.isdigit():
                bot.send_message(chat_id, "❌ শুধুমাত্র সঠিক সংখ্যা লিখুন।", reply_markup=withdraw_method_keyboard())
                return
            
            amount = float(text)
            min_amount = 30
            fee = 5.0

            if amount < min_amount:
                bot.send_message(chat_id, f"❌ সর্বনিম্ন উইথড্র {min_amount} টাকা।", reply_markup=withdraw_method_keyboard())
                return

            user_data = get_user(user_id)
            current_balance = user_data[2] if user_data else 0.0

            if current_balance < amount:
                bot.send_message(
                    chat_id, 
                    f"❌ <b>আপনার পর্যাপ্ত ব্যালেন্স নেই!</b>\n\n💵 বর্তমান ব্যালেন্স: <b>{current_balance:.2f} BDT</b>\n💸 উইথড্র করতে চেয়েছেন: <b>{amount} BDT</b>", 
                    reply_markup=withdraw_method_keyboard()
                )
                return

            address = user_states[user_id].get("address")
            method = user_states[user_id].get("method", "USDT (BEP20)")
            net_amount = amount - fee

            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, user_id))
            cur.execute("INSERT INTO withdrawals (user_id, amount, net_amount, method, address) VALUES (?, ?, ?, ?, ?)",
                        (user_id, amount, net_amount, method, address))
            w_id = cur.lastrowid
            conn.commit()
            conn.close()

            bot.send_message(
                chat_id,
                f"⏳ <b>আপনার উইথড্র রিকুয়েস্টটি পেন্ডিংয়ে রয়েছে!</b>\n\n💳 মাধ্যম: {method}\n💰 পরিমাণ: {amount} BDT\n⛽ ফি কেটে পাবেন: {net_amount} BDT",
                reply_markup=main_reply_keyboard(user_id)
            )
            
            bot.send_message(
                ADMIN_ID,
                f"🚨 <b>নতুন উইথড্র রিকুয়েস্ট #{w_id}</b>\nUser: <code>{user_id}</code>\nAmount: {amount} BDT\nNet: {net_amount} BDT\nAddress: <code>{address}</code>\n\nঅ্যাপ্রুভ করতে: `/approve_w {w_id}`"
            )
            del user_states[user_id]
            return

    if text == "📖কাজ ▸":
        bot.send_message(chat_id, "👇 <b>নিচের ক্যাটাগরি থেকে আপনার পছন্দের কাজটি সিলেক্ট করুন:</b>", reply_markup=task_reply_keyboard())

    elif text == "📸 ইনস্টাگرام কাজ >":
        username = generate_human_ig_username()
        password = get_fb_ig_password()
        msg = f"📸 <b>INSTAGRAM ACCOUNT TASK</b> (রিওয়ার্ড: ৪.১০ টাকা)\n\n👤 <b>Username:</b> <code>{username}</code>\n🔑 <b>Password:</b> <code>{password}</code>"
        
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            types.InlineKeyboardButton("🔑 ২এফএ কী সেট করুন", callback_data="ig_click_2fa_btn"),
            types.InlineKeyboardButton("❌ বাতিল", callback_data="cancel_task")
        )
        sent_msg = bot.send_message(chat_id, msg, reply_markup=keyboard)
        user_states[user_id] = {"step": "ig_wait_2fa_key", "username": username, "password": password, "reward": 4.10, "cred_msg_id": sent_msg.message_id}

    elif text == "📘 Facebook কাজ":
        f_name = random.choice(FB_FIRST_NAMES)
        l_name = random.choice(FB_LAST_NAMES)
        password = get_fb_ig_password()
        msg = f"📘 <b>FACEBOOK ACCOUNT TASK</b> (রিওয়ার্ড: ৫.৫০ টাকা)\n\n👤 <b>First Name:</b> <code>{f_name}</code>\n👤 <b>Last Name:</b> <code>{l_name}</code>\n🔑 <b>Password:</b> <code>{password}</code>"
        
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            types.InlineKeyboardButton("🆔 ইউআইডি সেন্ড করুন", callback_data="fb_click_uid_btn"),
            types.InlineKeyboardButton("❌ বাতিল", callback_data="cancel_task")
        )
        sent_msg = bot.send_message(chat_id, msg, reply_markup=keyboard)
        user_states[user_id] = {"step": "fb_wait_uid", "f_name": f_name, "l_name": l_name, "password": password, "reward": 5.50, "cred_msg_id": sent_msg.message_id}

    elif text == "ব্যালেন্স💰":
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("SELECT balance, total_income FROM users WHERE user_id=?", (user_id,))
        user_row = cur.fetchone()
        balance = user_row[0] if user_row else 0.0
        total_income = user_row[1] if user_row else 0.0

        cur.execute("SELECT SUM(amount) FROM withdrawals WHERE user_id=? AND status='pending'", (user_id,))
        pend_w_row = cur.fetchone()
        pending_withdraw = pend_w_row[0] if pend_w_row and pend_w_row[0] else 0.0

        cur.execute("SELECT COUNT(*) FROM tasks WHERE user_id=? AND status='approved'", (user_id,))
        success_tasks = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM tasks WHERE user_id=? AND status='pending'", (user_id,))
        pending_tasks = cur.fetchone()[0]
        conn.close()

        msg = f"""
💵 <b>আপনার ব্যালেন্স</b>
━━━━━━━━━━━━━━━━━━━━━━
💵 <b>ব্যালেন্স:</b> {balance:.2f} BDT
💸 <b>পেন্ডিং (উইথড্র):</b> {pending_withdraw:.2f} BDT
💰 <b>Total Income:</b> {total_income:.2f} BDT
━━━━━━━━━━━━━━━━━━━━━━
✅ <b>সম্পন্ন কাজ:</b> {success_tasks} টি
⏳ <b>রিভিউতে আছে:</b> {pending_tasks} টি
"""
        bot.send_message(chat_id, msg, reply_markup=main_reply_keyboard(user_id))

    elif text == "📥টাকা উত্তোলন":
        user_states[user_id] = {"step": "select_withdraw_method"}
        bot.send_message(chat_id, "💰 <b>টাকা তোলার মাধ্যম সিলেক্ট করুন:</b>", reply_markup=withdraw_method_keyboard())

    elif "USDT" in text:
        if user_id in user_states and user_states[user_id].get("step") == "select_withdraw_method":
            user_states[user_id]["method"] = text
            user_states[user_id]["step"] = "withdraw_address"
            bot.send_message(chat_id, f"💸 আপনি সিলেক্ট করেছেন: <b>{text}</b>\n\n📍 <b>আপনার সঠিক USDT (BEP20) অ্যাড্রেসটি এখানে প্রদান করুন:</b>", reply_markup=withdraw_method_keyboard())
        else:
            bot.send_message(chat_id, "দয়া করে নিচের মেনু থেকে সঠিক অপশনটি বেছে নিন:", reply_markup=main_reply_keyboard(user_id))

    elif text == "My Referrals🎁":
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (user_id,))
        total_refer = cur.fetchone()[0]
        cur.execute("SELECT referral_income FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        total_refer_income = row[0] if row and row[0] else 0.0
        conn.close()

        me = bot.get_me()
        link = f"https://t.me/{me.username}?start={user_id}"
        
        msg = f"""🎁 <b>My Referrals</b>
👤 <b>Total Refer:</b> {total_refer}
😃 <b>Total Refer Income:</b> {total_refer_income:.2f} BDT
🔗 <b>আপনার রেফার লিংক:</b>
<code>{link}</code>

ℹ️ আপনি আপনার প্রতিটি রেফারেলের সম্পূর্ণ করা কাজ থেকে আয়ের 10% কমিশন পাবেন।"""
        bot.send_message(chat_id, msg, reply_markup=main_reply_keyboard(user_id))

    elif text == "সাপোর্ট📞":
        msg = """📞 <b>গ্রাহক সেবা কেন্দ্র</b>
━━━━━━━━━━━━━━━━━━━━━━
সম্মানিত মেম্বার, আপনার যেকোনো সমস্যা বা জিজ্ঞাসার জন্য আমাদের সাপোর্ট টিমের সাথে যোগাযোগ করুন।"""
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        keyboard.add(types.InlineKeyboardButton("💬 সাপোর্ট টিমের সাথে কথা বলুন", url="https://t.me/Jihadfrelancer1"))
        keyboard.add(types.InlineKeyboardButton("📢 আমাদের অফিশিয়াল গ্রুপ", url="https://t.me/crazyteam1123"))
        bot.send_message(chat_id, msg, reply_markup=keyboard)

    elif text == "আমি নতুন🥰":
        new_user_msg = """👋 <b>স্বাগতম নতুন মেম্বার!</b>
আমাদের এই বটের মাধ্যমে খুব সহজেই বিভিন্ন সোশ্যাল মিডিয়া টাস্ক সম্পন্ন করে আয় করতে পারবেন। কাজ শুরু করতে <b>📖কাজ ▸</b> অপশনে ক্লিক করুন।"""
        bot.send_message(chat_id, new_user_msg, reply_markup=main_reply_keyboard(user_id))

    else:
        bot.send_message(chat_id, "দয়া করে নিচের মেনু থেকে সঠিক অপশনটি বেছে নিন:", reply_markup=main_reply_keyboard(user_id))

# ==============================
# CALLBACK HANDLERS
# ==============================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    if user_id == ADMIN_ID:
        if call.data == "upload_task_file":
            admin_states[ADMIN_ID] = "waiting_for_file"
            bot.answer_callback_query(call.id)
            bot.send_message(chat_id, "📂 অনুগ্রহ করে আপনার চেক করা এক্সেল ফাইলটি (.xlsx) এখন এই বটে পাঠিয়ে দিন।")
            return

        elif call.data == "show_stats":
            bot.answer_callback_query(call.id)
            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            t_users = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM tasks WHERE status='approved'")
            a_tasks = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'")
            p_tasks = cur.fetchone()[0]
            cur.execute("SELECT SUM(amount) FROM withdrawals")
            t_withdraws = cur.fetchone()[0] or 0.0
            conn.close()

            stats_msg = f"""
📊 <b>অ্যাডমিন স্ট্যাটিস্টিক্স</b>
━━━━━━━━━━━━━━━━━━━━━━
👥 মোট ইউজার: <b>{t_users} জন</b>
✅ সফল টাস্ক: <b>{a_tasks} টি</b>
⏳ পেন্ডিং টাস্ক: <b>{p_tasks} টি</b>
💸 মোট উইথড্র: <b>{t_withdraws:.2f} BDT</b>
━━━━━━━━━━━━━━━━━━━━━━
"""
            bot.send_message(chat_id, stats_msg)
            return

        elif call.data == "broadcast_msg":
            admin_states[ADMIN_ID] = "waiting_for_broadcast"
            bot.answer_callback_query(call.id)
            bot.send_message(chat_id, "📢 সব ইউজারের কাছে পাঠানোর জন্য আপনার মেসেজটি লিখে পাঠান:")
            return

    if call.data == "ig_click_2fa_btn":
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "📥 আপনার <b>2FA Secret Key</b> টি মেসেজ বক্সে পাঠান:")

    elif call.data == "ig_finish":
        if user_id not in user_states or "secret" not in user_states[user_id]:
            bot.answer_callback_query(call.id, "❌ কোনো ২এফএ ডাটা পাওয়া যায়নি!", show_alert=True)
            return

        u_data = user_states[user_id]
        proof = f"IG: {u_data['username']} | Secret: {u_data['secret']}"

        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("INSERT INTO tasks (user_id, task_type, proof_data, reward) VALUES (?, 'instagram', ?, ?)",
                    (user_id, proof, u_data['reward']))
        conn.commit()
        conn.close()

        save_to_google_sheet("Instagram", user_id, u_data['username'], u_data['password'], u_data['secret'])
        delete_credentials_msg(chat_id, user_id)
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "🎉 <b>আপনার ইনস্টাگرام টাস্কটি সফলভাবে জমা নেওয়া হয়েছে!</b>", reply_markup=main_reply_keyboard(user_id))
        if user_id in user_states:
            del user_states[user_id]

    elif call.data == "fb_click_uid_btn":
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "📥 আপনার Facebook <b>UID</b> টি মেসেজ করে পাঠান:")

    elif call.data == "fb_click_cookie_btn":
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "📥 এবার অ্যাকাউন্টটির <b>Cookie</b> টি পেস্ট করে পাঠান:")

    elif call.data == "fb_finish":
        if user_id not in user_states or "cookie" not in user_states[user_id]:
            bot.answer_callback_query(call.id, "❌ কোনো তথ্য পাওয়া যায়নি!", show_alert=True)
            return

        u_data = user_states[user_id]
        proof = f"FB Name: {u_data['f_name']} {u_data['l_name']} | UID: {u_data.get('uid')} | Cookie: {u_data['cookie']}"

        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("INSERT INTO tasks (user_id, task_type, proof_data, reward) VALUES (?, 'facebook', ?, ?)",
                    (user_id, proof, u_data['reward']))
        conn.commit()
        conn.close()

        save_to_google_sheet("Facebook", user_id, u_data.get('uid'), u_data['password'], u_data['cookie'])
        delete_credentials_msg(chat_id, user_id)
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "🎉 <b>ফেসবুক টাস্কটি সফলভাবে জমা নেওয়া হয়েছে!</b>", reply_markup=main_reply_keyboard(user_id))
        if user_id in user_states:
            del user_states[user_id]

    elif call.data == "cancel_task":
        delete_credentials_msg(chat_id, user_id)
        if user_id in user_states:
            del user_states[user_id]
        bot.answer_callback_query(call.id, "টাস্ক বাতিল করা হয়েছে।")
        bot.send_message(chat_id, "❌ <b>টাস্কটি বাতিল করা হয়েছে।</b>", reply_markup=main_reply_keyboard(user_id))

# ==============================
# DOCUMENT HANDLER (ADMIN TASK FILE PROCESSING)
# ==============================
@bot.message_handler(content_types=['document'])
def handle_documents(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        file_path = "checked_tasks.xlsx"
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        bot.reply_to(message, "🔄 ফাইল প্রসেসিং শুরু হয়েছে...")
        
        df = pd.read_excel(file_path)
        success_count = 0
        reject_count = 0

        for _, row in df.iterrows():
            u_id = int(row['User_ID'])
            status = str(row['Status']).strip().lower()
            
            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            
            if status in ['complete', 'completed']:
                cur.execute("SELECT id, reward FROM tasks WHERE user_id=? AND status='pending' ORDER BY id ASC LIMIT 1", (u_id,))
                task = cur.fetchone()
                if task:
                    t_id, reward = task[0], task[1]
                    cur.execute("UPDATE tasks SET status='approved' WHERE id=?", (t_id,))
                    cur.execute("UPDATE users SET balance = balance + ?, total_income = total_income + ? WHERE user_id=?", (reward, reward, u_id))
                    
                    cur.execute("SELECT referred_by FROM users WHERE user_id=?", (u_id,))
                    ref_row = cur.fetchone()
                    if ref_row and ref_row[0]:
                        ref_id = ref_row[0]
                        ref_bonus = reward * 0.10
                        cur.execute("UPDATE users SET balance = balance + ?, total_income = total_income + ?, referral_income = referral_income + ? WHERE user_id=?", (ref_bonus, ref_bonus, ref_bonus, ref_id))
                        try:
                            bot.send_message(ref_id, f"🎉 <b>রেফারেল বোনাস!</b> আপনার ১০% কমিশন (<b>+{ref_bonus:.2f} BDT</b>) যোগ হয়েছে।")
                        except Exception:
                            pass
                    
                    conn.commit()
                    try:
                        bot.send_message(u_id, f"🎉 আপনার কাজটি সফলভাবে অনুমোদিত হয়েছে এবং <b>{reward:.2f} BDT</b> আপনার ব্যালেন্সে যোগ হয়েছে!")
                        success_count += 1
                    except Exception:
                        pass
            elif status in ['reject', 'rejected']:
                cur.execute("SELECT id FROM tasks WHERE user_id=? AND status='pending' ORDER BY id ASC LIMIT 1", (u_id,))
                task = cur.fetchone()
                if task:
                    t_id = task[0]
                    cur.execute("UPDATE tasks SET status='rejected' WHERE id=?", (t_id,))
                    conn.commit()
                    try:
                        bot.send_message(u_id, f"❌ দুঃখিত, আপনার জমাকৃত কাজটি বাতিল (Reject) করা হয়েছে।")
                        reject_count += 1
                    except Exception:
                        pass
            conn.close()

        admin_states[ADMIN_ID] = "none"
        bot.send_message(ADMIN_ID, f"✅ <b>রিপোর্ট প্রসেসিং সম্পন্ন!</b>\n\n✅ সফল: {success_count} টি\n❌ রিজেক্ট: {reject_count} টি")

    except Exception as e:
        bot.reply_to(message, f"❌ ত্রুটি দেখা দিয়েছে: {str(e)}")

# ==============================
# ADMIN COMMANDS
# ==============================
@bot.message_handler(commands=["admin"])
def admin_panel_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📂 টাস্ক ফাইল আপলোড", callback_data="upload_task_file"),
        types.InlineKeyboardButton("📊 স্ট্যাটিস্টিক্স", callback_data="show_stats"),
        types.InlineKeyboardButton("📢 ব্রডকাস্ট মেসেজ", callback_data="broadcast_msg")
    )
    
    bot.send_message(
        ADMIN_ID, 
        "👑 <b>অ্যাডমিন প্যানেল</b>\n\nনিচের অপশনগুলো থেকে আপনার প্রয়োজনীয় কাজ সিলেক্ট করুন:", 
        reply_markup=markup
    )

@bot.message_handler(commands=["approve_w"])
def approve_withdraw_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        bot.send_message(ADMIN_ID, "উপায়: `/approve_w <withdraw_id>`")
        return

    w_id = int(args[1])
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT user_id, net_amount, method, address, status FROM withdrawals WHERE id=?", (w_id,))
    w_data = cur.fetchone()

    if not w_data or w_data[4] != 'pending':
        bot.send_message(ADMIN_ID, "❌ উইথড্র ডাটা পাওয়া যায়নি বা ইতোমধ্যে অ্যাপ্রুভড।")
        conn.close()
        return

    u_id, net_amount, method, address = w_data[0], w_data[1], w_data[2], w_data[3]
    cur.execute("UPDATE withdrawals SET status='approved' WHERE id=?", (w_id,))
    conn.commit()
    conn.close()

    bot.send_message(ADMIN_ID, f"✅ Withdraw #{w_id} Confirmed!")
    try:
        bot.send_message(
            u_id,
            f"🎉 <b>আপনার উইথড্রটি সাকসেস করা হয়েছে!</b>\n\nমাধ্যম: {method}\nআপনার <b>{net_amount:.2f} BDT</b> সফলভাবে পাঠানো হয়েছে:\n📍 <code>{address}</code>"
        )
    except Exception:
        pass

# ==============================
# MAIN LOOP (FLASK + TELEGRAM BOT)
# ==============================
if __name__ == "__main__":
    init_db()
    
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    print("========================================")
    print("🤖 ADMIN PANEL & TASK BOT ARE RUNNING")
    print("========================================")
    
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)
