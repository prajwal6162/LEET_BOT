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
from threading import Thread
from http.server import SimpleHTTPRequestHandler, HTTPServer

# --- Windows event loop fix ---
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# === LOAD ENV ===
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 60))
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", 8080))   # required by Render

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
        submissions = await asyncio.to_thread(get_recent_submission, username)

        if not submissions:
            continue

        latest = submissions[0]
        try:
            latest_ts = int(latest.get("timestamp") or 0)
        except Exception:
            latest_ts = 0

        if not last_ts and latest_ts:
            cursor.execute("UPDATE users SET last_timestamp=%s WHERE telegram_id=%s",
                           (latest_ts, telegram_id))
            conn.commit()
            continue

        if latest_ts and latest_ts != (last_ts or 0):
            msg = (f"🚀 {username} just submitted:\n"
                   f"{latest.get('title')} ({latest.get('statusDisplay')}, {latest.get('lang')})\n"
                   f"https://leetcode.com/problems/{latest.get('titleSlug')}/")
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg)

            cursor.execute("UPDATE users SET last_timestamp=%s WHERE telegram_id=%s",
                           (latest_ts, telegram_id))
            conn.commit()

def run_http_server():
    """Dummy HTTP server so Render sees a running web service."""
    handler = SimpleHTTPRequestHandler
    httpd = HTTPServer(("", PORT), handler)
    print(f"🌍 HTTP server running on port {PORT}")
    httpd.serve_forever()

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_user))
    application.add_handler(CommandHandler("remove", remove_user))
    application.add_handler(CommandHandler("list", list_users))

    application.job_queue.run_repeating(poll_job, interval=POLL_INTERVAL, first=5)

    # Run HTTP server in another thread
    Thread(target=run_http_server, daemon=True).start()

    print("🤖 Bot running...")
    application.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
