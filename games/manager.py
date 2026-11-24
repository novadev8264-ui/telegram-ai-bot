
import asyncio
import logging
import secrets

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger("PULSE.GAMES")

# بازی‌های فعال
ACTIVE_GAMES = {}

# قفل جلوگیری از ثبت‌نام هم‌زمان تکراری
GAME_LOCK = asyncio.Lock()


def player_link(user):
    """ساخت لینک قابل کلیک برای پروفایل بازیکن."""

    name = user.full_name or "بازیکن"

    if user.username:
        return f'<a href="https://t.me/{user.username}">{name}</a>'

    return (
        f'<a href="tg://user?id={user.id}">{name}</a>'
    )


def create_game(game_type, owner):
    """ساخت بازی جدید."""

    game_id = secrets.token_hex(4)

    ACTIVE_GAMES[game_id] = {
        "id": game_id,
        "type": game_type,
        "owner_id": owner.id,
        "owner_name": owner.full_name,
        "players": {},
        "status": "registering",
        "created_at": asyncio.get_running_loop().time(),
    }

    return ACTIVE_GAMES[game_id]


def get_game(game_id):
    return ACTIVE_GAMES.get(game_id)


def game_keyboard(game_id):
    """دکمه‌های ثبت‌نام و شروع بازی."""

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎮 ورود به بازی",
                callback_data=f"game_join:{game_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "👥 بازیکنان",
                callback_data=f"game_players:{game_id}",
            ),
            InlineKeyboardButton(
                "🏁 شروع بازی",
                callback_data=f"game_start:{game_id}",
            )
        ]
    ])


def game_text(game):
    """ساخت پیام وضعیت بازی."""

    players = game["players"]

    lines = [
        "🎮 <b>بازی جدید PULSE</b>",
        "",
        f"🆔 کد بازی: <code>{game['id']}</code>",
        f"👑 برگزارکننده: {player_link_from_id(game)}",
        "",
        f"👥 تعداد بازیکنان: {len(players)}",
        "",
        "📋 <b>بازیکنان ثبت‌نام‌شده:</b>",
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
        "برای شرکت در بازی روی دکمه ورود بزن."
    ])

    return "\n".join(lines)


def player_link_from_id(game):
    name = game["owner_name"]
    user_id = game["owner_id"]

    return (
        f'<a href="tg://user?id={user_id}">{name}</a>'
    )


async def join_game(game_id, user):

    async with GAME_LOCK:

        game = get_game(game_id)

        if not game:
            return False, "این بازی پیدا نشد."

        if game["status"] != "registering":
            return False, "ثبت‌نام این بازی بسته شده است."

        if user.id in game["players"]:
            return False, "شما قبلاً در این بازی ثبت‌نام کرده‌اید."

        game["players"][user.id] = {
            "id": user.id,
            "name": user.full_name,
            "username": user.username,
            "mention": player_link(user),
            "score": 0,
        }

        return True, "با موفقیت وارد بازی شدی! 🎮"


async def close_registration(game_id, user_id):

    async with GAME_LOCK:

        game = get_game(game_id)

        if not game:
            return False, "بازی پیدا نشد."

        if game["owner_id"] != user_id:
            return False, "فقط برگزارکننده می‌تواند بازی را شروع کند."

        if game["status"] != "registering":
            return False, "این بازی قبلاً شروع شده است."

        if not game["players"]:
            return False, "هنوز هیچ بازیکنی ثبت‌نام نکرده است."

        game["status"] = "playing"

        return True, game


async def finish_game(game_id, winner_id=None):

    async with GAME_LOCK:

        game = get_game(game_id)

        if not game:
            return None

        game["status"] = "finished"
        game["winner_id"] = winner_id

        return game


async def remove_game(game_id):

    async with GAME_LOCK:

        return ACTIVE_GAMES.pop(game_id, None)
        
