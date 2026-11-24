
import os
import re
import json
import time
import asyncio
import logging
import threading
import urllib.request
import urllib.error

from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# -----------------------------
# تنظیمات اصلی
# -----------------------------

OWNER_ID = 7361198009

TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("API_KEY")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openrouter/free"

PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("PULSE")

SYSTEM_PROMPT = """
تو دستیار هوشمند PULSE هستی.
با زبان فارسی طبیعی، روان، محترمانه و دوستانه صحبت کن.
پاسخ‌ها را متناسب با سؤال کاربر بنویس.
از جواب‌های تکراری و بیش از حد رسمی خودداری کن.
اگر پاسخ چیزی را نمی‌دانی، صادقانه بگو.
اطلاعات محرمانه، کلیدها و توکن‌ها را افشا نکن.
بدون درخواست کاربر درباره کدنویسی، زیرساخت یا سازنده خودت توضیح نده.
"""

last_error_time = {}
ERROR_COOLDOWN = 60


# -----------------------------
# سرور سلامت Railway
# -----------------------------

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"PULSE is running")

    def log_message(self, format, *args):
        return


def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()


# -----------------------------
# ارتباط با هوش مصنوعی
# -----------------------------

def ask_ai(user_text):

    if not API_KEY:
        raise RuntimeError("API_KEY تنظیم نشده است.")

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_text,
            },
        ],
        "temperature": 0.7,
        "max_tokens": 600,
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        OPENROUTER_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://railway.app",
            "X-Title": "PULSE Bot",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))

        answer = result["choices"][0]["message"]["content"]

        if not answer:
            return "فعلاً پاسخی دریافت نکردم. دوباره امتحان کن."

        return str(answer).strip()

    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="ignore")
        logger.error("OpenRouter HTTP error %s: %s", error.code, details)

        if error.code == 401:
            raise RuntimeError("کلید اتصال معتبر نیست.")

        if error.code == 402:
            raise RuntimeError("درخواست از طرف سرویس پذیرفته نشد؛ محدودیت اعتبار یا دسترسی مدل را بررسی کن.")

        if error.code == 429:
            raise RuntimeError("تعداد درخواست‌ها زیاد شده؛ کمی بعد دوباره امتحان کن.")

        raise RuntimeError(f"خطای ارتباط با سرویس: {error.code}")

    except urllib.error.URLError as error:
        logger.error("Connection error: %s", error)
        raise RuntimeError("ارتباط با سرویس برقرار نشد.")

    except (KeyError, IndexError, json.JSONDecodeError) as error:
        logger.error("Invalid AI response: %s", error)
        raise RuntimeError("پاسخ سرویس قابل خواندن نبود.")


# -----------------------------
# تشخیص پیام‌های مجاز در گروه
# -----------------------------

def should_respond(update, context):

    message = update.message

    if not message:
        return False

    # در گفت‌وگوی خصوصی همیشه پاسخ بده
    if update.effective_chat.type == "private":
        return True

    bot_id = context.bot.id
    bot_username = context.bot.username

    # اگر کاربر به پیام خود ربات ریپلای کرده باشد
    if message.reply_to_message:
        replied_user = message.reply_to_message.from_user

        if replied_user and replied_user.id == bot_id:
            return True

    # اگر کاربر نام کاربری ربات را صدا زده باشد
    if bot_username:
        pattern = rf"@{re.escape(bot_username)}\b"

        if re.search(pattern, message.text or "", re.IGNORECASE):
            return True

    return False


# -----------------------------
# جلوگیری از تکرار پیام خطا
# -----------------------------

async def send_error_once(chat_id, context, error_message):

    now = time.time()
    previous = last_error_time.get(chat_id, 0)

    if now - previous < ERROR_COOLDOWN:
        return

    last_error_time[chat_id] = now

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=error_message,
        )
    except Exception:
        logger.exception("Could not send error message")


# -----------------------------
# دستور شروع
# -----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "سلام! من ربات هوشمند PULSE هستم. آماده‌ام! ✨"
    )


# -----------------------------
# راهنما
# -----------------------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = (
        "راهنمای استفاده از PULSE:\n\n"
        "در گفت‌وگوی خصوصی پیام خودت را بفرست.\n\n"
        "در گروه برای صحبت با من، روی یکی از پیام‌هایم ریپلای کن "
        "یا نام کاربری‌ام را منشن کن.\n\n"
        "من به پیام‌های عادی گروه پاسخ نمی‌دهم."
    )

    await update.message.reply_text(text)


# -----------------------------
# دستور مالک
# -----------------------------

async def owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("این دستور مخصوص مالک ربات است.")
        return

    await update.message.reply_text(
        "پنل مالک PULSE\n\n"
        "وضعیت ربات: فعال\n"
        "مدل: OpenRouter Free"
    )


# -----------------------------
# تقسیم پاسخ‌های طولانی
# -----------------------------

async def send_long_message(message, text):

    max_length = 4000

    for index in range(0, len(text), max_length):
        await message.reply_text(text[index:index + max_length])


# -----------------------------
# دریافت پیام و پاسخ هوشمند
# -----------------------------

async def chat_with_ai(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    message = update.message

    if not message or not message.text:
        return

    if not should_respond(update, context):
        return

    user_text = message.text.strip()

    # حذف منشن ربات از متن ارسالی
    username = context.bot.username

    if username:
        user_text = re.sub(
            rf"@{re.escape(username)}\b",
            "",
            user_text,
            flags=re.IGNORECASE,
        ).strip()

    if not user_text:
        await message.reply_text("پیامت رو بنویس تا پاسخ بدم.")
        return

    try:
        await context.bot.send_chat_action(
            chat_id=message.chat_id,
            action=ChatAction.TYPING,
        )

        answer = await asyncio.to_thread(ask_ai, user_text)

        if answer:
            await send_long_message(message, answer)

    except RuntimeError as error:
        logger.warning("AI request failed: %s", error)

        await send_error_once(
            message.chat_id,
            context,
            str(error),
        )

    except Exception:
        logger.exception("Unexpected error in chat_with_ai")

        await send_error_once(
            message.chat_id,
            context,
            "فعلاً در پاسخ‌گویی مشکلی پیش آمده. کمی بعد دوباره امتحان کن.",
        )


# -----------------------------
# اجرای اصلی ربات
# -----------------------------

def main():

    if not TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده است.")

    if not API_KEY:
        raise RuntimeError("API_KEY تنظیم نشده است.")

    # اجرای سرور سلامت Railway
    health_thread = threading.Thread(
        target=start_health_server,
        daemon=True,
    )
    health_thread.start()

    logger.info("PULSE bot is starting...")

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CommandHandler("owner", owner_command)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            chat_with_ai,
        )
    )

    logger.info("PULSE bot is ready.")

    application.run_polling(
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
    
