import logging, asyncio, os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from pymongo import MongoClient

# MongoDB setup
client = MongoClient("mongodb+srv://karinuzumaki0007:rwro5SJzPU2js4Eg@cluster0.aczm0tm.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["word_chain_bot"]
games = db["games"]

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load valid English words
with open("words.txt", "r") as f:
    valid_words = set(word.strip().lower() for word in f)

def is_valid_word(word):
    return word.lower() in valid_words

def get_game(chat_id):
    game = games.find_one({"chat_id": chat_id})
    if not game:
        game = {
            "chat_id": chat_id,
            "used_words": [],
            "players": [],
            "current_turn": 0,
            "last_letter": None,
            "scores": {},
            "warnings": {},
            "timer_task": None,
            "turn_time": 30,
            "min_length": 3
        }
        games.insert_one(game)
    return game

def update_game(chat_id, data):
    games.update_one({"chat_id": chat_id}, {"$set": data})

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    game = get_game(chat_id)
    if user.id not in game["players"]:
        game["players"].append(user.id)
        game["scores"][str(user.id)] = 0
        game["warnings"][str(user.id)] = 0
        update_game(chat_id, {"players": game["players"], "scores": game["scores"], "warnings": game["warnings"]})

    await update.message.reply_text(f"{user.first_name} joined! Total players: {len(game['players'])}")

    if len(game["players"]) == 1:
        await start_turn_timer(chat_id, context)

async def word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    text = update.message.text.lower().strip()

    if not text.isalpha():
        return await update.message.reply_text("Send a valid word (letters only).")

    game = get_game(chat_id)

    if user.id not in game["players"]:
        return await update.message.reply_text("You're not part of the game. Use /start to join.")

    if game["players"][game["current_turn"]] != user.id:
        return await update.message.reply_text("It's not your turn!")

    if text in game["used_words"]:
        return await update.message.reply_text("This word has already been used!")

    if not is_valid_word(text):
        return await update.message.reply_text("Invalid English word.")

    if game["last_letter"] and not text.startswith(game["last_letter"]):
        return await update.message.reply_text(f"Word must start with '{game['last_letter']}'.")

    if len(text) < game.get("min_length", 3):
        return await update.message.reply_text(f"Word must be at least {game['min_length']} letters long.")

    if game.get("timer_task"):
        context.job_queue.get_jobs_by_name(f"turn_timer_{chat_id}")[0].schedule_removal()

    game["used_words"].append(text)
    game["last_letter"] = text[-1]
    game["scores"][str(user.id)] += 1
    game["current_turn"] = (game["current_turn"] + 1) % len(game["players"])

    word_count = len(game["used_words"])
    game["turn_time"] = max(5, 30 - (word_count // 10) * 5)
    game["min_length"] = min(10, 3 + (word_count // 7))

    update_game(chat_id, {
        "used_words": game["used_words"],
        "last_letter": game["last_letter"],
        "scores": game["scores"],
        "current_turn": game["current_turn"],
        "turn_time": game["turn_time"],
        "min_length": game["min_length"]
    })

    next_id = game["players"][game["current_turn"]]
    next_user = await context.bot.get_chat_member(chat_id, next_id)

    await update.message.reply_text(
        f"✅ {user.first_name} scored! Word: {text}\nNext letter: {text[-1].upper()}\n🔁 {next_user.user.first_name}'s turn!"
    )

    await start_turn_timer(chat_id, context)

async def turn_timeout(context: ContextTypes.DEFAULT_TYPE):
    chat_id = int(context.job.name.split("_")[-1])
    game = get_game(chat_id)

    user_id = game["players"][game["current_turn"]]
    user_warning_count = game["warnings"].get(str(user_id), 0) + 1

    if user_warning_count >= 3:
        game["players"].remove(user_id)
        del game["scores"][str(user_id)]
        del game["warnings"][str(user_id)]
        msg = f"⚠️ Player <a href='tg://user?id={user_id}'>removed</a> for 3 missed turns!"
    else:
        game["warnings"][str(user_id)] = user_warning_count
        game["current_turn"] = (game["current_turn"] + 1) % len(game["players"])
        msg = f"⚠️ <a href='tg://user?id={user_id}'>missed their turn</a>! Warning {user_warning_count}/3."

    update_game(chat_id, {
        "players": game["players"],
        "current_turn": game["current_turn"],
        "scores": game["scores"],
        "warnings": game["warnings"]
    })

    await context.bot.send_message(chat_id, msg, parse_mode="HTML")

    if game["players"]:
        await start_turn_timer(chat_id, context)

async def start_turn_timer(chat_id, context: ContextTypes.DEFAULT_TYPE):
    game = get_game(chat_id)
    turn_time = game.get("turn_time", 30)

    context.job_queue.run_once(
        turn_timeout,
        turn_time,
        name=f"turn_timer_{chat_id}",
        chat_id=chat_id
    )

    current_id = game["players"][game["current_turn"]]
    user = await context.bot.get_chat_member(chat_id, current_id)
    await context.bot.send_message(
        chat_id,
        f"⏳ {user.user.first_name}, your turn! You have {turn_time} seconds."
    )

async def score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = get_game(chat_id)
    scores = game.get("scores", {})
    if not scores:
        return await update.message.reply_text("No scores yet.")
    msg = "🏆 Group Scores:\n"
    for uid, score in scores.items():
        try:
            user = await context.bot.get_chat_member(chat_id, int(uid))
            msg += f"{user.user.first_name}: {score}\n"
        except:
            msg += f"User {uid}: {score}\n"
    await update.message.reply_text(msg)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_scores = games.find({}, {"scores": 1})
    global_scores = {}
    for game in all_scores:
        for uid, score in game.get("scores", {}).items():
            global_scores[uid] = global_scores.get(uid, 0) + score
    sorted_scores = sorted(global_scores.items(), key=lambda x: x[1], reverse=True)[:10]
    msg = "🌍 Global Leaderboard:\n"
    for idx, (uid, score) in enumerate(sorted_scores, 1):
        msg += f"{idx}. User {uid}: {score}\n"
    await update.message.reply_text(msg)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = get_game(chat_id)
    turn_time = game.get("turn_time", 30)
    min_length = game.get("min_length", 3)
    used_words = len(game.get("used_words", []))
    current_id = game["players"][game["current_turn"]]
    user = await context.bot.get_chat_member(chat_id, current_id)
    await update.message.reply_text(
        f"📊 Game Status:\nTurn Time: {turn_time} seconds\nMin Word Length: {min_length}\nWords Guessed: {used_words}\nCurrent Turn: {user.user.first_name}"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📚 *Word Chain Bot Help*\n"
        "\n/start - Join or start the game"
        "\n/score - Show scores in this group"
        "\n/status - Show current game status"
        "\n/resetgame - Admins can reset the game"
        "\n/leaderboard - Global top scores"
        "\n/help - Show this help message\n"
        "\nGame Rules:\n- Start with a valid English word."
        "\n- Next word must start with the last letter of previous."
        "\n- Minimum word length increases every 7 correct guesses."
        "\n- You get 30s to play. Timer reduces after 10 correct guesses."
        "\n- 3 skips and you’re out!"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    member = await context.bot.get_chat_member(chat_id, user.id)
    if not member.status in ["administrator", "creator"]:
        return await update.message.reply_text("Only admins can reset the game.")
    games.delete_one({"chat_id": chat_id})
    await update.message.reply_text("🔄 Game has been reset!")

# Webhook version of main()
async def main():
    # Setup MongoDB
    db_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    db = db_client["word_chain_bot"]

    # Load dictionary
    with open("words.txt", "r") as f:
        word_list = set(w.strip().lower() for w in f)

    # Setup Application
    app = Application.builder().token(BOT_TOKEN).build()

    # Register all your handlers here
    app.add_handler(CommandHandler("start", start))
    # Add your other handlers here as needed

    # Webhook startup
    await app.initialize()
    await app.start()
    await app.bot.set_webhook(f"{WEBHOOK_DOMAIN}/bot{BOT_TOKEN}")
    await asyncio.Event().wait()
    BOT_TOKEN = "7510117884:AAHjoZRQRg9MBNow7wdYlYgN9BAR2sbnHd0"  # Replace with actual token if needed
    WEBHOOK_DOMAIN = "https://frequent-hedy-rahulgaikwad27-2a4e.koyeb.app"  # Replace with actual Koyeb domain
    WEBHOOK_PATH = f"/bot7510117884:AAHjoZRQRg9MBNow7wdYlYgN9BAR2sbnHd0"
    PORT = int(os.environ.get("PORT", 8080))

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("score", score))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("resetgame", reset))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), word))

    await app.initialize()
await app.start()
await app.bot.set_webhook(f"{WEBHOOK_DOMAIN}/bot{BOT_TOKEN}")
await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
