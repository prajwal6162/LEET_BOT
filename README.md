A Telegram bot that tracks LeetCode submissions of users and posts updates in a Telegram group.

Features

Add or remove LeetCode usernames.

List all registered users.

Automatic polling of recent submissions.

PostgreSQL database for user tracking.

Deployable on Render (with a dummy HTTP server to keep the bot alive).

Technologies

Python 3.10+

python-telegram-bot
 20.6

PostgreSQL (Render Postgres or local)

Requests

Dotenv

Requirements

Python 3.10+

Telegram Bot token (create via BotFather
)

PostgreSQL database

Render account (optional for deployment)

Setup Locally
1. Clone the repository
git clone https://github.com/yourusername/leetcode-telegram-bot.git
cd leetcode-telegram-bot

2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

3. Install dependencies
pip install -r requirements.txt

4. Configure environment variables

Create a .env file in the project root:

BOT_TOKEN=your_telegram_bot_token
GROUP_CHAT_ID=your_telegram_group_chat_id
DATABASE_URL=postgres://username:password@host:port/dbname
POLL_INTERVAL=60
PORT=8080


BOT_TOKEN: From BotFather.

GROUP_CHAT_ID: ID of the Telegram group to send updates.

DATABASE_URL: PostgreSQL connection URL.

POLL_INTERVAL: Polling interval in seconds (default 60).

PORT: Required for Render deployment (default 8080).

5. Run the bot locally
python src/bot.py


You should see:

🌍 HTTP server running on port 8080
🤖 Bot running...


Test the bot in your Telegram group with commands:

/start

/add <leetcode_username>

/remove

/list

Database Setup

Local PostgreSQL (optional):

CREATE DATABASE leetcode_bot;
CREATE USER bot_user WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE leetcode_bot TO bot_user;


The bot automatically creates the users table if it doesn’t exist:

CREATE TABLE IF NOT EXISTS users (
    telegram_id TEXT PRIMARY KEY,
    leetcode_username TEXT NOT NULL,
    last_timestamp BIGINT DEFAULT 0
);

Deployment on Render

Create a Web Service on Render
.

Connect your GitHub repository.

Set environment variables (BOT_TOKEN, GROUP_CHAT_ID, DATABASE_URL, POLL_INTERVAL, PORT).

Start command:

python src/bot.py


Ensure Python version is 3.10–3.13.

Optional: add a render.yaml for advanced configuration:

services:
  - type: web
    name: telegram-bot
    env: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: python src/bot.py
    envVars:
      - key: BOT_TOKEN
        value: "your_bot_token_here"
      - key: GROUP_CHAT_ID
        value: "your_group_chat_id_here"
      - key: DATABASE_URL
        value: "your_postgres_url_here"
      - key: POLL_INTERVAL
        value: "60"
      - key: PORT
        value: "10000"

Commands
Command	Description
/start	Welcome message and instructions
/add <username>	Add your LeetCode username
/remove	Remove your registered LeetCode username
/list	List all registered users
Tips & Troubleshooting

_Updater__polling_cleanup_cb error → Make sure python-telegram-bot 20.6 is installed and no old PTB versions exist.

Use a fresh Render build and delete build cache if errors persist.

Render web service requires a PORT variable and a dummy HTTP server.

For PostgreSQL SSL connections, ensure sslmode="require" in psycopg2.connect.
