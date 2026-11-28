"""ثبت‌نام، نام نمایشی و لینک پروفایل بازیکنان."""
import html

MIN_PLAYERS = 4
MAX_PLAYERS = 12

def player_profile(user):
    name = html.escape(user.full_name or "بازیکن")
    if user.username:
        username = html.escape(user.username)
        return f'<a href="https://t.me/{username}">{name}</a>'
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def make_player(user):
    return {
        "id": user.id,
        "name": user.full_name or "بازیکن",
        "username": user.username,
        "mention": player_profile(user),
        "team": None,
        "alive": True,
        "pos": None,
        "symbol": None,
        "moved_round": 0,
    }

def assign_teams(game):
    """تعداد گربه‌ها بر اساس تعداد کل بازیکنان."""
    ids = list(game["players"])
    count = len(ids)
    if count < MIN_PLAYERS or count > MAX_PLAYERS:
        raise ValueError(f"تعداد بازیکنان باید بین {MIN_PLAYERS} تا {MAX_PLAYERS} باشد.")
    cats = 1 if count <= 5 else 2 if count <= 8 else 3 if count <= 11 else 4
    import random
    random.shuffle(ids)
    for index, uid in enumerate(ids):
        player = game["players"][uid]
        player["team"] = "cat" if index < cats else "mouse"
        player["symbol"] = "🐱" if player["team"] == "cat" else "🐭"
    return cats, count - cats

def players_text(game):
    if any(p["team"] is None for p in game["players"].values()):
        lines = ["👥 <b>بازیکنان ثبت‌نام‌شده</b>", ""]
        for i, p in enumerate(game["players"].values(), 1):
            lines.append(f'{i}. {p["mention"]}')
        lines += ["", f'👥 مجموع: {len(game["players"])} نفر']
        return "\n".join(lines)

    cats, mice = [], []
    for p in game["players"].values():
        line = f'{p["symbol"]} {p["mention"]}'
        (cats if p["team"] == "cat" else mice).append(line)
    lines = ["👥 <b>بازیکنان بازی موش و گربه</b>", "", "🐭 <b>تیم موش‌ها</b>"]
    lines.extend(f"{i}. {line}" for i, line in enumerate(mice, 1))
    lines += ["", "🐱 <b>تیم گربه‌ها</b>"]
    lines.extend(f"{i}. {line}" for i, line in enumerate(cats, 1))
    lines += ["", f'👥 مجموع: {len(game["players"])} نفر']
    return "\n".join(lines)

    
