"""هندلرهای مستقل بازی موش و گربه PULSE."""
import html
import logging
import secrets
from telegram import Update
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

def _owner_mention(user):
    name = html.escape(user.full_name or "برگزارکننده")
    return f'<a href="tg://user?id={user.id}">{name}</a>'

async def mousegame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await message.reply_text("این بازی را داخل گروه تلگرام ایجاد کن.")
        return
    # جلوگیری از چند بازی ثبت‌نامی همزمان در یک گروه
    for g in ACTIVE_CAT_MOUSE.values():
        if g["chat_id"] == chat.id and g["status"] in ("registering", "playing"):
            await message.reply_text("در این گروه یک بازی موش و گربه فعال وجود دارد.")
            return
    game_id = secrets.token_hex(4)
    game = {
        "id": game_id, "chat_id": chat.id, "owner_id": user.id,
        "owner_mention": _owner_mention(user), "players": {},
        "status": "registering", "board": None, "round": 1,
        "phase": "mouse", "turn_index": 0, "cheese": 0,
        "winner": None, "group_message_id": None,
    }
    game["players"][user.id] = make_player(user)
    ACTIVE_CAT_MOUSE[game_id] = game
    sent = await message.reply_text(
        registration_text(game), reply_markup=registration_keyboard(game_id),
        parse_mode=ParseMode.HTML,
    )
    game["group_message_id"] = sent.message_id

async def _edit_registration(context, game):
    try:
        await context.bot.edit_message_text(
            registration_text(game), chat_id=game["chat_id"],
            message_id=game["group_message_id"],
            reply_markup=registration_keyboard(game["id"]),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        logger.exception("Could not update Cat & Mouse registration")

async def _send_team_turn(context, game, user_id):
    player = game["players"][user_id]
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=team_private_text(game, player),
            reply_markup=move_keyboard(game["id"]),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        await context.bot.send_message(
            chat_id=game["chat_id"],
            text=f'⚠️ {player["mention"]} باید ابتدا به ربات خصوصی پیام بدهد و /start را بزند تا بتواند حرکت کند.',
            parse_mode=ParseMode.HTML,
        )

async def _start_game(query, context, game):
    if query.from_user.id != game["owner_id"]:
        await query.answer("فقط برگزارکننده می‌تواند بازی را شروع کند.", show_alert=True)
        return
    count = len(game["players"])
    if not MIN_PLAYERS <= count <= MAX_PLAYERS:
        await query.answer("برای شروع به ۴ تا ۱۲ بازیکن نیاز است.", show_alert=True)
        return
    # بررسی دسترسی پیام خصوصی همه بازیکنان پیش از آغاز
    blocked = []
    for uid in game["players"]:
        try:
            await context.bot.send_message(uid, "✅ دسترسی خصوصی بازی موش و گربه آماده است.")
        except Exception:
            blocked.append(uid)
    if blocked:
        await query.answer("همه بازیکنان باید ابتدا در خصوصی ربات /start را بزنند.", show_alert=True)
        return
    cats, mice = assign_teams(game)
    game["board"] = create_map()
    # محل شروع موش‌ها و گربه‌ها از هم جداست.
    mouse_spawns = [(0,0), (0,1), (1,0), (1,1), (2,0), (0,2), (2,1), (1,2)]
    cat_spawns = [(7,6), (6,7), (6,6), (5,7)]
    mi = ci = 0
    for p in game["players"].values():
        if p["team"] == "mouse":
            p["pos"] = mouse_spawns[mi % len(mouse_spawns)]; mi += 1
        else:
            p["pos"] = cat_spawns[ci % len(cat_spawns)]; ci += 1
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
    if game["current_turn"] is not None:
        await _send_team_turn(context, game, game["current_turn"])

async def cat_mouse_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = (query.data or "").split(":")
    if len(parts) < 3:
        await query.answer("درخواست نامعتبر است.", show_alert=True); return
    action, game_id = parts[1], parts[2]
    game = ACTIVE_CAT_MOUSE.get(game_id)
    if not game:
        await query.answer("این بازی پیدا نشد یا پایان یافته است.", show_alert=True); return
    if not query.message or query.message.chat_id != game["chat_id"]:
        await query.answer("این دکمه مربوط به گروه دیگری است.", show_alert=True); return
    if action == "join":
        if game["status"] != "registering":
            await query.answer("ثبت‌نام بسته شده است.", show_alert=True); return
        user = query.from_user
        if user.id in game["players"]:
            await query.answer("شما قبلاً ثبت‌نام کرده‌اید.", show_alert=True); return
        if len(game["players"]) >= MAX_PLAYERS:
            await query.answer("ظرفیت بازی تکمیل است.", show_alert=True); return
        game["players"][user.id] = make_player(user)
        await query.answer("به بازی پیوستی! 🐭")
        await _edit_registration(context, game)
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
            await query.answer("بازی در حال اجرا نیست.", show_alert=True); return
        uid = query.from_user.id
        if uid != game.get("current_turn"):
            await query.answer("این نوبت متعلق به شما نیست.", show_alert=True); return
        direction = parts[3] if len(parts) > 3 else ""
        ok, result = move_player(game, uid, direction)
        if not ok:
            await query.answer(result, show_alert=True); return
        player = game["players"][uid]
        player["moved_round"] = game["round"]
        note, winner = resolve_after_move(game, uid)
        if winner:
            game["status"] = "finished"
            game["winner"] = winner
            team_label = "تیم موش‌ها 🐭" if winner == "mouse" else "تیم گربه‌ها 🐱"
            await query.answer("بازی تمام شد!")
            await context.bot.edit_message_text(
                chat_id=game["chat_id"],
                message_id=game["group_message_id"],
                text=f'🏆 <b>برنده بازی: {team_label}</b>\n\n{group_status_text(game, note)}',
                parse_mode=ParseMode.HTML,
            )
            try:
                await query.edit_message_text("🏁 بازی تمام شد. نتیجه در گروه اعلام شد.")
            except Exception:
                pass
            return
        game["current_turn"] = next_turn(game)
        if game["current_turn"] is None:
            game["status"] = "finished"
            game["winner"] = "mouse"
            await query.answer("ده دور تمام شد؛ موش‌ها برنده شدند!")
            await context.bot.edit_message_text(
                chat_id=game["chat_id"],
                message_id=game["group_message_id"],
                text=f'🏆 <b>برنده بازی: تیم موش‌ها 🐭</b>\n\n{group_status_text(game, "ده دور به پایان رسید و موش‌ها زنده ماندند.")}',
                parse_mode=ParseMode.HTML,
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
        await context.bot.edit_message_text(
            chat_id=game["chat_id"],
            message_id=game["group_message_id"],
            text=group_status_text(game, note or f'حرکت {player["symbol"]} ثبت شد.'),
            parse_mode=ParseMode.HTML,
        )
        if game["current_turn"] is not None:
            await _send_team_turn(context, game, game["current_turn"])
        return

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
        if game["chat_id"] == chat_id and game["status"] in ("registering", "playing"):
            return game
    return None

def register_cat_mouse_handlers(application: Application):
    application.add_handler(CommandHandler("mousegame", mousegame_command))
    application.add_handler(CommandHandler("mousemap", mousemap_command))
    application.add_handler(CommandHandler("mousestatus", mousestatus_command))
    application.add_handler(CallbackQueryHandler(cat_mouse_callback, pattern=r"^cm:"))
    logger.info("Cat & Mouse handlers registered.")
