
import os
import json
import asyncio
import logging
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

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
API_KEY = os.getenv("API_KEY")
PORT = int(os.getenv("PORT", "10000"))

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openrouter/free"


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

    def log_message(self, format, *args):
        pass


def ask_ai(user_text):
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "تو دستیار فارسی‌زبان ربات PULSE هستی. "
                    "طبیعی، محترمانه، دوستانه و روشن پاسخ بده. "
                    "پاسخ‌ها را بی‌دلیل طولانی نکن."
                ),
            },
            {
                "role": "user",
                "content": user_text,
            },
        ],
        "temperature": 0.7,
        "max_tokens": 600,
    }

    request = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.loads(response.read().decode("utf-8"))

    return result["choices"][0]["message"]["content"].strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! من ربات هوشمند PULSE هستم. آماده‌ام!"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "پیامت را بنویس تا به کمک هوش مصنوعی پاسخ بدهم.\n"
        "دستورهای من:\n"
        "/start - شروع\n"
        "/help - راهنما\n"
        "/owner - ارتباط با مالک"
    )


async def owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("این دستور مخصوص مالک ربات است.")
        return

    await update.message.reply_text("سلام مالک! خوش آمدی!")


async def chat_with_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text.strip()

    if not user_text:
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )

    try:
        answer = await asyncio.to_thread(ask_ai, user_text)

        if not answer:
            answer = "فعلاً نتونستم جواب مناسبی پیدا کنم."

        await update.message.reply_text(answer[:4000])

    except urllib.error.HTTPError as error:
        logging.error("OpenRouter HTTP error: %s", error.code)

        if error.code == 429:
            message = "درخواست‌ها زیاد شده؛ کمی بعد دوباره امتحان کن."
        elif error.code == 401:
            message = "کلید اتصال هوش مصنوعی معتبر نیست. تنظیمات را بررسی کنید."
        else:
            message = "فعلاً سرویس هوش مصنوعی پاسخ نمی‌دهد. کمی بعد امتحان کن."

        await update.message.reply_text(message)

    except Exception:
        logging.exception("AI request failed")
        await update.message.reply_text(
            "در ارتباط با هوش مصنوعی مشکلی پیش آمد. کمی بعد دوباره امتحان کن."
        )


def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده است.")

    if not API_KEY:
        raise RuntimeError("API_KEY تنظیم نشده است.")

    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("owner", owner_command))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, chat_with_ai)
    )

    logging.info("PULSE bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
    
