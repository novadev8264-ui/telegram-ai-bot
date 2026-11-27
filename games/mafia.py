
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
    send_private_roles,
    send_private_invitation,
    send_pending_role_to_player,
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
    if query is None or query.message is None:
        return

    game_id = query.data.split(":", 1)[1]
    game = get_game(game_id)
    if not game or game.get("type") != "mafia":
        await query.answer("این بازی پیدا نشد.", show_alert=True)
        return
    if game["owner_id"] != query.from_user.id:
        await query.answer("فقط برگزارکننده می‌تواند بازی را شروع کند.", show_alert=True)
        return
    if game["status"] != "registering":
        await query.answer("این بازی در حال بررسی یا قبلاً شروع شده است.", show_alert=True)
        return

    player_count = len(game["players"])
    if player_count < MIN_PLAYERS:
        await query.answer(f"برای شروع حداقل {MIN_PLAYERS} بازیکن لازم است.", show_alert=True)
        return
    if player_count > MAX_PLAYERS:
        await query.answer(f"حداکثر ظرفیت بازی {MAX_PLAYERS} نفر است.", show_alert=True)
        return

    locked, result = await begin_registration_check(game_id, query.from_user.id)
    if not locked:
        await query.answer(str(result), show_alert=True)
        return
    game = result
    await query.answer("در حال آماده‌سازی و ارسال نقش‌ها...")

    # Generate roles/questions once and keep them while players activate their DMs.
    try:
        questions = await get_mafia_questions()
        if (not isinstance(questions, dict)
                or not isinstance(questions.get("citizen"), str)
                or not questions["citizen"].strip()
                or not isinstance(questions.get("mafia"), str)
                or not questions["mafia"].strip()):
            raise ValueError("سؤال‌های معتبر برای بازی تولید نشدند.")
        roles = assign_mafia_roles(game["players"])
    except Exception:
        logger.exception("Mafia question or role preparation failed: game=%s", game_id)
        await reopen_registration(game_id)
        await update_message(
            query,
            "⚠️ <b>آماده‌سازی بازی انجام نشد.</b>\n\nثبت‌نام باز ماند؛ لطفاً کمی بعد دوباره تلاش کنید.",
            registration_keyboard(game_id),
        )
        return

    success, result = await close_registration(game_id, query.from_user.id)
    if not success:
        await reopen_registration(game_id)
        await update_message(query, f"⚠️ {html.escape(str(result))}", registration_keyboard(game_id))
        return

    game = result
    game["roles"] = roles
    game["questions"] = questions
    game["role_delivered"] = set()
    game["role_pending"] = set()
    game["phase"] = "roles_pending"

    try:
        pending_ids = await send_private_roles(context.bot, game, roles, questions)
        if pending_ids:
            await send_private_invitation(context.bot, game, query.message.chat_id, pending_ids)
    except Exception:
        logger.exception("Mafia role delivery workflow failed: game=%s", game_id)
        # Do not destroy the game or reroll roles. The organizer can retry after fixing the issue.
        await update_message(
            query,
            "⚠️ <b>ارسال بعضی پیام‌ها با خطا روبه‌رو شد.</b>\n\nبازی و نقش‌های تعیین‌شده حفظ شده‌اند. لاگ Railway را بررسی کنید.",
        )
        return

    mafia_count = sum(1 for role in roles.values() if role == "mafia")
    if pending_ids:
        game["phase"] = "roles_pending"
        await update_message(
            query,
            (
                "⏳ <b>بازی آماده است؛ ارسال نقش بعضی بازیکنان در انتظار فعال‌سازی پیوی است.</b>\n\n"
                f"👥 بازیکنان: {len(game['players'])}\n"
                f"🔴 مافیا: {mafia_count}\n"
                f"🟢 شهروند: {len(game['players']) - mafia_count}\n\n"
                "بازیکنان دعوت‌شده پس از زدن Start، نقش و سؤال خود را خودکار دریافت می‌کنند."
            ),
        )
    else:
        game["phase"] = "roles_sent"
        await update_message(
            query,
            (
                "🌙 <b>نقش‌های بازی مافیای PULSE برای همه ارسال شدند!</b>\n\n"
                f"👥 تعداد بازیکنان: {len(game['players'])}\n"
                f"🔴 تعداد مافیا: {mafia_count}\n"
                f"🟢 تعداد شهروندان: {len(game['players']) - mafia_count}\n\n"
                "🎭 نقش و سؤال اختصاصی در پیوی همه بازیکنان ارسال شد."
            ),
        )

    logger.info(
        "Mafia role dispatch complete: game=%s players=%s delivered=%s pending=%s mafia=%s",
        game_id, len(game["players"]), len(game["role_delivered"]), len(pending_ids), mafia_count,
    )


async def handle_mafia_start_payload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle a player-specific deep link and immediately deliver their pending role."""
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    args = context.args or []

    if not message or not chat or not user or chat.type != "private":
        return False
    if not args or not args[0].startswith("mafia_"):
        return False

    parts = args[0].split("_")
    if len(parts) != 3:
        await message.reply_text("لینک دعوت مافیا معتبر نیست.")
        return True

    _, game_id, invited_user_id = parts
    try:
        invited_user_id = int(invited_user_id)
    except ValueError:
        await message.reply_text("لینک دعوت مافیا معتبر نیست.")
        return True

    if user.id != invited_user_id:
        await message.reply_text("این لینک مخصوص بازیکن دیگری است. لطفاً دکمه مربوط به نام خودت را در گروه بزن.")
        return True

    game = get_game(game_id)
    if not game or game.get("type") != "mafia":
        await message.reply_text("این بازی دیگر در حافظه ربات فعال نیست. از برگزارکننده بخواه بازی را دوباره ایجاد کند.")
        return True

    if user.id not in game.get("players", {}):
        await message.reply_text("نام شما در فهرست این بازی نیست. ابتدا از داخل گروه ثبت‌نام کن.")
        return True

    # The user has now opened the private conversation. Deliver the already-assigned role.
    try:
        delivered, response = await send_pending_role_to_player(context.bot, game, user.id)
    except TelegramError:
        logger.exception("Could not deliver pending role after deep link: game=%s user=%s", game_id, user.id)
        await message.reply_text("پیوی فعال شد، اما ارسال نقش با خطای تلگرام مواجه شد. لطفاً به برگزارکننده اطلاع بده.")
        return True

    await message.reply_text(("✅ " if delivered else "⚠️ ") + response)
    if delivered:
        pending = game.get("role_pending", set())
        pending.discard(user.id)
        if not pending and len(game.get("role_delivered", set())) == len(game.get("players", {})):
            game["phase"] = "roles_sent"
            logger.info("All mafia roles delivered: game=%s", game_id)
    logger.info("Mafia private activation processed: game=%s user=%s delivered=%s", game_id, user.id, delivered)
    return True


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

                    
