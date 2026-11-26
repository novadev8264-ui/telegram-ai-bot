
import logging
import random
import html
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, TelegramError
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
    begin_registration_check,
    reopen_registration,
    close_registration,
    remove_game,
)

from games.mafia_roles import (
    check_private_chats,
    send_private_roles,
)

from games.mafia_questions import get_mafia_questions

logger = logging.getLogger("PULSE.MAFIA")

MIN_PLAYERS = 4
MAX_PLAYERS = 15


ASSET_DIR = (
    Path(__file__).resolve().parent.parent
    / "telegram-ai-bot"
    / "games"
    / "assets"
    / "mafia"
)

IMAGE_FILES = [
    "file_00000000d2a481f4ba3c8367b292eaee.png",
    "file_00000000504481f4a7e8fa6eae44dd28.png",
    "IMG_۲۰۲۶۱۱۲۴_۲۰۱۷۵۹.jpg",
    "IMG_۲۰۲۶۱۱۲۴_۲۰۱۰۳۱.jpg",
    "IMG_۲۰۲۶۱۱۲۴_۲۰۱۰۱۲.jpg",
    "IMG_۲۰۲۶۱۱۲۴_۲۰۰۸۳۴.jpg",
]


def get_mafia_count(player_count):
    if 4 <= player_count <= 6:
        return 1
    if 7 <= player_count <= 9:
        return 2
    if 10 <= player_count <= 12:
        return 3
    if 13 <= player_count <= 15:
        return 4
    return 0


def assign_mafia_roles(players):
    player_ids = list(players.keys())
    mafia_count = get_mafia_count(len(player_ids))

    if not mafia_count:
        raise ValueError("تعداد بازیکنان برای شروع معتبر نیست.")

    mafia_ids = set(random.sample(player_ids, mafia_count))

    return {
        user_id: "mafia" if user_id in mafia_ids else "citizen"
        for user_id in player_ids
    }


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
        f"👥 بازیکنان ثبت‌نام‌شده: {len(players)} از {MAX_PLAYERS}",
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
        f"حداکثر بازیکنان: {MAX_PLAYERS} نفر",
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
    game["max_players"] = MAX_PLAYERS
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

    if query.from_user.id not in game["players"] and len(game["players"]) >= MAX_PLAYERS:
        await query.answer(
            f"ظرفیت بازی تکمیل شده است؛ حداکثر {MAX_PLAYERS} نفر.",
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
            "ثبت‌نام این بازی قبلاً بسته شده یا در حال بررسی است.",
            show_alert=True,
        )
        return

    player_count = len(game["players"])

    if player_count < MIN_PLAYERS:
        await query.answer(
            f"برای شروع حداقل {MIN_PLAYERS} بازیکن لازم است.",
            show_alert=True,
        )
        return

    if player_count > MAX_PLAYERS:
        await query.answer(
            f"حداکثر ظرفیت بازی {MAX_PLAYERS} نفر است.",
            show_alert=True,
        )
        return

    locked, result = await begin_registration_check(
        game_id,
        query.from_user.id,
    )

    if not locked:
        await query.answer(str(result), show_alert=True)
        return

    await query.answer("در حال بررسی چت خصوصی بازیکنان...")

    try:
        failed_players = await check_private_chats(
            context.bot,
            game,
            query.message.chat_id,
        )

    except TelegramError:
        logger.exception(
            "Private chat check failed: game=%s",
            game_id,
        )

        await reopen_registration(game_id)

        await update_message(
            query,
            (
                "⚠️ <b>بررسی چت خصوصی انجام نشد.</b>\n\n"
                "احتمالاً خطای موقت ارتباط با تلگرام رخ داده است.\n"
                "لطفاً کمی بعد دوباره تلاش کنید."
            ),
            registration_keyboard(game_id),
        )
        return

    if failed_players:
        await reopen_registration(game_id)

        await update_registration_message(query, game)

        if len(game["players"]) < MIN_PLAYERS:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    "⚠️ تعداد بازیکنان باقی‌مانده کمتر از حداقل لازم است.\n"
                    f"برای شروع دوباره باید حداقل {MIN_PLAYERS} نفر ثبت‌نام کنند."
                ),
            )

        logger.warning(
            "Players unavailable in private chat: game=%s removed=%s remaining=%s",
            game_id,
            len(failed_players),
            len(game["players"]),
        )
        return

    try:
        questions = await get_mafia_questions()

        if (
            not isinstance(questions, dict)
            or not questions.get("citizen")
            or not questions.get("mafia")
        ):
            raise ValueError("سؤال‌های معتبر برای بازی تولید نشدند.")

        roles = assign_mafia_roles(game["players"])

    except Exception:
        logger.exception(
            "Mafia question or role preparation failed: game=%s",
            game_id,
        )

        await reopen_registration(game_id)

        await update_message(
            query,
            (
                "⚠️ <b>آماده‌سازی بازی انجام نشد.</b>\n\n"
                "ثبت‌نام همچنان باز است.\n"
                "لطفاً کمی بعد دوباره تلاش کنید."
            ),
            registration_keyboard(game_id),
        )
        return

    success, result = await close_registration(
        game_id,
        query.from_user.id,
    )

    if not success:
        await reopen_registration(game_id)

        await update_message(
            query,
            f"⚠️ {html.escape(str(result))}",
            registration_keyboard(game_id),
        )
        return

    game["phase"] = "roles_pending"

    mafia_count = sum(1 for role in roles.values() if role == "mafia")

    try:
        roles_sent, failed_user_id = await send_private_roles(
            context.bot,
            game,
            roles,
            questions,
        )

    except Exception:
        logger.exception(
            "Unexpected error sending mafia roles: game=%s",
            game_id,
        )
        roles_sent = False
        failed_user_id = None

    if not roles_sent:
        logger.error(
            "Mafia role delivery failed: game=%s user=%s",
            game_id,
            failed_user_id,
        )

        await remove_game(game_id)

        await update_message(
            query,
            (
                "❌ <b>ارسال نقش‌ها با مشکل روبه‌رو شد.</b>\n\n"
                "بازی لغو شد تا نقش هیچ بازیکنی ناقص باقی نماند.\n"
                "لطفاً یک بازی جدید بسازید."
            ),
        )
        return

    game["phase"] = "roles_sent"

    await update_message(
        query,
        (
            "🌙 <b>بازی مافیای PULSE آغاز شد!</b>\n\n"
            f"👥 تعداد بازیکنان: {len(game['players'])}\n"
            f"🔴 تعداد مافیا: {mafia_count}\n"
            f"🟢 تعداد شهروندان: {len(game['players']) - mafia_count}\n\n"
            "🎭 نقش و سؤال اختصاصی هر بازیکن در چت خصوصی ارسال شد.\n"
            "🤫 نقش و سؤال خود را برای دیگران فاش نکنید."
        ),
    )

    logger.info(
        "Mafia game started: game=%s players=%s mafia=%s",
        game_id,
        len(game["players"]),
        mafia_count,
    )


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
    
