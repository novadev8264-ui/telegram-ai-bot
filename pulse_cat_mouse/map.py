"""ساخت و نمایش نقشه ۸×۸ بازی موش و گربه."""
import random

SIZE = 8
WALL = "🧱"
EMPTY = "▫️"
CHEESE = "🧀"
DEN = "🏠"
TUNNEL = "🌀"

def create_map():
    """ساخت نقشه ۸×۸ با مسیر باز بین محل شروع موش‌ها، پنیرها و لانه."""
    starts = {
        (0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (0, 2), (2, 1), (1, 2),
        (7, 7), (7, 6), (6, 7), (6, 6), (5, 7), (0, 7), (7, 0),
    }
    cheese_positions = [(3, 3), (2, 5), (4, 2), (5, 6), (6, 3)]
    for _ in range(100):
        cells = [[EMPTY for _ in range(SIZE)] for _ in range(SIZE)]
        candidates = [(r, c) for r in range(SIZE) for c in range(SIZE)
                      if (r, c) not in starts and (r, c) not in cheese_positions]
        random.shuffle(candidates)
        for r, c in candidates[:10]:
            cells[r][c] = WALL
        for r, c in cheese_positions:
            cells[r][c] = CHEESE
        cells[7][7] = DEN
        cells[0][7] = TUNNEL
        cells[7][0] = TUNNEL

        # اطمینان از اینکه موش‌ها می‌توانند به تمام پنیرها و لانه برسند.
        seen = {(0, 0)}
        stack = [(0, 0)]
        while stack:
            r, c = stack.pop()
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if (0 <= nr < SIZE and 0 <= nc < SIZE
                        and cells[nr][nc] != WALL and (nr, nc) not in seen):
                    seen.add((nr, nc))
                    stack.append((nr, nc))
        if all(pos in seen for pos in cheese_positions + [(7, 7)]):
            return cells
    # نقشه کاملاً باز، fallback مطمئن
    cells = [[EMPTY for _ in range(SIZE)] for _ in range(SIZE)]
    for r, c in cheese_positions:
        cells[r][c] = CHEESE
    cells[7][7], cells[0][7], cells[7][0] = DEN, TUNNEL, TUNNEL
    return cells

def in_bounds(pos):
    r, c = pos
    return 0 <= r < SIZE and 0 <= c < SIZE

def is_walkable(board, pos):
    r, c = pos
    return in_bounds(pos) and board[r][c] != WALL

def public_map(game):
    """نقشه عمومی بدون افشای موقعیت بازیکنان."""
    return "\n".join("".join(row) for row in game["board"])
  
