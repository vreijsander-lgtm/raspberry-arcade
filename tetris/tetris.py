"""Tetris game logic (no pygame needed). Used by main/main.py."""
import random

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
COLS, ROWS = 10, 20
CELL = 40
BOARD_X, BOARD_Y = 70, 140

DAS_DELAY = 170            # ms before left/right starts repeating
DAS_RATE = 50              # ms between repeats
SOFT_INTERVAL = 35         # ms per row while holding DOWN
LOCK_DELAY = 500           # ms a landed piece may still be moved
MAX_LOCK_RESETS = 15
MAX_START_LEVEL = 15
MAX_SCORES = 10
POINTS = {1: 100, 2: 300, 3: 500, 4: 800}
NAME_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "   # last one: space (DOWN from A)
NAME_LEN = 10

COLORS = {
    "I": (0, 200, 220),
    "O": (240, 220, 0),
    "T": (170, 60, 200),
    "S": (60, 200, 70),
    "Z": (225, 50, 50),
    "J": (50, 90, 230),
    "L": (240, 140, 30),
    "G": (115, 115, 130),    # garbage lines in multiplayer
}

# CHAOS mode: random shapes get one of these colours
CHAOS_COLORS = {"a": (255, 95, 95), "b": (255, 165, 60), "c": (245, 225, 80),
                "d": (110, 230, 110), "e": (80, 215, 235), "f": (95, 125, 255),
                "g": (190, 105, 255), "h": (255, 115, 200)}
COLORS.update(CHAOS_COLORS)
MODES = ("CLASSIC", "CHAOS")

# (box size, cells) - rotations are generated below
PIECES = {
    "I": (4, [(0, 1), (1, 1), (2, 1), (3, 1)]),
    "O": (2, [(0, 0), (1, 0), (0, 1), (1, 1)]),
    "T": (3, [(1, 0), (0, 1), (1, 1), (2, 1)]),
    "S": (3, [(1, 0), (2, 0), (0, 1), (1, 1)]),
    "Z": (3, [(0, 0), (1, 0), (1, 1), (2, 1)]),
    "J": (3, [(0, 0), (0, 1), (1, 1), (2, 1)]),
    "L": (3, [(2, 0), (0, 1), (1, 1), (2, 1)]),
}
BOX = {k: v[0] for k, v in PIECES.items()}
ROTATIONS = {}
for _kind, (_n, _cells) in PIECES.items():
    _rots = [list(_cells)]
    for _ in range(3):
        _rots.append([(_n - 1 - y, x) for x, y in _rots[-1]])
    ROTATIONS[_kind] = _rots

KICKS = [(0, 0), (-1, 0), (1, 0), (-2, 0), (2, 0), (0, -1), (-1, -1), (1, -1)]


def _rotations(n, cells):
    rots = [list(cells)]
    for _ in range(3):
        rots.append([(n - 1 - y, x) for x, y in rots[-1]])
    return rots


def random_shape(rng):
    """CHAOS: a brand new random block (3 to 6 squares, all touching).
    Returns (rotations, box size)."""
    size = rng.choices((3, 4, 5, 6), weights=(24, 34, 32, 10))[0]
    cells = {(0, 0)}
    while len(cells) < size:
        x, y = rng.choice(sorted(cells))
        dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        cells.add((x + dx, y + dy))
    minx = min(c[0] for c in cells)
    miny = min(c[1] for c in cells)
    cells = [(x - minx, y - miny) for x, y in cells]
    n = max(max(c[0] for c in cells), max(c[1] for c in cells)) + 1
    return _rotations(n, cells), n


# ----------------------------------------------------------------------------
# Game logic (no pygame needed)
# ----------------------------------------------------------------------------
class Tetris:
    def __init__(self, start_level=1, seed=None, mode="CLASSIC"):
        self.rng = random.Random(seed)   # same seed = same pieces for everyone
        self.mode = mode if mode in MODES else "CLASSIC"
        self.grid = [[None] * COLS for _ in range(ROWS)]
        self.bag = []
        self.score = 0
        self.lines = 0
        self.start_level = start_level
        self.level = start_level
        self.game_over = False
        self.soft_block = False
        self.fall_timer = 0
        self.soft_timer = 0
        self.lock_timer = 0
        self.lock_resets = 0
        self.pending_garbage = []        # hole columns, applied after next lock
        self.clears_unsent = 0           # lines cleared, not yet sent to host
        self.next_kind, self.next_rots, self.next_box = self._new_piece()
        self._spawn()

    # -- helpers
    def _new_piece(self):
        """(colour key, rotations, box size) of the next piece."""
        if self.mode == "CHAOS":
            rots, n = random_shape(self.rng)
            return self.rng.choice(sorted(CHAOS_COLORS)), rots, n
        kind = self._draw()
        return kind, ROTATIONS[kind], BOX[kind]

    def _draw(self):
        if not self.bag:
            self.bag = list(PIECES.keys())
            self.rng.shuffle(self.bag)
        return self.bag.pop()

    def _spawn(self):
        self.kind, self.rots, self.box = self.next_kind, self.next_rots, self.next_box
        self.next_kind, self.next_rots, self.next_box = self._new_piece()
        self.rot = 0
        self.x = (COLS - self.box) // 2
        self.y = 0
        self.fall_timer = 0
        self.soft_timer = 0
        self.lock_timer = 0
        self.lock_resets = 0
        if self.collides(self.rot, self.x, self.y):
            self.game_over = True

    def cells(self, rot=None, x=None, y=None):
        rot = self.rot if rot is None else rot
        x = self.x if x is None else x
        y = self.y if y is None else y
        return [(x + cx, y + cy) for cx, cy in self.rots[rot]]

    def collides(self, rot, x, y):
        for gx, gy in self.cells(rot, x, y):
            if gx < 0 or gx >= COLS or gy >= ROWS:
                return True
            if gy >= 0 and self.grid[gy][gx] is not None:
                return True
        return False

    def can_fall(self):
        return not self.collides(self.rot, self.x, self.y + 1)

    def interval(self):
        return max(40, int(800 * (0.85 ** (self.level - 1))))

    def ghost_y(self):
        y = self.y
        while not self.collides(self.rot, self.x, y + 1):
            y += 1
        return y

    def _adjusted(self):
        """Called after a successful move/rotate: refresh the lock delay."""
        if not self.can_fall() and self.lock_resets < MAX_LOCK_RESETS:
            self.lock_timer = 0
            self.lock_resets += 1

    def snapshot(self):
        """The board (with the falling piece) as a 200 character string."""
        rows = [["." if c is None else c for c in row] for row in self.grid]
        if not self.game_over:
            for gx, gy in self.cells():
                if 0 <= gy < ROWS and 0 <= gx < COLS:
                    rows[gy][gx] = self.kind
        return "".join("".join(r) for r in rows)

    # -- multiplayer: garbage lines
    def queue_garbage(self, hole):
        self.pending_garbage.append(max(0, min(COLS - 1, int(hole))))

    def _apply_garbage(self):
        for hole in self.pending_garbage:
            if any(c is not None for c in self.grid[0]):
                self.game_over = True        # pushed out of the top
            self.grid.pop(0)
            row = ["G"] * COLS
            row[hole] = None                 # the one-block hole
            self.grid.append(row)            # new line at the bottom
        self.pending_garbage = []

    # -- player actions
    def move(self, dx):
        if self.game_over:
            return False
        if not self.collides(self.rot, self.x + dx, self.y):
            self.x += dx
            self._adjusted()
            return True
        return False

    def rotate(self):
        if self.game_over:
            return False
        new_rot = (self.rot + 1) % 4
        for dx, dy in KICKS:
            if not self.collides(new_rot, self.x + dx, self.y + dy):
                self.rot = new_rot
                self.x += dx
                self.y += dy
                self._adjusted()
                return True
        return False

    # -- time step
    def update(self, dt, soft):
        if self.game_over:
            return
        if not soft:
            self.soft_block = False
        if soft and not self.soft_block:
            self.soft_timer += dt
            while self.soft_timer >= SOFT_INTERVAL:
                self.soft_timer -= SOFT_INTERVAL
                if self.can_fall():
                    self.y += 1
                    self.score += 1
                    self.fall_timer = 0
                else:
                    break
        else:
            self.soft_timer = 0

        if self.can_fall():
            self.lock_timer = 0
            self.fall_timer += dt
            iv = self.interval()
            while self.fall_timer >= iv and self.can_fall():
                self.fall_timer -= iv
                self.y += 1
            if not self.can_fall():
                self.fall_timer = 0
        else:
            self.lock_timer += dt
            if self.lock_timer >= LOCK_DELAY:
                self._lock()

    def _lock(self):
        for gx, gy in self.cells():
            if 0 <= gy < ROWS and 0 <= gx < COLS:
                self.grid[gy][gx] = self.kind
        remaining = [row for row in self.grid if any(c is None for c in row)]
        cleared = ROWS - len(remaining)
        if cleared:
            self.grid = [[None] * COLS for _ in range(cleared)] + remaining
            self.score += POINTS.get(cleared, 800) * self.level
            self.lines += cleared
            self.clears_unsent += cleared
            self.level = self.start_level + self.lines // 10
        if self.pending_garbage:
            self._apply_garbage()
        self.soft_block = True   # must release DOWN before next piece soft-drops
        if not self.game_over:
            self._spawn()
