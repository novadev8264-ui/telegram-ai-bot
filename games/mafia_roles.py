import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.error import BadRequest, Forbidden, TelegramError

from games.manager import remove_game


logger = logging.getLogger("PULSE.MAFIA.ROLES")


def _is_private_chat_unavailable(error):
    """تشخیص خطاهایی که نشان می‌دهند چت خصوصی هنوز قابل دسترسی نیست."""

    if isinstance(error, Forbidden):
        return True

    if isinstance(error, BadRequest):
        description = str(error).lower()
        unavailable_messages = (
            "chat not found",
            "bot can't initiate conversation",
            "bot cannot initiate conversation",
            "user is deactivated",
            "user deactivated",
            "bot was blocked by the user",
        )
        return any(message in description for message in unavailable_messages)

    return False


async def check_private_chats(bot, game, group_chat_id):
    """بررسی پیوی بازیکنان و ارسال لینک اختصاصی برای کسانی که هنوز Start نزده‌اند.

    هیچ بازیکنی در این مرحله حذف نمی‌شود. پس از فعال‌سازی پیوی، برگزارکننده
    باید دوباره دکمه شروع بازی را بزند تا بررسی و ارسال نقش‌ها انجام شود.
    """

    failed_players = []

    for user_id, player in list(game["players"].items()):
        try:
            await bot.send_chat_action(
                chat_id=user_id,
                action=ChatAction.TYPING,
            )
        except (Forbidden, BadRequest) as error:
            if not _is_private_chat_unavailable(error):
                raise
            failed_players.append((user_id, player.copy()))
            logger.info(
                "Private chat not started: game=%s user=%s",
                game["id"], user_id,
            )

    if not failed_players:
        return []

    bot_info = await bot.get_me()
    if not bot_info.username:
        raise RuntimeError("ربات نام کاربری ندارد؛ ساخت لینک دعوت ممکن نیست.")

    lines = [
        "⚠️ <b>فعال‌سازی پیوی برای دریافت نقش مافیا</b>",
        "",
        "بازیکنان زیر هنوز گفت‌وگوی خصوصی با PULSE را فعال نکرده‌اند.",
        "برای هر نفر، دکمه مخصوص خودش را قرار داده‌ایم:",
        "",
    ]
    keyboard_rows = []

    for user_id, player in failed_players:
        name = html.escape(str(player.get("name") or "بازیکن"))
        username = player.get("username")
        if username:
            identity = f"{name} (@{html.escape(str(username))})"
        else:
            identity = f'{name} <code>{user_id}</code>'
        lines.append(f"• {identity}")

        payload = f"mafia_{game['id']}_{user_id}"
        deep_link = f"https://t.me/{bot_info.username}?start={payload}"
        button_name = str(player.get("name") or "بازیکن")
        if len(button_name) > 35:
            button_name = button_name[:32] + "..."
        keyboard_rows.append([
            InlineKeyboardButton(
                text=f"ورود به پیوی: {button_name}",
                url=deep_link,
            )
        ])

    lines.extend([
        "",
        "۱. هر بازیکن فقط روی دکمه مربوط به نام خودش بزند.",
        "۲. در پیوی ربات، دکمه Start را بزند.",
        "۳. بعد از فعال‌سازی همه افراد، برگزارکننده دوباره «شروع بازی» را بزند.",
        "",
        "هیچ بازیکنی به‌خاطر فعال نبودن پیوی از بازی حذف نمی‌شود.",
    ])

    await bot.send_message(
        chat_id=group_chat_id,
        text="\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard_rows),
        disable_web_page_preview=True,
    )

    return [player for _, player in failed_players]


async def send_private_roles(bot, game, roles, questions):
    """ارسال خصوصی نقش و سؤال به تمام بازیکنان؛ در خطا بازی لغو می‌شود."""

    game_id = game["id"]
    players = list(game["players"].values())

    if not players:
        logger.error("Cannot send roles: no players. game=%s", game_id)
        await remove_game(game_id)
        return False, None

    if not isinstance(roles, dict) or not isinstance(questions, dict):
        logger.error("Invalid roles/questions data: game=%s", game_id)
        await remove_game(game_id)
        return False, None

    # اعتبارسنجی همه اطلاعات قبل از ارسال اولین نقش
    for player in players:
        user_id = player.get("id")
        if user_id is None:
            logger.error("Player has no user ID: game=%s", game_id)
            await remove_game(game_id)
            return False, None

        role = roles.get(user_id)
        if role not in ("citizen", "mafia"):
            logger.error("Invalid role: game=%s user=%s", game_id, user_id)
            await remove_game(game_id)
            return False, user_id

        question = questions.get(role)
        if not isinstance(question, str) or not question.strip():
            logger.error("Missing question: game=%s role=%s", game_id, role)
            await remove_game(game_id)
            return False, user_id

    for player in players:
        user_id = player["id"]
        role = roles[user_id]
        role_name = "مافیا 🔴" if role == "mafia" else "شهروند 🟢"
        message = (
            "🌙 بازی مافیای PULSE\n\n"
            f"🎭 نقش شما: {role_name}\n\n"
            "❓ سؤال مخصوص شما:\n"
            f"{questions[role]}\n\n"
            "🔒 اطلاعات نقش و سؤال شما محرمانه است."
        )

        try:
            await bot.send_message(chat_id=user_id, text=message)
        except TelegramError:
            logger.exception(
                "Role delivery failed: game=%s user=%s", game_id, user_id
            )
            # ممکن است پیام بعضی بازیکنان ارسال شده باشد و قابل پس‌گرفتن نیست.
            await remove_game(game_id)
            return False, user_id

    game["roles"] = roles.copy()
    game["questions"] = questions.copy()
    game["phase"] = "roles_sent"

    logger.info("All roles delivered: game=%s players=%s", game_id, len(players))
    return True, None
    
