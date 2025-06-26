import os
import asyncio
import random
import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes
)
import motor.motor_asyncio

BOT_TOKEN = "7510117884:AAHjoZRQRg9MBNow7wdYlYgN9BAR2sbnHd0"
WEBHOOK_DOMAIN = "https://bot-2b6f13e0.koyeb.app"
MONGO_URI = "mongodb+srv://karinuzumaki0007:rwro5SJzPU2js4Eg@cluster0.aczm0tm.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
PORT = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

game_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to the Word Chain Game! Use /play to start the game.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/play - Start a new word chain game\n"
        "/leaderboard - Show global and group leaderboards\n"
        "Rules: Each word must start with the last letter of the previous word. Word must exist in the dictionary.\n"
        "Timer starts at 30s, reduces every 10 correct words (min 5s). Word length increases every 7 words (max 10)."
    )

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "group":
        return await update.message.reply_text("This game can only be played in groups.")

    chat_id = str(update.effective_chat.id)
    game_data[chat_id] = {
        "used_words": set(),
        "last_letter": None,
        "scores": {},
        "turn": None,
        "players": [],
        "timer": 30,
        "min_length": 3,
        "correct_count": 0
    }
    await update.message.reply_text("Game started! Send a word to begin.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text or update.effective_chat.type != "group":
        return

    word = message.text.strip().lower()
    chat_id = str(update.effective_chat.id)
    user = update.effective_user

    if chat_id not in game_data:
        return

    game = game_data[chat_id]
    if word in game['used_words'] or word not in context.bot_data['dictionary']:
        return await message.reply_text("Invalid or repeated word.")

    if game['last_letter'] and not word.startswith(game['last_letter']):
        return await message.reply_text(f"Word must start with '{game['last_letter']}'")

    if len(word) < game['min_length']:
        return await message.reply_text(f"Word must be at least {game['min_length']} letters long.")

    game['used_words'].add(word)
    game['last_letter'] = word[-1]
    game['correct_count'] += 1
    game['scores'][user.id] = game['scores'].get(user.id, 0) + 1

    if game['correct_count'] % 10 == 0 and game['timer'] > 5:
        game['timer'] -= 5
    if game['correct_count'] % 7 == 0 and game['min_length'] < 10:
        game['min_length'] += 1

    await message.reply_text(f"✅ Good job, {user.first_name}! Next word should start with '{word[-1]}'")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    db = context.bot_data['db']
    users = await db.scores.find().to_list(length=100)
    global_lb = sorted(users, key=lambda x: x.get('score', 0), reverse=True)[:10]

    text = "🏆 Global Leaderboard:\n"
    for i, u in enumerate(global_lb, 1):
        text += f"{i}. {u['name']} - {u['score']} pts\n"

    if chat_id:
        group_scores = await db.scores.find({"chat_id": chat_id}).to_list(length=100)
        group_lb = sorted(group_scores, key=lambda x: x.get('score', 0), reverse=True)[:10]
        text += "\n👥 Group Leaderboard:\n"
        for i, u in enumerate(group_lb, 1):
            text += f"{i}. {u['name']} - {u['score']} pts\n"

    await update.message.reply_text(text or "No leaderboard data yet.")

async def main():
    db_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    db = db_client["word_chain_bot"]

    with open("words.txt", "r") as f:
        dictionary = set(w.strip().lower() for w in f)

    app = Application.builder().token(BOT_TOKEN).build()
    app.bot_data['dictionary'] = dictionary
    app.bot_data['db'] = db

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("play", play))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await app.initialize()
    await app.start()
    await app.bot.set_webhook(f"{WEBHOOK_DOMAIN}/bot{BOT_TOKEN}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
    
