import os
import json
import secrets
import string
import datetime
import threading
import subprocess
from flask import Flask
from telegram import ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ======================================================
# 🛑 CONFIGURATION - ALL LOADED FROM ENVIRONMENT VARS
# ======================================================
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
GROUP_ID = int(os.environ.get("GROUP_ID", "0"))
REPO_URL = os.environ.get("REPO_URL")  # Format: github.com/user/repo.git
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

SUPPORT_USER = "@ibenium"
STAR_LINK = "https://t.me/+POl9XjjOQtE3NTM0"
BANK_DETAILS = "🏦 **Kuda MFB**\nAcct: 2057438085\nName: Enoch Ibidapo"
CRYPTO_ADDRESS = "🪙 **USDT (TRC20):**\n`TXxnLWMD8FBPec9oSBzqtvk7yu8hQCg6Eb`"

DB_FILE = "subscribers.json"

# ======================================================
# 🌐 HEALTH CHECK SERVER (For Render Free Tier)
# ======================================================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is alive and healthy!", 200

def run_health_check():
    # Render's Port Scan looks for 10000 by default
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

# ======================================================
# 💾 DATABASE & SYNC LOGIC
# ======================================================
def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "trials": [], "all_users": {}, "codes": {}}
    with open(DB_FILE, "r") as f:
        try: return json.load(f)
        except: return {"users": {}, "trials": [], "all_users": {}, "codes": {}}

def save_db_and_sync(data):
    with open(DB_FILE, "w") as f: 
        json.dump(data, f, indent=4)
    
    # Push to GitHub so your data survives a Render restart
    if REPO_URL and GITHUB_TOKEN:
        try:
            subprocess.run(["git", "config", "user.name", "RenderBot"], check=True)
            subprocess.run(["git", "config", "user.email", "bot@render.com"], check=True)
            subprocess.run(["git", "add", DB_FILE], check=True)
            subprocess.run(["git", "commit", "-m", "Auto-sync subscribers [skip ci]"], check=True)
            # Use token for authentication
            remote_url = f"https://{GITHUB_TOKEN}@{REPO_URL}"
            subprocess.run(["git", "push", remote_url, "main"], check=True)
            print("✅ Database synced to GitHub.")
        except Exception as e:
            print(f"❌ Git Sync Failed: {e}")

# ======================================================
# 🤖 BOT HANDLERS
# ======================================================
def main_menu_keyboard(user_id):
    keyboard = [['💳 Join Premium', '📊 My Status'], ['🎁 24h Free Trial', '🎟 Redeem Code'], ['🆘 Support']]
    if user_id == ADMIN_ID: keyboard.append(['🛠 Admin: Gen Code'])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    db = load_db()
    if user_id not in db["all_users"]:
        db["all_users"][user_id] = {"join": str(datetime.date.today())}
        save_db_and_sync(db)
    await update.message.reply_text("🚀 **2Aad Premium Signals**\nUse the menu below to navigate:", 
                                   reply_markup=main_menu_keyboard(update.effective_user.id), 
                                   parse_mode='Markdown')

async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    db = load_db()
    if user_id not in db["users"]: return await update.message.reply_text("❌ **No active plan found.**", parse_mode='Markdown')
    try:
        expiry = datetime.datetime.strptime(db["users"][user_id], "%Y-%m-%d %H:%M:%S")
        rem = expiry - datetime.datetime.now()
        if rem.total_seconds() <= 0: return await update.message.reply_text("⚠️ **Your plan has expired.**", parse_mode='Markdown')
        await update.message.reply_text(f"📊 **Plan Status:** Active\n⏳ **Time Left:** {rem.days}d {rem.seconds//3600}h\n📅 **Expiry:** {expiry.strftime('%Y-%m-%d')}", parse_mode='Markdown')
    except: await update.message.reply_text("❌ Status error. Contact Admin.")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data in ['pay_bank', 'pay_crypto']:
        context.user_data['method'] = query.data
        kb = [[InlineKeyboardButton("1 Day ($2)", callback_data='dur_1')],
              [InlineKeyboardButton("7 Days ($10)", callback_data='dur_7')],
              [InlineKeyboardButton("30 Days ($35)", callback_data='dur_30')]]
        await query.message.edit_text("⏳ **Select Duration:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif query.data.startswith('dur_'):
        days = query.data.split('_')[1]
        context.user_data['choice_days'] = days
        method = context.user_data.get('method')
        if method == 'pay_bank':
            context.user_data['state'] = 'WAIT_BANK'
            await query.message.reply_text(f"{BANK_DETAILS}\n\n📸 Upload receipt for **{days}D** plan:", parse_mode='Markdown')
        else:
            context.user_data['state'] = 'WAIT_CRYPTO'
            await query.message.reply_text(f"{CRYPTO_ADDRESS}\n\n🔗 Paste TXID for **{days}D** plan:", parse_mode='Markdown')

    elif query.data.startswith('approve_'):
        _, uid, d = query.data.split('_')
        db = load_db()
        db["users"][uid] = (datetime.datetime.now() + datetime.timedelta(days=int(d))).strftime("%Y-%m-%d %H:%M:%S")
        save_db_and_sync(db)
        link = await context.bot.create_chat_invite_link(GROUP_ID, member_limit=1)
        await context.bot.send_message(uid, f"🎉 **PAYMENT CONFIRMED!**\nJoin: {link.invite_link}", parse_mode='Markdown')
        if query.message.caption: await query.message.edit_caption(caption=f"✅ Approved User {uid}")
        else: await query.message.edit_text(text=f"✅ Approved User {uid}")

async def message_processor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = str(update.effective_user.id)
    state = context.user_data.get('state')

    if text == '📊 My Status': await handle_status(update, context)
    elif text == '💳 Join Premium':
        kb = [[InlineKeyboardButton("⭐ Stars", url=STAR_LINK)],
              [InlineKeyboardButton("🏦 Bank", callback_data='pay_bank')],
              [InlineKeyboardButton("🪙 Crypto", callback_data='pay_crypto')]]
        await update.message.reply_text("💎 **Choose Payment:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    elif text == '🎁 24h Free Trial':
        db = load_db()
        if user_id in db["trials"]: return await update.message.reply_text("❌ Trial used.", parse_mode='Markdown')
        db["users"][user_id] = (datetime.datetime.now() + datetime.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        db["trials"].append(user_id); save_db_and_sync(db)
        link = await context.bot.create_chat_invite_link(GROUP_ID, member_limit=1)
        await update.message.reply_text(f"🎁 **Trial Active!** Join: {link.invite_link}", parse_mode='Markdown')

# ======================================================
# 🚀 MAIN LAUNCHER
# ======================================================
def main():
    # 1. Start Flask in background thread to satisfy Render's port check
    threading.Thread(target=run_health_check, daemon=True).start()

    # 2. Start the Telegram Bot
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.ALL, message_processor))
    
    print("🚀 Bot starting with Health Check on Port 10000...")
    app.run_polling()

if __name__ == '__main__': 
    main()
