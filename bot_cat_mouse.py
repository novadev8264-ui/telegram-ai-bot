
import os
import re
import logging
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ApplicationHandlerStop,
)

from games.guess_number import register_guess_number_handlers
from games.tic_tac_toe import register_tictactoe_handlers
from games.mafia import register_mafia_handlers, handle_mafia_start_payload
from pulse_cat_mouse import register_cat_mouse_handlers


# =================================
# تنظیمات اصلی PULSE
# =================================

OWNER_ID = 7361198009

TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("PULSE")


# =================================
# سرور سلامت Railway
# =================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"PULSE Games is running")

    def log_message(self, format, *args):
        return


def start_health_server():

    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler,
    )

    server.serve_forever()


# =================================
# پنل بازیگردان
# =================================

def owner_panel_keyboard(enabled):

    if enabled:
        status = "🟢 بازیگردان روشن است"
        toggle_button = InlineKeyboardButton(
            "🔴 خاموش کردن بازیگردان",
            callback_data="pulse_games_off",
        )
    else:
        status = "🔴 بازیگردان خاموش است"
        toggle_button = InlineKeyboardButton(
            "🟢 روشن کردن بازیگردان",
            callback_data="pulse_games_on",
        )

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                status,
                callback_data="pulse_games_status",
            )
        ],
        [toggle_button],
    ])


async def owner_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    if not user or user.id != OWNER_ID:
        await update.effective_message.reply_text(
            "این دستور مخصوص مالک ربات است."
        )
        return

    enabled = context.application.bot_data.get(
        "games_enabled",
        True,
    )

    await update.effective_message.reply_text(
        "🎮 <b>پنل مدیریت PULSE</b>\n\n"
        "از این قسمت می‌توانی فعالیت بازی‌ها را کنترل کنی.\n\n"
        f"وضعیت فعلی: {'🟢 روشن' if enabled else '🔴 خاموش'}",
        reply_markup=owner_panel_keyboard(enabled),
        parse_mode="HTML",
    )


async def toggle_games(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query
    user = query.from_user

    if user.id != OWNER_ID:
        await query.answer(
            "این دسترسی مخصوص مالک ربات است.",
            show_alert=True,
        )
        return

    if query.data == "pulse_games_on":
        context.application.bot_data["games_enabled"] = True
        message = "بازیگردان روشن شد. 🎮"

    elif query.data == "pulse_games_off":
        context.application.bot_data["games_enabled"] = False
        message = "بازیگردان خاموش شد. ⛔"

    else:
        enabled = context.application.bot_data.get(
            "games_enabled",
            True,
        )
        await query.answer(
            "وضعیت: " + ("روشن 🟢" if enabled else "خاموش 🔴"),
            show_alert=True,
        )
        return

    enabled = context.application.bot_data["games_enabled"]

    await query.answer(message)

    await query.edit_message_text(
        "🎮 <b>پنل مدیریت PULSE</b>\n\n"
        "از این قسمت می‌توانی فعالیت بازی‌ها را کنترل کنی.\n\n"
        f"وضعیت فعلی: {'🟢 روشن' if enabled else '🔴 خاموش'}",
        reply_markup=owner_panel_keyboard(enabled),
        parse_mode="HTML",
    )

    logger.info("Games enabled changed: %s", enabled)


# =================================
# کنترل روشن و خاموش بودن بازی‌ها
# =================================

GAME_TEXT_COMMANDS = re.compile(
    r"^\s*(بازی حدس عدد|بازی دوز|بازی مافیا|بازی موش و گربه)\s*$"
)

GAME_SLASH_COMMANDS = {
    "/guessnumber",
    "/tictactoe",
    "/mafia",
    "/mousegame",
    "/mousemap",
    "/mousestatus",
}


async def game_message_guard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    enabled = context.application.bot_data.get(
        "games_enabled",
        True,
    )

    if enabled:
        return

    message = update.effective_message

    if not message:
        return

    text = (message.text or "").strip()

    command = text.split("@")[0].split()[0] if text else ""

    is_game_command = (
        bool(GAME_TEXT_COMMANDS.fullmatch(text))
        or command in GAME_SLASH_COMMANDS
    )

    if is_game_command:
        await message.reply_text(
            "⛔ بازیگردان PULSE در حال حاضر خاموش است.\n"
            "لطفاً بعد از روشن شدن دوباره امتحان کن."
        )
        raise ApplicationHandlerStop


async def game_callback_guard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    enabled = context.application.bot_data.get(
        "games_enabled",
        True,
    )

    if enabled:
        return

    query = update.callback_query

    if not query:
        return

    # اجازه می‌دهیم مالک دکمه روشن کردن را بزند.
    if query.data in (
        "pulse_games_on",
        "pulse_games_off",
        "pulse_games_status",
    ):
        return

    await query.answer(
        "⛔ بازیگردان PULSE خاموش است.",
        show_alert=True,
    )

    raise ApplicationHandlerStop


# =================================
# دستور شروع
# =================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    # لینک اختصاصی دعوت مافیا به شکل /start mafia_<game_id>_<user_id>
    # ابتدا پردازش می‌شود؛ Start معمولی همچنان رفتار قبلی را دارد.
    handled = await handle_mafia_start_payload(update, context)
    if handled:
        return

    await update.effective_message.reply_text(
        "سلام! به ربات بازی‌های PULSE خوش آمدی. 🎮\n\n"
        "برای دیدن راهنما، دستور /help را بفرست."
    )


# =================================
# راهنمای بازی‌ها
# =================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = (
        "🎮 <b>راهنمای بازی‌های PULSE</b>\n\n"
        "🎯 بازی حدس عدد:\n"
        "بازی حدس عدد\n"
        "/guessnumber\n\n"
        "⭕ بازی دوز:\n"
        "بازی دوز\n"
        "/tictactoe\n\n"
        "🌙 بازی مافیا:\n"
        "بازی مافیا\n"
        "/mafia\n\n"
        "🐱 بازی موش و گربه:\n"
        "/mousegame برای ساخت بازی\n"
        "/mousemap برای نمایش نقشه\n"
        "/mousestatus برای وضعیت و بازیکنان\n\n"
        "برای مدیریت ربات، مالک می‌تواند از دستور /owner استفاده کند."
    )

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
    )


# =================================
# اجرای اصلی
# =================================

def main():

    if not TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده است.")

    health_thread = threading.Thread(
        target=start_health_server,
        daemon=True,
    )

    health_thread.start()

    logger.info("PULSE Games bot is starting...")

    application = (
        Application.builder()
        .token(TOKEN)
        .concurrent_updates(4)
        .build()
    )

    # وضعیت اولیه بازیگردان
    application.bot_data["games_enabled"] = True

    # دستورهای اصلی
    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CommandHandler("owner", owner_command)
    )

    # کنترل وضعیت بازی‌ها؛ قبل از هندلرهای بازی
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            game_message_guard,
        ),
        group=-1,
    )

    application.add_handler(
        CallbackQueryHandler(
            game_callback_guard,
        ),
        group=-1,
    )

    # دکمه‌های پنل مالک
    application.add_handler(
        CallbackQueryHandler(
            toggle_games,
            pattern=r"^pulse_games_(on|off|status)$",
        )
    )

    # اتصال بازی‌های PULSE
    register_guess_number_handlers(application)
    register_tictactoe_handlers(application)
    register_mafia_handlers(application)
    register_cat_mouse_handlers(application)

    logger.info("All PULSE games registered.")
    logger.info("PULSE Games bot is ready.")

    application.run_polling(
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()


  
