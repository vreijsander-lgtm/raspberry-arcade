"""
Star Toss - game logic (no pygame in here, so it can be tested anywhere).

A throwing game for the tall screen. At the bottom of a tall shaft a launcher
droid on a bobbing hover pad holds your astronaut on its arm:
    PRESS BUTTON2   it starts spinning you round - faster and faster
    PRESS AGAIN     it lets go: you fly off the way you were moving
Wait too long (3.4 s) and it gets DIZZY and drops you. The pad bobs and tilts,
which shifts the angle a little every throw. Once you fly you can't steer.

Helper droids sit in the walls, alternating left / right (64 m apart, a few
metres up or down). Touch one and it bounces you up and across straight away.
How hard depends on how you hit it:
    ANGLE   steep (mostly up / down) is good, a flat sideways hit loses lift
    SPOT    rising: hit the front of its arms, not behind them (UNDER-CLIP);
            falling: land on top of it (a springboard)
    SPEED   rising fast carries on into the bounce, falling in gives a
            little trampoline push
Every bounce in a throw is a bit weaker, and after 4 the helpers aim you up
the middle, so every throw comes down in the end.

POWER-UP capsules drift down the shaft on parachutes - fly through one (it
works on the astronaut that touched it):
    M  MULTI    that astronaut splits into three (up to 9)
    R  ROCKET   a burst of rocket thrust
    G  GIANT    bigger: easier to hit helpers, but heavier and slower
    T  TINY     smaller: lighter and faster, but easy to miss helpers
    ?  MYSTERY  SPLIT + ROCKET or a MEGA ROCKET... or an ANVIL (heavy for a
                moment) or a TINY ANVIL - an anvil breaks off at a helper
The highest astronaut counts; a throw ends when the last one is back down.
When the highest astronaut reaches a new highest point and starts to fall,
the picture freezes for a moment (a snapshot).

A game is 5 throws; the score is the heights of all 5 added up (a throw
lower than 12 m counts as 0).
"""
import math
import random

SW, SH = 540, 960
PX_PER_M = 10                    # 1 m = 10 px (all the sizes below are in px)
WALL_L, WALL_R = 50, SW - 50     # the shaft: 44 m wide
CENTRE = SW / 2.0
PUP_R = 17                       # astronaut radius (1.7 m)
GRAVITY = 955.0                  # px/s^2
AIR_DRAG_X = 0.04                # (per second)
AIR_DRAG_Y = 0.012
WALL_RESTITUTION = 0.34
WALL_MAX_VX = 220.0              # a wall bounces you back at most this fast
WALL_FRICTION = 0.88             # upward speed kept when you hit a wall going up
THROWS = 5
MIN_THROW_M = 12.0               # lower than this: the throw counts as 0

# the launcher droid on its hover pad
PAD_H = 32.0                     # pad height above the ground
SHOULDER = 58.0                  # its arm turns this far above the pad
ARM = 46.0                       # arm length
SPIN_START = 7.8                 # rad/s when it starts ...
SPIN_ACCEL = 2.8                 # ... + this much per second you wait
DIZZY_TIME = 3.4                 # after this long it gets dizzy and drops you
DIZZY_WARN = 0.45                # (it starts to look dizzy after this part of it)
LAUNCH_SPEED = 2300.0            # every throw leaves the arm this fast
LAUNCH_X_SCALE = 0.62            # (sideways it's a bit softer)
SWAY_SPEED = 1.65                # the pad bobs, sways and tilts at this rate
PAD_BOB, PAD_SWAY, PAD_TILT = 3.8, 14.0, math.radians(6.5)

# helpers in the walls
HELPER_FIRST = 640.0             # height of the first helper ...
HELPER_GAP = 640.0               # ... and the next ones this much higher ...
HELPER_JITTER = 45.0             # ... give or take this much (0 = exactly the same gaps)
HIT_SPAN = 49.0                  # hit area around a helper's arms (plus your size)
HELPER_COOL = 0.45               # a helper can't bounce anyone again for this long
BOOST = 1760.0                   # first bounce speed ...
BOOST_DECAY = 0.87               # ... x this for every next one ...
BOOST_MIN = 950.0                # ... but at least this
BOUNCE_MIN, BOUNCE_MAX = 620.0, 2320.0
CROSS_MIN, CROSS_MAX = 280.0, 440.0     # sideways speed of a bounce (across the shaft)
LATE_BOUNCE = 4                  # after this many bounces (or falling fast) ...
FAST_FALL = -300.0
LATE_CROSS = (40.0, 62.0)        # ... it sends you up the middle
SUPER_V = 1850.0

# power-up capsules
POWERUPS = ("multi", "giant", "tiny", "rocket", "mystery")
LABELS = {"multi": "M", "giant": "G", "tiny": "T", "rocket": "R", "mystery": "?"}
CAPSULE_FALL = 72.0              # px/s down (parachutes)
CAPSULE_SWAY = 22.0
CAPSULE_R = 26.0                 # pick-up distance (plus your size)
CAPSULE_FIRST = 880.0
CAPSULE_EVERY = (520.0, 700.0)
CAPSULE_X = 125.0                # capsules float within this of the middle
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

# the peak snapshot
PHOTO_MIN = 200.0                # only above 20 m
PHOTO_FREEZE = 0.75              # the picture stops this long


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


class StarToss:
    mode = "CLASSIC"

    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.t = 0.0                     # time (for the bobbing pad and the helpers)
        self.throw_no = 0
        self.throws = THROWS
        self.heights = []                # metres of each finished throw
        self.score = 0
        self.powers_got = 0
        self.best_bounces = 0
        self.game_over = False
        self.effects = []                # [kind, x, h, age, max_age]   (h = height above ground)
        self.popups = []                 # [text, x, h, age]
        # the helpers stay in the same places for the whole game (5 throws)
        self.helpers = []                # {"side", "h", "anim", "cool", "peek"}
        self.next_side = self.rng.choice((0, 1))
        self.next_h = HELPER_FIRST
        self._build_helpers(SH * 2)
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
        self.phase = "ready"             # ready -> spin -> fly -> result
        self.phase_t = 0.0
        self.angle = -math.pi * 0.55     # arm angle (anticlockwise, 0 = pointing right)
        self.omega = 0.0
        self.held_t = 0.0                # how long it has been spinning
        self.dizzy = False
        self.x, self.h = self.hand()
        self.vx = self.vh = 0.0          # (the highest astronaut; vh > 0 = going up)
        self.best_h = 0.0
        self.cam = 0.0                   # height at the bottom of the screen
        self.pups = []
        self.bounces = 0
        self.freeze_t = 0.0              # the peak snapshot: picture stopped
        self.flash = 0.0
        self.photo_h = 0.0               # height of the last snapshot
        self.photo = None                # (text, x, h) of the last snapshot
        for hp in self.helpers:
            hp["cool"] = 0.0
            hp["anim"] = 0.0
        self.capsules = []               # {"x0", "x", "h", "kind", "ph"}
        self.next_cap = CAPSULE_FIRST
        first = list(POWERUPS)
        self.rng.shuffle(first)
        for kind in first:               # all five kinds in the first climb, every throw
            self._add_capsule(kind)
        self._build_capsules(SH * 2)

    # ------------------------------------------------------------------
    def _build_helpers(self, upto):
        while self.next_h < upto:
            h = self.next_h + self.rng.uniform(-HELPER_JITTER, HELPER_JITTER)
            self.helpers.append({"side": self.next_side, "h": h, "anim": 0.0, "cool": 0.0,
                                 "peek": 0.0, "ph": self.rng.uniform(0, math.tau)})
            self.next_side = 1 - self.next_side
            self.next_h += HELPER_GAP

    def _add_capsule(self, kind):
        x0 = CENTRE + self.rng.uniform(-CAPSULE_X, CAPSULE_X)
        self.capsules.append({"x0": x0, "x": x0, "h": self.next_cap + self.rng.uniform(-80, 80),
                              "kind": kind, "ph": self.rng.uniform(0, math.tau)})
        self.next_cap += self.rng.uniform(*CAPSULE_EVERY)

    def _build_capsules(self, upto):
        while self.next_cap < upto:
            self._add_capsule(self.rng.choice(POWERUPS))

    def hub(self):
        """Where the arm turns (it moves with the bobbing pad)."""
        s = SWAY_SPEED
        tilt = self.pad_tilt()
        if self.dizzy and self.phase != "ready":
            tilt += math.sin(self.t * 22.0) * 0.16
        bx = CENTRE + math.sin(self.t * s * 0.6) * PAD_SWAY
        by = PAD_H + math.sin(self.t * s) * PAD_BOB
        return bx + math.sin(tilt) * SHOULDER, by + math.cos(tilt) * SHOULDER

    def pad_tilt(self):
        return math.cos(self.t * SWAY_SPEED * 0.85) * PAD_TILT

    def hand(self):
        hx, hh = self.hub()
        a = self.angle + self.pad_tilt()
        return hx + math.cos(a) * ARM, hh + math.sin(a) * ARM

    def dizziness(self):
        """0..1: how dizzy the launcher is getting (it drops you at 1)."""
        return min(1.0, self.held_t / DIZZY_TIME) if self.phase == "spin" else 0.0

    def spin_power(self):
        return self.dizziness()

    def pup_r(self, p):
        return PUP_R * SIZES[p["size"]][0]

    def snout(self, hp):
        """Where a helper's arms are (what you bounce off): they reach out when you come near."""
        inward = 1 if hp["side"] == 0 else -1
        wall = WALL_L if hp["side"] == 0 else WALL_R
        ext = 32.0 + hp["peek"] + (26.0 if hp["anim"] > 0 else 0.0)
        return wall + inward * ext, hp["h"] + (12.0 if hp["anim"] > 0 else 0.0)

    def _pup(self, x, h, vx, vh):
        return {"x": x, "h": h, "vx": vx, "vh": vh, "peak": max(0.0, h), "size": "normal",
                "rocket_t": 0.0, "anvil_t": 0.0, "bounces": 0, "bounce": 0}

    # ------------------------------------------------------------------
    def update(self, dt_ms, left=False, right=False, held=False, presses=()):
        dt = min(dt_ms, 50) / 1000.0
        self.flash = max(0.0, self.flash - 760.0 * dt)
        if self.freeze_t > 0:                               # the peak snapshot: everything stops
            self.freeze_t = max(0.0, self.freeze_t - dt)
            return
        self.t += dt
        for e in self.effects:
            e[3] += dt
        self.effects = [e for e in self.effects if e[3] < e[4]]
        for p in self.popups:
            p[3] += dt
        self.popups = [p for p in self.popups if p[3] < 1.1]
        if self.game_over:
            return
        self.phase_t += dt
        press = "button2" in presses
        if self.phase == "ready":
            self.x, self.h = self.hand()
            if press:
                self.phase, self.phase_t = "spin", 0.0
                self.angle = -math.pi * 0.5
                self.held_t = 0.0
                self.omega = SPIN_START
        elif self.phase == "spin":
            self._spin(dt, press)
        elif self.phase == "fly":
            self._fly(dt)
        elif self.phase == "result":
            self.cam += (0.0 - self.cam) * (1.0 - math.exp(-5.5 * dt))
            if self.phase_t >= 2.4 or (self.phase_t >= 0.35 and press):
                if self.throw_no >= self.throws:
                    self.game_over = True
                else:
                    self.next_throw()
        if self.phase in ("ready", "spin"):
            self.cam += (0.0 - self.cam) * (1.0 - math.exp(-5.5 * dt))
        self._tick_helpers(dt)

    def _tick_helpers(self, dt):
        k = int((self.h - HELPER_FIRST) // HELPER_GAP)
        for i in range(max(0, k - 3), min(len(self.helpers), k + 5)):
            hp = self.helpers[i]
            hp["cool"] = max(0.0, hp["cool"] - dt)
            hp["anim"] = max(0.0, hp["anim"] - dt)
            eager = 0.0
            for p in self.pups:                             # it leans out when you come near
                dy = abs(p["h"] - hp["h"])
                if dy < 280.0:
                    eager = max(eager, (1.0 - dy / 280.0) * 14.0)
            hp["peek"] = 6.5 + 6.5 * math.sin(self.t * 2.4 + hp["ph"]) + eager

    def _spin(self, dt, press):
        if press:                                           # second press: let go
            self._release()
            return
        self.held_t += dt
        self.omega = SPIN_START + SPIN_ACCEL * self.held_t
        self.angle += self.omega * dt
        self.x, self.h = self.hand()
        if self.held_t >= DIZZY_TIME:                       # waited too long: it drops you
            self._fumble()

    def _release(self):
        hx, hh = self.hand()
        a = self.angle + self.pad_tilt()
        self.vx = -math.sin(a) * LAUNCH_SPEED * LAUNCH_X_SCALE
        self.vh = math.cos(a) * LAUNCH_SPEED
        self.pups = [self._pup(hx, hh, self.vx, self.vh)]
        self.phase, self.phase_t = "fly", 0.0
        self.effects.append(["release", hx, hh, 0.0, 0.4])

    def _fumble(self):
        hx, hh = self.hand()
        self.dizzy = True
        side = self.rng.choice((-1, 1))
        self.pups = [self._pup(hx, hh, side * self.rng.uniform(280.0, 480.0), -320.0)]
        self.phase, self.phase_t = "fly", 0.0
        self.popups.append(["TOO DIZZY!", CENTRE, 240, 0.0])

    def throw_dir(self):
        """Unit vector (x, up) the astronaut would fly if let go now."""
        a = self.angle + self.pad_tilt()
        dx, du = -math.sin(a) * LAUNCH_X_SCALE, math.cos(a)
        n = math.hypot(dx, du) or 1.0
        return dx / n, du / n

    # ------------------------------------------------------------------
    def _fly(self, dt):
        top = max([p["h"] for p in self.pups] + [0.0])
        self._build_helpers(top + 5200.0)
        self._build_capsules(top + 5200.0)
        respawn = max(3600.0, top + 900.0)
        for cp in self.capsules:                            # parachutes drift down and sway
            cp["h"] -= CAPSULE_FALL * dt
            cp["x"] = cp["x0"] + math.sin(self.t * 2.1 + cp["ph"]) * CAPSULE_SWAY
            if cp["h"] < 220.0:                             # (back up above the action)
                cp["h"] = self.rng.uniform(respawn, respawn + 1800.0)
                cp["x0"] = CENTRE + self.rng.uniform(-CAPSULE_X, CAPSULE_X)
        champion = None
        for p in list(self.pups):
            if p not in self.pups:
                continue
            prev_vh = p["vh"]
            self._move(p, dt)
            self._collide(p)
            if p in self.pups:
                self.best_h = max(self.best_h, p["peak"])
                if (prev_vh >= 0 > p["vh"] and p["peak"] >= PHOTO_MIN
                        and round(p["peak"]) > round(self.photo_h)):
                    if champion is None or p["peak"] > champion["peak"]:
                        champion = p
        if not self.pups:                                   # the last one is back down
            self._end_throw()
            return
        lead = max(self.pups, key=lambda q: q["h"])         # the camera follows the highest one
        if champion is not lead:                            # snapshot only when the TOP one turns down
            champion = None
        self.x, self.h, self.vx, self.vh = lead["x"], lead["h"], lead["vx"], lead["vh"]
        look = _clamp(self.vh * 0.075, -80.0, 160.0)
        target = max(0.0, self.h - SH * 0.45 + look)
        rate = 9.5 if target >= self.cam else 7.0
        self.cam += (target - self.cam) * (1.0 - math.exp(-rate * dt))
        if champion is not None:                            # a new highest point: snapshot!
            self.photo_h = champion["peak"]
            self.photo = ("PEAK %.1f M" % (champion["peak"] / PX_PER_M), champion["x"], champion["peak"])
            self.freeze_t = PHOTO_FREEZE
            self.flash = 235.0

    def _move(self, p, dt):
        scale, grav, _, _ = SIZES[p["size"]]
        g = GRAVITY * grav
        if p["rocket_t"] > 0:
            p["rocket_t"] = max(0.0, p["rocket_t"] - dt)
            p["vh"] = min(ROCKET_MAX_V, p["vh"] + ROCKET_THRUST * dt)
        elif p["anvil_t"] > 0:
            p["anvil_t"] = max(0.0, p["anvil_t"] - dt)
            g *= ANVIL_GRAVITY
        p["vh"] -= g * dt
        p["vx"] *= max(0.0, 1.0 - AIR_DRAG_X * dt)
        p["vh"] *= max(0.0, 1.0 - AIR_DRAG_Y * dt)
        p["x"] += p["vx"] * dt
        p["h"] += p["vh"] * dt
        p["peak"] = max(p["peak"], p["h"])

    def _collide(self, p):
        r = self.pup_r(p)
        for cp in list(self.capsules):                      # 0. power-ups
            if math.hypot(p["x"] - cp["x"], p["h"] - cp["h"]) <= r + CAPSULE_R:
                self.capsules.remove(cp)
                self._power(cp["kind"], p)
        k = int((p["h"] - HELPER_FIRST) // HELPER_GAP)      # 1. helpers
        for i in range(max(0, k - 1), min(len(self.helpers), k + 3)):
            hp = self.helpers[i]
            if hp["cool"] > 0:
                continue
            sx, sy = self.snout(hp)
            if math.hypot(p["x"] - sx, p["h"] - sy) <= HIT_SPAN + r:
                self._bounce(p, hp)
                return
        cap = WALL_MAX_VX * SIZES[p["size"]][3]             # 2. the walls
        if p["x"] < WALL_L + r:
            p["x"] = WALL_L + r
            if p["vx"] < 0:
                p["vx"] = min(cap, abs(p["vx"]) * WALL_RESTITUTION)
                if p["vh"] > 0:
                    p["vh"] *= WALL_FRICTION
                self.effects.append(["wall", WALL_L, p["h"], 0.0, 0.3])
        elif p["x"] > WALL_R - r:
            p["x"] = WALL_R - r
            if p["vx"] > 0:
                p["vx"] = -min(cap, abs(p["vx"]) * WALL_RESTITUTION)
                if p["vh"] > 0:
                    p["vh"] *= WALL_FRICTION
                self.effects.append(["wall", WALL_R, p["h"], 0.0, 0.3])
        if p["h"] <= 0.0:                                   # 3. back down: this one is done
            self.pups.remove(p)
            self.effects.append(["land", p["x"], 0.0, 0.0, 0.5])

    def _bounce(self, p, hp):
        """A helper bounces you up and across - how hard depends on the angle you come
        in at, the spot you hit and how fast you were going."""
        sx, sy = self.snout(hp)
        hp["cool"] = HELPER_COOL
        hp["anim"] = 0.42
        p["anvil_t"] = 0.0                                  # an anvil breaks off
        p["bounces"] += 1
        self.bounces = max(self.bounces, p["bounces"])
        self.best_bounces = max(self.best_bounces, self.bounces)
        inward = 1 if hp["side"] == 0 else -1
        r = self.pup_r(p)
        span = HIT_SPAN + r
        _, _, boost_scale, vx_scale = SIZES[p["size"]]
        vx, vy = p["vx"], p["vh"]
        angle_q = _clamp((abs(vy) / max(10.0, math.hypot(vx, vy)) - 0.25) / 0.65, 0.20, 1.00)
        front = (p["x"] - sx) * inward / span
        rel_y = _clamp((p["h"] - sy) / span, -1.0, 1.0)
        under = False
        if vy >= 0:
            if front >= 0.10:
                zone = 1.06 + 0.10 * min(1.0, front)
            elif front >= -0.22:
                zone = 0.96
            else:
                under = True
                zone = max(0.55, 0.85 + front * 0.55)
        else:
            if rel_y >= 0.10 and front >= -0.25:
                zone = 1.08 + 0.10 * min(1.0, rel_y)
            elif front >= -0.35:
                zone = 0.95
            else:
                under = True
                zone = 0.62
        quality = angle_q * zone
        core = max(BOOST_MIN, BOOST * BOOST_DECAY ** (p["bounces"] - 1))
        if vy >= 0:
            raw = (core * (0.56 + 0.48 * quality) + vy * 0.24 * angle_q) * boost_scale
        else:
            tramp = min(460.0, abs(vy) * 0.20)
            raw = (core * 0.78 + tramp) * (0.54 + 0.46 * quality) * boost_scale
        new_vh = max(BOUNCE_MIN, min(BOUNCE_MAX * max(1.0, boost_scale), raw))
        if p["bounces"] <= LATE_BOUNCE and vy >= FAST_FALL:
            kick = 60.0 if under else 0.0
            cross = min(CROSS_MAX, CROSS_MIN + (1.0 - angle_q) * 140.0 + kick) * vx_scale
        else:                                               # late / rescue bounce: up the middle
            cross = self.rng.uniform(*LATE_CROSS)
        p["vx"] = inward * cross
        p["vh"] = new_vh
        p["x"] = sx + inward * (14.0 + (r - PUP_R) * 0.5)
        if under:
            text, kind = "UNDER-CLIP!", "clip"
        elif angle_q < 0.52:
            text, kind = "FLAT HIT!", "flat"
        elif quality >= 0.98 and new_vh >= SUPER_V * min(1.0, boost_scale):
            text, kind = "SUPER BOUNCE!", "super"
        else:
            text, kind = "NICE BOUNCE!", "boost"
        self.effects.append([kind, sx + inward * 28, sy + 6, 0.0, 0.5])
        self.popups.append([text, p["x"], p["h"] + 70, 0.0])

    def _split(self, p, rocket=False):
        p["vh"] = max(p["vh"], 750.0) + 140.0
        if rocket:
            self._rocket(p, 0.45)
        for dvx in (-SPLIT_VX, SPLIT_VX):
            if len(self.pups) >= MAX_PUPS:
                break
            r = self.pup_r(p)
            n = self._pup(_clamp(p["x"] + (16 if dvx > 0 else -16), WALL_L + r + 5, WALL_R - r - 5),
                          p["h"], p["vx"] + dvx, p["vh"] + SPLIT_VH)
            n["size"], n["bounces"] = p["size"], p["bounces"]
            n["peak"] = max(0.0, p["h"])
            if rocket:
                self._rocket(n, 0.45)
            self.pups.append(n)

    def _rocket(self, p, t):
        p["anvil_t"] = 0.0
        p["rocket_t"] = max(p["rocket_t"], t)
        p["vh"] = max(p["vh"], 1350.0)

    def _anvil(self, p, t):
        p["rocket_t"] = 0.0
        p["anvil_t"] = max(p["anvil_t"], t)
        p["vh"] = min(p["vh"], 350.0) - 450.0

    def _size(self, p, size):
        p["size"] = size
        if size == "giant":
            p["vx"] *= 0.82
            p["vh"] *= 0.88
        elif size == "tiny":
            p["vx"] *= 1.12
            if p["vh"] > 0:
                p["vh"] *= 1.08

    def _power(self, kind, p):
        self.powers_got += 1
        self.effects.append(["power", p["x"], p["h"], 0.0, 0.5])
        if kind == "multi":
            self._split(p)
            label = "MULTI x3!"
        elif kind == "giant":
            self._size(p, "giant")
            label = "GIANT! (HEAVY)"
        elif kind == "tiny":
            self._size(p, "tiny")
            label = "TINY! (FAST)"
        elif kind == "rocket":
            self._rocket(p, ROCKET_TIME)
            label = "ROCKET!"
        else:                                               # mystery: a gamble
            pick = self.rng.choice(("split", "mega", "anvil", "tinyanvil"))
            if pick == "split":
                self._split(p, rocket=True)
                label = "SPLIT + ROCKET!"
            elif pick == "mega":
                self._rocket(p, ROCKET_TIME * 1.25)
                label = "MEGA ROCKET!"
            elif pick == "anvil":
                self._anvil(p, ANVIL_TIME)
                label = "ANVIL!"
                self.effects.append(["anvil", p["x"], p["h"], 0.0, 0.5])
            else:
                self._size(p, "tiny")
                self._anvil(p, ANVIL_TIME * 0.85)
                label = "TINY ANVIL!"
                self.effects.append(["anvil", p["x"], p["h"], 0.0, 0.5])
        self.popups.append([label, p["x"], p["h"] + 60, 0.0])

    def _end_throw(self):
        m = round(self.best_h / PX_PER_M, 1)
        if m < MIN_THROW_M:
            m = 0.0
        self.heights.append(m)
        self.score = int(round(sum(self.heights)))
        self.phase, self.phase_t = "result", 0.0
        self.vx = self.vh = 0.0
        self.h = 0.0
