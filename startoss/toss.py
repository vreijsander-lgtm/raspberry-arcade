"""
Star Toss - game logic (no pygame in here, so it can be tested anywhere).

A throwing game for the tall screen. At the bottom of a tall shaft a launcher
droid swings your astronaut round on a tether:
    HOLD BUTTON2   it spins faster and faster
    LET GO         the astronaut flies off the way it was moving right then
Don't hold too long: after a few seconds the launcher gets DIZZY and drops
you (a wasted throw). Once you fly you can't steer.

Up the shaft, helper droids stand on ledges in the walls, zig-zagging left /
right, ALWAYS EXACTLY THE SAME DISTANCE APART. Touch one and it bounces you up
and across to the other wall straight away (you never stop). How hard depends
on how you hit it:
    ANGLE   coming in steep (mostly up / down) is good, a flat sideways
            slam loses lift ("FLAT HIT")
    SPOT    rising: hit its outstretched arms, not behind them near the wall
            ("UNDER-CLIP"); falling: land on top of its head (a springboard)
    SPEED   rising fast carries on into the bounce; falling in gives a
            little trampoline push
Every bounce in a throw is a bit weaker than the last, and after a few the
helpers aim you up the middle of the shaft, so every throw comes down in the
end.

POWER-UP capsules float down the shaft on little parachutes - fly through one
(it only works on the astronaut that touched it):
    x3      MULTI   that astronaut splits into three (more guys!)
    R       ROCKET  a burst of rocket thrust straight up (more speed!)
    G       GIANT   bigger: easier to hit helpers, but heavier and slower
    T       TINY    smaller: lighter and faster, but easy to miss helpers
    B       BOUNCE  the next time it hits the ground it bounces back up
    +1      THROW   an extra throw this game
    ?       MYSTERY a gamble: SPLIT + ROCKET or a MEGA ROCKET... or an
                    ANVIL (heavy for a moment) or a TINY ANVIL - an anvil
                    breaks off when you hit a helper
With more astronauts the highest one counts, and the throw ends when the
last one is back on the ground.

Every game is 5 throws (+ any extra ones); the score is the height of all of
them added up (10 points a metre) plus 50 per star and 25 per power-up. A
throw lower than 12 m doesn't count.
"""
import math
import random

SW, SH = 540, 960
WALL_L, WALL_R = 46, SW - 46     # the shaft's inner walls
PUP_R = 18
PX_PER_M = 10
GRAVITY = 955.0                  # px/s^2
AIR_DRAG_X = 0.04                # (per second, gentle)
AIR_DRAG_Y = 0.012
WALL_RESTITUTION = 0.34
WALL_MAX_VX = 220.0              # a wall bounces you back at most this fast
WALL_SCRAPE = 0.88               # vertical speed kept when you hit a wall
THROWS = 5
MIN_THROW_M = 12                 # lower than this: the throw counts as 0

# the launcher
HUB = (SW / 2.0, 150.0)          # spin centre: x, height above the ground
TETHER = 74.0
SPIN_IDLE = 2.2                  # rad/s while not holding
SPIN_ACCEL = 7.5                 # rad/s^2 while holding
SPIN_MAX = 15.0
THROW_MULT = 2.1                 # throw speed = spin speed x tether x this
LAUNCH_X_SCALE = 0.62            # (sideways throws are a bit softer)
MIN_HOLD = 0.25                  # a tap does nothing
DIZZY_TIME = 3.4                 # holding longer than this: it drops you
DIZZY_WARN = 0.45                # (it starts to look dizzy after this part of it)

# helpers on the walls - always the same distance apart, alternating sides
HELPER_X = (WALL_L + 18, WALL_R - 18)
HELPER_FIRST = 520.0             # height of the first helper ...
HELPER_GAP = 640.0               # ... and the next ones, always exactly this much higher
HIT_SPAN = 34.0                  # its hit area around its arms (plus your size)
HELPER_COOL = 0.45               # the same helper can't bounce the same astronaut again so soon
CORE_BOOST = 1760.0              # px/s: the first bounce of a throw ...
BOOST_DECAY = 0.87               # ... and every next one x this ...
BOOST_MIN = 950.0                # ... but never weaker than this
BOUNCE_MIN, BOUNCE_MAX = 620.0, 2320.0
CROSS_MIN, CROSS_MAX = 280.0, 440.0     # sideways speed of an early bounce (to the other wall)
LATE_BOUNCE = 4                  # after this many bounces (or falling fast) ...
FAST_FALL = -300.0
LATE_CROSS = (40.0, 62.0)        # ... it aims you up the middle (so the throw ends)

STAR_POINTS = 50
STAR_R = 16
CAPSULE_POINTS = 25

# power-ups
POWERUPS = {                     # kind: (label on the capsule, chance weight)
    "multi": ("x3", 24),
    "rocket": ("R", 22),
    "giant": ("G", 14),
    "tiny": ("T", 14),
    "bounce": ("B", 10),
    "throw": ("+1", 4),
    "mystery": ("?", 12),
}
FIRST_KINDS = ("multi", "rocket", "giant", "tiny", "mystery")   # always all in the first climb
CAPSULE_FALL = 72.0              # px/s down (parachutes)
CAPSULE_SWAY = 22.0
CAPSULE_EVERY = (520.0, 700.0)
CAPSULE_FIRST = 420.0
CAPSULE_W, CAPSULE_H = 46, 24
MAX_PUPS = 9
SPLIT_VX, SPLIT_VH = 155.0, 160.0
ROCKET_TIME = 0.72
ROCKET_THRUST = 1850.0
ROCKET_MAX_V = 2680.0
SIZES = {                        # size: (scale, gravity, bounce, sideways)
    "normal": (1.0, 1.0, 1.0, 1.0),
    "giant": (1.85, 1.18, 0.84, 0.78),
    "tiny": (0.55, 0.86, 1.14, 1.16),
}
ANVIL_TIME = 1.15
ANVIL_GRAVITY = 2.25


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


class StarToss:
    mode = "CLASSIC"

    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.throw_no = 0
        self.throws = THROWS             # (+1 power-ups add more)
        self.heights = []                # metres of each finished throw
        self.score = 0
        self.stars_got = 0
        self.powers_got = 0
        self.best_bounces = 0
        self.game_over = False
        self.effects = []                # [kind, x, h, age, max_age]   (h = height above ground)
        self.popups = []                 # [text, x, h, age]
        self.next_throw()

    # ------------------------------------------------------------------
    @property
    def level(self):
        return self.throw_no

    @property
    def meters(self):
        return int(self.best_h / PX_PER_M)

    def next_throw(self):
        self.throw_no += 1
        self.phase = "spin"              # spin -> fly -> result
        self.phase_t = 0.0
        self.angle = math.pi / 2         # straight down under the hub
        self.omega = SPIN_IDLE
        self.held_t = 0.0
        self.was_held = False
        self.dizzy = False               # dropped because it held on too long
        self.x, self.h = HUB[0], HUB[1] - TETHER
        self.vx = self.vh = 0.0          # vh > 0 = going up (the highest astronaut)
        self.best_h = 0.0
        self.cam = 0.0                   # height at the bottom of the screen
        self.hub = HUB
        self.pups = []                   # the flying astronauts (see _pup)
        self.bounces = 0                 # helper bounces this throw (all astronauts)
        self.helpers = []                # {"side", "h", "anim"}
        self.stars = []                  # {"x", "h"}
        self.capsules = []               # {"x0", "x", "h", "kind", "t"}
        self.next_h = HELPER_FIRST
        self.next_cap = CAPSULE_FIRST
        self.first_kinds = list(FIRST_KINDS)
        self.rng.shuffle(self.first_kinds)
        self._build(SH * 2)

    def _build(self, upto):
        """Helpers zig-zag up the walls, always exactly HELPER_GAP apart, a
        star between every other pair, and power-up capsules in between."""
        while self.next_h < upto:
            i = len(self.helpers)
            h = self.next_h
            self.helpers.append({"side": i % 2, "h": h, "anim": 0.0})
            if i % 2 == 1:
                self.stars.append({"x": SW / 2.0 + (90 if i % 4 == 1 else -90), "h": h + HELPER_GAP / 2})
            self.next_h += HELPER_GAP
        while self.next_cap < upto:
            if self.first_kinds:
                kind = self.first_kinds.pop()
            else:
                kinds = sorted(POWERUPS)
                kind = self.rng.choices(kinds, weights=[POWERUPS[k][1] for k in kinds])[0]
            x = self.rng.uniform(WALL_L + 60, WALL_R - 60)
            self.capsules.append({"x0": x, "x": x, "h": self.next_cap, "kind": kind,
                                  "t": self.rng.uniform(0, 6)})
            self.next_cap += self.rng.uniform(*CAPSULE_EVERY)

    def _pup(self, x, h, vx, vh, parent=None):
        p = {"x": x, "h": h, "vx": vx, "vh": vh, "peak": max(0.0, h),
             "size": "normal", "rocket_t": 0.0, "anvil_t": 0.0, "bounce": 0,
             "bounces": 0, "cool": {}}
        if parent is not None:
            for k in ("size", "bounce", "bounces"):
                p[k] = parent[k]
        return p

    def pup_r(self, p):
        return PUP_R * SIZES[p["size"]][0]

    # ------------------------------------------------------------------
    def spin_power(self):
        """0..1 for the power meter."""
        return (self.omega - SPIN_IDLE) / (SPIN_MAX - SPIN_IDLE)

    def dizziness(self):
        """0..1: how dizzy the launcher is getting (it drops you at 1)."""
        return min(1.0, self.held_t / DIZZY_TIME) if self.phase == "spin" else 0.0

    def throw_dir(self):
        """Unit vector (x, up) the astronaut would fly if you let go now."""
        # angle is measured in screen terms (y down); the tangent of a
        # clockwise swing at angle a is (-sin a, cos a) in screen x / y
        return (-math.sin(self.angle), -math.cos(self.angle))

    def update(self, dt_ms, left=False, right=False, held=False, presses=()):
        dt = min(dt_ms, 50) / 1000.0
        for e in self.effects:
            e[3] += dt
        self.effects = [e for e in self.effects if e[3] < e[4]]
        for p in self.popups:
            p[3] += dt
        self.popups = [p for p in self.popups if p[3] < 1.1]
        for hp in self.helpers:
            hp["anim"] = max(0.0, hp["anim"] - dt)
        if self.game_over:
            return
        self.phase_t += dt
        if self.phase == "spin":
            self._spin(dt, held)
        elif self.phase == "fly":
            self._fly(dt)
        elif self.phase == "result":
            if self.phase_t >= 2.4 or (self.phase_t >= 0.35 and "button2" in presses):
                if self.throw_no >= self.throws:
                    self.game_over = True
                else:
                    self.next_throw()

    def _spin(self, dt, held):
        if held:
            self.held_t += dt
            self.omega = min(SPIN_MAX, self.omega + SPIN_ACCEL * dt)
            self.was_held = True
            if self.held_t >= DIZZY_TIME:                  # held on too long: it drops you
                self._fumble()
                return
        else:
            if self.was_held and self.held_t >= MIN_HOLD:
                self._release()
                return
            self.was_held = False
            self.held_t = 0.0
            self.omega += (SPIN_IDLE - self.omega) * min(1.0, dt * 2)
        self.angle = (self.angle + self.omega * dt) % math.tau
        self.x = self.hub[0] + math.cos(self.angle) * TETHER
        self.h = self.hub[1] - math.sin(self.angle) * TETHER
        target = max(0.0, self.hub[1] - SH * 0.5)          # (the camera looks at the hub)
        self.cam += (target - self.cam) * min(1.0, dt * 6)

    def _release(self):
        dx, dup = self.throw_dir()
        sp = self.omega * TETHER * THROW_MULT
        self.vx, self.vh = dx * sp * LAUNCH_X_SCALE, dup * sp
        self.pups = [self._pup(self.x, self.h, self.vx, self.vh)]
        self.phase, self.phase_t = "fly", 0.0
        self.effects.append(["release", self.x, self.h, 0.0, 0.4])

    def _fumble(self):
        self.dizzy = True
        dx = -1 if self.x < self.hub[0] else 1
        self.pups = [self._pup(self.x, self.h, dx * 120.0, -200.0)]
        self.phase, self.phase_t = "fly", 0.0
        self.popups.append(["TOO DIZZY!", self.hub[0], self.hub[1] + 120, 0.0])

    # ------------------------------------------------------------------
    def _fly(self, dt):
        drag_x = math.exp(-AIR_DRAG_X * dt)
        drag_y = math.exp(-AIR_DRAG_Y * dt)
        for cp in self.capsules:                           # parachutes drift down and sway
            cp["t"] += dt
            cp["h"] -= CAPSULE_FALL * dt
            cp["x"] = cp["x0"] + math.sin(cp["t"] * 1.3) * CAPSULE_SWAY
        for p in list(self.pups):
            scale, grav, _, _ = SIZES[p["size"]]
            r = PUP_R * scale
            for k in list(p["cool"]):
                p["cool"][k] -= dt
                if p["cool"][k] <= 0:
                    del p["cool"][k]
            p["anvil_t"] = max(0.0, p["anvil_t"] - dt)
            g = GRAVITY * grav * (ANVIL_GRAVITY if p["anvil_t"] > 0 else 1.0)
            p["vh"] -= g * dt
            if p["rocket_t"] > 0:
                p["rocket_t"] -= dt
                p["vh"] = min(ROCKET_MAX_V, p["vh"] + ROCKET_THRUST * dt)
            p["vx"] *= drag_x
            p["vh"] *= drag_y
            p["x"] += p["vx"] * dt
            p["h"] += p["vh"] * dt
            cap = WALL_MAX_VX * SIZES[p["size"]][3]
            if p["x"] < WALL_L + r:
                p["x"], p["vx"] = WALL_L + r, min(cap, abs(p["vx"]) * WALL_RESTITUTION)
                p["vh"] *= WALL_SCRAPE
            elif p["x"] > WALL_R - r:
                p["x"], p["vx"] = WALL_R - r, -min(cap, abs(p["vx"]) * WALL_RESTITUTION)
                p["vh"] *= WALL_SCRAPE
            p["peak"] = max(p["peak"], p["h"])
            self.best_h = max(self.best_h, p["h"])
            # the nearest helpers (they are always the same distance apart)
            k = int((p["h"] - HELPER_FIRST) // HELPER_GAP)
            for i in range(max(0, k - 1), min(len(self.helpers), k + 3)):
                if i in p["cool"]:
                    continue
                hp = self.helpers[i]
                sx, sy = self.snout(hp)
                if math.hypot(p["x"] - sx, p["h"] - sy) < HIT_SPAN + r:
                    self._bounce(p, hp, i)
                    break
            for s in list(self.stars):
                if abs(s["h"] - p["h"]) < 60 and math.hypot(s["x"] - p["x"], s["h"] - p["h"]) < STAR_R + r:
                    self.stars.remove(s)
                    self.stars_got += 1
                    self.score += STAR_POINTS
                    self.effects.append(["star", s["x"], s["h"], 0.0, 0.5])
                    self.popups.append(["+%d" % STAR_POINTS, s["x"], s["h"] + 30, 0.0])
            for cp in list(self.capsules):
                if (abs(cp["h"] - p["h"]) < CAPSULE_H / 2 + r
                        and abs(cp["x"] - p["x"]) < CAPSULE_W / 2 + r):
                    self.capsules.remove(cp)
                    self._power(cp["kind"], p)
            # back on the ground: bounce back up (BOUNCE) or this astronaut is done
            if p["h"] <= r and p["vh"] < 0:
                p["h"] = r
                if p["bounce"] > 0:
                    p["bounce"] -= 1
                    p["vh"] = 1500.0
                    p["vx"] = self.rng.choice((-1, 1)) * 160.0
                    self.effects.append(["power", p["x"], p["h"], 0.0, 0.5])
                    self.popups.append(["BOUNCE!", p["x"], p["h"] + 80, 0.0])
                else:
                    self.pups.remove(p)
                    self.effects.append(["land", p["x"], r, 0.0, 0.5])
        if not self.pups:                                  # the last one is back on the ground
            self._end_throw()
            return
        lead = max(self.pups, key=lambda q: q["h"])        # the camera follows the highest one
        self.x, self.h, self.vx, self.vh = lead["x"], lead["h"], lead["vx"], lead["vh"]
        self._build(self.h + SH * 2)
        self.capsules = [c for c in self.capsules if c["h"] > self.cam - SH]
        target = max(0.0, self.h - SH * 0.45)
        self.cam += (target - self.cam) * min(1.0, dt * 6)

    def snout(self, hp):
        """Where a helper's arms are (what you bounce off)."""
        inward = 1 if hp["side"] == 0 else -1
        return HELPER_X[hp["side"]] + inward * 22, hp["h"] + 16

    def _bounce(self, p, hp, i):
        """A helper bounces you up and across - how hard depends on the
        angle you come in at, the spot you hit and how fast you were going."""
        inward = 1 if hp["side"] == 0 else -1
        sx, sy = self.snout(hp)
        _, _, boost_scale, vx_scale = SIZES[p["size"]]
        vx, vy = p["vx"], p["vh"]
        sp = math.hypot(vx, vy) or 1.0
        angle_q = _clamp((abs(vy) / sp - 0.25) / 0.65, 0.20, 1.00)
        span = HIT_SPAN + self.pup_r(p)
        front = (p["x"] - sx) * inward / span               # > 0: out in front of its arms
        rel_y = (p["h"] - sy) / span                        # > 0: above them
        under = False
        zone = 1.0
        if vy >= 0:
            if front >= 0.10:
                zone = 1.06 + 0.10 * min(1.0, (front - 0.10) / 0.9)
            elif front < -0.22:
                under = True
                zone = 0.55 + 0.18 * max(0.0, 1.0 + front)
        else:
            if rel_y >= 0.10:
                zone = 1.08 + 0.10 * min(1.0, (rel_y - 0.10) / 0.9)
            elif front < -0.22:
                under = True
                zone = 0.62
        quality = angle_q * zone
        p["bounces"] += 1
        self.bounces += 1
        self.best_bounces = max(self.best_bounces, self.bounces)
        core = max(BOOST_MIN, CORE_BOOST * BOOST_DECAY ** (p["bounces"] - 1))
        if vy >= 0:
            raw = (core * (0.56 + 0.48 * quality) + vy * 0.24 * angle_q) * boost_scale
        else:
            tramp = min(460.0, abs(vy) * 0.20)
            raw = (core * 0.78 + tramp) * (0.54 + 0.46 * quality) * boost_scale
        new_vh = _clamp(raw, BOUNCE_MIN, BOUNCE_MAX * max(1.0, boost_scale))
        if p["bounces"] <= LATE_BOUNCE and vy >= FAST_FALL:
            kick = 40.0 if vy < 0 and rel_y >= 0.10 else 0.0
            cross = _clamp(CROSS_MIN + (1 - angle_q) * 140.0 + kick, CROSS_MIN, CROSS_MAX) * vx_scale
        else:                                               # late / rescue bounce: up the middle
            cross = self.rng.uniform(*LATE_CROSS)
        p["vh"] = new_vh
        p["vx"] = inward * cross
        p["x"] = sx + inward * (span + 2)                   # (off its arms, so it can't hit twice)
        p["anvil_t"] = 0.0                                  # an anvil breaks off
        p["cool"][i] = HELPER_COOL
        hp["anim"] = 0.6
        self.score += 10
        if under:
            text, kind = "UNDER-CLIP!", "clip"
        elif angle_q < 0.52:
            text, kind = "FLAT HIT!", "flat"
        elif quality >= 0.98 and new_vh > 1800:
            text, kind = "SUPER BOUNCE!", "super"
            self.score += 50
        else:
            text, kind = "NICE BOUNCE!", "boost"
        self.effects.append([kind, p["x"], p["h"], 0.0, 0.5])
        self.popups.append([text, p["x"], p["h"] + 70, 0.0])

    def _power(self, kind, p):
        self.powers_got += 1
        self.score += CAPSULE_POINTS
        self.effects.append(["power", p["x"], p["h"], 0.0, 0.5])
        label = ""
        if kind == "mystery":
            kind = self.rng.choice(("splitrocket", "megarocket", "anvil", "tinyanvil"))
        if kind in ("multi", "splitrocket"):
            if kind == "splitrocket":
                p["rocket_t"] = ROCKET_TIME
            for side in (-1, 1):
                if len(self.pups) >= MAX_PUPS:
                    break
                n = self._pup(p["x"], p["h"], p["vx"] + side * SPLIT_VX, p["vh"] + SPLIT_VH, parent=p)
                n["rocket_t"] = p["rocket_t"]
                self.pups.append(n)
            p["vh"] += SPLIT_VH
            label = "SPLIT + ROCKET!" if kind == "splitrocket" else "x3 ASTRONAUTS!"
        elif kind in ("rocket", "megarocket"):
            p["rocket_t"] = ROCKET_TIME * (2 if kind == "megarocket" else 1)
            p["anvil_t"] = 0.0
            label = "MEGA ROCKET!" if kind == "megarocket" else "ROCKET!"
        elif kind == "giant":
            p["size"] = "giant"
            label = "GIANT!"
        elif kind == "tiny":
            p["size"] = "tiny"
            label = "TINY!"
        elif kind == "bounce":
            p["bounce"] += 1
            label = "BOUNCE!"
        elif kind == "throw":
            self.throws += 1
            label = "EXTRA THROW!"
        elif kind in ("anvil", "tinyanvil"):
            p["anvil_t"] = ANVIL_TIME
            p["rocket_t"] = 0.0
            if kind == "tinyanvil":
                p["size"] = "tiny"
            label = "TINY ANVIL!" if kind == "tinyanvil" else "ANVIL!"
            self.effects.append(["anvil", p["x"], p["h"], 0.0, 0.5])
        self.popups.append([label, p["x"], p["h"] + 60, 0.0])

    def _end_throw(self):
        m = int(self.best_h / PX_PER_M)
        if m < MIN_THROW_M:
            m = 0
        self.heights.append(m)
        self.score += m * 10
        self.phase, self.phase_t = "result", 0.0
        self.vx = self.vh = 0.0
        self.h = PUP_R
