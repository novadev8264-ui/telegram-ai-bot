
import logging
import random
import html
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from games.manager import (
    create_game,
    get_game,
    join_game,
    close_registration,
    remove_game,
)

from games.mafia_roles import check_private_chats

logger = logging.getLogger("PULSE.MAFIA")

MIN_PLAYERS = 4

# مسیر واقعی پوشه تصاویر در مخزن GitHub
ASSET_DIR = (
    Path(__file__).resolve().parent.parent
    / "telegram-ai-bot"
    / "games"
    / "assets"
    / "mafia"
)

# نام واقعی ۶ تصویر؛ بدون تغییر نام فایل‌ها
IMAGE_FILES = [
    "file_00000000d2a481f4ba3c8367b292eaee.png",
    "file_00000000504481f4a7e8fa6eae44dd28.png",
    "IMG_۲۰۲۶۱۱۲۴_۲۰۱۷۵۹.jpg",
    "IMG_۲۰۲۶۱۱۲۴_۲۰۱۰۳۱.jpg",
    "IMG_۲۰۲۶۱۱۲۴_۲۰۱۰۱۲.jpg",
    "IMG_۲۰۲۶۱۱۲۴_۲۰۰۸۳۴.jpg",
]


def get_character_images():
    logger.warning("========== MAFIA IMAGE DIAGNOSTICS ==========")
    logger.warning("Mafia asset directory: %s", ASSET_DIR.resolve())
    logger.warning("Directory exists: %s", ASSET_DIR.is_dir())

    if not ASSET_DIR.is_dir():
        logger.error("MAFIA IMAGE ERROR: Asset directory does not exist.")
        return []

    images = []

    for filename in IMAGE_FILES:
        image_path = ASSET_DIR / filename

        if not image_path.is_file():
            logger.error("MAFIA IMAGE MISSING: %s", image_path)
            continue

        try:
            size = image_path.stat().st_size

            logger.warning(
                "MAFIA FILE CHECK: name=%s size=%s bytes",
                filename,
                size,
            )

            if size > 0:
                images.append(image_path)
            else:
                logger.error("MAFIA IMAGE EMPTY: %s", filename)

        except Exception:
            logger.exception("Could not inspect image: %s", filename)

    logger.warning("Supported images found: %s", len(images))
    logger.warning("========== END IMAGE DIAGNOSTICS ==========")

    return images


def intro_text():
    return (
        "🌙 <b>به بازی مافیای PULSE خوش آمدید</b>\n\n"
        "در این بازی، شهروندان و مافیا در برابر یکدیگر قرار می‌گیرند.\n"
        "با دقت، استدلال و رأی‌گیری تلاش کنید تیم خود را به پیروزی برسانید.\n\n"
        "👥 برای شروع، برگزارکننده باید بازی جدیدی بسازد.\n"
        "🎭 نقش‌ها در مراحل بعدی بازی به‌صورت خصوصی برای بازیکنان ارسال می‌شوند."
    )


def intro_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎮 ساخت بازی",
                callback_data="mafia_create",
            )
        ]
    ])


def registration_keyboard(game_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎮 ورود به بازی",
                callback_data=f"mafia_join:{game_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "👥 نمایش بازیکنان",
                callback_data=f"mafia_players:{game_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "🏁 شروع بازی",
                callback_data=f"mafia_start:{game_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "❌ لغو بازی",
                callback_data=f"mafia_cancel:{game_id}",
            )
        ],
    ])


def player_list_text(game):
    players = game["players"]

    lines = [
        "🌙 <b>بازی مافیای PULSE</b>",
        "",
        f"🆔 کد بازی: <code>{html.escape(str(game['id']))}</code>",
        f"👑 برگزارکننده: {html.escape(game['owner_name'])}",
        "",
        f"👥 بازیکنان ثبت‌نام‌شده: {len(players)}",
        "",
        "📋 <b>فهرست بازیکنان:</b>",
    ]

    if not players:
        lines.append("هنوز کسی ثبت‌نام نکرده است.")
    else:
        for number, player in enumerate(players.values(), 1):
            lines.append(f"{number}. {player['mention']}")

    lines.extend([
        "",
        f"حداقل بازیکنان برای شروع: {MIN_PLAYERS} نفر",
        "",
        "برای شرکت در بازی، دکمه ورود را انتخاب کنید.",
    ])

    return "\n".join(lines)


async def update_message(query, text, keyboard=None):
    try:
        await query.edit_message_caption(
            caption=text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return
    except BadRequest:
        pass

    try:
        await query.edit_message_text(
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    except BadRequest:
        logger.exception("Could not update mafia message")


async def update_registration_message(query, game):
    await update_message(
        query,
        player_list_text(game),
        registration_keyboard(game["id"]),
    )


async def mafia_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    logger.warning("MAFIA COMMAND RECEIVED")

    available_images = get_character_images()

    if available_images:
        selected_image = random.choice(available_images)

        logger.warning(
            "Selected mafia image: %s",
            selected_image.name,
        )

        try:
            with selected_image.open("rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=intro_text(),
                    reply_markup=intro_keyboard(),
                    parse_mode="HTML",
                )

            logger.warning(
                "MAFIA INTRO IMAGE SENT SUCCESSFULLY: %s",
                selected_image.name,
            )
            return

        except Exception:
            logger.exception(
                "MAFIA IMAGE SEND FAILED: %s",
                selected_image.name,
            )

    else:
        logger.error(
            "MAFIA INTRO: No image available. Sending text-only intro."
        )

    try:
        await update.message.reply_text(
            intro_text(),
            reply_markup=intro_keyboard(),
            parse_mode="HTML",
        )
        logger.warning("MAFIA TEXT INTRO SENT")
    except Exception:
        logger.exception("MAFIA TEXT INTRO SEND FAILED")


async def create_mafia_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    game = create_game("mafia", user)

    await join_game(game["id"], user)

    game["min_players"] = MIN_PLAYERS
    game["phase"] = "registration"

    await update_registration_message(query, game)

    logger.info(
        "Mafia registration created: game=%s owner=%s",
        game["id"],
        user.id,
    )


async def join_mafia_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    game_id = query.data.split(":", 1)[1]
    game = get_game(game_id)

    if not game or game["type"] != "mafia":
        await query.answer("این بازی پیدا نشد.", show_alert=True)
        return

    if game["status"] != "registering":
        await query.answer(
            "ثبت‌نام این بازی بسته شده است.",
            show_alert=True,
        )
        return

    success, message = await join_game(game_id, query.from_user)

    if not success:
        await query.answer(message, show_alert=True)
        return

    await query.answer("با موفقیت وارد بازی شدی.")
    await update_registration_message(query, game)


async def show_mafia_players(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    game_id = query.data.split(":", 1)[1]
    game = get_game(game_id)

    if not game or game["type"] != "mafia":
        await query.answer("این بازی پیدا نشد.", show_alert=True)
        return

    await query.answer(
        f"تعداد بازیکنان: {len(game['players'])}",
        show_alert=True,
    )


async def cancel_mafia_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    game_id = query.data.split(":", 1)[1]
    game = get_game(game_id)

    if not game or game["type"] != "mafia":
        await query.answer("این بازی پیدا نشد.", show_alert=True)
        return

    if game["owner_id"] != query.from_user.id:
        await query.answer(
            "فقط برگزارکننده می‌تواند بازی را لغو کند.",
            show_alert=True,
        )
        return

    if game["status"] != "registering":
        await query.answer(
            "این بازی دیگر در مرحله ثبت‌نام نیست.",
            show_alert=True,
        )
        return

    await remove_game(game_id)
    await query.answer("بازی با موفقیت لغو شد.")

    await update_message(
        query,
        "❌ <b>این بازی توسط برگزارکننده لغو شد.</b>",
    )

    logger.info(
        "Mafia game cancelled: game=%s owner=%s",
        game_id,
        query.from_user.id,
    )


async def start_mafia_registration(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    game_id = query.data.split(":", 1)[1]
    game = get_game(game_id)

    if not game or game["type"] != "mafia":
        await query.answer("این بازی پیدا نشد.", show_alert=True)
        return

    if game["owner_id"] != query.from_user.id:
        await query.answer(
            "فقط برگزارکننده می‌تواند بازی را شروع کند.",
            show_alert=True,
        )
        return

    if game["status"] != "registering":
        await query.answer(
            "ثبت‌نام این بازی قبلاً بسته شده است.",
            show_alert=True,
        )
        return

    if len(game["players"]) < MIN_PLAYERS:
        await query.answer(
            f"برای شروع حداقل {MIN_PLAYERS} بازیکن لازم است.",
            show_alert=True,
        )
        return

    failed_players = await check_private_chats(
        context.bot,
        game,
        query.message.chat_id,
    )

    if failed_players:
        await query.answer(
            "چت خصوصی بعضی بازیکنان فعال نیست. ثبت‌نام همچنان باز است.",
            show_alert=True,
        )

        await update_registration_message(query, game)
        return

    success, result = await close_registration(
        game_id,
        query.from_user.id,
    )

    if not success:
        await query.answer(result, show_alert=True)
        return

    game["phase"] = "roles_pending"

    await query.answer("ثبت‌نام بسته شد.")

    await update_message(
        query,
        (
            "🌙 <b>ثبت‌نام بازی مافیا بسته شد!</b>\n\n"
            f"👥 تعداد بازیکنان: {len(game['players'])}\n"
            "✅ بازیکنان با موفقیت ثبت‌نام شدند.\n\n"
            "🎭 مرحله بعد: آماده‌سازی و ارسال خصوصی نقش‌ها."
        ),
    )

    logger.info("Mafia registration closed: game=%s", game_id)


def register_mafia_handlers(application: Application):
    application.add_handler(
        CommandHandler("mafia", mafia_command)
    )

    application.add_handler(
        MessageHandler(
            filters.Regex(r"^\s*بازی مافیا\s*$"),
            mafia_command,
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            create_mafia_game,
            pattern=r"^mafia_create$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            join_mafia_game,
            pattern=r"^mafia_join:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            show_mafia_players,
            pattern=r"^mafia_players:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            start_mafia_registration,
            pattern=r"^mafia_start:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            cancel_mafia_game,
            pattern=r"^mafia_cancel:",
        )
    )

    logger.info("Mafia handlers registered successfully")
        
