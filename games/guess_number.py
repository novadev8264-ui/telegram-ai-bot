
import html
import logging
import random

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from games.manager import (
    ACTIVE_GAMES,
    create_game,
    join_game,
    close_registration,
    finish_game,
)

logger = logging.getLogger("PULSE.GAMES.GUESS_NUMBER")

MIN_NUMBER = 1
MAX_NUMBER = 20
MIN_PLAYERS = 2


# =================================
# لینک پروفایل بازیکن
# =================================

def make_player_link(player):
    name = html.escape(player.get("name") or "بازیکن")

    if player.get("username"):
        username = html.escape(player["username"])
        return f'<a href="https://t.me/{username}">{name}</a>'

    return f'<a href="tg://user?id={player["id"]}">{name}</a>'


def make_owner_link(game):
    name = html.escape(game.get("owner_name") or "برگزارکننده")
    return (
        f'<a href="tg://user?id={game["owner_id"]}">'
        f'{name}</a>'
    )


# =================================
# متن ثبت‌نام
# =================================

def registration_text(game):
    players = list(game["players"].values())

    lines = [
        "🎯 <b>بازی حدس عدد PULSE</b>",
        "",
        f"👑 برگزارکننده: {make_owner_link(game)}",
        f"🔢 محدوده عدد: {MIN_NUMBER} تا {MAX_NUMBER}",
        f"👥 تعداد بازیکنان: {len(players)}",
        "",
        "<b>بازیکنان ثبت‌نام‌شده:</b>",
    ]

    if not players:
        lines.append("هنوز کسی ثبت‌نام نکرده است.")
    else:
        for index, player in enumerate(players, 1):
            lines.append(
                f"{index}. {make_player_link(player)}"
            )

    lines.extend([
        "",
        f"برای شروع حداقل {MIN_PLAYERS} بازیکن لازم است.",
        "برای شرکت روی دکمه ورود بزن.",
    ])

    return "\n".join(lines)


def registration_keyboard(game_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎮 ورود به بازی",
                callback_data=f"gn_join:{game_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "👥 بازیکنان",
                callback_data=f"gn_players:{game_id}",
            ),
            InlineKeyboardButton(
                "🏁 شروع بازی",
                callback_data=f"gn_start:{game_id}",
            ),
        ],
    ])


# =================================
# دکمه‌های حدس عدد
# =================================

def guess_keyboard(game_id):
    rows = []

    for start in range(MIN_NUMBER, MAX_NUMBER + 1, 4):
        row = []

        for number in range(
            start,
            min(start + 4, MAX_NUMBER + 1),
        ):
            row.append(
                InlineKeyboardButton(
                    str(number),
                    callback_data=f"gn_guess:{game_id}:{number}",
                )
            )

        rows.append(row)

    return InlineKeyboardMarkup(rows)


# =================================
# متن بازی
# =================================

def playing_text(game, message=None):
    players = list(game["players"].values())

    if not players:
        return "بازیکنی برای ادامه بازی وجود ندارد."

    current_index = game["turn_index"] % len(players)
    current_player = players[current_index]

    text = (
        "🎯 <b>بازی حدس عدد PULSE شروع شد!</b>\n\n"
        f"🔢 عدد مخفی بین {MIN_NUMBER} تا {MAX_NUMBER} است.\n"
        f"👥 تعداد بازیکنان: {len(players)}\n"
        f"🎲 تعداد حدس‌ها: {game['attempts']}\n\n"
        f"⏳ نوبت: {make_player_link(current_player)}\n"
    )

    if message:
        text += f"\n{message}\n"

    text += "\n👇 عدد موردنظرت را انتخاب کن:"

    return text


# =================================
# شروع بازی با دستور
# =================================

async def guess_number_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    message = update.effective_message

    if not user or not message:
        return

    if message.chat.type not in ("group", "supergroup"):
        await message.reply_text(
            "این بازی را داخل گروه تلگرام اجرا کن."
        )
        return

    game = create_game("guess_number", user)

    success, result = await join_game(game["id"], user)

    if not success:
        await message.reply_text(result)
        return

    game["attempts"] = 0
    game["turn_index"] = 0
    game["secret_number"] = None

    await message.reply_text(
        registration_text(game),
        reply_markup=registration_keyboard(game["id"]),
        parse_mode=ParseMode.HTML,
    )


# =================================
# ورود بازیکن
# =================================

async def guess_join_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    game_id = query.data.split(":")[1]

    game = ACTIVE_GAMES.get(game_id)

    if not game:
        await query.answer(
            "این بازی پیدا نشد.",
            show_alert=True,
        )
        return

    success, result = await join_game(
        game_id,
        query.from_user,
    )

    await query.answer(
        result,
        show_alert=not success,
    )

    if success:
        try:
            await query.edit_message_text(
                registration_text(game),
                reply_markup=registration_keyboard(game_id),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.exception("Could not update registration message")


# =================================
# نمایش بازیکنان
# =================================

async def guess_players_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    game_id = query.data.split(":")[1]

    game = ACTIVE_GAMES.get(game_id)

    if not game:
        await query.answer(
            "بازی پیدا نشد.",
            show_alert=True,
        )
        return

    players = list(game["players"].values())

    if not players:
        text = "هنوز کسی ثبت‌نام نکرده است."
    else:
        lines = [
            f"{index}. {make_player_link(player)}"
            for index, player in enumerate(players, 1)
        ]
        text = "\n".join(lines)

    await query.answer(
        f"تعداد بازیکنان: {len(players)}",
        show_alert=True,
    )


# =================================
# شروع بازی توسط برگزارکننده
# =================================

async def guess_start_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    game_id = query.data.split(":")[1]

    game = ACTIVE_GAMES.get(game_id)

    if not game:
        await query.answer(
            "بازی پیدا نشد.",
            show_alert=True,
        )
        return

    if query.from_user.id != game["owner_id"]:
        await query.answer(
            "فقط برگزارکننده می‌تواند بازی را شروع کند.",
            show_alert=True,
        )
        return

    if game["status"] != "registering":
        await query.answer(
            "این بازی قبلاً شروع شده است.",
            show_alert=True,
        )
        return

    if len(game["players"]) < MIN_PLAYERS:
        await query.answer(
            f"برای شروع حداقل {MIN_PLAYERS} بازیکن لازم است.",
            show_alert=True,
        )
        return

    success, result = await close_registration(
        game_id,
        query.from_user.id,
    )

    if not success:
        await query.answer(result, show_alert=True)
        return

    game["secret_number"] = random.randint(
        MIN_NUMBER,
        MAX_NUMBER,
    )
    game["attempts"] = 0
    game["turn_index"] = 0

    await query.answer("بازی شروع شد! 🎯")

    await query.edit_message_text(
        playing_text(game, "🚀 بازی آغاز شد!"),
        reply_markup=guess_keyboard(game_id),
        parse_mode=ParseMode.HTML,
    )


# =================================
# ثبت حدس بازیکن
# =================================

async def guess_number_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    try:
        _, game_id, number_text = query.data.split(":")
        guessed_number = int(number_text)
    except (ValueError, AttributeError):
        await query.answer(
            "درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    if not MIN_NUMBER <= guessed_number <= MAX_NUMBER:
        await query.answer(
            "این عدد در محدوده بازی نیست.",
            show_alert=True,
        )
        return

    game = ACTIVE_GAMES.get(game_id)

    if not game:
        await query.answer(
            "این بازی پیدا نشد.",
            show_alert=True,
        )
        return

    if game["status"] != "playing":
        await query.answer(
            "این بازی در حال اجرا نیست.",
            show_alert=True,
        )
        return

    players = list(game["players"].values())

    if not players:
        await query.answer(
            "بازیکنی در بازی وجود ندارد.",
            show_alert=True,
        )
        return

    current_index = game["turn_index"] % len(players)
    current_player = players[current_index]

    if query.from_user.id != current_player["id"]:
        await query.answer(
            "الان نوبت شما نیست!",
            show_alert=True,
        )
        return

    game["attempts"] += 1
    secret = game["secret_number"]

    # پاسخ صحیح
    if guessed_number == secret:
        await finish_game(game_id, query.from_user.id)

        winner = make_player_link(current_player)

        await query.answer("آفرین! عدد را درست حدس زدی.")

        await query.edit_message_text(
            "🏆 <b>بازی تمام شد!</b>\n\n"
            f"🎉 برنده: {winner}\n"
            f"🔢 عدد مخفی: <b>{secret}</b>\n"
            f"🎯 تعداد حدس‌ها: {game['attempts']}\n\n"
            "🔥 تبریک به برنده بازی PULSE!",
            parse_mode=ParseMode.HTML,
        )
        return

    # پاسخ اشتباه
    if guessed_number < secret:
        result = "🔼 عدد مخفی بزرگ‌تر از اینه!"
    else:
        result = "🔽 عدد مخفی کوچک‌تر از اینه!"

    game["turn_index"] = (
        game["turn_index"] + 1
    ) % len(players)

    await query.answer("حدست ثبت شد!")

    await query.edit_message_text(
        playing_text(game, result),
        reply_markup=guess_keyboard(game_id),
        parse_mode=ParseMode.HTML,
    )


# =================================
# اتصال هندلرهای بازی به ربات
# =================================

def register_guess_number_handlers(
    application: Application,
):
    application.add_handler(
        CommandHandler(
            "guessnumber",
            guess_number_command,
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            guess_join_callback,
            pattern=r"^gn_join:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            guess_players_callback,
            pattern=r"^gn_players:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            guess_start_callback,
            pattern=r"^gn_start:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            guess_number_callback,
            pattern=r"^gn_guess:",
        )
    )

    logger.info("Guess Number game handlers registered.")
