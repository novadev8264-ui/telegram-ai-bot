
import logging

from telegram.error import TelegramError

from games.manager import remove_game

logger = logging.getLogger("PULSE.MAFIA.ROLES")


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
    """

    players = list(game["players"].values())

    # بررسی کامل بودن اطلاعات قبل از ارسال
    for player in players:
        user_id = player["id"]
        role = roles.get(user_id)

        if role not in ("citizen", "mafia"):
            return False, user_id

        if not questions.get(role):
            return False, user_id

    # ارسال نقش و سؤال به‌صورت خصوصی
    for player in players:
        user_id = player["id"]
        role = roles[user_id]

        if role == "mafia":
            role_name = "مافیا 🔴"
        else:
            role_name = "شهروند 🟢"

        message = (
            "🌙 بازی مافیای PULSE\n\n"
            f"🎭 نقش شما: {role_name}\n\n"
            "❓ سؤال مخصوص شما:\n"
            f"{questions[role]}\n\n"
            "این اطلاعات محرمانه است."
        )

        try:
            await bot.send_message(
                chat_id=user_id,
                text=message,
            )

        except TelegramError:
            logger.exception(
                "Private role delivery failed: user=%s game=%s",
                user_id,
                game["id"],
            )

            await remove_game(game["id"])

            return False, user_id

    # ثبت اطلاعات داخلی بازی پس از ارسال موفق همه پیام‌ها
    game["roles"] = roles.copy()
    game["questions"] = questions.copy()
    game["phase"] = "roles_sent"

    logger.info(
        "All private roles sent successfully: game=%s",
        game["id"],
    )

    return True, None
  
