"""بررسی پنیر، شکار و شرایط پایان بازی."""
import html
from .map import CHEESE, DEN, TUNNEL

CHEESE_TO_WIN = 5

def resolve_after_move(game, user_id):
    player = game["players"][user_id]
    r, c = player["pos"]
    tile = game["board"][r][c]
    note = ""
    if player["team"] == "mouse" and tile == CHEESE:
        game["board"][r][c] = "▫️"
        game["cheese"] += 1
        note = f'🧀 یک پنیر پیدا شد! مجموع پنیرها: {game["cheese"]}'
    if tile == TUNNEL:
        note = (note + "\n" if note else "") + "🌀 به یک تونل رسیدی؛ تونل فعلاً فقط خانه ویژه است."
    # اگر موش یا گربه وارد خانه حریف شود، موش گرفته می‌شود.
    for other in game["players"].values():
        if (other["alive"] and other["team"] == "mouse"
                and other["pos"] == player["pos"]):
            opposing_cat_here = any(
                p["alive"] and p["team"] == "cat" and p["pos"] == player["pos"]
                for p in game["players"].values()
            )
            if opposing_cat_here:
                other["alive"] = False
                note += ("\n" if note else "") + f'🐱 یک موش گرفته شد: {html.escape(other["name"])}'
    # موش در لانه پس از جمع شدن پنیر کافی، تیم موش‌ها را برنده می‌کند.
    if player["team"] == "mouse" and player["alive"] and tile == DEN and game["cheese"] >= CHEESE_TO_WIN:
        game["status"] = "finished"
        game["winner"] = "mouse"
        return note, "mouse"
    mice_alive = any(p["alive"] and p["team"] == "mouse" for p in game["players"].values())
    if not mice_alive:
        game["status"] = "finished"
        game["winner"] = "cat"
        return note, "cat"
    return note, None
  
