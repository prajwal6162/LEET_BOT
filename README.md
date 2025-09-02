# 📌 LeetCode Telegram Tracker Bot

A Telegram bot that tracks LeetCode submissions of users and posts updates in a Telegram group.
  - It is deployed on **Render** for free 24×7 running, using **Render's PostgreSQL database**.
  - A dummy HTTP server is used to make it appear as a web service on Render.
---

## **Features**

- Add or remove LeetCode usernames.  
- List all registered users.  
- Automatic polling of recent submissions.  
- PostgreSQL database for user tracking.  
- Deployable on Render (with a dummy HTTP server to keep the bot alive).

---

## **Technologies**

- Python 3.10+  
- `python-telegram-bot` 20.6  
- PostgreSQL (Render Postgres or local)  
- Requests  
- Dotenv  

---

## **Requirements**

- Python 3.10+  
- Telegram Bot token (create via [BotFather](https://t.me/BotFather))  
- PostgreSQL database  
- Render account (optional for deployment)  

---

## **Installation**

### 1. Clone the Repository
```python
git clone https://github.com/yourusername/leetcode-telegram-bot.git
cd leetcode-telegram-bot
```

### 2. Create a Virtual Environment
```python
python -m venv venv
```
Activate it:
####
Linux/macOS:
```python
source venv/bin/activate
```
#### 
Windows:
```python
venv\Scripts\activate
```
  
### 3. Install Dependencies
```python
pip install -r requirements.txt
```

### 4.Configure Environment Variables (.env)
Create a file named .env in the project root:
```env
BOT_TOKEN=your_telegram_bot_token
GROUP_CHAT_ID=your_telegram_group_chat_id
DATABASE_URL=postgres://username:password@host:port/dbname
POLL_INTERVAL=60
PORT=8080
```
### Explanation

| Variable       | Description                                                                 |
|----------------|-----------------------------------------------------------------------------|
| BOT_TOKEN      | Telegram bot token from [BotFather](https://t.me/BotFather)                 |
| GROUP_CHAT_ID  | ID of the Telegram group where updates will be sent                         |
| DATABASE_URL   | PostgreSQL connection URL (`postgres://user:pass@host:port/dbname`)        |
| POLL_INTERVAL  | Polling interval in seconds for checking submissions (default: 60)         |
| PORT           | Required for Render deployment (default: 8080)                              |


### 5. Run the Bot Locally
```python
python src/bot.py
```

You should see:\
🌍 HTTP server running on port 8080\
🤖 Bot running...

### 6. Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and instructions |
| `/add <leetcode_username>` | Add your LeetCode username |
| `/remove` | Remove your registered username |
| `/list` | List all registered users |


### 7. Database Setup (Optional for Local PostgreSQL)
```sql
CREATE DATABASE leetcode_bot;
CREATE USER bot_user WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE leetcode_bot TO bot_user;

CREATE TABLE IF NOT EXISTS users (
    telegram_id TEXT PRIMARY KEY,
    leetcode_username TEXT NOT NULL,
    last_timestamp BIGINT DEFAULT 0
);
```
-The bot will automatically create the users table if it doesn’t exist.
