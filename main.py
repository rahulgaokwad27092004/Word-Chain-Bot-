import logging
import random
import nltk
nltk.download('words')
from nltk.corpus import words
from telegram import Update, ForceReply
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pymongo import MongoClient
import os

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Telegram bot token and webhook domain
BOT_TOKEN = "7510117884:AAHjoZRQRg9MBNow7wdYlYgN9BAR2sbnHd0"
WEBHOOK_DOMAIN = "https://your-app-name.koyeb.app"  # <- Replace this before deploy
MONGO_URI = "mongodb+srv://karinuzumaki0007:rwro5SJzPU2js4Eg@cluster0.aczm0tm.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# MongoDB setup
client = MongoClient(MONGO_URI)
db = client["word_chain_game"]
game_state = db["game_state"]
players = db["players"]
scores = db["scores"]
used_words = db["used_words"]

# Load English words
ENGLISH_WORDS = set(w.lower() for w in words.words())

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to Word Chain Game! Use /join to join the game.")

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.first_name

    if players.find_one({"chat_id": chat_id, "user_id": user_id}):
        await update.message.reply_text(f"{username}, you already joined.")
        return

    players.insert_one({"chat_id": chat_id, "user_id": user_id, "username": username})
    await update.message.reply_text(f"{username} joined the game!")

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    joined_players = list(players.find({"chat_id": chat_id}))

    if len(joined_players) < 2:
        await update.message.reply_text("At least 2 players needed to start the game.")
        return

    first_word = random.choice(list(ENGLISH_WORDS))
    game_state.update_one(
        {"chat_id": chat_id},
        {"$set": {
            "last_word": first_word,
            "turn_index": 0
        }}, upsert=True
    )
    used_words.delete_many({"chat_id": chat_id})
    used_words.insert_one({"chat_id": chat_id, "word": first_word})

    first_player = joined_players[0]
    await update.message.reply_text(
        f"Game started! First word: *{first_word}*\n{first_player['username']}'s turn.",
        parse_mode="Markdown")

async def word_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.first_name
    word = update.message.text.strip().lower()

    game = game_state.find_one({"chat_id": chat_id})
    if not game:
        return

    all_players = list(players.find({"chat_id": chat_id}))
    if not any(p["user_id"] == user_id for p in all_players):
        return

    current_turn_index = game.get("turn_index", 0)
    current_player = all_players[current_turn_index % len(all_players)]
    if user_id != current_player["user_id"]:
        await update.message.reply_text(f"Wait for your turn, {username}!")
        return

    last_word = game.get("last_word")
    if word in [w['word'] for w in used_words.find({"chat_id": chat_id})]:
        await update.message.reply_text("This word has already been used!")
        return

    if word not in ENGLISH_WORDS:
        await update.message.reply_text("That's not a valid English word!")
        return

    if word[0] != last_word[-1]:
        await update.message.reply_text(f"Your word must start with '{last_word[-1]}'!")
        return

    scores.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {"score": 1}, "$set": {"username": username}},
        upsert=True
    )
    used_words.insert_one({"chat_id": chat_id, "word": word})

    game_state.update_one({"chat_id": chat_id}, {"$set": {
        "last_word": word,
        "turn_index": (current_turn_index + 1) % len(all_players)
    }})

    next_player = all_players[(current_turn_index + 1) % len(all_players)]
    await update.message.reply_text(f"✅ Good word!\nNext: {next_player['username']}")

async def score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    all_scores = list(scores.find({"chat_id": chat_id}).sort("score", -1))
    if not all_scores:
        await update.message.reply_text("No scores yet.")
        return

    msg = "🏆 Scores:\n"
    for s in all_scores:
        msg += f"{s['username']}: {s['score']}\n"
    await update.message.reply_text(msg)

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game_state.delete_one({"chat_id": chat_id})
    players.delete_many({"chat_id": chat_id})
    scores.delete_many({"chat_id": chat_id})
    used_words.delete_many({"chat_id": chat_id})
    await update.message.reply_text("Game has been reset!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
Word Chain Game Rules:
- Join with /join
- Start with /startgame
- Use valid English words
- Each word must start with the last letter of the previous word
- Take turns — bot tells you when it's your turn
- View scores with /score
- Reset with /resetgame
""")

if __name__ == '__main__':
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("startgame", start_game))
    app.add_handler(CommandHandler("score", score))
    app.add_handler(CommandHandler("resetgame", reset))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, word_message))

    import asyncio
    asyncio.run(app.bot.set_webhook(f"{WEBHOOK_DOMAIN}/webhook"))

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        webhook_url=f"{WEBHOOK_DOMAIN}/webhook"
)
            
