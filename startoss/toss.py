"""
Star Toss - game logic (no pygame in here, so it can be tested anywhere).

A throwing game for the tall screen. At the bottom of a tall shaft a launcher
droid swings your astronaut round on a tether:
    HOLD BUTTON2   it spins faster and faster
    LET GO         the astronaut flies off the way it was moving right then -
                   let go when it swings UP (on the left side of the circle)
That is the only control: once it flies you can't steer it.
Up the shaft, helper droids stand on ledges in the walls - ALWAYS IN THE SAME
PLACES, zig-zagging left / right. Fly past one close to its wall and it grabs
you and throws you up and across to the other wall, towards the next one
(press BUTTON2 just as it grabs you for a PERFECT throw). Helpers can catch
you again (up to 3 times each per throw), but every time a helper throws you
again it is more tired (a weaker throw), so you always come down in the end.
So it all depends on your throw: straight up misses the walls, a slightly
slanted throw bounces off them into the helpers. Every helper throw IN A ROW
throws you harder (a chain); the chain breaks when you have been falling for
a while before the next helper grabs you.
Every 100 m there is a SPIN STATION across the shaft: reach it and it grabs
you and spins you round - HOLD BUTTON2 and LET GO again to throw from there
(each station works once per throw). A throw is over when you are back on
the ground.

Every game is 3 throws; your score is the height of all three added up
(10 points a metre) plus 50 for every star you fly through.
"""
import math
import random

SW, SH = 540, 960
WALL_L, WALL_R = 46, SW - 46     # the shaft's inner walls
PUP_R = 18
PX_PER_M = 30
GRAVITY = 1250.0
WALL_BOUNCE = 0.85              # (no steering: the walls keep you zig-zagging)
THROWS = 3

# the launcher
HUB = (SW / 2.0, 150.0)          # spin centre: x, height above the ground
TETHER = 74.0
SPIN_IDLE = 2.2                  # rad/s while not holding
SPIN_ACCEL = 7.5                 # rad/s^2 while holding
SPIN_MAX = 15.0
THROW_MULT = 2.15                # throw speed = spin speed x tether x this
MIN_HOLD = 0.25                  # a tap does nothing

# helpers on the walls - a fixed layout, the same every throw and every game
HELPER_X = (WALL_L + 18, WALL_R - 18)
HELPER_FIRST = 620.0             # height of the first helper ...
HELPER_GAP = 330.0               # ... and the next ones, every this much higher
GRAB_WALL = 115.0                # it grabs you when you're this close to its wall ...
GRAB_HEIGHT = 70.0               # ... and this close to its height
CARRY = 0.3                      # helpers pass on this part of the speed you arrive with
HELPER_COOL = 1.2                # a helper can grab you again after this (s) ...
TIRED = 0.55                     # ... but every time it throws again: x this
MAX_USES = 3                     # ... and after 3 throws it rests (until the next throw)
STATION_EVERY = 100 * PX_PER_M   # a spin station every 100 m
STATION_GRAB = 70.0              # it grabs you when you're this close to its height
STATION_BONUS = 200
CROSS_VX = 360.0                 # helpers throw you across to the other wall this fast
HELPER_HOLD = 0.16               # how long it holds you before throwing
HELPER_BOOST = 1450.0            # upwards speed after a helper throw
PERFECT_MULT = 1.6
PERFECT_WINDOW = 0.3             # B2 this close before the throw = perfect
STAR_POINTS = 50
STAR_R = 16
CHAIN_STEP = 0.15                # each helper in a row throws 15 % harder ...
CHAIN_MAX = 2.0                  # ... up to twice as hard
CHAIN_FALL = 0.8                 # falling longer than this (s) before a catch breaks the chain


class StarToss:
    mode = "CLASSIC"

    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.throw_no = 0
        self.heights = []                # metres of each finished throw
        self.score = 0
        self.stars_got = 0
        self.perfects = 0
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
        self.x, self.h = HUB[0], HUB[1] - TETHER
        self.vx = self.vh = 0.0          # vh > 0 = going up
        self.best_h = 0.0
        self.cam = 0.0                   # height at the bottom of the screen
        self.caught = None               # the helper holding us
        self.catch_t = 0.0
        self.perfect_t = 0.0             # > 0: B2 was just pressed
        self.throw_stars = 0
        self.chain = 0                   # helper throws in a row
        self.best_chain = getattr(self, "best_chain", 0)
        self.fall_t = 0.0                # seconds falling since the last helper throw
        self.helpers = []                # {"side", "h", "kind", "uses", "cool", "anim"}
        self.stars = []                  # {"x", "h"}
        self.stations = []               # {"h", "used"}  (a spin station every 100 m)
        self.hub = HUB                   # where we're spinning now (the ground launcher or a station)
        self.stations_used = 0
        self.built = 0                   # helpers placed so far
        self.next_h = HELPER_FIRST
        self._build(SH * 2)

    def _build(self, upto):
        """The same shaft every time: helpers zig-zag up the walls at fixed
        heights (further apart higher up), stars in between, and a spin
        station every 100 m."""
        while (len(self.stations) + 1) * STATION_EVERY < upto:
            self.stations.append({"h": (len(self.stations) + 1) * STATION_EVERY, "used": False})
        while self.next_h < upto:
            i = self.built
            h = self.next_h
            self.helpers.append({"side": i % 2, "h": h, "kind": "helper",
                                 "uses": 0, "cool": 0.0, "anim": 0.0})
            if i % 2 == 1:
                self.stars.append({"x": SW / 2.0 + (90 if i % 4 == 1 else -90),
                                   "h": h + (HELPER_GAP + h * 0.035) / 2})
            self.built += 1
            self.next_h += HELPER_GAP + h * 0.035

    # ------------------------------------------------------------------
    def spin_power(self):
        """0..1 for the power meter."""
        return (self.omega - SPIN_IDLE) / (SPIN_MAX - SPIN_IDLE)

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
            hp["cool"] = max(0.0, hp["cool"] - dt)
        if self.game_over:
            return
        self.phase_t += dt
        if "button2" in presses:
            self.perfect_t = PERFECT_WINDOW
        self.perfect_t = max(0.0, self.perfect_t - dt)

        if self.phase == "spin":
            self._spin(dt, held)
        elif self.phase == "fly":
            self._fly(dt, left, right)
        elif self.phase == "result":
            if self.phase_t >= 2.4:
                if self.throw_no >= THROWS:
                    self.game_over = True
                else:
                    self.next_throw()

    def _spin(self, dt, held):
        if held:
            self.held_t += dt
            self.omega = min(SPIN_MAX, self.omega + SPIN_ACCEL * dt)
            self.was_held = True
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
        self.vx, self.vh = dx * sp, dup * sp
        self.phase, self.phase_t = "fly", 0.0
        self.effects.append(["release", self.x, self.h, 0.0, 0.4])

    def _fly(self, dt, left, right):
        # (left / right are ignored: once thrown you can't steer)
        if self.caught is not None:                       # a helper is holding us
            hp = self.caught
            self.catch_t += dt
            self.x = HELPER_X[hp["side"]] + (22 if hp["side"] == 0 else -22)
            self.h = hp["h"] + 24
            if self.catch_t >= HELPER_HOLD:
                self._helper_throw(hp)
            return
        self.vh -= GRAVITY * dt
        self.x += self.vx * dt
        self.h += self.vh * dt
        self.fall_t = self.fall_t + dt if self.vh < 0 else 0.0
        if self.x < WALL_L + PUP_R:
            self.x, self.vx = WALL_L + PUP_R, abs(self.vx) * WALL_BOUNCE
        elif self.x > WALL_R - PUP_R:
            self.x, self.vx = WALL_R - PUP_R, -abs(self.vx) * WALL_BOUNCE
        self.best_h = max(self.best_h, self.h)
        self._build(self.h + SH * 2)
        # a spin station (every 100 m) grabs you anywhere across the shaft
        for st in self.stations:
            if not st["used"] and abs(st["h"] - self.h) < STATION_GRAB:
                self._to_station(st)
                return
        # helpers (they can grab you again, once they've had a moment)
        for hp in self.helpers:
            if hp["cool"] > 0 or hp["uses"] >= MAX_USES or abs(hp["h"] - self.h) > 200:
                continue
            near_wall = (self.x - WALL_L if hp["side"] == 0 else WALL_R - self.x) < GRAB_WALL
            if near_wall and abs(hp["h"] + 20 - self.h) < GRAB_HEIGHT:
                hp["anim"] = 0.5
                self.caught = hp
                self.catch_t = 0.0
                self.arrive_v = max(0.0, self.vh)          # (part of it is passed on)
                break
        for s in list(self.stars):
            if math.hypot(s["x"] - self.x, s["h"] - self.h) < STAR_R + PUP_R:
                self.stars.remove(s)
                self.throw_stars += 1
                self.stars_got += 1
                self.score += STAR_POINTS
                self.effects.append(["star", s["x"], s["h"], 0.0, 0.5])
                self.popups.append(["+%d" % STAR_POINTS, s["x"], s["h"] + 30, 0.0])
        # the camera follows (the astronaut 45 % up the screen), never below the ground
        target = max(0.0, self.h - SH * 0.45)
        self.cam += (target - self.cam) * min(1.0, dt * 6)
        # the throw is over only when you are back on the ground
        if self.h <= PUP_R and self.vh < 0:
            self.h = PUP_R
            self._end_throw()

    def _to_station(self, st):
        """Grabbed by a spin station: spin again - hold B2, let go to throw."""
        st["used"] = True
        self.stations_used += 1
        self.hub = (SW / 2.0, st["h"])
        self.angle = math.atan2(st["h"] - self.h, self.x - self.hub[0])
        self.omega = SPIN_IDLE * 1.5
        self.held_t = 0.0
        self.was_held = False
        self.vx = self.vh = 0.0
        self.chain = 0
        self.score += STATION_BONUS
        self.phase, self.phase_t = "spin", 0.0
        self.effects.append(["station", self.hub[0], st["h"], 0.0, 0.6])
        self.popups.append(["%d M STATION! +%d" % (st["h"] // PX_PER_M, STATION_BONUS),
                            self.hub[0], st["h"] + 110, 0.0])

    def chain_mult(self):
        """How much harder the next helper throws (1.0 = normal)."""
        return min(CHAIN_MAX, 1.0 + CHAIN_STEP * self.chain)

    def _helper_throw(self, hp):
        perfect = self.perfect_t > 0
        self.perfect_t = 0.0
        if self.fall_t > CHAIN_FALL:                       # fell too long: a new chain
            if self.chain >= 2:
                self.popups.append(["CHAIN BROKEN", self.x, self.h + 90, 0.0])
            self.chain = 0
        boost = HELPER_BOOST * self.chain_mult() * (PERFECT_MULT if perfect else 1.0)
        boost *= TIRED ** hp["uses"]                       # it gets tired of throwing you
        hp["uses"] += 1
        hp["cool"] = HELPER_COOL
        self.chain += 1
        self.best_chain = max(self.best_chain, self.chain)
        self.fall_t = 0.0
        if self.chain >= 2:
            self.popups.append(["CHAIN x%d" % self.chain, self.x, self.h + 90, 0.0])
        self.vh = boost + CARRY * getattr(self, "arrive_v", 0.0)
        self.vx = CROSS_VX if hp["side"] == 0 else -CROSS_VX      # across to the other wall
        self.caught = None
        hp["anim"] = 0.6
        self.effects.append(["perfect" if perfect else "boost", self.x, self.h, 0.0, 0.5])
        if perfect:
            self.perfects += 1
            self.score += 100
            self.popups.append(["PERFECT! +100", self.x, self.h + 50, 0.0])

    def _end_throw(self):
        m = int(self.best_h / PX_PER_M)
        self.heights.append(m)
        self.score += m * 10
        self.phase, self.phase_t = "result", 0.0
        self.vx = self.vh = 0.0
