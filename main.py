import os
import json
import datetime
import threading
import asyncio
import subprocess
from flask import Flask, request
from telegram import ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ======================================================
# 🛑 CONFIGURATION
# ======================================================
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
GROUP_ID = int(os.environ.get("GROUP_ID", "0"))
REPO_URL = os.environ.get("REPO_URL")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# Crypto Addresses
USDT_ADDR = os.environ.get("USDT_TRC20")
SOL_ADDR = "FAiYeTLfRH325KxKa5D8wAoQ7QvPCauAokWT4cx9aMtT"
TON_ADDR = "UQC2Uldo7XpyI2djwk_dMdY3OYSgwKWTvqFYZcC14piBQsUc"

DB_FILE = "subscribers.json"

# ======================================================
# 🌐 FLASK & DB LOGIC (Same as before)
# ======================================================
web_app = Flask(__name__)
bot_app = None 

@web_app.route('/')
def home(): return "Bot is alive!", 200

@web_app.route('/webhook', methods=['POST'])
async def tradingview_webhook():
    data = request.json
    msg = (f"🔔 **NEW SIGNAL: {data.get('ticker')}**\n"
           f"📈 **Action:** {data.get('action', 'Signal').upper()}\n"
           f"💎 **Cluster:** {data.get('cluster')}/5\n"
           f"💰 **Price:** {data.get('price')}\n"
           f"⚡ *2Aad Ribbon Advanced*")
    await bot_app.bot.send_message(chat_id=GROUP_ID, text=msg, parse_mode='Markdown')
    return "OK", 200

def run_flask():
    web_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def load_db():
    if not os.path.exists(DB_FILE): return {"users": {}, "trials": [], "all_users": {}}
    with open(DB_FILE, "r") as f: return json.load(f)

def save_db_and_sync(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)
    if REPO_URL and GITHUB_TOKEN:
        try:
            subprocess.run(["git", "add", DB_FILE], check=True)
            subprocess.run(["git", "commit", "-m", "Sync DB"], check=True)
            subprocess.run(["git", "push", f"https://{GITHUB_TOKEN}@{REPO_URL}", "main"], check=True)
        except: pass

# ======================================================
# 🤖 BOT HANDLERS
# ======================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = load_db()
    if str(user_id) not in db["all_users"]:
        db["all_users"][str(user_id)] = {"join": str(datetime.date.today())}
        save_db_and_sync(db)
    
    kb = [['💳 Join Premium', '📊 My Status'], ['🎁 24h Free Trial'], ['📞 Support']]
    if user_id == ADMIN_ID:
        kb.append(['🛠 Admin: Broadcast']) # Added Broadcast Button
    
    await update.message.reply_text("🚀 **2Aad Premium Trading Signals**", 
                                   reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = str(update.effective_user.id)
    state = context.user_data.get('state')

    # --- Handle Admin Broadcast Flow ---
    if text == '🛠 Admin: Broadcast' and int(user_id) == ADMIN_ID:
        context.user_data['state'] = 'WAITING_FOR_BROADCAST'
        return await update.message.reply_text("📢 **Broadcast Mode Active**\n\nPlease type the message you want to send to ALL users.\n\nType `cancel` to stop.")

    if state == 'WAITING_FOR_BROADCAST':
        if text.lower() == 'cancel':
            context.user_data['state'] = None
            return await update.message.reply_text("❌ Broadcast cancelled.")
        
        context.user_data['state'] = None # Reset state
        db = load_db()
        all_users = db.get("all_users", {}).keys()
        count = 0
        for uid in all_users:
            try:
                await context.bot.send_message(chat_id=uid, text=f"📢 **ANNOUNCEMENT**\n\n{text}", parse_mode='Markdown')
                count += 1
                await asyncio.sleep(0.05)
            except: continue
        return await update.message.reply_text(f"✅ Broadcast sent to {count} users.")

    # --- Regular Menu Options ---
    if text == '📞 Support':
        await update.message.reply_text("💬 Need help? Contact our support: @ibenium")

    elif text == '💳 Join Premium':
        kb = [[InlineKeyboardButton("🪙 USDT (TRC20)", callback_data='p_usdt')],
              [InlineKeyboardButton("☀️ Solana (SOL)", callback_data='p_sol')],
              [InlineKeyboardButton("💎 TON", callback_data='p_ton')]]
        await update.message.reply_text("💎 **Select Crypto Method:**", reply_markup=InlineKeyboardMarkup(kb))

    elif text == '🎁 24h Free Trial':
        db = load_db()
        if user_id in db["trials"]: return await update.message.reply_text("❌ Trial already used.")
        db["users"][user_id] = (datetime.datetime.now() + datetime.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        db["trials"].append(user_id); save_db_and_sync(db)
        link = await context.bot.create_chat_invite_link(GROUP_ID, member_limit=1)
        await update.message.reply_text(f"🎁 **Trial Activated!**\nJoin here: {link.invite_link}")

async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    addrs = {'p_usdt': ("USDT (TRC20)", USDT_ADDR), 'p_sol': ("SOL", SOL_ADDR), 'p_ton': ("TON", TON_ADDR)}
    name, addr = addrs.get(query.data)
    msg = (f"✅ **Deposit {name}**\n\n`{addr}`\n\n"
           "💰 **Price:** $10 (7D) | $35 (30D)\n"
           "📩 Send TXID/Screenshot to @ibenium after payment.")
    await query.message.edit_text(msg, parse_mode='Markdown')

def main():
    global bot_app
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    bot_app.add_handler(CallbackQueryHandler(callback_query))
    threading.Thread(target=run_flask, daemon=True).start()
    bot_app.run_polling()

if __name__ == '__main__': main()
