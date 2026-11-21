
import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

OWNER_ID = 7361198009
TOKEN = os.getenv("BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! من ربات هوشمند مدیریت گروه هستم. آماده‌ام!"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "من برای مدیریت گروه و گفت‌وگو با اعضا طراحی شده‌ام."
    )


async def owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("این دستور مخصوص مالک ربات است.")
        return

    await update.message.reply_text("سلام مالک! دستورات مدیریتی فقط با اجازه تو اجرا می‌شوند.")


def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده است.")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("owner", owner_command))

    app.run_polling()


if __name__ == "__main__":
    main()
  
