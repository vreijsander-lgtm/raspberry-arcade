"""
Pulsar - game logic (no pygame in here, so it can be tested anywhere).

A paddle game for the tall screen: your paddle at the bottom, the
computer's at the top, a ball of plasma in between. Get the ball past the
computer to score a point; if it gets past you, you lose a life (3 lives).
THE LONGER NOBODY SCORES, THE FASTER THE BALL GOES - after every point it
starts slow again.

Controls (see main.py) - the same six buttons as the other games:
    LEFT / RIGHT   move your paddle
    BUTTON2        SMASH: press it just before the ball reaches you and it
                   flies back extra fast (hard for the computer to reach;
                   in BRICKS it plows straight through the bricks)
    BUTTON1        menu
Where the ball hits your paddle decides the angle: the edges send it off
steeply, the middle sends it straight.

Modes:
    CLASSIC     as above
    MULTIBALL   one extra ball for every 5 points you have (up to 3 at once)
    SHRINK      your paddle gets a bit smaller with every point (x2 points)
    BRICKS      no computer: break walls of bricks at the top instead.
                The ball keeps one steady speed here (no speeding up).
                Broken bricks sometimes drop a power-up capsule - catch it
                with your paddle (see POWERUPS). With more balls you only
                lose a life when the LAST ball is gone.
    POWER       power-up orbs float across the middle; a ball flying through
                one gives it to whoever hit that ball last (see ORBS) - the
                computer collects them too.
Multiplayer (PulsarVersus): two players, first to 7 points. The host Pi runs
it and sends snapshots; both players see their own paddle at the bottom.
"""
import math
import random

SW, SH = 540, 960
TOP, BOTTOM = 132, 912           # the arena (balls leaving it score)
LEFT, RIGHT = 14, SW - 14        # side walls
PLAYER_Y = 856                   # paddle centres
CPU_Y = 190
PAD_W, PAD_H = 112, 16
BALL_R = 9
START_LIVES = 3
MODES = ("CLASSIC", "MULTIBALL", "SHRINK", "BRICKS", "POWER")
VERSUS_MODES = ("CLASSIC", "MULTIBALL", "SHRINK", "POWER")     # BRICKS: single player only

BALL_SPEED = 430.0               # px/s right after a point ...
RALLY_ACCEL = 15.0               # ... + this much for every second nobody scores
BRICK_SPEED = 470.0              # BRICKS: always this speed (it never speeds up)
BALL_MAX = 1500.0
SMASH_MULT = 1.35
SMASH_WINDOW = 0.2               # seconds: B2 this close before the hit = smash
PLAYER_SPEED = 720.0
CPU_SPEED = 300.0
CPU_MAX = 900.0
CPU_ERROR = 22.0                 # how far off the computer guesses (px, grows with speed)
MAX_ANGLE = math.radians(62)     # steepest bounce off a paddle edge
SERVE_TIME = 1.1
POINT_TIME = 0.9

# BRICKS
BRICK_COLS, BRICK_ROWS = 9, 7
BRICK_TOP = 168
BRICK_GAP = 3
BRICK_W = (RIGHT - LEFT - BRICK_GAP * (BRICK_COLS + 1)) / float(BRICK_COLS)
BRICK_H = 22
BRICK_POINTS = 20

# BRICKS power-ups: falling capsules, caught with the paddle
POWERUPS = {                     # kind: (label, chance weight)
    "multi": ("x3", 26),         # every ball splits into three
    "wide": ("WIDE", 24),        # a much wider paddle for a while
    "fire": ("FIRE", 18),        # the balls burn straight through bricks for a while
    "shield": ("SHIELD", 14),    # a barrier under the paddle saves one ball
    "life": ("1UP", 6),          # an extra life
    "mini": ("MINI", 12),        # BAD: a smaller paddle for a while - dodge it!
}
DROP_CHANCE = 0.2                # per broken brick
DROP_SPEED = 170.0               # px/s
DROP_W, DROP_H = 50, 20
MAX_DROPS = 3
MAX_BALLS = 6
WIDE_TIME = 15.0
MINI_TIME = 10.0
FIRE_TIME = 8.0
SHIELD_Y = BOTTOM - 22           # the shield barrier line (bottom player)
SHIELD2_Y = TOP + 22             # (top player)

# POWER mode: orbs floating across the middle, collected by the ball
ORBS = {                         # kind: (label, chance weight)
    "wide": ("WIDE", 20),        # your paddle gets wider
    "mini": ("MINI", 18),        # the OTHER paddle gets smaller
    "multi": ("x3", 16),         # the ball splits into three
    "shield": ("SHIELD", 14),    # a barrier behind your paddle saves one ball
    "freeze": ("FREEZE", 14),    # the OTHER paddle can't move for a moment
    "smash": ("SMASH", 18),      # your next return is an automatic smash
}
ORB_R = 23
ORB_EVERY = (3.5, 6.5)           # seconds between new orbs
ORB_LIFE = 12.0
MAX_ORBS = 2
POWER_WIDE = 12.0
POWER_MINI = 9.0
FREEZE_TIME = 1.6
POWER_MAX_BALLS = 4


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class Pulsar:
    versus = False

    def __init__(self, seed=None, mode="CLASSIC"):
        self.rng = random.Random(seed)
        self.mode = mode if mode in MODES else "CLASSIC"
        self.mult = 2 if self.mode == "SHRINK" else 1
        self.points = 0                  # points you scored
        self.cpu_points = 0
        self.hits = 0                    # returns (all game)
        self.rally = 0                   # returns since the last serve
        self.best_rally = 0
        self.rally_t = 0.0               # seconds since the ball came in (sets the speed)
        self.score = 0
        self.lives = START_LIVES
        self.game_over = False
        self.px = SW / 2.0               # your paddle (bottom)
        self.pvx = 0.0
        self.cx = SW / 2.0               # the computer's / player 2's paddle (top)
        self.cvx = 0.0
        self.cpu_target = SW / 2.0
        self.cpu_think = 0.0
        self.smash_t = 0.0               # > 0: a smash is ready (bottom paddle)
        self.smash2_t = 0.0              # (top paddle, multiplayer)
        self.balls = []
        self.serve_dir = -1              # first serve goes up
        self.phase = "serve"
        self.phase_t = 0.0
        self.effects = []                # [kind, x, y, age, max_age]
        self.popups = []                 # [text, x, y, age]
        self.flash = None                # ("point" / "miss", seconds left)
        # BRICKS
        self.wall = 0
        self.bricks = []                 # {"x", "y", "w", "h", "hp", "max", "row"}
        self.broken = 0
        self.wall_size = 0
        self.drops = []                  # falling power-ups {"x", "y", "kind"}
        self.wide_t = 0.0
        self.mini_t = 0.0
        self.fire_t = 0.0
        self.shield = 0                  # balls the shield can still save
        # POWER (and the top paddle's side of things)
        self.orbs = []                   # {"x", "y", "vx", "kind", "age"}
        self.orb_t = 3.0
        self.wide2_t = 0.0
        self.mini2_t = 0.0
        self.shield2 = 0
        self.freeze_t = [0.0, 0.0]       # [bottom, top]
        self.auto_smash = [False, False]
        if self.mode == "BRICKS":
            self.next_wall()

    # ------------------------------------------------------------------
    # how fast things are
    # ------------------------------------------------------------------
    @property
    def level(self):
        return self.wall if self.mode == "BRICKS" else 1 + self.points

    def ball_speed(self):
        if self.mode == "BRICKS":
            return BRICK_SPEED
        return min(BALL_MAX, BALL_SPEED + RALLY_ACCEL * self.rally_t)

    def cpu_speed(self):
        return min(CPU_MAX, CPU_SPEED + 0.55 * (self.ball_speed() - BALL_SPEED))

    def side_w(self, side):
        """Paddle width: side 0 = bottom (you / player 1), 1 = top."""
        w = float(PAD_W)
        if self.mode == "SHRINK" and (side == 0 or self.versus):
            w = max(48.0, PAD_W - 4.0 * (self.points if side == 0 else self.cpu_points))
        wide, mini = (self.wide_t, self.mini_t) if side == 0 else (self.wide2_t, self.mini2_t)
        if wide > 0:
            w *= 1.6
        if mini > 0:
            w *= 0.6
        return w

    def pad_w(self):
        return self.side_w(0)

    def top_w(self):
        return self.side_w(1)

    def speed_frac(self):
        """0..1: how close the ball is to its top speed (for the HUD)."""
        return (self.ball_speed() - BALL_SPEED) / (BALL_MAX - BALL_SPEED)

    # ------------------------------------------------------------------
    # BRICKS: the walls
    # ------------------------------------------------------------------
    def next_wall(self):
        self.wall += 1
        w = self.wall
        rows = min(BRICK_ROWS, 4 + w)
        pattern = (w - 1) % 4
        tough = (w - 1) // 2                         # more 2-hit rows on later walls
        self.bricks = []
        for r in range(rows):
            for c in range(BRICK_COLS):
                if pattern == 1 and (r + c) % 2:                         # checkers
                    continue
                if pattern == 2 and abs(c - BRICK_COLS // 2) > rows - 1 - r + 1:   # pyramid
                    continue
                if pattern == 3 and c in (2, 6) and r > 0:               # two shafts
                    continue
                if w > 4 and self.rng.random() < 0.12:                   # random holes
                    continue
                hp = 2 if r < tough else 1
                x = LEFT + BRICK_GAP + c * (BRICK_W + BRICK_GAP)
                y = BRICK_TOP + r * (BRICK_H + BRICK_GAP)
                self.bricks.append({"x": x, "y": y, "w": BRICK_W, "h": BRICK_H,
                                    "hp": hp, "max": hp, "row": r})
        self.wall_size = len(self.bricks)        # (for the progress bar)

    def _hit_bricks(self, b):
        """Ball b against the bricks: break them, bounce (unless smashed)."""
        for br in self.bricks:
            nx = _clamp(b["x"], br["x"], br["x"] + br["w"])
            ny = _clamp(b["y"], br["y"], br["y"] + br["h"])
            dx, dy = b["x"] - nx, b["y"] - ny
            if dx * dx + dy * dy > BALL_R * BALL_R:
                continue
            pierce = b["smash"] or self.fire_t > 0
            br["hp"] -= 2 if pierce else 1
            cx, cy = br["x"] + br["w"] / 2, br["y"] + br["h"] / 2
            if br["hp"] <= 0:
                self.bricks.remove(br)
                self.broken += 1
                self.score += BRICK_POINTS * br["max"]
                self.effects.append(["brick", cx, cy, 0.0, 0.35])
                if len(self.drops) < MAX_DROPS and self.rng.random() < DROP_CHANCE:
                    kinds = sorted(POWERUPS)
                    kind = self.rng.choices(kinds, weights=[POWERUPS[k][1] for k in kinds])[0]
                    self.drops.append({"x": cx, "y": cy, "kind": kind})
            else:
                self.effects.append(["dent", cx, cy, 0.0, 0.25])
            if not pierce:
                # bounce off the side it came from
                over_x = (br["w"] / 2 + BALL_R) - abs(b["x"] - cx)
                over_y = (br["h"] / 2 + BALL_R) - abs(b["y"] - cy)
                if over_x < over_y:
                    b["vx"] = abs(b["vx"]) if b["x"] > cx else -abs(b["vx"])
                else:
                    b["vy"] = abs(b["vy"]) if b["y"] > cy else -abs(b["vy"])
                return

    # ------------------------------------------------------------------
    # balls
    # ------------------------------------------------------------------
    def serve(self):
        n = 1
        if self.mode == "MULTIBALL":
            pts = self.points + self.cpu_points if self.versus else self.points
            n = 1 + min(2, pts // 5)
        self.balls = []
        self.rally_t = 0.0
        for i in range(n):
            ang = self.rng.uniform(-0.55, 0.55)
            sp = BALL_SPEED * 0.85
            d = self.serve_dir if i % 2 == 0 else -self.serve_dir
            y0 = (TOP + BOTTOM) / 2.0 if self.mode != "BRICKS" else 620.0
            self.balls.append({"x": SW / 2.0 + (i - (n - 1) / 2.0) * 60, "y": y0,
                               "vx": sp * math.sin(ang), "vy": d * sp * math.cos(ang),
                               "smash": False, "boost": 1.0, "trail": []})
        self.rally = 0
        self.phase, self.phase_t = "play", 0.0

    def _bounce(self, b, pad_x, pad_w, up, smash=False):
        """Send ball b off a paddle: the angle depends on where it hit."""
        off = _clamp((b["x"] - pad_x) / (pad_w / 2.0 + BALL_R), -1.0, 1.0)
        ang = off * MAX_ANGLE
        b["vx"] = math.sin(ang)
        b["vy"] = (-1 if up else 1) * math.cos(ang)
        b["smash"] = smash
        b["boost"] = SMASH_MULT if smash else 1.0
        b["owner"] = 0 if up else 1          # (POWER: who gets the orbs it flies through)
        b.pop("err", None)                   # the computer guesses again
        self._set_speed(b)

    def _set_speed(self, b):
        """Keep the ball's direction, set its speed to the rally speed."""
        sp = self.ball_speed() * b["boost"]
        d = math.hypot(b["vx"], b["vy"]) or 1.0
        b["vx"], b["vy"] = b["vx"] / d * sp, b["vy"] / d * sp

    # ------------------------------------------------------------------
    # the computer
    # ------------------------------------------------------------------
    def _predict_x(self, b, y):
        """Where ball b will cross height y (walls bounce it)."""
        if b["vy"] == 0:
            return b["x"]
        t = (y - b["y"]) / b["vy"]
        if t < 0:
            return SW / 2.0
        lo, hi = LEFT + BALL_R, RIGHT - BALL_R
        span = hi - lo
        x = (b["x"] + b["vx"] * t - lo) % (2 * span)
        return lo + (x if x <= span else 2 * span - x)

    def _cpu(self, dt):
        self.cpu_think -= dt
        if self.cpu_think <= 0:
            self.cpu_think = 0.11
            coming = [b for b in self.balls if b["vy"] < 0]
            if coming:
                b = min(coming, key=lambda b: (b["y"] - CPU_Y) / -b["vy"])
                if "err" not in b:
                    # one guess per shot: it is a bit off, more so for fast,
                    # steep and smashed balls (so you CAN get one past it)
                    sigma = (CPU_ERROR + 0.035 * math.hypot(b["vx"], b["vy"])
                             + 0.06 * abs(b["vx"]) + (45 if b["smash"] else 0))
                    b["err"] = self.rng.gauss(0, sigma)
                self.cpu_target = self._predict_x(b, CPU_Y) + b["err"]
            else:
                self.cpu_target = SW / 2.0 + (self.px - SW / 2.0) * 0.25
        if self.freeze_t[1] > 0:                      # frozen by an orb
            return
        d = self.cpu_target - self.cx
        step = self.cpu_speed() * dt
        half = self.top_w() / 2
        self.cx += _clamp(d, -step, step)
        self.cx = _clamp(self.cx, LEFT + half, RIGHT - half)

    # ------------------------------------------------------------------
    # the frame
    # ------------------------------------------------------------------
    def _tick_common(self, dt_ms):
        dt = min(dt_ms, 50) / 1000.0
        for e in self.effects:
            e[3] += dt
        self.effects = [e for e in self.effects if e[3] < e[4]]
        for p in self.popups:
            p[3] += dt
        self.popups = [p for p in self.popups if p[3] < 0.9]
        if self.flash:
            self.flash = (self.flash[0], self.flash[1] - dt)
            if self.flash[1] <= 0:
                self.flash = None
        return dt

    def _move_paddle(self, x, vx, left, right, dt, width):
        want = ((1 if right else 0) - (1 if left else 0)) * PLAYER_SPEED
        vx += (want - vx) * min(1.0, dt * 22)
        x = _clamp(x + vx * dt, LEFT + width / 2, RIGHT - width / 2)
        return x, vx

    def update(self, dt_ms, left=False, right=False, presses=()):
        dt = self._tick_common(dt_ms)
        if self.game_over:
            return
        self.phase_t += dt
        if self.freeze_t[0] > 0:                      # frozen by an orb
            left = right = False
            self.pvx = 0.0
        self.px, self.pvx = self._move_paddle(self.px, self.pvx, left, right, dt, self.pad_w())
        if "button2" in presses:
            self.smash_t = SMASH_WINDOW
        self.smash_t = max(0.0, self.smash_t - dt)
        if self.mode != "BRICKS":
            self._cpu(dt)
        self._run_balls(dt)

    # ------------------------------------------------------------------
    # BRICKS: power-ups
    # ------------------------------------------------------------------
    def _tick_powers(self, dt):
        self.wide_t = max(0.0, self.wide_t - dt)
        self.mini_t = max(0.0, self.mini_t - dt)
        self.fire_t = max(0.0, self.fire_t - dt)
        self.wide2_t = max(0.0, self.wide2_t - dt)
        self.mini2_t = max(0.0, self.mini2_t - dt)
        self.freeze_t = [max(0.0, f - dt) for f in self.freeze_t]

    def _move_drops(self, dt):
        keep = []
        half = self.pad_w() / 2
        for d in self.drops:
            d["y"] += DROP_SPEED * dt
            if (abs(d["y"] - PLAYER_Y) < (DROP_H + PAD_H) / 2
                    and abs(d["x"] - self.px) < half + DROP_W / 2):
                self._power(d["kind"], d["x"])
                continue
            if d["y"] < BOTTOM + 20:
                keep.append(d)
        self.drops = keep

    def _power(self, kind, x):
        label = POWERUPS[kind][0]
        self.effects.append(["power", x, PLAYER_Y, 0.0, 0.45])
        self.score += 50
        if kind == "multi":
            new = []
            for b in self.balls:
                sp = math.hypot(b["vx"], b["vy"]) or 1.0
                ang = math.atan2(b["vx"], -b["vy"])
                for turn in (-0.45, 0.45):
                    if len(self.balls) + len(new) >= MAX_BALLS:
                        break
                    a = ang + turn
                    vy = -abs(math.cos(a)) if b["vy"] < 0 else abs(math.cos(a))
                    new.append({"x": b["x"], "y": b["y"], "vx": math.sin(a) * sp,
                                "vy": vy * sp, "smash": False, "boost": b["boost"],
                                "trail": []})
            self.balls.extend(new)
            label = "MULTIBALL!"
        elif kind == "wide":
            self.wide_t, self.mini_t = WIDE_TIME, 0.0
            label = "WIDE PADDLE!"
        elif kind == "mini":
            self.mini_t, self.wide_t = MINI_TIME, 0.0
            label = "MINI PADDLE..."
        elif kind == "fire":
            self.fire_t = FIRE_TIME
            label = "FIRE BALL!"
        elif kind == "shield":
            self.shield = 1
            label = "SHIELD!"
        elif kind == "life":
            self.lives += 1
            label = "EXTRA LIFE!"
        self.popups.append([label, x, PLAYER_Y - 50, 0.0])

    # ------------------------------------------------------------------
    # POWER: the orbs
    # ------------------------------------------------------------------
    def _tick_orbs(self, dt):
        self.orb_t -= dt
        if self.orb_t <= 0:
            self.orb_t = self.rng.uniform(*ORB_EVERY)
            if len(self.orbs) < MAX_ORBS:
                kinds = sorted(ORBS)
                kind = self.rng.choices(kinds, weights=[ORBS[k][1] for k in kinds])[0]
                self.orbs.append({"x": self.rng.uniform(LEFT + 50, RIGHT - 50),
                                  "y": self.rng.uniform(TOP + 190, BOTTOM - 190),
                                  "vx": self.rng.choice((-1, 1)) * self.rng.uniform(25, 60),
                                  "kind": kind, "age": 0.0})
        keep = []
        for o in self.orbs:
            o["age"] += dt
            o["x"] += o["vx"] * dt
            if o["x"] < LEFT + ORB_R or o["x"] > RIGHT - ORB_R:
                o["vx"] = -o["vx"]
                o["x"] = _clamp(o["x"], LEFT + ORB_R, RIGHT - ORB_R)
            if o["age"] < ORB_LIFE:
                keep.append(o)
        self.orbs = keep

    def _orb_power(self, side, kind, b, x, y):
        """Side 0 (bottom) or 1 (top) collected an orb."""
        other = 1 - side
        if kind == "wide":
            if side == 0:
                self.wide_t, self.mini_t = POWER_WIDE, 0.0
            else:
                self.wide2_t, self.mini2_t = POWER_WIDE, 0.0
        elif kind == "mini":
            if other == 0:
                self.mini_t, self.wide_t = POWER_MINI, 0.0
            else:
                self.mini2_t, self.wide2_t = POWER_MINI, 0.0
        elif kind == "multi":
            sp = math.hypot(b["vx"], b["vy"]) or 1.0
            ang = math.atan2(b["vx"], b["vy"])
            for turn in (-0.4, 0.4):
                if len(self.balls) >= POWER_MAX_BALLS:
                    break
                a = ang + turn
                self.balls.append({"x": b["x"], "y": b["y"], "vx": math.sin(a) * sp,
                                   "vy": math.cos(a) * sp, "smash": False, "boost": b["boost"],
                                   "owner": side, "trail": []})
        elif kind == "shield":
            if side == 0:
                self.shield = 1
            else:
                self.shield2 = 1
        elif kind == "freeze":
            self.freeze_t[other] = FREEZE_TIME
        elif kind == "smash":
            self.auto_smash[side] = True
        self.effects.append(["orb", x, y, 0.0, 0.45])
        self.popups.append([ORBS[kind][0] + "!", x, y - 26, 0.0])

    def _run_balls(self, dt):
        if self.phase == "serve":
            if self.phase_t >= SERVE_TIME:
                self.serve()
            return
        if self.phase in ("point", "clear"):
            if self.phase_t >= POINT_TIME * (2 if self.phase == "clear" else 1):
                if self.phase == "clear":
                    self.next_wall()
                self.phase, self.phase_t = "serve", 0.0
            return
        if self.phase != "play":
            return
        self.rally_t += dt
        self._tick_powers(dt)
        if self.drops:
            self._move_drops(dt)
        if self.mode == "POWER":
            self._tick_orbs(dt)
        # balls: in small steps so fast balls never jump through a paddle
        for b in list(self.balls):
            self._set_speed(b)                       # faster and faster
            b["trail"].append((b["x"], b["y"]))
            del b["trail"][:-8]
            sp = math.hypot(b["vx"], b["vy"])
            steps = max(1, int(sp * dt / 6) + 1)
            h = dt / steps
            for _ in range(steps):
                if self._step_ball(b, h):
                    break
        if self.phase == "play":
            if self.mode == "BRICKS" and not self.bricks:
                bonus = 500 * self.wall
                self.score += bonus
                self.popups.append(["WALL CLEAR! +%d" % bonus, SW / 2, 500, 0.0])
                self.balls = []
                self.drops = []
                self.fire_t = 0.0
                self.phase, self.phase_t = "clear", 0.0
            elif not self.balls:
                self.phase, self.phase_t = "point", 0.0

    def _step_ball(self, b, h):
        """Move one ball a little. True if it left the arena."""
        b["x"] += b["vx"] * h
        b["y"] += b["vy"] * h
        if b["x"] < LEFT + BALL_R:
            b["x"] = 2 * (LEFT + BALL_R) - b["x"]
            b["vx"] = abs(b["vx"])
            self.effects.append(["wall", b["x"], b["y"], 0.0, 0.2])
        elif b["x"] > RIGHT - BALL_R:
            b["x"] = 2 * (RIGHT - BALL_R) - b["x"]
            b["vx"] = -abs(b["vx"])
            self.effects.append(["wall", b["x"], b["y"], 0.0, 0.2])
        bricks = self.mode == "BRICKS"
        if bricks:
            if b["y"] < TOP + BALL_R:                   # the top is a wall here
                b["y"] = 2 * (TOP + BALL_R) - b["y"]
                b["vy"] = abs(b["vy"])
                b["smash"] = False
                b["boost"] = 1.0
                self.effects.append(["wall", b["x"], b["y"], 0.0, 0.2])
            self._hit_bricks(b)
        # bottom paddle (you / player 1)
        pw = self.pad_w()
        if (b["vy"] > 0 and PLAYER_Y - PAD_H / 2 - BALL_R <= b["y"] <= PLAYER_Y + PAD_H / 2
                and abs(b["x"] - self.px) <= pw / 2 + BALL_R):
            smash = self.smash_t > 0 or self.auto_smash[0]
            self.smash_t = 0.0
            self.auto_smash[0] = False
            self.rally += 1
            self.hits += 1
            self.best_rally = max(self.best_rally, self.rally)
            self._bounce(b, self.px, pw, up=True, smash=smash)
            b["y"] = PLAYER_Y - PAD_H / 2 - BALL_R
            if not self.versus:
                self.score += 10 * self.mult
            self.effects.append(["smash" if smash else "hit", b["x"], b["y"], 0.0, 0.35])
            if smash:
                self.popups.append(["SMASH!", b["x"], b["y"] - 20, 0.0])
        # top paddle (the computer / player 2)
        elif (not bricks and b["vy"] < 0 and CPU_Y - PAD_H / 2 <= b["y"] <= CPU_Y + PAD_H / 2 + BALL_R
                and abs(b["x"] - self.cx) <= self.top_w() / 2 + BALL_R):
            smash = (self.versus and self.smash2_t > 0) or self.auto_smash[1]
            self.auto_smash[1] = False
            if smash:
                self.smash2_t = 0.0
                self.popups.append(["SMASH!", b["x"], b["y"] + 20, 0.0])
            self.rally += 1
            self._bounce(b, self.cx, self.top_w(), up=False, smash=smash)
            b["y"] = CPU_Y + PAD_H / 2 + BALL_R
            self.effects.append(["smash" if smash else "cpu", b["x"], b["y"], 0.0, 0.3])
        # out?
        if not bricks and b["y"] < TOP:                 # past the top paddle: bottom scores
            self.balls.remove(b)
            self.points += 1
            if not self.versus:
                pts = 100 * (1 + self.points // 5) * self.mult
                self.score += pts
                self.popups.append(["+%d" % pts, b["x"], TOP + 30, 0.0])
            self.effects.append(["goal", b["x"], TOP, 0.0, 0.5])
            self.flash = ("point", 0.6)
            self.serve_dir = -1
            self.on_point()
            return True
        if self.orbs:
            for o in list(self.orbs):
                if (b.get("owner") is not None
                        and math.hypot(o["x"] - b["x"], o["y"] - b["y"]) < BALL_R + ORB_R):
                    self.orbs.remove(o)
                    self._orb_power(b["owner"], o["kind"], b, o["x"], o["y"])
        if not bricks and self.shield2 and b["vy"] < 0 and b["y"] <= SHIELD2_Y + BALL_R:
            b["y"] = SHIELD2_Y + BALL_R                 # the top shield bounces it back
            b["vy"] = abs(b["vy"])
            self.shield2 -= 1
            self.effects.append(["shield", b["x"], SHIELD2_Y, 0.0, 0.5])
            return False
        if self.shield and b["vy"] > 0 and b["y"] >= SHIELD_Y - BALL_R:
            b["y"] = SHIELD_Y - BALL_R                  # the shield bounces it back (once)
            b["vy"] = -abs(b["vy"])
            self.shield -= 1
            self.effects.append(["shield", b["x"], SHIELD_Y, 0.0, 0.5])
            return False
        if b["y"] > BOTTOM and bricks and len(self.balls) > 1:
            self.balls.remove(b)                        # other balls still in play
            return True
        if b["y"] > BOTTOM:                             # past the bottom paddle
            self.balls.remove(b)
            if bricks:                                  # the last ball: power-ups end too
                self.drops = []
                self.wide_t = self.mini_t = self.fire_t = 0.0
            self.cpu_points += 1
            self.effects.append(["miss", b["x"], BOTTOM, 0.0, 0.5])
            self.flash = ("miss", 0.6)
            self.serve_dir = 1 if not bricks else -1
            if not self.versus:
                self.lives -= 1
                if self.lives <= 0:
                    self.lives = 0
                    self.balls = []
                    self.game_over = True
            self.on_point()
            return True
        return False

    def on_point(self):
        """Somebody scored (multiplayer checks for the winner here)."""


# ----------------------------------------------------------------------------
# Multiplayer: two players, first to 7
# ----------------------------------------------------------------------------
WIN_POINTS = 7
MATCH_OVER_TIME = 4.0
ACTIONS = ("left", "right", "button2")
PHASES = ("serve", "play", "point", "matchover")


class PulsarVersus(Pulsar):
    """Player 1 = bottom paddle (px), player 2 = top paddle (cx).
    me = 0 / 1 = which one is on this screen (None = the host watching).
    Player 2 sees the field turned around, so for them LEFT / RIGHT are
    swapped here (the host does that)."""
    versus = True

    def __init__(self, seed=None, names=("P1", "P2"), me=None, mode="CLASSIC"):
        Pulsar.__init__(self, seed, mode if mode in VERSUS_MODES else "CLASSIC")
        self.names = [str(n)[:12] for n in names][:2]
        self.me = me
        self.serve_dir = self.rng.choice((-1, 1))

    def update(self, dt_ms, in1=((), ()), in2=((), ())):
        """in1 / in2 = (held buttons, new presses) of player 1 / player 2."""
        dt = self._tick_common(dt_ms)
        if self.game_over:
            return
        self.phase_t += dt
        if self.phase == "matchover":
            if self.phase_t >= MATCH_OVER_TIME:
                self.game_over = True
            return
        h1, p1 = in1
        h2, p2 = in2
        if self.freeze_t[0] > 0:                      # frozen by an orb
            h1, self.pvx = (), 0.0
        if self.freeze_t[1] > 0:
            h2, self.cvx = (), 0.0
        self.px, self.pvx = self._move_paddle(self.px, self.pvx, "left" in h1, "right" in h1, dt,
                                              self.pad_w())
        # player 2 looks at the field the other way round: swap left / right
        self.cx, self.cvx = self._move_paddle(self.cx, self.cvx, "right" in h2, "left" in h2, dt,
                                              self.top_w())
        if "button2" in p1:
            self.smash_t = SMASH_WINDOW
        if "button2" in p2:
            self.smash2_t = SMASH_WINDOW
        self.smash_t = max(0.0, self.smash_t - dt)
        self.smash2_t = max(0.0, self.smash2_t - dt)
        self._run_balls(dt)

    def on_point(self):
        if max(self.points, self.cpu_points) >= WIN_POINTS:
            self.balls = []
            self.phase, self.phase_t = "matchover", 0.0

    def match_winner(self):
        if self.points == self.cpu_points:
            return None
        return 0 if self.points > self.cpu_points else 1

    # -- network
    def snapshot(self):
        return {
            "ph": self.phase, "pt": round(self.phase_t, 3), "rt": round(self.rally_t, 2),
            "px": round(self.px, 1), "cx": round(self.cx, 1),
            "s1": self.smash_t > 0, "s2": self.smash2_t > 0,
            "pts": [self.points, self.cpu_points],
            "b": [[round(b["x"], 1), round(b["y"], 1), round(b["vx"], 1), round(b["vy"], 1),
                   b["smash"]] for b in self.balls],
            "fx": [[e[0], round(e[1]), round(e[2]), round(e[3], 3), e[4]] for e in self.effects[:12]],
            "pop": [[p[0], round(p[1]), round(p[2]), round(p[3], 2)] for p in self.popups[:4]],
            "fl": list(self.flash) if self.flash else None,
            "o": [[round(o["x"]), round(o["y"]), o["kind"]] for o in self.orbs],
            "pw": [round(v, 2) for v in (self.wide_t, self.mini_t, self.wide2_t, self.mini2_t,
                                         self.freeze_t[0], self.freeze_t[1])],
            "sh": [self.shield, self.shield2],
            "as": list(self.auto_smash),
        }

    def apply(self, snap):
        """Show the host's game (ignores anything broken)."""
        try:
            phase = snap["ph"] if snap["ph"] in PHASES else "play"
            vals = (float(snap["pt"]), float(snap["rt"]), float(snap["px"]), float(snap["cx"]),
                    bool(snap["s1"]), bool(snap["s2"]), int(snap["pts"][0]), int(snap["pts"][1]))
            old = self.balls
            balls = []
            for i, d in enumerate(snap["b"][:3]):
                trail = old[i]["trail"] if i < len(old) else []
                trail = (trail + [(float(d[0]), float(d[1]))])[-8:]
                balls.append({"x": float(d[0]), "y": float(d[1]), "vx": float(d[2]),
                              "vy": float(d[3]), "smash": bool(d[4]), "boost": 1.0, "trail": trail})
            effects = [[str(k), float(x), float(y), float(a), float(m)]
                       for k, x, y, a, m in snap.get("fx", [])[:12]]
            popups = [[str(t)[:12], float(x), float(y), float(a)]
                      for t, x, y, a in snap.get("pop", [])[:4]]
            fl = snap.get("fl")
            flash = (str(fl[0]), float(fl[1])) if fl else None
            orbs = [{"x": float(x), "y": float(y), "vx": 0.0, "kind": k, "age": 0.0}
                    for x, y, k in snap.get("o", [])[:MAX_ORBS] if k in ORBS]
            pw = [float(v) for v in snap.get("pw", [0] * 6)][:6]
            sh = [int(v) for v in snap.get("sh", [0, 0])][:2]
            auto = [bool(v) for v in snap.get("as", [False, False])][:2]
        except (KeyError, TypeError, ValueError, IndexError):
            return
        self.orbs = orbs
        if len(pw) == 6:
            self.wide_t, self.mini_t, self.wide2_t, self.mini2_t = pw[:4]
            self.freeze_t = pw[4:]
        if len(sh) == 2:
            self.shield, self.shield2 = sh
        if len(auto) == 2:
            self.auto_smash = auto
        self.phase = phase
        (self.phase_t, self.rally_t, self.px, self.cx, s1, s2,
         self.points, self.cpu_points) = vals
        self.smash_t = SMASH_WINDOW if s1 else 0.0
        self.smash2_t = SMASH_WINDOW if s2 else 0.0
        self.balls, self.effects, self.popups, self.flash = balls, effects, popups, flash
