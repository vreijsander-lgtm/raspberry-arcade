"""
Sky Hopper - game logic (no pygame in here, so it can be tested anywhere).

An endless climbing platformer for the tall screen: run and jump up from
platform to platform. The screen follows you up and, once you get going,
slowly keeps rising by itself - fall off the bottom and the run is over.

Controls (see main.py) - the same six buttons as the other games:
    LEFT / RIGHT   run
    BUTTON2 or UP  jump (hold it to jump higher)
    DOWN           drop down through the platform you stand on
    BUTTON1        menu

Things on the way up:
    platforms   green = normal, pink = moving, orange = crumbles after you
                land on it, wide grey = the starting ground
    springs     land on one for a huge jump - until you land again you are
                powered up and smash every enemy you bump into
    walkers     purple blobs walking on platforms - jump on their head to
                squash them (and bounce), touching them from the side hurts
    flyers      bats flying across the screen (higher up) - same rules
You have 3 hearts. Every new zone (every 150 m) gets harder.

Multiplayer: everybody gets the same world (same seed). The screen of every
player follows the HIGHEST player (set_leader_cam), so whoever is too slow
falls off the bottom and is out. The other players are shown as ghosts.
"""
import math
import random

SW, SH = 540, 960                # playfield size (same as the screen)

# player
PW, PH = 34, 44                  # hit box
GRAVITY = 2300.0                 # px/s^2
JUMP_GRAVITY = 1300.0            # while rising and holding jump (= higher jump)
MAX_FALL = 1150.0
JUMP_V = 880.0
STOMP_V = 700.0                  # bounce after squashing an enemy
SPRING_V = 1550.0
RUN_SPEED = 310.0
RUN_EASE = 11.0                  # how fast you reach full speed (higher = snappier)
AIR_EASE = 6.5                   # the same in the air
STOP_EASE = 9.0                  # how fast you slow down on the ground
AIR_DRIFT = 1.2                  # ... and in the air without pressing anything
COYOTE = 0.09                    # you can still jump this long after walking off
JUMP_BUFFER = 0.13               # a jump pressed this early before landing still counts
START_HEARTS = 3
MODES = ("CLASSIC", "TURBO")
INVULN_TIME = 1.6

# world
FLOOR_Y = SH - 70                # top of the starting ground (world y)
PLAT_H = 18
PX_PER_M = 30                    # pixels per metre (for the height shown)
ZONE_M = 150                     # a new zone every 150 m
CAMERA_EASE = 7.0                # how quickly the screen catches up when you climb
LEADER_EASE = 4.0                # multiplayer: how quickly you are pulled up to the leader
CAMERA_LEAD = 0.40               # keep the player this far from the top when climbing
SCROLL_START_M = 8               # the screen starts rising by itself after this
CRUMBLE_TIME = 0.45

# enemies
WALKER_W, WALKER_H = 34, 28
FLYER_W, FLYER_H = 40, 24

# points
POINTS_PER_M = 5
STOMP_POINTS = 50


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def _overlap(ax, ay, aw, ah, bx, by, bw, bh):
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


class Platformer:
    def __init__(self, seed=None, mode="CLASSIC"):
        self.rng = random.Random(seed)
        # TURBO: the screen rises fast right away.
        self.mode = mode if mode in MODES else "CLASSIC"
        # player (x, y = top-left of the hit box, world coordinates, y down)
        self.x = SW / 2.0 - PW / 2.0
        self.y = FLOOR_Y - PH
        self.vx = 0.0
        self.vy = 0.0
        self.face = 1
        self.ground = None             # platform we stand on
        self.coyote = 0.0
        self.buffer = 0.0
        self.jump_held = False
        self.jumping = False           # rising from our own jump (variable height)
        self.drop_plat = None          # platform we are dropping through
        self.drop_timer = 0.0
        self.hearts = START_HEARTS
        self.invuln = 0.0
        self.run_t = 0.0               # for the running animation
        self.squash = 0.0              # >0 just landed, <0 just jumped (for drawing)
        self.powered = False           # launched by a spring: enemies you hit get smashed

        self.cam_y = 0.0               # world y of the top of the screen
        self.leader_cam = None         # multiplayer: camera of the highest other player
        self.max_h = 0.0               # best height in pixels
        self.stomps = 0
        self.bonus = 0
        self.zone = 1
        self.banner = None             # (text, seconds left)
        self.dead = False
        self.fell = False
        self.dead_timer = 0.0
        self.game_over = False
        self.time = 0.0

        self.plats = []
        self.springs = []
        self.enemies = []
        self.effects = []              # rings: [x, y, age, max_age, color]
        self.popups = []               # floating texts: [x, y, text, age]
        floor = self._plat(0, FLOOR_Y, SW, "floor")
        self.plats.append(floor)
        self.next_y = FLOOR_Y
        self.last_cx = SW / 2.0
        self._generate()

    # ------------------------------------------------------------------
    # Info for drawing / the scoreboard
    # ------------------------------------------------------------------
    @property
    def meters(self):
        return int(self.max_h / PX_PER_M)

    @property
    def score(self):
        return int(self.meters * POINTS_PER_M + self.stomps * STOMP_POINTS + self.bonus)

    def difficulty(self):
        """0.0 at the start, 1.0 at 1200 m."""
        return _clamp(self.meters / 1200.0, 0.0, 1.0)

    def scroll_speed(self):
        if self.mode == "TURBO":
            if self.meters < 3:                  # a tiny head start
                return 0.0
            return 1.6 * (30.0 + 70.0 * self.difficulty() + 4.0 * min(10, self.zone - 1))
        if self.meters < SCROLL_START_M:
            return 0.0
        return 22.0 + 70.0 * self.difficulty() + 4.0 * min(10, self.zone - 1)

    # ------------------------------------------------------------------
    # World generation
    # ------------------------------------------------------------------
    def _plat(self, x, y, w, kind):
        p = {"x": float(x), "y": float(y), "w": float(w), "kind": kind,
             "vx": 0.0, "min": 0.0, "max": 0.0, "crumble": -1.0, "fall": 0.0,
             "dx": 0.0, "gone": False}
        return p

    def _generate(self):
        top_needed = self.cam_y - SH * 0.6
        rng = self.rng
        while self.next_y > top_needed:
            h_m = (FLOOR_Y - self.next_y) / PX_PER_M
            d = _clamp(h_m / 1200.0, 0.0, 1.0)
            gap = rng.uniform(85 + 45 * d, 135 + 75 * d)
            y = self.next_y - gap
            w = rng.uniform(150 - 60 * d, 205 - 75 * d)
            # stay reachable: not too far sideways from the last one
            reach = 250 + 30 * d
            lo = max(10.0, self.last_cx - reach - w / 2)
            hi = min(SW - 10.0 - w, self.last_cx + reach - w / 2)
            if lo > hi:
                lo, hi = 10.0, SW - 10.0 - w
            x = rng.uniform(lo, hi)
            # pick a kind
            r = rng.random()
            moving = 0.05 + 0.25 * d if h_m > 25 else 0.0
            crumble = 0.04 + 0.18 * d if h_m > 45 else 0.0
            if r < moving:
                kind = "move"
            elif r < moving + crumble:
                kind = "crumble"
            else:
                kind = "normal"
            p = self._plat(x, y, w, kind)
            if kind == "move":
                span = rng.uniform(70, 170)
                p["min"] = max(6.0, x - span)
                p["max"] = min(SW - 6.0 - w, x + span)
                p["vx"] = rng.choice((-1, 1)) * rng.uniform(55, 85 + 70 * d)
            self.plats.append(p)
            self.next_y = y
            self.last_cx = x + w / 2

            # things on / above the platform
            if kind == "normal" and rng.random() < 0.07 + 0.03 * d and h_m > 5:
                self.springs.append({"p": p, "off": rng.uniform(4, w - 34), "t": 0.0})
            elif kind == "normal" and w >= 100 and h_m > 20 and rng.random() < 0.10 + 0.28 * d:
                ex = x + rng.uniform(0, w - WALKER_W)
                self.enemies.append({"k": "walker", "p": p, "x": ex,
                                     "y": y - WALKER_H, "dir": rng.choice((-1, 1)),
                                     "speed": rng.uniform(45, 70 + 50 * d),
                                     "t": rng.uniform(0, 6), "dead": 0.0})
            # flyers in the air higher up
            if h_m > 120 and rng.random() < 0.03 + 0.10 * d:
                fy = y - gap * 0.5
                self.enemies.append({"k": "flyer", "p": None,
                                     "x": rng.uniform(20, SW - 20 - FLYER_W),
                                     "y": fy, "base": fy, "dir": rng.choice((-1, 1)),
                                     "speed": rng.uniform(70, 110 + 60 * d),
                                     "t": rng.uniform(0, 6), "dead": 0.0})

    def _cleanup(self):
        bottom = self.cam_y + SH + 250
        self.plats = [p for p in self.plats if p["y"] < bottom and not p["gone"]]
        alive = set(id(p) for p in self.plats)
        self.springs = [s for s in self.springs if id(s["p"]) in alive]
        self.enemies = [e for e in self.enemies
                        if e["y"] < bottom and (e["p"] is None or id(e["p"]) in alive)
                        and e["dead"] < 0.6]
        if self.ground is not None and id(self.ground) not in alive:
            self.ground = None

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def press(self, action):
        if self.dead:
            return
        if action in ("button2", "up"):
            self.buffer = JUMP_BUFFER
        elif action == "down":
            p = self.ground
            if p is not None and p["kind"] != "floor":
                self.drop_plat = p
                self.drop_timer = 0.3
                self.ground = None
                self.coyote = 0.0
                self.y += 2
                self.vy = max(self.vy, 60.0)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(self, dt_ms, left, right, jump_held):
        dt = min(0.1, dt_ms / 1000.0)
        self.jump_held = jump_held
        self.time += dt
        if self.game_over:                       # out: just watch the others climb
            self._move_world(dt)
            self._follow_leader(dt)
            self._update_effects(dt)
            self._generate()
            self._cleanup()
            return
        steps = max(1, int(math.ceil(dt / (1 / 120.0))))
        h = dt / steps
        for _ in range(steps):
            self._step(h, left, right)
            if self.game_over:
                break
        self._update_effects(dt)
        if self.banner:
            self.banner = (self.banner[0], self.banner[1] - dt)
            if self.banner[1] <= 0:
                self.banner = None
        self._generate()
        self._cleanup()

    def _step(self, dt, left, right):
        self._move_world(dt)
        if self.dead:
            self._step_dead(dt)
            self._follow_leader(dt)
            return
        self._step_player(dt, left, right)

    def _move_world(self, dt):
        """Moving platforms, crumbling platforms and springs."""
        for p in self.plats:
            p["dx"] = 0.0
            if p["kind"] == "move":
                nx = p["x"] + p["vx"] * dt
                if nx < p["min"] or nx > p["max"]:
                    p["vx"] = -p["vx"]
                    nx = _clamp(nx, p["min"], p["max"])
                p["dx"] = nx - p["x"]
                p["x"] = nx
            if p["crumble"] >= 0:
                p["crumble"] += dt
                if p["crumble"] >= CRUMBLE_TIME:
                    p["fall"] += 900 * dt
                    p["y"] += p["fall"] * dt
                    if p is self.ground:
                        self.ground = None
                        self.coyote = COYOTE
        for s in self.springs:
            if s["t"] > 0:
                s["t"] = max(0.0, s["t"] - dt)

    def _step_player(self, dt, left, right):
        self.invuln = max(0.0, self.invuln - dt)
        self.buffer = max(0.0, self.buffer - dt)
        self.drop_timer = max(0.0, self.drop_timer - dt)
        if self.drop_timer <= 0:
            self.drop_plat = None
        if self.squash > 0:
            self.squash = max(0.0, self.squash - dt * 5)
        elif self.squash < 0:
            self.squash = min(0.0, self.squash + dt * 5)

        # running
        move = (1 if right else 0) - (1 if left else 0)
        if move:
            self.face = move
        on_ground = self.ground is not None
        if move:
            rate = RUN_EASE if on_ground else AIR_EASE
        else:
            rate = STOP_EASE if on_ground else AIR_DRIFT
        # ease the speed towards where the stick points (smooth start / stop)
        self.vx += (move * RUN_SPEED - self.vx) * (1 - math.exp(-rate * dt))
        if self.ground is not None and abs(self.vx) > 20:
            self.run_t += dt * abs(self.vx) / 40.0

        # jumping
        if self.ground is not None:
            self.coyote = COYOTE
        else:
            self.coyote = max(0.0, self.coyote - dt)
        if self.buffer > 0 and self.coyote > 0:
            self.buffer = 0.0
            self.coyote = 0.0
            self.ground = None
            self.vy = -JUMP_V - 0.12 * abs(self.vx)      # a running jump goes a bit higher
            self.jumping = True
            self.squash = -1.0

        # gravity (lighter while rising and holding jump)
        if self.ground is None:
            g = GRAVITY
            if self.vy < 0 and self.jumping and self.jump_held:
                g = JUMP_GRAVITY
            if self.vy < 0 and self.jumping and not self.jump_held:
                g = GRAVITY * 1.45                           # let go = short hop
            self.vy = min(MAX_FALL, self.vy + g * dt)
            if self.vy >= 0:
                self.jumping = False

        # move
        if self.ground is not None:
            self.x += self.ground["dx"]
        self.x += self.vx * dt
        if self.x < 0:
            self.x, self.vx = 0.0, max(0.0, self.vx)
        elif self.x > SW - PW:
            self.x, self.vx = float(SW - PW), min(0.0, self.vx)

        prev_bottom = self.y + PH
        if self.ground is None:
            self.y += self.vy * dt
            self._land(prev_bottom)
        else:
            g = self.ground
            self.y = g["y"] - PH
            if not (self.x + PW > g["x"] + 4 and self.x < g["x"] + g["w"] - 4):
                self.ground = None                           # walked off the edge
                self.vy = 0.0

        self._touch_things()
        self._camera(dt)

        h = FLOOR_Y - (self.y + PH)
        if h > self.max_h:
            self.max_h = h
            zone = 1 + self.meters // ZONE_M
            if zone > self.zone:
                self.zone = zone
                self.bonus += 100 * (zone - 1)
                self.banner = ("ZONE %d" % zone, 2.2)

        if self.y > self.cam_y + SH + 10:                   # fell off the screen
            self.hearts = 0
            self._die(fell=True)

    def _land(self, prev_bottom):
        if self.vy < 0:
            return
        bottom = self.y + PH
        best = None
        for p in self.plats:
            if p is self.drop_plat or p["fall"] > 0:
                continue
            top = p["y"]
            if prev_bottom <= top + 1 and bottom >= top and \
                    self.x + PW > p["x"] + 3 and self.x < p["x"] + p["w"] - 3:
                if best is None or top < best["y"]:
                    best = p
        if best is None:
            return
        p = best
        self.y = p["y"] - PH
        self.squash = min(1.0, 0.3 + self.vy / 1000.0)
        self.vy = 0.0
        self.jumping = False
        self.ground = p
        self.powered = False
        if p["kind"] == "crumble" and p["crumble"] < 0:
            p["crumble"] = 0.0
        # spring?
        for s in self.springs:
            if s["p"] is p:
                sx = p["x"] + s["off"]
                if self.x + PW > sx + 2 and self.x < sx + 30 - 2:
                    s["t"] = 0.3
                    self.ground = None
                    self.vy = -SPRING_V
                    self.jumping = False
                    self.powered = True
                    self.squash = -1.0
                    self.effects.append([sx + 15, p["y"], 0.0, 0.35, (120, 255, 200)])
                    break

    def _touch_things(self):
        # enemies
        for e in self.enemies:
            if e["dead"] > 0:
                continue
            ew, eh = (WALKER_W, WALKER_H) if e["k"] == "walker" else (FLYER_W, FLYER_H)
            if not _overlap(self.x + 3, self.y, PW - 6, PH, e["x"], e["y"], ew, eh):
                continue
            feet = self.y + PH
            if self.powered:                        # spring power: smash it, keep flying
                e["dead"] = 0.01
                self.stomps += 1
                self.effects.append([e["x"] + ew / 2, e["y"] + eh / 2, 0.0, 0.4,
                                     (120, 255, 200)])
                self.popups.append([e["x"] + ew / 2, e["y"] - 6,
                                    "+%d" % STOMP_POINTS, 0.0])
            elif self.vy > 0 and feet - self.vy * (1 / 60.0) <= e["y"] + eh * 0.6:
                e["dead"] = 0.01
                self.stomps += 1
                self.vy = -STOMP_V if not self.jump_held else -STOMP_V * 1.25
                self.jumping = self.jump_held
                self.ground = None
                self.effects.append([e["x"] + ew / 2, e["y"] + eh / 2, 0.0, 0.35,
                                     (255, 120, 220)])
                self.popups.append([e["x"] + ew / 2, e["y"] - 6,
                                    "+%d" % STOMP_POINTS, 0.0])
            elif self.invuln <= 0:
                self._hurt(e["x"] + ew / 2)

    def _hurt(self, from_x):
        self.hearts -= 1
        if self.hearts <= 0:
            self._die()
            return
        self.invuln = INVULN_TIME
        self.vy = -520.0
        self.vx = 280.0 if self.x + PW / 2 > from_x else -280.0
        self.ground = None
        self.jumping = False
        self.powered = False
        self.effects.append([self.x + PW / 2, self.y + PH / 2, 0.0, 0.4, (255, 80, 80)])

    def _die(self, fell=False):
        if self.dead:
            return
        self.dead = True
        self.dead_timer = 0.0
        self.ground = None
        self.vx = 0.0
        self.vy = 0.0 if fell else -650.0
        self.fell = fell

    def _step_dead(self, dt):
        self.dead_timer += dt
        if not self.fell:
            self.vy = min(MAX_FALL, self.vy + GRAVITY * dt)
            self.y += self.vy * dt
        if self.dead_timer >= (0.7 if self.fell else 1.4):
            self.game_over = True

    def _camera(self, dt):
        self.cam_y -= self.scroll_speed() * dt
        target = self.y - SH * CAMERA_LEAD
        if target < self.cam_y:
            # follow up smoothly (fast enough for springs)
            self.cam_y += (target - self.cam_y) * (1 - math.exp(-CAMERA_EASE * dt))
        self._follow_leader(dt)

    def _follow_leader(self, dt):
        """Multiplayer: the screen never stays below the highest player's."""
        if self.leader_cam is not None and self.leader_cam < self.cam_y:
            self.cam_y += (self.leader_cam - self.cam_y) * (1 - math.exp(-LEADER_EASE * dt))

    # ------------------------------------------------------------------
    # Multiplayer
    # ------------------------------------------------------------------
    def set_leader_cam(self, cam):
        self.leader_cam = cam

    def snapshot(self):
        """Small dict sent to the host (and from there to the other players)."""
        return {"x": round(self.x, 1), "y": round(self.y, 1), "c": round(self.cam_y, 1),
                "f": self.face, "w": 1 if self.powered else 0,
                "d": 1 if self.dead else 0, "m": self.meters, "h": max(0, self.hearts),
                "g": 1 if self.ground is not None else 0}

    def advance_world(self, dt_ms, cam):
        """Spectator (host) view: move the world, no player, camera at `cam`."""
        dt = min(0.1, dt_ms / 1000.0)
        self.time += dt
        self._move_world(dt)
        if cam is not None and cam < self.cam_y:
            self.cam_y += (cam - self.cam_y) * (1 - math.exp(-CAMERA_EASE * dt))
        self._update_effects(dt)
        self._generate()
        self._cleanup()

    def _update_effects(self, dt):
        for e in self.enemies:
            e["t"] += dt
            if e["dead"] > 0:
                e["dead"] += dt
                continue
            if e["k"] == "walker":
                p = e["p"]
                e["x"] += e["dir"] * e["speed"] * dt
                if e["x"] < p["x"]:
                    e["x"], e["dir"] = p["x"], 1
                elif e["x"] > p["x"] + p["w"] - WALKER_W:
                    e["x"], e["dir"] = p["x"] + p["w"] - WALKER_W, -1
                e["y"] = p["y"] - WALKER_H
            else:
                e["x"] += e["dir"] * e["speed"] * dt
                if e["x"] < 4:
                    e["x"], e["dir"] = 4.0, 1
                elif e["x"] > SW - 4 - FLYER_W:
                    e["x"], e["dir"] = float(SW - 4 - FLYER_W), -1
                e["y"] = e["base"] + 26 * math.sin(e["t"] * 2.4)
        for fx in self.effects:
            fx[2] += dt
        self.effects = [fx for fx in self.effects if fx[2] < fx[3]]
        for pu in self.popups:
            pu[3] += dt
            pu[1] -= 50 * dt
        self.popups = [pu for pu in self.popups if pu[3] < 0.8]
