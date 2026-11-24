
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
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from games.manager import (
    create_game,
    join_game,
    close_registration,
    finish_game,
    get_game,
)

logger = logging.getLogger("PULSE.GAMES.TICTACTOE")

MIN_PLAYERS = 2

WIN_LINES = [
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
]


def registration_text(game):
    lines = [
        "⭕ <b>بازی دوز PULSE</b> ❌",
        "",
        f"🆔 کد بازی: <code>{game['id']}</code>",
        f"👥 تعداد بازیکنان: {len(game['players'])}/2",
        "",
        "📋 <b>بازیکنان:</b>",
    ]

    if not game["players"]:
        lines.append("هنوز بازیکنی ثبت‌نام نکرده است.")
    else:
        for number, player in enumerate(game["players"].values(), 1):
            lines.append(f"{number}. {player['mention']}")

    lines.extend([
        "",
        "برای شرکت در بازی دکمه ورود را بزن.",
        "شروع بازی فقط توسط برگزارکننده انجام می‌شود.",
    ])

    return "\n".join(lines)


def registration_keyboard(game_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎮 ورود به بازی",
                callback_data=f"ttt_join:{game_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "👥 بازیکنان",
                callback_data=f"ttt_players:{game_id}"
            ),
            InlineKeyboardButton(
                "🏁 شروع بازی",
                callback_data=f"ttt_start:{game_id}"
            )
        ],
    ])


def board_keyboard(game):
    keyboard = []
    board = game["board"]

    for row in range(3):
        buttons = []

        for col in range(3):
            index = row * 3 + col
            value = board[index] or "▫️"

            buttons.append(
                InlineKeyboardButton(
                    value,
                    callback_data=f"ttt_move:{game['id']}:{index}"
                )
            )

        keyboard.append(buttons)

    return InlineKeyboardMarkup(keyboard)


def get_player_name(game, user_id):
    player = game["players"].get(user_id)

    if not player:
        return "بازیکن"

    return html.escape(player["name"])


def playing_text(game):
    player_x = game["players"][game["player_x"]]
    player_o = game["players"][game["player_o"]]
    current_name = get_player_name(game, game["turn_id"])

    return (
        "⭕ <b>بازی دوز PULSE</b> ❌\n\n"
        f"❌ بازیکن X: {player_x['mention']}\n"
        f"⭕ بازیکن O: {player_o['mention']}\n\n"
        f"🎯 نوبت: {current_name}\n\n"
        "خانه موردنظر را انتخاب کن."
    )


def find_winner(board):
    for a, b, c in WIN_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]

    return None


async def tictactoe_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ("group", "supergroup"):
        await message.reply_text("این بازی فقط داخل گروه اجرا می‌شود.")
        return

    game = create_game("tic_tac_toe", user)

    success, result = await join_game(game["id"], user)

    if not success:
        await message.reply_text(result)
        return

    await message.reply_text(
        registration_text(game),
        reply_markup=registration_keyboard(game["id"]),
        parse_mode=ParseMode.HTML,
    )

    logger.info("TicTacToe created: %s", game["id"])


async def join_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    user = query.from_user
    game_id = query.data.split(":", 1)[1]

    success, result = await join_game(game_id, user)

    await query.answer(result, show_alert=not success)

    if success:
        game = get_game(game_id)

        if game:
            await query.edit_message_text(
                registration_text(game),
                reply_markup=registration_keyboard(game_id),
                parse_mode=ParseMode.HTML,
            )


async def players_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    game_id = query.data.split(":", 1)[1]
    game = get_game(game_id)

    if not game:
        await query.answer("این بازی پیدا نشد.", show_alert=True)
        return

    lines = ["👥 بازیکنان بازی دوز:", ""]

    if not game["players"]:
        lines.append("هنوز بازیکنی ثبت‌نام نکرده است.")
    else:
        for number, player in enumerate(game["players"].values(), 1):
            lines.append(f"{number}. {player['mention']}")

    await query.answer(
        "\n".join(lines),
        show_alert=True,
    )


async def start_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    user = query.from_user
    game_id = query.data.split(":", 1)[1]

    game = get_game(game_id)

    if not game:
        await query.answer("این بازی پیدا نشد.", show_alert=True)
        return

    if game["owner_id"] != user.id:
        await query.answer(
            "فقط برگزارکننده می‌تواند بازی را شروع کند.",
            show_alert=True,
        )
        return

    if len(game["players"]) != MIN_PLAYERS:
        await query.answer(
            "برای شروع بازی دقیقاً دو بازیکن لازم است.",
            show_alert=True,
        )
        return

    success, result = await close_registration(game_id, user.id)

    if not success:
        await query.answer(result, show_alert=True)
        return

    player_ids = list(game["players"].keys())

    game["board"] = [None] * 9
    game["player_x"] = player_ids[0]
    game["player_o"] = player_ids[1]
    game["turn_id"] = player_ids[0]
    game["symbols"] = {
        player_ids[0]: "❌",
        player_ids[1]: "⭕",
    }

    await query.answer("بازی دوز شروع شد! 🎮")

    await query.edit_message_text(
        playing_text(game),
        reply_markup=board_keyboard(game),
        parse_mode=ParseMode.HTML,
    )


async def move_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    user = query.from_user

    try:
        _, game_id, index_text = query.data.split(":")
        index = int(index_text)
    except (ValueError, TypeError):
        await query.answer("حرکت نامعتبر است.", show_alert=True)
        return

    if index < 0 or index > 8:
        await query.answer("خانه انتخاب‌شده معتبر نیست.", show_alert=True)
        return

    game = get_game(game_id)

    if not game or game["status"] != "playing":
        await query.answer("این بازی فعال نیست.", show_alert=True)
        return

    if user.id not in game["players"]:
        await query.answer("شما عضو این بازی نیستید.", show_alert=True)
        return

    if user.id != game["turn_id"]:
        await query.answer("الان نوبت شما نیست.", show_alert=True)
        return

    if game["board"][index] is not None:
        await query.answer("این خانه قبلاً انتخاب شده است.", show_alert=True)
        return

    symbol = game["symbols"][user.id]
    game["board"][index] = symbol

    winner_symbol = find_winner(game["board"])

    if winner_symbol:
        winner_id = (
            game["player_x"]
            if winner_symbol == "❌"
            else game["player_o"]
        )

        await finish_game(game_id, winner_id)

        winner_name = get_player_name(game, winner_id)

        text = (
            "🏆 <b>بازی دوز به پایان رسید!</b>\n\n"
            f"🎉 برنده: {winner_name}\n"
            f"علامت برنده: {winner_symbol}\n\n"
            "تبریک به برنده! 🎮"
        )

        await query.answer("تبریک! شما برنده شدید! 🏆")

        await query.edit_message_text(
            text,
            reply_markup=board_keyboard(game),
            parse_mode=ParseMode.HTML,
        )
        return

    if all(game["board"]):
        await finish_game(game_id)

        await query.answer("بازی مساوی شد!")

        await query.edit_message_text(
            "🤝 <b>بازی دوز مساوی شد!</b>\n\n"
            "هیچ‌کدام از بازیکنان برنده نشدند.",
            reply_markup=board_keyboard(game),
            parse_mode=ParseMode.HTML,
        )
        return

    game["turn_id"] = (
        game["player_o"]
        if user.id == game["player_x"]
        else game["player_x"]
    )

    await query.answer("حرکت ثبت شد.")

    await query.edit_message_text(
        playing_text(game),
        reply_markup=board_keyboard(game),
        parse_mode=ParseMode.HTML,
    )


def register_tictactoe_handlers(application: Application):
    application.add_handler(
        CommandHandler("tictactoe", tictactoe_command)
    )

    application.add_handler(
        MessageHandler(
            filters.Regex(r"^\s*بازی دوز\s*$"),
            tictactoe_command,
        )
    )

    application.add_handler(
        CallbackQueryHandler(join_callback, pattern=r"^ttt_join:")
    )

    application.add_handler(
        CallbackQueryHandler(players_callback, pattern=r"^ttt_players:")
    )

    application.add_handler(
        CallbackQueryHandler(start_callback, pattern=r"^ttt_start:")
    )

    application.add_handler(
        CallbackQueryHandler(move_callback, pattern=r"^ttt_move:")
    )

    logger.info("TicTacToe handlers registered.")
        
