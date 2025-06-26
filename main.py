import os
import asyncio
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes
)
import motor.motor_asyncio

BOT_TOKEN = "7510117884:AAHjoZRQRg9MBNow7wdYlYgN9BAR2sbnHd0"
WEBHOOK_DOMAIN = "https://bot-2b6f13e0.koyeb.app"
MONGO_URI = "mongodb+srv://karinuzumaki0007:rwro5SJzPU2js4Eg@cluster0.aczm0tm.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
PORT = int(os.environ.get("PORT", 8080))


# Sample handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to the Word Chain Game!")


async def main():
    # MongoDB setup
    db_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    db = db_client["word_chain_bot"]

    # Load word list
    with open("words.txt", "r") as f:
        word_list = set(word.strip().lower() for word in f)

    # Create application
    app = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    app.add_handler(CommandHandler("start", start))

    # Start webhook
    await app.initialize()
    await app.start()
    await app.bot.set_webhook(f"{WEBHOOK_DOMAIN}/bot{BOT_TOKEN}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
    
