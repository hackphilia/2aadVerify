import os, json, datetime, subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- VARIABLES (Set these in Render Environment Variables) ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
GROUP_ID = int(os.getenv("GROUP_ID", "0"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") 
REPO_URL = os.getenv("REPO_URL")         # Format: github.com/user/repo.git
DB_FILE = "subscribers.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "trials": [], "all_users": {}, "codes": {}}
    with open(DB_FILE, "r") as f:
        try:
            return json.load(f)
        except:
            return {"users": {}, "trials": [], "all_users": {}, "codes": {}}

def save_and_push(data):
    """Saves data locally and pushes to GitHub to survive Render restarts"""
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)
    
    try:
        # Configure Git identity for the bot
        subprocess.run(["git", "config", "user.name", "2Aad-Membership-Bot"])
        subprocess.run(["git", "config", "user.email", "bot@2aad.com"])
        
        # Add, commit, and push the updated JSON
        subprocess.run(["git", "add", DB_FILE])
        subprocess.run(["git", "commit", "-m", "Update subscribers list"])
        
        # Authenticate push using the GitHub Token
        remote_push_url = f"https://{GITHUB_TOKEN}@{REPO_URL}"
        subprocess.run(["git", "push", remote_push_url, "main"])
        print("✅ Database synced to GitHub successfully.")
    except Exception as e:
        print(f"❌ Git Push Error: {e}")

# --- AUTO-REMOVER LOGIC ---
async def check_expirations(context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    now = datetime.datetime.now()
    expired_users = []
    has_changes = False

    for uid, expiry_str in list(db["users"].items()):
        try:
            expiry_dt = datetime.datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
            if now > expiry_dt:
                # Ban and Unban to remove from group
                await context.bot.ban_chat_member(GROUP_ID, int(uid))
                await context.bot.unban_chat_member(GROUP_ID, int(uid))
                expired_users.append(uid)
                has_changes = True
                await context.bot.send_message(uid, "⚠️ Your 2Aad Premium subscription has expired. Access revoked.")
        except Exception as e:
            print(f"Error checking user {uid}: {e}")

    # Clean up expired users from the list
    for uid in expired_users:
        del db["users"][uid]
    
    if has_changes:
        save_and_push(db)
        await context.bot.send_message(ADMIN_ID, f"🧹 Auto-Cleanup: Removed {len(expired_users)} members.")

# --- ADMIN COMMAND TO MANUALLY ADD USERS ---
async def add_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        # Command: /add 12345678 30 (ID and Days)
        user_id = context.args[0]
        days = int(context.args[1])
        db = load_db()
        expiry = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        db["users"][user_id] = expiry
        save_and_push(db)
        await update.message.reply_text(f"✅ Added {user_id} for {days} days.")
    except:
        await update.message.reply_text("Usage: /add USER_ID DAYS")

def main():
    app = Application.builder().token(TOKEN).build()
    
    # Check every 60 minutes for expired members
    job_queue = app.job_queue
    job_queue.run_repeating(check_expirations, interval=3600, first=10)
    
    app.add_handler(CommandHandler("add", add_member))
    
    print("🚀 Membership Manager Running on Render...")
    app.run_polling()

if __name__ == '__main__':
    main()
