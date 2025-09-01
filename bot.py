import os
import sys
import asyncio
import requests
import asyncpg  # Changed
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
PORT = int(os.getenv("PORT", 8080))

# --- Sanity checks ---
for var in ["BOT_TOKEN", "GROUP_CHAT_ID", "DATABASE_URL"]:
    if not globals()[var]:
        raise RuntimeError(f"{var} missing in env")

# === DATABASE SETUP (ASYNC) ===
# This pool will be used by all async functions to safely get connections
db_pool = None

async def setup_database():
    """Create the users table if it doesn't exist."""
    global db_pool
    # Establish a connection pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, ssl='require')
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id TEXT PRIMARY KEY,
                leetcode_username TEXT NOT NULL,
                last_timestamp BIGINT DEFAULT 0
            )
        """)
    print("✅ Database connection pool established and table checked.")


# === LEETCODE API FUNCTION (Unchanged) ===
# This function is synchronous, so we'll call it with asyncio.to_thread
def get_recent_submission(username: str):
    # ... (your existing function code is perfect here) ...
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
    headers = {"Content-Type": "application/json", "Referer": "https://leetcode.com"}
    try:
        resp = requests.post(url, json={"query": query, "variables": {"username": username}}, headers=headers, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("recentSubmissionList", [])
    except Exception as e:
        print(f"[LEETCODE] Error fetching {username}: {e}")
        return []


# === BOT COMMANDS (Refactored for asyncpg) ===
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

    # Acquire a connection from the pool safely
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (telegram_id, leetcode_username, last_timestamp)
            VALUES ($1, $2, 0)
            ON CONFLICT (telegram_id) DO UPDATE
            SET leetcode_username = EXCLUDED.leetcode_username
        """, telegram_id, leetcode_username)

    await update.message.reply_text(f"✅ Linked LeetCode username: {leetcode_username}")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM users WHERE telegram_id=$1", telegram_id)
    await update.message.reply_text("❌ Your LeetCode username has been removed.")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with db_pool.acquire() as conn:
        users = await conn.fetch("SELECT leetcode_username FROM users ORDER BY leetcode_username")

    if not users:
        await update.message.reply_text("No users registered yet.")
    else:
        msg = "📜 Registered LeetCode Users:\n" + "\n".join(u['leetcode_username'] for u in users)
        await update.message.reply_text(msg)


# === JOBQUEUE POLLING (Refactored for asyncpg) ===
async def poll_job(context: ContextTypes.DEFAULT_TYPE):
    async with db_pool.acquire() as conn:
        # fetchval, fetchrow, fetch - powerful asyncpg methods
        rows = await conn.fetch("SELECT telegram_id, leetcode_username, last_timestamp FROM users")

    for record in rows:
        # Run the blocking network call in a separate thread
        submissions = await asyncio.to_thread(get_recent_submission, record['leetcode_username'])

        if not submissions:
            continue

        latest = submissions[0]
        latest_ts = int(latest.get("timestamp", 0))
        last_ts = record['last_timestamp']
        telegram_id = record['telegram_id']
        username = record['leetcode_username']
        
        # Simplified Logic: If there's a new submission, process it.
        if latest_ts > last_ts:
            # Only send a message if this isn't the very first submission we've seen
            if last_ts != 0:
                msg = (
                    f"🚀 {username} just submitted:\n"
                    f"{latest.get('title')} ({latest.get('statusDisplay')}, {latest.get('lang')})\n"
                    f"https://leetcode.com/problems/{latest.get('titleSlug')}/"
                )
                try:
                    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg)
                except Exception as e:
                    print(f"[TG] Send error: {e}")
            
            # Update the timestamp in the database
            async with db_pool.acquire() as conn:
                await conn.execute("UPDATE users SET last_timestamp=$1 WHERE telegram_id=$2", latest_ts, telegram_id)


# === DUMMY HTTP SERVER (Unchanged) ===
def run_http_server():
    # ... (your existing function is fine) ...
    handler = SimpleHTTPRequestHandler
    httpd = HTTPServer(("", PORT), handler)
    print(f"🌍 HTTP server running on port {PORT}")
    httpd.serve_forever()

# === MAIN FUNCTION (Updated to initialize DB) ===
async def main_async():
    """Asynchronous main function to setup DB and run the bot."""
    # Setup the database pool first
    await setup_database()
    
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_user))
    application.add_handler(CommandHandler("remove", remove_user))
    application.add_handler(CommandHandler("list", list_users))

    # Add polling job
    application.job_queue.run_repeating(poll_job, interval=POLL_INTERVAL, first=5)

    # Start HTTP server in a separate daemon thread
    Thread(target=run_http_server, daemon=True).start()

    print("🤖 Bot running...")
    # Run the bot until the user presses Ctrl-C
    # Using with block for graceful shutdown
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        # Keep the script running
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")
