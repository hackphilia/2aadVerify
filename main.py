import os, json, datetime, threading, asyncio, subprocess, secrets, string
from flask import Flask
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
DB_FILE = "subscribers.json"

USDT_ADDR = "TXxnLWMD8FBPec9oSBzqtvk7yu8hQCg6Eb"
SOL_ADDR = "FAiYeTLfRH325KxKa5D8wAoQ7QvPCauAokWT4cx9aMtT"
TON_ADDR = "UQC2Uldo7XpyI2djwk_dMdY3OYSgwKWTvqFYZcC14piBQsUc"

web_app = Flask(__name__)
bot_app = None

# ======================================================
# 💾 DATABASE & SYNC
# ======================================================
def load_db():
    if not os.path.exists(DB_FILE): return {"users": {}, "trials": [], "all_users": {}, "codes": {}}
    with open(DB_FILE, "r") as f:
        try: return json.load(f)
        except: return {"users": {}, "trials": [], "all_users": {}, "codes": {}}

def save_db_and_sync(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)
    if REPO_URL and GITHUB_TOKEN:
        try:
            subprocess.run(["git", "config", "user.name", "RenderBot"], check=True)
            subprocess.run(["git", "config", "user.email", "bot@render.com"], check=True)
            subprocess.run(["git", "add", DB_FILE], check=True)
            subprocess.run(["git", "commit", "-m", "Sync DB"], check=True)
            subprocess.run(["git", "push", f"https://{GITHUB_TOKEN}@{REPO_URL}", "main"], check=True)
        except: pass

# ======================================================
# 🕒 AUTO-KICK SYSTEM
# ======================================================
async def check_expirations():
    while True:
        db = load_db()
        now = datetime.datetime.now()
        to_remove = []
        for uid, exp_str in db["users"].items():
            exp_dt = datetime.datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
            if now > exp_dt:
                try:
                    await bot_app.bot.ban_chat_member(GROUP_ID, int(uid))
                    await bot_app.bot.unban_chat_member(GROUP_ID, int(uid))
                    await bot_app.bot.send_message(uid, "⚠️ Your subscription has expired.")
                    to_remove.append(uid)
                except: pass
        if to_remove:
            for uid in to_remove: del db["users"][uid]
            save_db_and_sync(db)
        await asyncio.sleep(3600)

# ======================================================
# 🤖 BOT HANDLERS
# ======================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    db = load_db()
    if user_id not in db["all_users"]:
        db["all_users"][user_id] = {"join": str(datetime.date.today())}
        save_db_and_sync(db)
    
    kb = [['💳 Join Premium', '📊 My Status'], ['🎁 24h Free Trial', '🎟 Redeem Code'], ['📞 Support']]
    if int(user_id) == ADMIN_ID:
        kb.append(['🛠 Admin: Broadcast', '🛠 Admin: Gen Code'])
    
    await update.message.reply_text("🚀 2Aad Premium Management", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command-only Admin Sync Test"""
    if update.effective_user.id != ADMIN_ID: return
    db = load_db()
    db["last_test_sync"] = str(datetime.datetime.now())
    await update.message.reply_text("🔄 Testing GitHub Sync...")
    save_db_and_sync(db)
    await update.message.reply_text("✅ Sync command sent. Check GitHub commits.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = str(update.effective_user.id)
    state = context.user_data.get('state')

    # ADMIN: GENERATE CODE BUTTON LOGIC
    if text == '🛠 Admin: Gen Code' and int(user_id) == ADMIN_ID:
        context.user_data['state'] = 'WAIT_GEN_DAYS'
        return await update.message.reply_text("Enter number of days for this code:")

    if state == 'WAIT_GEN_DAYS' and int(user_id) == ADMIN_ID:
        try:
            days = int(text)
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
            db = load_db()
            db["codes"][code] = days
            save_db_and_sync(db)
            await update.message.reply_text(f"🎟 Code: `{code}`\n⏳ Duration: {days} Days")
            context.user_data['state'] = None
        except:
            await update.message.reply_text("Please enter a valid number.")
        return

    # ADMIN: BROADCAST BUTTON LOGIC
    if text == '🛠 Admin: Broadcast' and int(user_id) == ADMIN_ID:
        context.user_data['state'] = 'WAIT_BC'
        return await update.message.reply_text("Send broadcast text:")

    if state == 'WAIT_BC' and int(user_id) == ADMIN_ID:
        context.user_data['bc_msg'] = text; context.user_data['state'] = 'CONF_BC'
        kb = [[InlineKeyboardButton("✅ Send", callback_data='bc_confirm'), InlineKeyboardButton("❌ Cancel", callback_data='bc_cancel')]]
        return await update.message.reply_text(f"PREVIEW:\n{text}\n\nProceed?", reply_markup=InlineKeyboardMarkup(kb))

    # REDEEM CODE
    if text == '🎟 Redeem Code':
        context.user_data['state'] = 'WAIT_CODE'
        return await update.message.reply_text("Enter your 12-digit code:")

    if state == 'WAIT_CODE':
        db = load_db(); code = text.upper().strip()
        if code in db["codes"]:
            days = db["codes"].pop(code)
            db["users"][user_id] = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            save_db_and_sync(db)
            link = await context.bot.create_chat_invite_link(GROUP_ID, member_limit=1)
            await update.message.reply_text(f"✅ Success! {days} days added.\nLink: {link.invite_link}")
            context.user_data['state'] = None
        else: await update.message.reply_text("❌ Invalid code.")

    # PAYMENT PROOF FORWARDING
    if not text.startswith('/') and state is None and int(user_id) != ADMIN_ID:
        kb = [[InlineKeyboardButton("Approve 1D", callback_data=f"adm_1_{user_id}"),
               InlineKeyboardButton("Approve 7D", callback_data=f"adm_7_{user_id}"),
               InlineKeyboardButton("Approve 30D", callback_data=f"adm_30_{user_id}")],
              [InlineKeyboardButton("❌ Reject", callback_data=f"adm_rej_{user_id}")]]
        await context.bot.send_message(ADMIN_ID, f"📩 Proof from {user_id}:\n{text}", reply_markup=InlineKeyboardMarkup(kb))
        await update.message.reply_text("Proof sent to Admin.")

    # USER MENUS
    if text == '📊 My Status':
        db = load_db()
        if user_id not in db["users"]: return await update.message.reply_text("❌ No active plan.")
        exp = datetime.datetime.strptime(db["users"][user_id], "%Y-%m-%d %H:%M:%S")
        rem = exp - datetime.datetime.now()
        await update.message.reply_text(f"⏳ Left: {rem.days}d {rem.seconds//3600}h")
    elif text == '💳 Join Premium':
        kb = [[InlineKeyboardButton("🪙 USDT", callback_data='p_usdt')], [InlineKeyboardButton("☀️ SOL", callback_data='p_sol')], [InlineKeyboardButton("💎 TON", callback_data='p_ton')]]
        await update.message.reply_text("Select Coin:", reply_markup=InlineKeyboardMarkup(kb))
    elif text == '🎁 24h Free Trial':
        db = load_db()
        if user_id in db["trials"]: return await update.message.reply_text("❌ Used.")
        db["users"][user_id] = (datetime.datetime.now() + datetime.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        db["trials"].append(user_id); save_db_and_sync(db)
        link = await context.bot.create_chat_invite_link(GROUP_ID, member_limit=1)
        await update.message.reply_text(f"🎁 Trial Active! Join: {link.invite_link}")
    elif text == '📞 Support': await update.message.reply_text("📞 @ibenium")

async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; data = query.data; await query.answer()

    if data.startswith('adm_'):
        _, days, uid = data.split('_')
        if days == 'rej':
            await context.bot.send_message(uid, "❌ Rejected."); return await query.message.edit_text("Rejected.")
        db = load_db()
        db["users"][uid] = (datetime.datetime.now() + datetime.timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M:%S")
        save_db_and_sync(db)
        link = await context.bot.create_chat_invite_link(GROUP_ID, member_limit=1)
        await context.bot.send_message(uid, f"✅ Approved!\nLink: {link.invite_link}")
        await query.message.edit_text(f"Approved {uid} for {days}D")

    elif data.startswith('p_'):
        context.user_data['coin'] = data
        kb = [[InlineKeyboardButton("1 Day ($2)", callback_data='d_1')], [InlineKeyboardButton("7 Days ($10)", callback_data='d_7')], [InlineKeyboardButton("30 Days ($35)", callback_data='d_30')]]
        await query.message.edit_text("Select Duration:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith('d_'):
        context.user_data['days'] = data.split('_')[1]
        kb = [[InlineKeyboardButton("✅ Proceed", callback_data='pay_confirm'), InlineKeyboardButton("❌ Cancel", callback_data='pay_cancel')]]
        await query.message.edit_text(f"Pay for {context.user_data['days']} day(s)?", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'pay_confirm':
        coin = context.user_data.get('coin')
        addr = USDT_ADDR if 'usdt' in coin else SOL_ADDR if 'sol' in coin else TON_ADDR
        await query.message.edit_text(f"Address: `{addr}`\n\nPaste TXID/Screenshot here.")

    elif data in ['pay_cancel', 'bc_cancel']:
        context.user_data.clear(); await query.message.edit_text("Cancelled."); await start(update, context)

    elif data == 'bc_confirm':
        msg = context.user_data.get('bc_msg'); db = load_db()
        for uid in db["all_users"].keys():
            try: await context.bot.send_message(uid, f"📢 ANNOUNCEMENT\n\n{msg}"); await asyncio.sleep(0.05)
            except: pass
        await query.message.edit_text("✅ Sent."); context.user_data['state'] = None

def main():
    global bot_app
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("test", test_command))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    bot_app.add_handler(CallbackQueryHandler(callback_query))
    threading.Thread(target=lambda: web_app.run(host='0.0.0.0', port=10000), daemon=True).start()
    asyncio.get_event_loop().create_task(check_expirations())
    bot_app.run_polling()

if __name__ == '__main__': main()
