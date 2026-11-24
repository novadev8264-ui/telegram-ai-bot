
import random
import html
import logging

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


# -----------------------------
# تنظیمات بازی
# -----------------------------

MIN_NUMBER = 1
MAX_NUMBER = 20


def make_player_link(player):
    """ساخت لینک قابل کلیک پروفایل بازیکن."""

    name = html.escape(player["name"])

    if player.get("username"):
        username = html.escape(player["username"])
        return f'<a href="https://t.me/{username}">{name}</a>'

    return f'<a href="tg://user?id={player["id"]}">{name}</a>'


def get_players_text(game):
    """نمایش فهرست بازیکنان."""

    players = list(game["players"].values())

    if not players:
        return "هنوز کسی وارد بازی نشده است."

    lines = []

    for index, player in enumerate(players, 1):
        lines.append(f'{index}. {make_player_link(player)}')

    return "\n".join(lines)


def registration_text(game):
    """متن زمان ثبت‌نام."""

    return (
        "🎯 <b>بازی حدس عدد PULSE</b>\n\n"
        "یک عدد مخفی بین ۱ تا ۲۰ انتخاب می‌شود.\n"
        "بازیکنان به نوبت عدد را حدس می‌زنند.\n\n"
        f"👑 برگزارکننده: "
        f'<a href="tg://user?id={game["owner_id"]}">'
        f'{html.escape(game["owner_name"])}</a>\n'
        f"👥 تعداد بازیکنان: {len(game['players'])}\n\n"
        "<b>بازیکنان:</b>\n"
        f"{get_players_text(game)}\n\n"
        "برای شرکت در بازی روی دکمه ورود بزن."
    )


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
            )
        ]
    ])


def guess_keyboard(game_id):
    """ساخت دکمه‌های انتخاب عدد."""

    rows = []

    for start in range(MIN_NUMBER, MAX_NUMBER + 1, 4):
        row = []

        for number in range(start, min(start + 4, MAX_NUMBER + 1)):
            row.append(
                InlineKeyboardButton(
                    str(number),
                    callback_data=f"gn_guess:{game_id}:{number}",
                )
            )

        rows.append(row)

    return InlineKeyboardMarkup(rows)


def playing_text(game, message=""):
    """متن وضعیت بازی."""

    players = list(game["players"].values())
    current_index = game["turn_index"] % len(players)
    current_player = players[current_index]

    text = (
        "🎯 <b>بازی حدس عدد PULSE شروع شد!</b>\n\n"
        f"🔢 عدد مخفی بین {MIN_NUMBER} تا {MAX_NUMBER} است.\n"
        f"👥 بازیکنان: {len(players)}\n"
        f"🎲 تعداد حدس‌ها: {game['attempts']}\n\n"
        f"⏳ نوبت: {make_player_link(current_player)}\n"
    )

    if message:
        text += f"\n{message}\n"

    text += "\n👇 عدد موردنظرت را انتخاب کن:"

    return text


# -----------------------------
# دستور شروع بازی
# -----------------------------

async def guess_number_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    message = update.effective_message

    if not user or not message:
        return

    game = create_game("guess_number", user)

    success, result = await join_game(game["id"], user)

    if not success:
        await message.reply_text(result)
        return

    game["secret_number"] = None
    game["attempts"] = 0
    game["turn_index"] = 0
    game["status"] = "registering"

    await message.reply_text(
        registration_text(game),
        reply_markup=registration_keyboard(game["id"]),
        parse_mode=ParseMode.HTML,
    )


# -----------------------------
# ورود بازیکن
# -----------------------------

async def guess_join_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split(":")[1]
    user = query.from_user

    game = ACTIVE_GAMES.get(game_id)

    if not game:
        await query.answer("این بازی پیدا نشد.", show_alert=True)
        return

    if game["status"] != "registering":
        await query.answer(
            "ثبت‌نام این بازی بسته شده است.",
            show_alert=True,
        )
        return

    success, result = await join_game(game_id, user)

    await query.answer(result, show_alert=not success)

    if success:
        await query.edit_message_text(
            registration_text(game),
            reply_markup=registration_keyboard(game_id),
            parse_mode=ParseMode.HTML,
        )


# -----------------------------
# نمایش بازیکنان
# -----------------------------

async def guess_players_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split(":")[1]
    game = ACTIVE_GAMES.get(game_id)

    if not game:
        await query.answer("بازی پیدا نشد.", show_alert=True)
        return

    await query.answer(
        f"تعداد بازیکنان: {len(game['players'])}",
        show_alert=True,
    )


# -----------------------------
# شروع بازی
# -----------------------------

async def guess_start_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    game_id = query.data.split(":")[1]
    user = query.from_user

    game = ACTIVE_GAMES.get(game_id)

    if not game:
        await query.answer("بازی پیدا نشد.", show_alert=True)
        return

    if game["owner_id"] != user.id:
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

    success, result = await close_registration(game_id, user.id)

    if not success:
        await query.answer(result, show_alert=True)
        return

    game["secret_number"] = random.randint(
        MIN_NUMBER,
        MAX_NUMBER,
    )

    game["attempts"] = 0
    game["turn_index"] = 0

    await query.edit_message_text(
        playing_text(game, "🚀 بازی آغاز شد!"),
        reply_markup=guess_keyboard(game_id),
        parse_mode=ParseMode.HTML,
    )


# -----------------------------
# ثبت حدس بازیکن
# -----------------------------

async def guess_number_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    game_id = parts[1]
    guessed_number = int(parts[2])

    user = query.from_user
    game = ACTIVE_GAMES.get(game_id)

    if not game:
        await query.answer("بازی پیدا نشد.", show_alert=True)
        return

    if game["status"] != "playing":
        await query.answer(
            "این بازی در حال اجرا نیست.",
            show_alert=True,
        )
        return

    players = list(game["players"].values())

    if not players:
        await query.answer("بازیکنی در بازی نیست.", show_alert=True)
        return

    current_player = players[
        game["turn_index"] % len(players)
    ]

    if user.id != current_player["id"]:
        await query.answer(
            "الان نوبت شما نیست!",
            show_alert=True,
        )
        return

    game["attempts"] += 1
    secret = game["secret_number"]

    if guessed_number == secret:
        await finish_game(game_id, user.id)

        winner = make_player_link(current_player)

        await query.edit_message_text(
            "🏆 <b>بازی تمام شد!</b>\n\n"
            f"🎉 برنده: {winner}\n"
            f"🔢 عدد مخفی: <b>{secret}</b>\n"
            f"🎯 تعداد حدس‌ها: {game['attempts']}\n\n"
            "🔥 تبریک به برنده بازی PULSE!",
            parse_mode=ParseMode.HTML,
        )
        return

    if guessed_number < secret:
        result = "🔼 عدد مخفی بزرگ‌تر از اینه!"
    else:
        result = "🔽 عدد مخفی کوچک‌تر از اینه!"

    game["turn_index"] = (
        game["turn_index"] + 1
    ) % len(players)

    await query.edit_message_text(
        playing_text(game, result),
        reply_markup=guess_keyboard(game_id),
        parse_mode=ParseMode.HTML,
    )


# -----------------------------
# ثبت هندلرهای بازی
# -----------------------------

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
      
