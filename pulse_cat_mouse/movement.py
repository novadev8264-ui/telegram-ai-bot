"""قواعد حرکت بازیکنان روی نقشه."""
from .map import is_walkable, TUNNEL

DELTAS = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1),
}

def move_player(game, user_id, direction):
    player = game["players"].get(user_id)
    if not player or not player["alive"]:
        return False, "شما بازیکن فعال این بازی نیستید."
    if direction not in DELTAS:
        return False, "جهت حرکت معتبر نیست."
    dr, dc = DELTAS[direction]
    old_r, old_c = player["pos"]
    target = (old_r + dr, old_c + dc)
    if not is_walkable(game["board"], target):
        return False, "این مسیر بسته است یا از نقشه خارج می‌شود."
    player["pos"] = target
    if game["board"][target[0]][target[1]] == TUNNEL:
        tunnels = [(r, c) for r in range(8) for c in range(8)
                   if game["board"][r][c] == TUNNEL]
        if len(tunnels) == 2:
            player["pos"] = tunnels[1] if target == tunnels[0] else tunnels[0]
            return True, "از تونل عبور کردی! 🌀"
    return True, "حرکت ثبت شد."
  
