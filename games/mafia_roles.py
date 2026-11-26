
import logging

from telegram.constants import ChatAction
from telegram.error import TelegramError

from games.manager import remove_game

logger = logging.getLogger("PULSE.MAFIA.ROLES")


async def check_private_chats(bot, game, group_chat_id):
    """
    بررسی امکان ارسال پیام خصوصی به بازیکنان.
    بازیکنانی که چت خصوصی فعال ندارند از فهرست بازی
    خارج می‌شوند و در گروه راهنمای فعال‌سازی دریافت می‌کنند.
    """

    failed_players = []

    for user_id, player in list(game["players"].items()):
        try:
            await bot.send_chat_action(
                chat_id=user_id,
                action=ChatAction.TYPING,
            )

        except TelegramError:
            failed_players.append(player.copy())
            game["players"].pop(user_id, None)

            logger.warning(
                "Private chat unavailable: game=%s user=%s",
                game["id"],
                user_id,
            )

    if failed_players:
        lines = [
            "⚠️ <b>فعال‌سازی چت خصوصی</b>",
            "",
            "بازیکنان زیر هنوز امکان دریافت پیام خصوصی از ربات را ندارند:",
            "",
        ]

        for player in failed_players:
            lines.append(f"• {player['mention']}")

        lines.extend([
            "",
            "برای شرکت در بازی:",
            "۱. وارد گفت‌وگوی خصوصی ربات PULSE شوید.",
            "۲. دستور /start را ارسال کنید.",
            "۳. دوباره دکمه ورود به بازی را بزنید.",
            "",
            "ثبت‌نام بازی همچنان باز است.",
        ])

        try:
            await bot.send_message(
                chat_id=group_chat_id,
                text="\n".join(lines),
                parse_mode="HTML",
            )
        except TelegramError:
            logger.exception(
                "Could not notify group about private chat failures: game=%s",
                game["id"],
            )

    return failed_players


async def send_private_roles(bot, game, roles, questions):
    """
    ارسال خصوصی نقش و سؤال به تمام بازیکنان.

    roles:
        {user_id: "citizen" یا "mafia"}

    questions:
        {
            "citizen": "سؤال شهروندان",
            "mafia": "سؤال مافیا"
        }

    در صورت شکست ارسال حتی یک نقش، کل بازی لغو می‌شود.
    """

    players = list(game["players"].values())

    if not players:
        return False, None

    # بررسی اطلاعات تمام بازیکنان قبل از ارسال
    for player in players:
        user_id = player["id"]
        role = roles.get(user_id)

        if role not in ("citizen", "mafia"):
            logger.error("Invalid role: user=%s", user_id)
            return False, user_id

        if not questions.get(role):
            logger.error("Missing question: role=%s", role)
            return False, user_id

    # ارسال خصوصی نقش‌ها
    for player in players:
        user_id = player["id"]
        role = roles[user_id]

        role_name = (
            "مافیا 🔴"
            if role == "mafia"
            else "شهروند 🟢"
        )

        message = (
            "🌙 بازی مافیای PULSE\n\n"
            f"🎭 نقش شما: {role_name}\n\n"
            "❓ سؤال مخصوص شما:\n"
            f"{questions[role]}\n\n"
            "🔒 اطلاعات نقش و سؤال شما محرمانه است."
        )

        try:
            await bot.send_message(
                chat_id=user_id,
                text=message,
            )

        except TelegramError:
            logger.exception(
                "Role delivery failed: game=%s user=%s",
                game["id"],
                user_id,
            )

            # لغو کامل بازی در صورت شکست ارسال
            await remove_game(game["id"])

            return False, user_id

    # ثبت موفقیت ارسال تمام نقش‌ها
    game["roles"] = roles.copy()
    game["questions"] = questions.copy()
    game["phase"] = "roles_sent"

    logger.info(
        "All roles delivered: game=%s players=%s",
        game["id"],
        len(players),
    )

    return True, None
                        
