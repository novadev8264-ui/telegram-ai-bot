"""هندلرهای بازی موش و گربه PULSE."""
import asyncio
import html
import logging
import secrets

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from .map import create_map
from .players import make_player, MIN_PLAYERS, MAX_PLAYERS, assign_teams
from .movement import move_player
from .rules import resolve_after_move
from .turns import next_turn
from .display import (
    registration_keyboard, move_keyboard, registration_text,
    team_private_text, group_status_text, roster_text,
)

logger = logging.getLogger("PULSE.GAMES.CAT_MOUSE")
ACTIVE_CAT_MOUSE = {}
LOBBY_TIMEOUT_SECONDS = 120
ACTIVE_STATUSES = ("registering", "checking_private", "playing")


def _owner_mention(user):
    name = html.escape(user.full_name or "برگزارکننده")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def _cancel_lobby_timer(game):
    task = game.get("lobby_timer")
    if task and not task.done():
        task.cancel()
    game["lobby_timer"] = None


async def _expire_empty_lobby(application, game_id):
    try:
        await asyncio.sleep(LOBBY_TIMEOUT_SECONDS)
        game = ACTIVE_CAT_MOUSE.get(game_id)
        # سازنده به‌تنهایی بازیکن محسوب نمی‌شود؛ باید حداقل یک نفر دیگر وارد شده باشد.
        if not game or game.get("status") != "registering":
            return
        if len(game.get("players", {})) > 1:
            return

        game["status"] = "expired"
        ACTIVE_CAT_MOUSE.pop(game_id, None)
        chat_id = game.get("chat_id")
        message_id = game.get("group_message_id")
        if chat_id and message_id:
            try:
                await application.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="⌛ ثبت‌نام بازی موش و گربه به دلیل نپیوستن بازیکن دیگری، پس از ۲ دقیقه منقضی شد.\nبرای ساخت بازی تازه از «بازی موش و گربه» یا /mousegame استفاده کنید.",
                )
            except Exception:
                try:
                    await application.bot.delete_message(chat_id, message_id)
                except Exception:
                    logger.exception("Could not expire Cat & Mouse lobby message")
        logger.info("Cat & Mouse lobby %s expired: no additional player joined", game_id)
    except asyncio.CancelledError:
        return


def _private_start_url(bot_username, game_id, user_id):
    return f"https://t.me/{bot_username}?start=cm_{game_id}_{user_id}"


async def _bot_username(context):
    cached = context.application.bot_data.get("cat_mouse_bot_username")
    if cached:
        return cached
    me = await context.bot.get_me()
    username = me.username
    if not username:
        raise RuntimeError("Bot username is unavailable")
    context.application.bot_data["cat_mouse_bot_username"] = username
    return username


async def _send_group_private_link(context, game, user_id):
    player = game["players"][user_id]
    if player.get("private_prompted"):
        return
    try:
        username = await _bot_username(context)
        url = _private_start_url(username, game["id"], user_id)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("📩 ورود به پی‌وی ربات و دریافت پیام بازی", url=url)
        ]])
        await context.bot.send_message(
            chat_id=game["chat_id"],
            text=(
                f'🔔 {player["mention"]}\n'
                "برای دریافت پیام‌ها و دکمه‌های حرکت بازی، روی دکمه زیر بزن و در پی‌وی ربات «شروع» را فعال کن."
            ),
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        player["private_prompted"] = True
    except Exception:
        logger.exception("Could not send private-start link for player %s", user_id)


async def _ensure_private_access(context, game, user_id, send_notice=True):
    player = game["players"][user_id]
    try:
        if send_notice:
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ پی‌وی ربات فعال است. پیام‌ها و نوبت‌های بازی موش و گربه را همین‌جا دریافت می‌کنی.",
            )
        player["private_ready"] = True
        return True
    except Exception:
        player["private_ready"] = False
        await _send_group_private_link(context, game, user_id)
        return False


async def _send_team_turn(context, game, user_id):
    player = game["players"].get(user_id)
    if not player:
        return
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=team_private_text(game, player),
            reply_markup=move_keyboard(game["id"]),
            parse_mode=ParseMode.HTML,
        )
        player["private_ready"] = True
    except Exception:
        player["private_ready"] = False
        await _send_group_private_link(context, game, user_id)


async def mousegame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not message or not user or not chat:
        return
    if chat.type not in ("group", "supergroup"):
        await message.reply_text("این بازی را داخل گروه تلگرام ایجاد کن.")
        return

    for active in ACTIVE_CAT_MOUSE.values():
        if active["chat_id"] == chat.id and active["status"] in ACTIVE_STATUSES:
            await message.reply_text("در این گروه یک بازی موش و گربه فعال وجود دارد.")
            return

    game_id = secrets.token_hex(4)
    game = {
        "id": game_id,
        "chat_id": chat.id,
        "owner_id": user.id,
        "owner_mention": _owner_mention(user),
        "players": {},
        "status": "registering",
        "board": None,
        "round": 1,
        "phase": "mouse",
        "turn_index": 0,
        "cheese": 0,
        "winner": None,
        "group_message_id": None,
        "lobby_timer": None,
    }
    game["players"][user.id] = make_player(user)
    ACTIVE_CAT_MOUSE[game_id] = game

    sent = await message.reply_text(
        registration_text(game),
        reply_markup=registration_keyboard(game_id),
        parse_mode=ParseMode.HTML,
    )
    game["group_message_id"] = sent.message_id
    game["lobby_timer"] = asyncio.create_task(
        _expire_empty_lobby(context.application, game_id)
    )


async def _edit_registration(context, game):
    try:
        await context.bot.edit_message_text(
            registration_text(game),
            chat_id=game["chat_id"],
            message_id=game["group_message_id"],
            reply_markup=registration_keyboard(game["id"]),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        logger.exception("Could not update Cat & Mouse registration")


async def _start_game(query, context, game):
    if query.from_user.id != game["owner_id"]:
        await query.answer("فقط برگزارکننده می‌تواند بازی را شروع کند.", show_alert=True)
        return
    if game["status"] != "registering":
        await query.answer("این بازی در حال شروع یا اجراست.", show_alert=True)
        return

    count = len(game["players"])
    if not MIN_PLAYERS <= count <= MAX_PLAYERS:
        await query.answer("برای شروع به ۴ تا ۱۲ بازیکن نیاز است.", show_alert=True)
        return

    _cancel_lobby_timer(game)
    game["status"] = "checking_private"

    cats, mice = assign_teams(game)
    game["board"] = create_map()

    mouse_spawns = [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (0, 2), (2, 1), (1, 2)]
    cat_spawns = [(7, 6), (6, 7), (6, 6), (5, 7)]
    mi = ci = 0
    for player in game["players"].values():
        if player["team"] == "mouse":
            player["pos"] = mouse_spawns[mi % len(mouse_spawns)]
            mi += 1
        else:
            player["pos"] = cat_spawns[ci % len(cat_spawns)]
            ci += 1

    game["status"] = "playing"
    game["round"] = 1
    game["phase"] = "mouse"
    game["turn_index"] = 0
    game["current_turn"] = next_turn(game)

    await query.answer("بازی شروع شد!")
    await query.edit_message_text(
        group_status_text(game, f"🚀 بازی آغاز شد! گربه‌ها: {cats} | موش‌ها: {mice}"),
        parse_mode=ParseMode.HTML,
    )

    # اگر بازیکن قبلاً پی‌وی ربات را فعال کرده باشد، پیام مستقیم می‌گیرد.
    # اگر فعال نکرده باشد، لینک اختصاصی ورود به پی‌وی در گروه برای خودش ارسال می‌شود.
    for uid in list(game["players"]):
        await _ensure_private_access(context, game, uid, send_notice=True)

    if game["current_turn"] is not None:
        await _send_team_turn(context, game, game["current_turn"])


async def _finish_game(context, game, winner, note):
    game["status"] = "finished"
    game["winner"] = winner
    team_label = "تیم موش‌ها 🐭" if winner == "mouse" else "تیم گربه‌ها 🐱"
    try:
        await context.bot.edit_message_text(
            chat_id=game["chat_id"],
            message_id=game["group_message_id"],
            text=f"🏆 <b>برنده بازی: {team_label}</b>\n\n{group_status_text(game, note)}",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        logger.exception("Could not publish Cat & Mouse result")


async def cat_mouse_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = (query.data or "").split(":")
    if len(parts) < 3:
        await query.answer("درخواست نامعتبر است.", show_alert=True)
        return

    action, game_id = parts[1], parts[2]
    game = ACTIVE_CAT_MOUSE.get(game_id)
    if not game:
        await query.answer("این بازی پیدا نشد یا پایان یافته است.", show_alert=True)
        return
    if not query.message:
        await query.answer("پیام این دکمه در دسترس نیست.", show_alert=True)
        return

    if action == "move":
        if query.message.chat.type != "private" or query.message.chat.id != query.from_user.id:
            await query.answer("حرکت باید از پیام خصوصی ربات انجام شود.", show_alert=True)
            return
    elif query.message.chat.id != game["chat_id"]:
        await query.answer("این دکمه مربوط به گروه دیگری است.", show_alert=True)
        return

    if action == "join":
        if game["status"] != "registering":
            await query.answer("ثبت‌نام بسته شده است.", show_alert=True)
            return
        user = query.from_user
        if user.id in game["players"]:
            await query.answer("شما قبلاً ثبت‌نام کرده‌اید.", show_alert=True)
            return
        if len(game["players"]) >= MAX_PLAYERS:
            await query.answer("ظرفیت بازی تکمیل است.", show_alert=True)
            return
        game["players"][user.id] = make_player(user)
        _cancel_lobby_timer(game)  # با ورود اولین بازیکن دیگر، لابی دیگر منقضی نمی‌شود.
        await query.answer("به بازی پیوستی! 🐭")
        await _edit_registration(context, game)
        await _ensure_private_access(context, game, user.id, send_notice=True)
        return

    if action == "players":
        await query.answer()
        await query.message.reply_text(roster_text(game), parse_mode=ParseMode.HTML)
        return

    if action == "start":
        await _start_game(query, context, game)
        return

    if action == "move":
        if game["status"] != "playing":
            await query.answer("بازی در حال اجرا نیست.", show_alert=True)
            return
        uid = query.from_user.id
        if uid not in game["players"] or uid != game.get("current_turn"):
            await query.answer("این نوبت متعلق به شما نیست.", show_alert=True)
            return
        direction = parts[3] if len(parts) > 3 else ""
        ok, result = move_player(game, uid, direction)
        if not ok:
            await query.answer(result, show_alert=True)
            return

        player = game["players"][uid]
        player["moved_round"] = game["round"]
        note, winner = resolve_after_move(game, uid)

        if winner:
            await query.answer("بازی تمام شد!")
            await _finish_game(context, game, winner, note)
            try:
                await query.edit_message_text("🏁 بازی تمام شد. نتیجه در گروه اعلام شد.")
            except Exception:
                pass
            return

        game["current_turn"] = next_turn(game)
        if game["current_turn"] is None:
            await query.answer("ده دور تمام شد؛ موش‌ها برنده شدند!")
            await _finish_game(
                context, game, "mouse",
                "ده دور به پایان رسید و موش‌ها زنده ماندند.",
            )
            try:
                await query.edit_message_text("🏁 ده دور تمام شد؛ تیم موش‌ها برنده شد.")
            except Exception:
                pass
            return

        await query.answer(result)
        try:
            await query.edit_message_text("✅ حرکت شما ثبت شد. نوبت بازیکن بعدی است.")
        except Exception:
            pass
        try:
            await context.bot.edit_message_text(
                chat_id=game["chat_id"],
                message_id=game["group_message_id"],
                text=group_status_text(game, note or f'حرکت {player["symbol"]} ثبت شد.'),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.exception("Could not update Cat & Mouse group status")
        await _send_team_turn(context, game, game["current_turn"])


async def handle_cat_mouse_start_payload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش لینک اختصاصی /start cm_<game_id>_<user_id>."""
    if not context.args:
        return False
    payload = context.args[0]
    match = __import__("re").fullmatch(r"cm_([0-9a-fA-F]{8})_(\d+)", payload)
    if not match:
        return False

    game_id, target_user_id = match.group(1), int(match.group(2))
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return True
    if user.id != target_user_id:
        await message.reply_text("این لینک دعوت مخصوص حساب کاربری دیگری است.")
        return True

    game = ACTIVE_CAT_MOUSE.get(game_id)
    if not game or user.id not in game.get("players", {}):
        await message.reply_text("این دعوت دیگر معتبر نیست؛ ممکن است بازی پایان یافته یا ثبت‌نام منقضی شده باشد.")
        return True

    player = game["players"][user.id]
    player["private_ready"] = True
    player["private_prompted"] = False
    await message.reply_text(
        "✅ پی‌وی ربات فعال شد. از این به بعد پیام‌ها و نوبت‌های بازی را همین‌جا دریافت می‌کنی."
    )
    if game.get("status") == "playing" and game.get("current_turn") == user.id:
        await _send_team_turn(context, game, user.id)
    return True


async def mouseend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user
    if not chat or not message or not user:
        return
    if chat.type not in ("group", "supergroup"):
        await message.reply_text("این دستور را داخل همان گروه بازی اجرا کن.")
        return

    game = next(
        (g for g in ACTIVE_CAT_MOUSE.values()
         if g["chat_id"] == chat.id and g["status"] in ACTIVE_STATUSES),
        None,
    )
    if not game:
        await message.reply_text("در این گروه بازی فعالی وجود ندارد.")
        return
    if user.id != game["owner_id"]:
        await message.reply_text("فقط برگزارکننده بازی می‌تواند آن را پایان دهد.")
        return

    _cancel_lobby_timer(game)
    game["status"] = "finished"
    ACTIVE_CAT_MOUSE.pop(game["id"], None)
    try:
        await context.bot.edit_message_text(
            chat_id=game["chat_id"],
            message_id=game["group_message_id"],
            text="🛑 بازی موش و گربه با دستور برگزارکننده پایان یافت. اکنون می‌توانید بازی تازه‌ای بسازید.",
        )
    except Exception:
        await message.reply_text("بازی پایان یافت و وضعیت آن آزاد شد.")


async def mousemap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = _find_chat_game(update.effective_chat.id)
    if not game:
        await update.effective_message.reply_text("در این گروه بازی فعالی پیدا نشد.")
        return
    await update.effective_message.reply_text(
        group_status_text(game), parse_mode=ParseMode.HTML
    )


async def mousestatus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = _find_chat_game(update.effective_chat.id)
    if not game:
        await update.effective_message.reply_text("در این گروه بازی فعالی پیدا نشد.")
        return
    await update.effective_message.reply_text(
        roster_text(game) + "\n\n" + group_status_text(game),
        parse_mode=ParseMode.HTML,
    )


def _find_chat_game(chat_id):
    for game in ACTIVE_CAT_MOUSE.values():
        if game["chat_id"] == chat_id and game["status"] in ACTIVE_STATUSES:
            return game
    return None


def register_cat_mouse_handlers(application: Application):
    application.add_handler(CommandHandler("mousegame", mousegame_command))
    application.add_handler(CommandHandler("mousemap", mousemap_command))
    application.add_handler(CommandHandler("mousestatus", mousestatus_command))
    application.add_handler(CommandHandler("mouseend", mouseend_command))
    application.add_handler(CallbackQueryHandler(cat_mouse_callback, pattern=r"^cm:"))
    logger.info("Cat & Mouse handlers registered.")
    
