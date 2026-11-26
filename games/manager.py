
import asyncio
import html
import logging
import secrets
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger("PULSE.GAMES")

ACTIVE_GAMES = {}
GAME_LOCK = asyncio.Lock()


def player_link(user):
    """ساخت لینک قابل کلیک پروفایل بازیکن."""

    name = html.escape(user.full_name or "بازیکن")

    if user.username:
        username = html.escape(user.username)
        return f'<a href="https://t.me/{username}">{name}</a>'

    return f'<a href="tg://user?id={user.id}">{name}</a>'


def create_game(game_type, owner):
    """ساخت بازی جدید."""

    game_id = secrets.token_hex(4)

    game = {
        "id": game_id,
        "type": game_type,
        "owner_id": owner.id,
        "owner_name": owner.full_name or "بازیکن",
        "players": {},
        "status": "registering",
        "winner_id": None,
        "created_at": time.time(),
    }

    ACTIVE_GAMES[game_id] = game

    logger.info(
        "Game created: id=%s type=%s owner=%s",
        game_id,
        game_type,
        owner.id,
    )

    return game


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


def player_link_from_id(game):
    """لینک پروفایل برگزارکننده."""

    name = html.escape(game["owner_name"])
    user_id = game["owner_id"]

    return f'<a href="tg://user?id={user_id}">{name}</a>'


def game_text(game):
    """ساخت متن وضعیت بازی."""

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
            lines.append(f"{number}. {player['mention']}")

    lines.extend([
        "",
        "برای شرکت در بازی روی دکمه ورود بزن."
    ])

    return "\n".join(lines)


async def join_game(game_id, user, max_players=None):
    """ثبت‌نام بازیکن با کنترل ظرفیت و جلوگیری از ثبت‌نام تکراری."""

    async with GAME_LOCK:
        game = get_game(game_id)

        if not game:
            return False, "این بازی پیدا نشد."

        if game["status"] != "registering":
            return False, "ثبت‌نام این بازی بسته شده است."

        if user.id in game["players"]:
            return False, "شما قبلاً در این بازی ثبت‌نام کرده‌اید."

        if (
            max_players is not None
            and len(game["players"]) >= max_players
        ):
            return False, (
                f"ظرفیت این بازی تکمیل شده است؛ "
                f"حداکثر {max_players} نفر."
            )

        game["players"][user.id] = {
            "id": user.id,
            "name": user.full_name or "بازیکن",
            "username": user.username,
            "mention": player_link(user),
            "score": 0,
        }

        logger.info(
            "Player joined: game=%s user=%s",
            game_id,
            user.id,
        )

        return True, "با موفقیت وارد بازی شدی! 🎮"


async def begin_registration_check(game_id, user_id):
    """قفل کردن ثبت‌نام هنگام بررسی چت خصوصی."""

    async with GAME_LOCK:
        game = get_game(game_id)

        if not game:
            return False, "بازی پیدا نشد."

        if game["owner_id"] != user_id:
            return False, "فقط برگزارکننده می‌تواند بازی را شروع کند."

        if game["status"] != "registering":
            return False, "این بازی در حال بررسی یا قبلاً شروع شده است."

        game["status"] = "checking_private"

        logger.info(
            "Private chat check started: game=%s",
            game_id,
        )

        return True, game


async def reopen_registration(game_id):
    """باز کردن دوباره ثبت‌نام پس از بررسی ناموفق."""

    async with GAME_LOCK:
        game = get_game(game_id)

        if not game:
            return False

        if game["status"] != "checking_private":
            return False

        game["status"] = "registering"

        logger.info(
            "Registration reopened: game=%s",
            game_id,
        )

        return True


async def close_registration(game_id, user_id):
    """بستن ثبت‌نام توسط برگزارکننده."""

    async with GAME_LOCK:
        game = get_game(game_id)

        if not game:
            return False, "بازی پیدا نشد."

        if game["owner_id"] != user_id:
            return False, "فقط برگزارکننده می‌تواند بازی را شروع کند."

        if game["status"] not in (
            "registering",
            "checking_private",
        ):
            return False, "این بازی قبلاً شروع شده است."

        if not game["players"]:
            return False, "هنوز هیچ بازیکنی ثبت‌نام نکرده است."

        game["status"] = "playing"

        logger.info("Game started: %s", game_id)

        return True, game


async def finish_game(game_id, winner_id=None):
    """پایان بازی و ثبت برنده."""

    async with GAME_LOCK:
        game = get_game(game_id)

        if not game:
            return None

        if game["status"] == "finished":
            return game

        game["status"] = "finished"
        game["winner_id"] = winner_id
        game["finished_at"] = time.time()

        logger.info(
            "Game finished: id=%s winner=%s",
            game_id,
            winner_id,
        )

        return game


async def remove_game(game_id):
    """حذف بازی از فهرست بازی‌های فعال."""

    async with GAME_LOCK:
        return ACTIVE_GAMES.pop(game_id, None)
    
