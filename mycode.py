from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 Bot is running from remote code!"
    )


def create_bot(token):
    app = Application.builder().token(token).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    return app
