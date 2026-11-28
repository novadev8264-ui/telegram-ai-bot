"""متن‌ها و صفحه‌کلیدهای تلگرام."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from .players import players_text
from .map import public_map

def registration_keyboard(game_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 ورود به بازی", callback_data=f"cm:join:{game_id}")],
        [InlineKeyboardButton("👥 بازیکنان", callback_data=f"cm:players:{game_id}"),
         InlineKeyboardButton("🏁 شروع", callback_data=f"cm:start:{game_id}")]
    ])

def move_keyboard(game_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬆️", callback_data=f"cm:move:{game_id}:up")],
        [InlineKeyboardButton("⬅️", callback_data=f"cm:move:{game_id}:left"),
         InlineKeyboardButton("➡️", callback_data=f"cm:move:{game_id}:right")],
        [InlineKeyboardButton("⬇️", callback_data=f"cm:move:{game_id}:down")]
    ])

def registration_text(game):
    return (
        "🐱 <b>بازی موش و گربه PULSE</b> 🐭\n\n"
        f'🆔 کد بازی: <code>{game["id"]}</code>\n'
        f'👑 برگزارکننده: {game["owner_mention"]}\n'
        f'👥 بازیکنان: {len(game["players"])}/12\n\n'
        + players_text(game) + "\n\n"
        "برای شرکت روی دکمه ورود بزن.\n"
        "شروع بازی به ۴ تا ۱۲ بازیکن نیاز دارد."
    )

def team_map_text(game, team):
    # موقعیت هم‌تیمی‌ها نمایش داده می‌شود؛ جایگاه تیم مقابل پنهان است.
    board = game["board"]
    positions = {}
    for p in game["players"].values():
        if p["alive"] and p["team"] == team:
            positions[p["pos"]] = p["symbol"]
    rows = []
    for r in range(8):
        row = []
        for c in range(8):
            row.append(positions.get((r, c), board[r][c]))
        rows.append("".join(row))
    return "\n".join(rows)

def team_private_text(game, player):
    team_name = "موش‌ها 🐭" if player["team"] == "mouse" else "گربه‌ها 🐱"
    return (
        f'🎮 <b>نوبت شما در بازی {game["id"]}</b>\n'
        f'تیم: {team_name}\n'
        f'دور: {game["round"]}\n'
        f'پنیر جمع‌شده: {game["cheese"]}/5\n\n'
        f'<pre>{team_map_text(game, player["team"])}</pre>\n'
        "یک خانه در جهت دلخواه حرکت کن."
    )

def group_status_text(game, note=""):
    cats = sum(1 for p in game["players"].values() if p["alive"] and p["team"] == "cat")
    mice = sum(1 for p in game["players"].values() if p["alive"] and p["team"] == "mouse")
    text = (
        "🐱 <b>موش و گربه PULSE</b> 🐭\n\n"
        f'🔄 دور: {game["round"]}\n'
        f'🧀 پنیر: {game["cheese"]}/5\n'
        f'🐱 گربه‌های باقی‌مانده: {cats}\n'
        f'🐭 موش‌های باقی‌مانده: {mice}\n\n'
        "<pre>" + public_map(game) + "</pre>\n"
        "موقعیت بازیکنان در نقشه عمومی پنهان است."
    )
    if note:
        text += "\n\n" + note
    return text

def roster_text(game):
    return players_text(game)

                                     
