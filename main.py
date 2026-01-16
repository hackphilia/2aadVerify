import os
import json
import time
import logging
import threading
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, JobQueue
import subprocess

# --- CONFIGURATION ---
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
GROUP_ID = os.environ.get("GROUP_ID")  # Format: -100...
REPO_URL = os.environ.get("REPO_URL")  # github.com/user/repo.git
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# --- FLASK SERVER (For Render Port Check) ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is alive and healthy!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

# --- DATABASE LOGIC ---
DB_FILE = "subscribers.json"

def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {"users": {}}

def save_and_push():
    """Saves data locally and pushes to GitHub to bypass Render's wipe."""
    try:
        # 1. Git Config (Needed for every restart)
        subprocess.run(["git", "config", "user.name", "RenderBot"], check=True)
        subprocess.run(["git", "config", "user.email", "bot@render.com"], check=True)
        
        # 2. Add and Commit
        subprocess.run(["git", "add", DB_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Update subscribers list [skip ci]"], check=True)
        
        # 3. Push using Token
        remote_url = f"https://{GITHUB_TOKEN}@{REPO_URL}"
        subprocess.run(["git", "push", remote_url, "main"], check=True)
        print("✅ Database synced to GitHub.")
    except Exception as e:
        print(f"❌ Git Push Failed: {e}")

# --- BOT COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Membership Manager is Active.")

async def add_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        user_id = context.args[0]
        days = int(context.args[1])
        expiry_date = (datetime.now() + timedelta(days=days)).isoformat()

        data = load_data()
        data["users"][user_id] = expiry_date
        
        with open(DB_FILE, "w") as f:
            json.dump(data, f)
        
        save_and_push()
        await update.message.reply_text(f"✅ User {user_id} added for {days} days.")
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /add <ID> <DAYS>")

async def check_expirations(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    now = datetime.now()
    to_remove = []

    for user_id, expiry_str in data["users"].items():
        expiry_date = datetime.fromisoformat(expiry_str)
        if now > expiry_date:
            try:
                await context.bot.ban_chat_member(GROUP_ID, user_id)
                await context.bot.unban_chat_member(GROUP_ID, user_id) # Leave unbanned so they can rejoin later
                to_remove.append(user_id)
                print(f"🚫 Removed expired user: {user_id}")
            except Exception as e:
                print(f"⚠️ Error removing {user_id}: {e}")

    if to_remove:
        for uid in to_remove:
            del data["users"][uid]
        with open(DB_FILE, "w") as f:
            json.dump(data, f)
        save_and_push()

# --- MAIN RUNNER ---
def main():
    # Start Flask in background
    threading.Thread(target=run_flask, daemon=True).start()

    # Start Telegram Bot
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_member))
    
    # Run cleanup every hour
    job_queue = app.job_queue
    job_queue.run_repeating(check_expirations, interval=3600, first=10)

    print("🚀 Bot starting...")
    app.run_polling()

if __name__ == '__main__':
    main()
