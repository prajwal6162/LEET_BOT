import os
import sys
import time
import asyncio
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- Windows event loop fix ---
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# === LOAD ENV ===
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 60))
DATABASE_URL = os.getenv("DATABASE_URL")

# Basic sanity checks
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing in env")
if not GROUP_CHAT_ID:
    raise RuntimeError("GROUP_CHAT_ID missing in env")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL missing in env")

# === DB CONNECTION ===
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
cursor = conn.cursor()

# Create table if not exists
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    telegram_id TEXT PRIMARY KEY,
    leetcode_username TEXT NOT NULL,
    last_timestamp BIGINT DEFAULT 0
)
""")
conn.commit()

# === LEETCODE API ===
def get_recent_submission(username: str):
    url = "https://leetcode.com/graphql"
    query = """
    query recentSubmissions($username: String!) {
      recentSubmissionList(username: $username, limit: 1) {
        title
        titleSlug
        timestamp
        statusDisplay
        lang
      }
    }
    """
    headers = {
        "Content-Type": "application/json",
        "Referer": "https://leetcode.com",
        "Origin": "https://leetcode.com",
        "User-Agent": "Mozilla/5.0"
    }
    try:
        resp = requests.post(url, json={"query": query, "variables": {"username": username}},
                             headers=headers, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("recentSubmissionList", [])
    except Exception as e:
        print(f"[LEETCODE] Error fetching {username}: {e}")
        return []

# === BOT COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! Use /add <leetcode_username> to link your account.\n"
        "Use /list to see all registered users."
    )

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /add <leetcode_username>")
        return

    leetcode_username = context.args[0].strip()
    telegram_id = str(update.effective_user.id)

    cursor.execute("""
        INSERT INTO users (telegram_id, leetcode_username, last_timestamp)
        VALUES (%s, %s, %s)
        ON CONFLICT (telegram_id) DO UPDATE
        SET leetcode_username = EXCLUDED.leetcode_username
    """, (telegram_id, leetcode_username, 0))
    conn.commit()

    await update.message.reply_text(f"✅ Linked LeetCode username: {leetcode_username}")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    cursor.execute("DELETE FROM users WHERE telegram_id=%s", (telegram_id,))
    conn.commit()
    await update.message.reply_text("❌ Your LeetCode username has been removed.")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT leetcode_username FROM users ORDER BY leetcode_username")
    users = cursor.fetchall()
    if not users:
        await update.message.reply_text("No users registered yet.")
    else:
        msg = "📜 Registered LeetCode Users:\n" + "\n".join(u[0] for u in users)
        await update.message.reply_text(msg)

# === JOBQUEUE POLLER (no custom threads) ===
async def poll_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        cursor.execute("SELECT telegram_id, leetcode_username, last_timestamp FROM users")
        rows = cursor.fetchall()
    except Exception as e:
        print(f"[DB] Read error: {e}")
        conn.rollback()
        return

    for telegram_id, username, last_ts in rows:
        # Make the blocking HTTP call in a thread to avoid blocking the event loop
        submissions = await asyncio.to_thread(get_recent_submission, username)

        if not submissions:
            print(f"[POLL] {username}: no submissions returned")
            continue

        latest = submissions[0]
        try:
            latest_ts = int(latest.get("timestamp") or 0)
        except Exception:
            latest_ts = 0

        print(f"[POLL] {username}: last_ts={last_ts} latest_ts={latest_ts}")

        # First-time setup: don't spam old submission, just record it
        if not last_ts and latest_ts:
            try:
                cursor.execute("UPDATE users SET last_timestamp=%s WHERE telegram_id=%s",
                               (latest_ts, telegram_id))
                conn.commit()
                print(f"[POLL] Initialized last_timestamp for {username} -> {latest_ts}")
            except Exception as e:
                print(f"[DB] Init update error: {e}")
                conn.rollback()
            continue

        # New submission detected
        if latest_ts and latest_ts != (last_ts or 0):
            msg = (f"🚀 {username} just submitted:\n"
                   f"{latest.get('title')} ({latest.get('statusDisplay')}, {latest.get('lang')})\n"
                   f"https://leetcode.com/problems/{latest.get('titleSlug')}/")
            try:
                await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg)
            except Exception as e:
                print(f"[TG] Send error: {e}")

            # Update last_timestamp
            try:
                cursor.execute("UPDATE users SET last_timestamp=%s WHERE telegram_id=%s",
                               (latest_ts, telegram_id))
                conn.commit()
                print(f"[DB] Updated {username} -> {latest_ts}")
            except Exception as e:
                print(f"[DB] Update error: {e}")
                conn.rollback()

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_user))
    application.add_handler(CommandHandler("remove", remove_user))
    application.add_handler(CommandHandler("list", list_users))

    # Schedule polling via JobQueue (no manual threads)
    application.job_queue.run_repeating(poll_job, interval=POLL_INTERVAL, first=5)

    print("🤖 Bot running...")
    application.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
