
import os
import re
import json
import time
import asyncio
import logging
import threading
import urllib.request
import urllib.error

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from games.guess_number import register_guess_number_handlers
from games.tic_tac_toe import register_tictactoe_handlers


# =================================
# تنظیمات اصلی
# =================================

OWNER_ID = 7361198009

TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("API_KEY")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openrouter/free"

PORT = int(os.getenv("PORT", "10000"))

MAX_AI_REQUESTS = 2
MAX_RETRIES = 3

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("PULSE")

SYSTEM_PROMPT = """
تو دستیار هوشمند PULSE هستی.

با زبان فارسی طبیعی، روان و محترمانه صحبت کن.
پاسخ‌ها را متناسب با سؤال کاربر بنویس.
از جواب‌های تکراری و بیش از حد رسمی خودداری کن.
پاسخ‌ها را تا حد ممکن سریع، مفید و واضح ارائه بده.
اگر پاسخ چیزی را نمی‌دانی، صادقانه بگو.
اطلاعات محرمانه، کلیدها و توکن‌ها را افشا نکن.
بدون درخواست کاربر درباره کدنویسی، زیرساخت یا سازنده خودت توضیح نده.
"""

ai_semaphore = None


# =================================
# سرور سلامت Railway
# =================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"PULSE is running")

    def log_message(self, format, *args):
        return


def start_health_server():

    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler,
    )

    server.serve_forever()


# =================================
# ارتباط با OpenRouter
# =================================

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

    for attempt in range(MAX_RETRIES):

        try:

            with urllib.request.urlopen(
                request,
                timeout=45,
            ) as response:

                result = json.loads(
                    response.read().decode("utf-8")
                )

            answer = result["choices"][0]["message"]["content"]

            if isinstance(answer, str) and answer.strip():
                return answer.strip()

            raise RuntimeError("پاسخ خالی از سرویس دریافت شد.")

        except urllib.error.HTTPError as error:

            code = error.code

            if code == 401:
                raise RuntimeError("کلید اتصال معتبر نیست.")

            if code == 402:
                raise RuntimeError(
                    "سرویس درخواست را نپذیرفت؛ محدودیت اعتبار یا دسترسی مدل را بررسی کن."
                )

            if code == 429:

                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError(
                        "مدل رایگان فعلاً شلوغ است. کمی بعد دوباره امتحان کن."
                    )

                retry_after = error.headers.get("Retry-After")

                try:
                    wait_time = float(retry_after)
                except (TypeError, ValueError):
                    wait_time = 2 ** (attempt + 1)

                wait_time = min(max(wait_time, 2), 15)

                logger.warning(
                    "OpenRouter rate limit. Retry in %s seconds.",
                    wait_time,
                )

                time.sleep(wait_time)
                continue

            if code in (500, 502, 503, 504):

                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError(
                        "سرویس هوش مصنوعی موقتاً در دسترس نیست."
                    )

                time.sleep(2 ** attempt)
                continue

            logger.error("OpenRouter HTTP error: %s", code)

            raise RuntimeError(
                f"خطای ارتباط با سرویس: {code}"
            )

        except urllib.error.URLError as error:

            logger.warning("Connection error: %s", error)

            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(
                    "ارتباط با سرویس برقرار نشد."
                )

            time.sleep(2 ** attempt)

        except (KeyError, IndexError, json.JSONDecodeError) as error:

            logger.exception("Invalid AI response")

            raise RuntimeError(
                "پاسخ سرویس قابل خواندن نبود."
            ) from error

    raise RuntimeError("دریافت پاسخ با مشکل مواجه شد.")


# =================================
# تشخیص پیام‌های مجاز هوش مصنوعی
# =================================

def should_respond(update, context):

    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return False

    if chat.type == "private":
        return True

    bot_id = context.bot.id
    bot_username = context.bot.username

    if message.reply_to_message:

        replied_message = message.reply_to_message
        replied_user = replied_message.from_user

        if replied_user and replied_user.id == bot_id:
            return True

    if bot_username:

        text = message.text or message.caption or ""

        pattern = rf"@{re.escape(bot_username)}\b"

        if re.search(pattern, text, re.IGNORECASE):
            return True

    return False


# =================================
# مدیریت خطا
# =================================

async def send_error(message, error_text):

    try:
        await message.reply_text(error_text)

    except Exception:
        logger.exception("Could not send error message")


# =================================
# دستور شروع
# =================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.effective_message.reply_text(
        "سلام! من ربات هوشمند PULSE هستم. آماده‌ام! ✨"
    )


# =================================
# راهنما
# =================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = (
        "راهنمای استفاده از PULSE:\n\n"
        "در گفت‌وگوی خصوصی پیام خودت را بفرست.\n\n"
        "در گروه روی پیام PULSE ریپلای کن "
        "یا نام کاربری ربات را منشن کن.\n\n"
        "🎮 بازی‌های PULSE:\n\n"
        "بازی حدس عدد:\n"
        "/guessnumber\n\n"
        "بازی دوز:\n"
        "/tictactoe\n\n"
        "به پیام‌های عادی گروه پاسخ نمی‌دهم."
    )

    await update.effective_message.reply_text(text)


# =================================
# دستور مالک
# =================================

async def owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user or user.id != OWNER_ID:

        await update.effective_message.reply_text(
            "این دستور مخصوص مالک ربات است."
        )
        return

    await update.effective_message.reply_text(
        "پنل مالک PULSE\n\n"
        "وضعیت ربات: فعال\n"
        "مدل: OpenRouter Free"
    )


# =================================
# ارسال پاسخ طولانی
# =================================

async def send_long_message(message, text):

    max_length = 4000

    chunks = [
        text[index:index + max_length]
        for index in range(0, len(text), max_length)
    ]

    for chunk in chunks:

        await message.reply_text(
            chunk,
            disable_web_page_preview=True,
        )


# =================================
# دریافت و پردازش پیام هوش مصنوعی
# =================================

async def chat_with_ai(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    message = update.effective_message

    if not message:
        return

    user_text = message.text or message.caption or ""

    if not user_text.strip():
        return

    if not should_respond(update, context):
        return

    user_text = user_text.strip()

    username = context.bot.username

    if username:

        user_text = re.sub(
            rf"@{re.escape(username)}\b",
            "",
            user_text,
            flags=re.IGNORECASE,
        ).strip()

    if not user_text:

        await message.reply_text(
            "پیامت رو بنویس تا پاسخ بدم."
        )
        return

    try:

        async with ai_semaphore:

            await context.bot.send_chat_action(
                chat_id=message.chat_id,
                action=ChatAction.TYPING,
            )

            answer = await asyncio.to_thread(
                ask_ai,
                user_text,
            )

        if answer:
            await send_long_message(message, answer)

    except RuntimeError as error:

        logger.warning("AI request failed: %s", error)

        await send_error(message, str(error))

    except Exception:

        logger.exception("Unexpected error in chat_with_ai")

        await send_error(
            message,
            "در پاسخ‌گویی مشکلی پیش آمد. لطفاً دوباره امتحان کن.",
        )


# =================================
# اجرای اصلی
# =================================

def main():

    global ai_semaphore

    if not TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده است.")

    if not API_KEY:
        raise RuntimeError("API_KEY تنظیم نشده است.")

    health_thread = threading.Thread(
        target=start_health_server,
        daemon=True,
    )

    health_thread.start()

    logger.info("PULSE bot is starting...")

    application = (
        Application.builder()
        .token(TOKEN)
        .concurrent_updates(4)
        .build()
    )

    ai_semaphore = asyncio.Semaphore(MAX_AI_REQUESTS)

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CommandHandler("owner", owner_command)
    )

    # اتصال بازی‌های PULSE
    register_guess_number_handlers(application)
    register_tictactoe_handlers(application)

    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION) & ~filters.COMMAND,
            chat_with_ai,
        )
    )

    logger.info("PULSE bot is ready.")

    application.run_polling(
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
        
