"""نوبت‌بندی تیم‌ها و بازیکنان."""
def alive_team_ids(game, team):
    return [uid for uid, p in game["players"].items()
            if p["alive"] and p["team"] == team]

def next_turn(game):
    """موش‌ها حرکت می‌کنند و سپس گربه‌ها؛ هر بازیکن یک حرکت در هر دور."""
    team_order = ("mouse", "cat")
    for _ in range(4):
        team = game["phase"]
        ids = alive_team_ids(game, team)
        if ids:
            start = game.get("turn_index", 0)
            for offset in range(len(ids)):
                index = (start + offset) % len(ids)
                uid = ids[index]
                if game["players"][uid]["moved_round"] < game["round"]:
                    game["turn_index"] = (index + 1) % len(ids)
                    return uid
        if team == "mouse":
            game["phase"] = "cat"
            game["turn_index"] = 0
        else:
            game["phase"] = "mouse"
            game["turn_index"] = 0
            game["round"] += 1
            if game["round"] > 10:
                return None
    return None

def current_team(game):
    return game.get("phase", "mouse")

