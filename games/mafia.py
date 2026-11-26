
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

MODULE_DIR = Path(__file__).resolve().parent

ASSET_DIR_CANDIDATES = [
    MODULE_DIR / "assets" / "mafia",
    MODULE_DIR.parent / "telegram-ai-bot" / "games" / "assets" / "mafia",
]

IMAGE_FILES = [
    "file_00000000d2a481f4ba3c8367b292eaee.png",
    "file_00000000504481f4a7e8fa6eae44dd28.png",
    "IMG_۲۰۲۶۱۱۲۴_۲۰۱۷۵۹.jpg",
    "IMG_۲۰۲۶۱۱۲۴_۲۰۱۰۳۱.jpg",
    "IMG_۲۰۲۶۱۱۲۴_۲۰۱۰۱۲.jpg",
    "IMG_۲۰۲۶۱۱۲۴_۲۰۰۸۳۴.jpg",
]


def get_asset_directory():
    """پیدا کردن پوشه تصاویر مافیا."""

    for directory in ASSET_DIR_CANDIDATES:
        if directory.is_dir():
            return directory

    return ASSET_DIR_CANDIDATES[0]


def get_mafia_count(player_count):
    """تعیین تعداد مافیا بر اساس تعداد بازیکنان."""

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
    """تخصیص تصادفی نقش شهروند و مافیا."""

    player_ids = list(players.keys())
    mafia_count = get_mafia_count(len(player_ids))

    if not mafia_count:
        raise ValueError(
            "تعداد بازیکنان برای شروع معتبر نیست."
        )

    mafia_ids = set(
        random.sample(player_ids, mafia_count)
    )

    return {
        user_id: (
            "mafia" if user_id in mafia_ids else "citizen"
        )
        for user_id in player_ids
    }


def get_character_images():
    """بررسی تصاویر معرفی بازی مافیا."""

    asset_dir = get_asset_directory()

    logger.info("Mafia asset directory: %s", asset_dir)
    logger.info("Asset directory exists: %s", asset_dir.is_dir())

    if not asset_dir.is_dir():
        logger.error(
            "Mafia image directory does not exist: %s",
            asset_dir,
        )
        return []

    images = []

    for filename in IMAGE_FILES:
        image_path = asset_dir / filename

        if not image_path.is_file():
            logger.warning(
                "Mafia image missing: %s",
                image_path,
            )
            continue

        try:
            if image_path.stat().st_size > 0:
                images.append(image_path)
            else:
                logger.warning(
                    "Mafia image is empty: %s",
                    image_path,
                )

        except OSError:
            logger.exception(
                "Could not inspect image: %s",
                image_path,
            )

    logger.info(
        "Mafia images available: %s",
        len(images),
    )

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
    """ساخت فهرست بازیکنان ثبت‌نام‌شده."""

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
            lines.append(
                f"{number}. {player['mention']}"
            )

    lines.extend([
        "",
        f"حداقل بازیکنان برای شروع: {MIN_PLAYERS} نفر",
        f"حداکثر بازیکنان: {MAX_PLAYERS} نفر",
        "",
        "برای شرکت در بازی، دکمه ورود را انتخاب کنید.",
    ])

    return "\n".join(lines)


async def update_message(query, text, keyboard=None):
    """به‌روزرسانی پیام بازی، چه تصویری باشد چه متنی."""

    try:
        message = query.message

        if message is None:
            logger.warning(
                "Cannot update mafia message: message is unavailable."
            )
            return False

        if message.photo:
            await query.edit_message_caption(
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        else:
            await query.edit_message_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )

        return True

    except TelegramError:
        logger.exception(
            "Could not update mafia message."
        )
        return False


async def update_registration_message(query, game):
    return await update_message(
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

    logger.info("Mafia command received.")

    available_images = get_character_images()

    if available_images:
        selected_image = random.choice(available_images)

        try:
            with selected_image.open("rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=intro_text(),
                    reply_markup=intro_keyboard(),
                    parse_mode="HTML",
                )

            logger.info(
                "Mafia intro image sent: %s",
                selected_image.name,
            )
            return

        except Exception:
            logger.exception(
                "Mafia image send failed: %s",
                selected_image.name,
            )

    try:
        await update.message.reply_text(
            intro_text(),
            reply_markup=intro_keyboard(),
            parse_mode="HTML",
        )

    except TelegramError:
        logger.exception(
            "Mafia text introduction could not be sent."
        )


async def create_mafia_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    await query.answer()

    user = query.from_user

    game = create_game("mafia", user)

    game["min_players"] = MIN_PLAYERS
    game["max_players"] = MAX_PLAYERS
    game["phase"] = "registration"

    joined, message = await join_game(
        game["id"],
        user,
        max_players=MAX_PLAYERS,
    )

    if not joined:
        await remove_game(game["id"])
        await query.answer(
            message,
            show_alert=True,
        )
        return

    await update_registration_message(
        query,
        game,
    )

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

    if query is None:
        return

    game_id = query.data.split(":", 1)[1]
    game = get_game(game_id)

    if not game or game["type"] != "mafia":
        await query.answer(
            "این بازی پیدا نشد.",
            show_alert=True,
        )
        return

    if game["status"] != "registering":
        await query.answer(
            "ثبت‌نام این بازی بسته شده است.",
            show_alert=True,
        )
        return

    success, message = await join_game(
        game_id,
        query.from_user,
        max_players=MAX_PLAYERS,
    )

    if not success:
        await query.answer(
            message,
            show_alert=True,
        )
        return

    await query.answer(
        "با موفقیت وارد بازی شدی."
    )

    await update_registration_message(
        query,
        game,
    )


async def show_mafia_players(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    game_id = query.data.split(":", 1)[1]
    game = get_game(game_id)

    if not game or game["type"] != "mafia":
        await query.answer(
            "این بازی پیدا نشد.",
            show_alert=True,
        )
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

    if query is None:
        return

    game_id = query.data.split(":", 1)[1]
    game = get_game(game_id)

    if not game or game["type"] != "mafia":
        await query.answer(
            "این بازی پیدا نشد.",
            show_alert=True,
        )
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

    await query.answer(
        "بازی با موفقیت لغو شد."
    )

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

    if query is None:
        return

    game_id = query.data.split(":", 1)[1]
    game = get_game(game_id)

    if not game or game["type"] != "mafia":
        await query.answer(
            "این بازی پیدا نشد.",
            show_alert=True,
        )
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
        await query.answer(
            str(result),
            show_alert=True,
        )
        return

    game = result

    await query.answer(
        "در حال بررسی چت خصوصی بازیکنان..."
    )

    try:
        failed_players = await check_private_chats(
            context.bot,
            game,
            query.message.chat_id,
        )

    except Exception:
        logger.exception(
            "Private chat check failed: game=%s",
            game_id,
        )

        await reopen_registration(game_id)

        await update_message(
            query,
            (
                "⚠️ <b>بررسی چت خصوصی انجام نشد.</b>\n\n"
                "یک خطا هنگام ارتباط با تلگرام رخ داد.\n"
                "ثبت‌نام دوباره باز شد؛ لطفاً کمی بعد تلاش کنید."
            ),
            registration_keyboard(game_id),
        )
        return

    if failed_players:
        await reopen_registration(game_id)

        await update_registration_message(
            query,
            game,
        )

        if len(game["players"]) < MIN_PLAYERS:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    "⚠️ تعداد بازیکنان باقی‌مانده کمتر از حداقل لازم است.\n"
                    f"برای شروع دوباره باید حداقل {MIN_PLAYERS} نفر ثبت‌نام کنند."
                ),
            )

        logger.warning(
            "Unavailable players: game=%s removed=%s remaining=%s",
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
            raise ValueError(
                "سؤال‌های معتبر برای بازی تولید نشدند."
            )

        roles = assign_mafia_roles(
            game["players"]
        )

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

    game = result
    game["phase"] = "roles_pending"

    mafia_count = sum(
        1
        for role in roles.values()
        if role == "mafia"
    )

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
                "❌ <b>ارسال نقش‌ها کامل نشد و بازی لغو شد.</b>\n\n"
                "ممکن است بعضی بازیکنان پیام نقش خود را دریافت کرده باشند.\n"
                "لطفاً از ادامه این بازی خودداری کنید و یک بازی جدید بسازید."
            ),
        )
        return

    game["phase"] = "roles_sent"

    await update_message(
        query,
        (
            "🌙 <b>نقش‌های بازی مافیای PULSE ارسال شدند!</b>\n\n"
            f"👥 تعداد بازیکنان: {len(game['players'])}\n"
            f"🔴 تعداد مافیا: {mafia_count}\n"
            f"🟢 تعداد شهروندان: {len(game['players']) - mafia_count}\n\n"
            "🎭 نقش و سؤال اختصاصی هر بازیکن در چت خصوصی ارسال شد.\n"
            "🤫 نقش و سؤال خود را برای دیگران فاش نکنید."
        ),
    )

    logger.info(
        "Mafia roles sent: game=%s players=%s mafia=%s",
        game_id,
        len(game["players"]),
        mafia_count,
    )


def register_mafia_handlers(application: Application):
    """ثبت دستورها و دکمه‌های بازی مافیا."""

    application.add_handler(
        CommandHandler(
            "mafia",
            mafia_command,
        )
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

    logger.info(
        "Mafia handlers registered successfully."
    )
    
