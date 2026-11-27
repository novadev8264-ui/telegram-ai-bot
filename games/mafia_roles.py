import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden, TelegramError

logger = logging.getLogger("PULSE.MAFIA.ROLES")


def is_private_chat_unavailable(error):
    """True only for Telegram errors indicating the bot cannot DM this user yet."""
    if isinstance(error, Forbidden):
        return True
    if isinstance(error, BadRequest):
        description = str(error).lower()
        return any(text in description for text in (
            "chat not found",
            "bot can't initiate conversation",
            "bot cannot initiate conversation",
            "user is deactivated",
            "user deactivated",
            "bot was blocked by the user",
        ))
    return False


def build_role_message(role, question):
    role_name = "مافیا 🔴" if role == "mafia" else "شهروند 🟢"
    return (
        "🌙 بازی مافیای PULSE\n\n"
        f"🎭 نقش شما: {role_name}\n\n"
        "❓ سؤال مخصوص شما:\n"
        f"{question}\n\n"
        "🔒 اطلاعات نقش و سؤال شما محرمانه است."
    )


async def send_private_roles(bot, game, roles, questions):
    """Try DM delivery to every player; return IDs that need a deep-link invitation.

    Role/question data are kept in game memory by the caller. A failed DM does not
    cancel the game and does not prevent delivery to other players.
    """
    game_id = game["id"]
    players = list(game["players"].values())
    failed_user_ids = []

    if not players or not isinstance(roles, dict) or not isinstance(questions, dict):
        raise ValueError("اطلاعات بازیکنان، نقش‌ها یا سؤال‌ها معتبر نیست.")

    for player in players:
        user_id = player.get("id")
        role = roles.get(user_id)
        question = questions.get(role) if role in ("citizen", "mafia") else None
        if user_id is None or not isinstance(question, str) or not question.strip():
            raise ValueError(f"اطلاعات نقش یا سؤال بازیکن معتبر نیست: {user_id}")

    game.setdefault("role_delivered", set())
    game.setdefault("role_pending", set())

    for player in players:
        user_id = player["id"]
        if user_id in game["role_delivered"]:
            continue
        role = roles[user_id]
        try:
            await bot.send_message(
                chat_id=user_id,
                text=build_role_message(role, questions[role]),
            )
        except (Forbidden, BadRequest) as error:
            if not is_private_chat_unavailable(error):
                logger.exception("Telegram rejected role DM: game=%s user=%s", game_id, user_id)
                raise
            failed_user_ids.append(user_id)
            game["role_pending"].add(user_id)
            logger.info("Role DM pending private activation: game=%s user=%s", game_id, user_id)
        except TelegramError:
            logger.exception("Role DM failed due to Telegram error: game=%s user=%s", game_id, user_id)
            raise
        else:
            game["role_delivered"].add(user_id)
            game["role_pending"].discard(user_id)
            logger.info("Role DM delivered: game=%s user=%s", game_id, user_id)

    return failed_user_ids


async def send_private_invitation(bot, game, group_chat_id, user_ids):
    """Send a group message with a personal deep-link button for each pending player."""
    if not user_ids:
        return

    bot_info = await bot.get_me()
    if not bot_info.username:
        raise RuntimeError("ربات نام کاربری ندارد؛ ساخت لینک دعوت ممکن نیست.")

    lines = [
        "⚠️ <b>برای دریافت نقش مافیا، پیوی ربات را فعال کنید</b>",
        "بازیکنان زیر هنوز نقش خود را در پیوی دریافت نکرده‌اند:",
        "",
    ]
    rows = []
    for user_id in user_ids:
        player = game["players"].get(user_id, {})
        name = html.escape(str(player.get("name") or "بازیکن"))
        username = player.get("username")
        identity = f"{name} (@{html.escape(str(username))})" if username else f"{name} <code>{user_id}</code>"
        lines.append(f"• {identity}")
        button_name = str(player.get("name") or "بازیکن")[:32]
        payload = f"mafia_{game['id']}_{user_id}"
        url = f"https://t.me/{bot_info.username}?start={payload}"
        rows.append([InlineKeyboardButton(f"ورود به پیوی: {button_name}", url=url)])

    lines.extend([
        "",
        "هر بازیکن روی دکمه مقابل نام خودش بزند و در پیوی، Start را انتخاب کند.",
        "نقش و سؤال همان بازیکن پس از فعال‌سازی به‌صورت خودکار ارسال می‌شود.",
    ])
    await bot.send_message(
        chat_id=group_chat_id,
        text="\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
        disable_web_page_preview=True,
    )
    logger.info("Private activation invitations sent: game=%s players=%s", game["id"], len(user_ids))


async def send_pending_role_to_player(bot, game, user_id):
    """Deliver the already-assigned role after the invited player presses Start."""
    player = game.get("players", {}).get(user_id)
    if player is None:
        return False, "شما در فهرست این بازی نیستید."

    roles = game.get("roles")
    questions = game.get("questions")
    if not isinstance(roles, dict) or not isinstance(questions, dict):
        return False, "نقش‌های این بازی هنوز آماده نشده‌اند. از برگزارکننده بخواه دوباره شروع بازی را بزند."

    role = roles.get(user_id)
    question = questions.get(role) if role in ("citizen", "mafia") else None
    if not isinstance(question, str) or not question.strip():
        return False, "اطلاعات نقش شما پیدا نشد؛ لطفاً به برگزارکننده اطلاع بده."

    if user_id in game.setdefault("role_delivered", set()):
        return True, "نقش و سؤال شما قبلاً ارسال شده‌اند. بازی را در همین پیوی دنبال کنید."

    await bot.send_message(chat_id=user_id, text=build_role_message(role, question))
    game["role_delivered"].add(user_id)
    game.setdefault("role_pending", set()).discard(user_id)
    logger.info("Pending role delivered after /start: game=%s user=%s", game["id"], user_id)
    return True, "نقش و سؤال اختصاصی شما ارسال شد. بازی را در همین پیوی دنبال کنید."
    
