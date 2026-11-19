"""
Space Shooter - game logic (no pygame in here, so it can be tested anywhere).

Controls (see main.py): LEFT/RIGHT move, BUTTON2 shoots (hold = keep firing),
BUTTON1 opens the menu - the same buttons as in Tetris.

Multiplayer: every enemy you kill that appeared on your own screen is sent to
another random player. Enemies that were sent to you do not get passed on again.

Upgrades: every few kills three big boxes fly in. Shoot one of them to pick
that upgrade - it lasts for the whole run and upgrades stack.
"""
import math
import random

SW, SH = 540, 960                 # playfield size (same as the screen)
PLAYER_W, PLAYER_H = 48, 40
HIT_W, HIT_H = 30, 28             # smaller hit box = fairer
PLAYER_Y = SH - 130
PLAYER_SPEED = 400.0              # px per second
START_LIVES = 3
INVULN_TIME = 2.0                 # seconds of protection after being hit
MAX_ENEMIES = 40
MAX_ENEMY_BULLETS = 80

BASE_COOL = 0.26                  # seconds between shots without upgrades
BULLET_SPEED = 720.0

# Upgrade boxes
FIRST_UPGRADE_KILLS = 8           # kills needed for the first choice
UPGRADE_KILLS_STEP = 3            # each next choice needs this many more kills
BOX_W, BOX_H = 150, 140
BOX_Y = 260                       # where the boxes stop and wait
BOX_XS = (90, 270, 450)
BOX_ARM_TIME = 0.5                # boxes can't be hit right after arriving
AFTER_PICK_PAUSE = 1.2            # calm moment before enemies come again

UPGRADES = {
    # key: name (two lines on the box), short description, max level
    "bullets": {"name": ("MORE", "BULLETS"), "desc": "+1 BULLET",   "max": 6},
    "damage":  {"name": ("MORE", "DAMAGE"),  "desc": "+1 DAMAGE",   "max": 8},
    "rate":    {"name": ("FIRE", "RATE"),    "desc": "SHOOT FASTER", "max": 6},
    "pierce":  {"name": ("PIERCE", ""),      "desc": "GO THROUGH +1", "max": 4},
    "homing":  {"name": ("HOMING", ""),      "desc": "BULLETS STEER", "max": 3},
    "size":    {"name": ("BIG", "BULLETS"),  "desc": "BIGGER SHOTS", "max": 4},
    "speed":   {"name": ("SHIP", "SPEED"),   "desc": "MOVE FASTER", "max": 4},
    "shield":  {"name": ("SHIELD", ""),      "desc": "BLOCKS 1 HIT", "max": 3},
    "life":    {"name": ("EXTRA", "LIFE"),   "desc": "+1 LIFE",     "max": 5},
}
UPGRADE_KINDS = tuple(UPGRADES)
ENEMY_CODE = {"drone": 0, "fighter": 1, "tank": 2}
ENEMIES = {
    "drone":   {"hp": 1, "w": 38, "h": 34, "speed": 140.0, "points": 10,
                "fire": None},
    "fighter": {"hp": 2, "w": 46, "h": 40, "speed": 110.0, "points": 25,
                "fire": (1.3, 2.4)},
    "tank":    {"hp": 7, "w": 70, "h": 56, "speed": 62.0,  "points": 60,
                "fire": (1.5, 2.6)},
}
ENEMY_KINDS = tuple(ENEMIES)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _overlap(ax, ay, aw, ah, bx, by, bw, bh):
    """Axis aligned boxes given by centre and size."""
    return abs(ax - bx) * 2 < aw + bw and abs(ay - by) * 2 < ah + bh


class Shooter:
    def __init__(self, seed=None, multiplayer=False):
        self.rng = random.Random(seed)
        self.mp = multiplayer
        self.x = SW / 2.0
        self.lives = START_LIVES
        self.score = 0
        self.kills = 0
        self.elapsed = 0.0
        self.game_over = False
        self.invuln = 1.0                 # short grace period at the start
        self.cool = 0.0
        self.spawn_timer = 1.0
        self.ups = {k: 0 for k in UPGRADE_KINDS}   # upgrade levels for this run
        self.shield = 0                   # shield charges ready right now
        self.shield_timer = 0.0           # recharge timer for the shield
        self.upgrades_taken = 0
        self.next_upgrade = FIRST_UPGRADE_KILLS    # kill count for the next choice
        self.last_upgrade = 0                      # kill count of the previous one
        self.boxes = []                   # the 3 upgrade boxes while choosing
        self.calm = 0.0                   # no spawning while > 0
        self.banner = None                # (text, time left) after a choice
        self.bullets = []                 # player bullets
        self.ebullets = []                # enemy bullets
        self.enemies = []
        self.effects = []                 # [x, y, age, max_age, colour]
        self.incoming = []                # (kind, fx) sent by other players
        self.incoming_timer = 0.0
        self.kills_unsent = []            # (kind, fx) to tell the host
        self.stars = [[self.rng.uniform(0, SW), self.rng.uniform(0, SH),
                       self.rng.uniform(30, 170)] for _ in range(60)]

    @property
    def wave(self):
        return 1 + int(self.elapsed // 20)

    @property
    def choosing(self):
        """True while the upgrade boxes are on screen."""
        return bool(self.boxes)

    @property
    def upgrade_progress(self):
        """0..1 - how close the next upgrade choice is."""
        need = self.next_upgrade - self.last_upgrade
        if self.choosing:
            return 1.0
        return _clamp((self.kills - self.last_upgrade) / float(need), 0.0, 1.0)

    # ------------------------------------------------------------------
    # Upgrade stats
    # ------------------------------------------------------------------
    def cooldown(self):
        return BASE_COOL * (0.82 ** self.ups["rate"])

    def ship_speed(self):
        return PLAYER_SPEED * (1 + 0.15 * self.ups["speed"])

    def bullet_damage(self):
        return 1 + self.ups["damage"]

    def bullet_count(self):
        return 1 + self.ups["bullets"]

    def available_upgrades(self):
        out = []
        for k in UPGRADE_KINDS:
            if k == "life":
                if self.lives < START_LIVES + UPGRADES["life"]["max"]:
                    out.append(k)
            elif self.ups[k] < UPGRADES[k]["max"]:
                out.append(k)
        return out

    def _offer_upgrades(self):
        kinds = self.available_upgrades()
        if not kinds:
            return
        picks = self.rng.sample(kinds, min(3, len(kinds)))
        xs = BOX_XS if len(picks) == 3 else (
            (160, 380) if len(picks) == 2 else (270,))
        for i, k in enumerate(picks):
            self.boxes.append({"k": k, "x": float(xs[i]),
                               "y": -BOX_H - i * 40.0, "arm": BOX_ARM_TIME})

    def _choose(self, box):
        k = box["k"]
        if k == "life":
            self.lives += 1
        else:
            self.ups[k] += 1
            if k == "shield":
                self.shield = self.ups["shield"]
        self.upgrades_taken += 1
        self.effects.append([box["x"], box["y"], 0.0, 0.6, (120, 255, 160)])
        for other in self.boxes:
            if other is not box:
                self.effects.append([other["x"], other["y"], 0.0, 0.3, (90, 90, 140)])
        self.boxes = []
        self.bullets = []
        self.banner = (UPGRADES[k]["desc"], 1.8)
        self.calm = AFTER_PICK_PAUSE
        self.last_upgrade = self.kills
        self.next_upgrade = (self.kills + FIRST_UPGRADE_KILLS
                             + UPGRADE_KILLS_STEP * self.upgrades_taken)

    # ------------------------------------------------------------------
    # Multiplayer helpers
    # ------------------------------------------------------------------
    def queue_enemy(self, kind, fx):
        """An enemy killed by another player is coming to us."""
        if kind in ENEMIES and len(self.incoming) < 30:
            try:
                fx = _clamp(float(fx), 0.0, 1.0)
            except (TypeError, ValueError):
                fx = self.rng.random()
            self.incoming.append((kind, fx))

    def snapshot(self):
        """Small dict describing the whole screen, for the host's spectator view."""
        return {
            "x": int(self.x),
            "v": 1 if self.invuln > 0 else 0,
            "l": self.lives,
            "e": [[ENEMY_CODE[e["k"]], int(e["x"]), int(e["y"]),
                   0 if e["native"] else 1] for e in self.enemies[:MAX_ENEMIES]],
            "b": [[int(b["x"]), int(b["y"]), 1 if b["w"] > 7 else 0]
                  for b in self.bullets[:60]],
            "q": [[int(q["x"]), int(q["y"])] for q in self.ebullets[:60]],
            "o": [[int(o["x"]), int(o["y"]), UPGRADE_KINDS.index(o["k"])]
                  for o in self.boxes[:3]],
        }

    # ------------------------------------------------------------------
    # Main step
    # ------------------------------------------------------------------
    def update(self, dt_ms, left, right, fire):
        dt = dt_ms / 1000.0
        for s in self.stars:                       # stars keep scrolling
            s[1] += s[2] * dt
            if s[1] > SH:
                s[1] -= SH
                s[0] = self.rng.uniform(0, SW)
        self._update_effects(dt)
        if self.game_over:
            return
        if not self.choosing:
            self.elapsed += dt            # difficulty doesn't grow while choosing
        self.calm = max(0.0, self.calm - dt)
        if self.banner:
            self.banner = (self.banner[0], self.banner[1] - dt)
            if self.banner[1] <= 0:
                self.banner = None

        move = (1 if right else 0) - (1 if left else 0)
        self.x = _clamp(self.x + move * self.ship_speed() * dt,
                        PLAYER_W / 2, SW - PLAYER_W / 2)
        self.invuln = max(0.0, self.invuln - dt)
        if self.shield < self.ups["shield"]:        # shield recharges slowly
            self.shield_timer += dt
            if self.shield_timer >= 15.0:
                self.shield_timer = 0.0
                self.shield += 1

        self.cool = max(0.0, self.cool - dt)
        if fire and self.cool <= 0:
            self._shoot()
            self.cool = self.cooldown()

        if (not self.choosing and self.kills >= self.next_upgrade):
            self._offer_upgrades()

        self._spawn(dt)
        self._move_bullets(dt)
        self._move_enemies(dt)
        self._move_ebullets(dt)
        self._move_boxes(dt)
        self._collisions()

    # ------------------------------------------------------------------
    # Shooting
    # ------------------------------------------------------------------
    def _bullet(self, x, y, vx, vy):
        grow = 1 + 0.45 * self.ups["size"]
        self.bullets.append({"x": x, "y": y, "vx": vx, "vy": vy,
                             "dmg": self.bullet_damage(),
                             "w": 5 * grow, "h": 16 * grow,
                             "pierce": self.ups["pierce"],   # extra enemies it may go through
                             "homing": self.ups["homing"], "hit": set()})

    def _shoot(self):
        x, y = self.x, PLAYER_Y - PLAYER_H / 2
        n = self.bullet_count()
        for i in range(n):
            off = i - (n - 1) / 2.0                  # e.g. -1, 0, 1
            if n <= 2:                               # 1-2 bullets: side by side
                self._bullet(x + off * 14, y, 0, -BULLET_SPEED)
            else:                                    # 3+: a fan that gets wider
                rad = math.radians(off * min(9.0, 30.0 / (n - 1)) * 1.6)
                self._bullet(x + off * 6, y, math.sin(rad) * BULLET_SPEED,
                             -math.cos(rad) * BULLET_SPEED)

    def _move_bullets(self, dt):
        alive = []
        for b in self.bullets:
            if b["homing"] and not self.choosing:    # don't steer into the boxes
                target = None
                best = 1e12
                for e in self.enemies:
                    if e["y"] > 0 and e["y"] < b["y"] + 40 and id(e) not in b["hit"]:
                        d = (e["x"] - b["x"]) ** 2 + (e["y"] - b["y"]) ** 2
                        if d < best:
                            best, target = d, e
                if target is not None:
                    dx, dy = target["x"] - b["x"], target["y"] - b["y"]
                    dist = math.hypot(dx, dy) or 1.0
                    turn = 900 * b["homing"]
                    b["vx"] += dx / dist * turn * dt
                    b["vy"] += dy / dist * turn * dt
                sp = math.hypot(b["vx"], b["vy"]) or 1.0
                b["vx"] *= BULLET_SPEED / sp
                b["vy"] *= BULLET_SPEED / sp
            b["x"] += b["vx"] * dt
            b["y"] += b["vy"] * dt
            if -90 < b["y"] < SH + 40 and -40 < b["x"] < SW + 40:
                alive.append(b)
        self.bullets = alive

    # ------------------------------------------------------------------
    # Enemies
    # ------------------------------------------------------------------
    def _pick_kind(self):
        t = self.elapsed
        w_tank = min(0.14, max(0.0, (t - 25) / 400.0))
        w_fighter = min(0.38, max(0.0, (t - 8) / 160.0))
        r = self.rng.random()
        if r < w_tank:
            return "tank"
        if r < w_tank + w_fighter:
            return "fighter"
        return "drone"

    def _spawn(self, dt):
        if self.choosing or self.calm > 0:           # quiet while picking an upgrade
            return
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.spawn_timer = (max(0.40, 1.15 - self.elapsed / 120.0)
                                * self.rng.uniform(0.8, 1.2))
            if len(self.enemies) < MAX_ENEMIES:
                self._spawn_enemy(self._pick_kind(), None, True)
        if self.incoming:
            self.incoming_timer -= dt
            if self.incoming_timer <= 0 and len(self.enemies) < MAX_ENEMIES:
                kind, fx = self.incoming.pop(0)
                self.incoming_timer = 0.3          # sent enemies arrive one by one
                self._spawn_enemy(kind, fx, False)

    def _spawn_enemy(self, kind, fx, native):
        spec = ENEMIES[kind]
        if fx is None:
            fx = self.rng.random()
        x = 40 + fx * (SW - 80)
        speed = spec["speed"] * (1 + min(0.8, self.elapsed / 200.0))
        fire = spec["fire"]
        # enemies get tougher over time so the upgrades stay useful
        hp = max(1, int(round(spec["hp"] * (1 + self.elapsed / 150.0))))
        self.enemies.append({
            "k": kind, "x": x, "bx": x, "y": -spec["h"],
            "hp": hp, "max": hp, "t": 0.0, "speed": speed,
            "fire": self.rng.uniform(*fire) if fire else None,
            "native": native,
            "phase": self.rng.uniform(0, 6.28),
            "drift": self.rng.uniform(-35, 35),
        })

    def _move_enemies(self, dt):
        alive = []
        for e in self.enemies:
            spec = ENEMIES[e["k"]]
            e["t"] += dt
            e["y"] += e["speed"] * dt
            if e["k"] == "drone":
                e["x"] = _clamp(e["bx"] + math.sin(e["t"] * 2.2 + e["phase"]) * 55,
                                22, SW - 22)
            elif e["k"] == "fighter":
                e["x"] = _clamp(e["bx"] + e["drift"] * e["t"], 26, SW - 26)
            if e["fire"] is not None and 10 < e["y"] < SH * 0.72:
                e["fire"] -= dt
                if e["fire"] <= 0:
                    e["fire"] = self.rng.uniform(*spec["fire"])
                    self._enemy_fire(e)
            if e["y"] < SH + 70:
                alive.append(e)
        self.enemies = alive

    def _enemy_fire(self, e):
        if len(self.ebullets) > MAX_ENEMY_BULLETS:
            return
        if e["k"] == "fighter":
            dx, dy = self.x - e["x"], PLAYER_Y - e["y"]
            dist = math.hypot(dx, dy) or 1.0
            self.ebullets.append({"x": e["x"], "y": e["y"] + 20,
                                  "vx": dx / dist * 270, "vy": dy / dist * 270})
        else:  # tank: three bullets
            for ang in (-18, 0, 18):
                rad = math.radians(ang)
                self.ebullets.append({"x": e["x"], "y": e["y"] + 26,
                                      "vx": math.sin(rad) * 250,
                                      "vy": math.cos(rad) * 250})

    def _move_ebullets(self, dt):
        alive = []
        for q in self.ebullets:
            q["x"] += q["vx"] * dt
            q["y"] += q["vy"] * dt
            if -20 < q["x"] < SW + 20 and q["y"] < SH + 20:
                alive.append(q)
        self.ebullets = alive

    def _move_boxes(self, dt):
        for o in self.boxes:
            if o["y"] < BOX_Y:                       # fly in, then wait
                o["y"] = min(BOX_Y, o["y"] + 520 * dt)
            else:
                o["arm"] = max(0.0, o["arm"] - dt)

    # ------------------------------------------------------------------
    # Collisions
    # ------------------------------------------------------------------
    def _collisions(self):
        # player bullets -> enemies
        remaining = []
        for b in self.bullets:
            used = False
            for e in self.enemies:
                if e["hp"] <= 0 or id(e) in b["hit"]:
                    continue
                spec = ENEMIES[e["k"]]
                if _overlap(b["x"], b["y"], b["w"], b["h"],
                            e["x"], e["y"], spec["w"], spec["h"]):
                    e["hp"] -= b["dmg"]
                    b["hit"].add(id(e))
                    if b["pierce"] > 0:
                        b["pierce"] -= 1
                    else:
                        used = True
                    if e["hp"] <= 0:
                        self._kill(e)
                    if used:
                        break
            if not used:
                remaining.append(b)
        self.bullets = remaining
        self.enemies = [e for e in self.enemies if e["hp"] > 0]

        # player bullets -> upgrade boxes (the first box hit is the choice)
        if self.boxes:
            for b in self.bullets:
                hit = None
                for o in self.boxes:
                    if o["y"] >= BOX_Y and o["arm"] <= 0 and _overlap(
                            b["x"], b["y"], b["w"], b["h"], o["x"], o["y"], BOX_W, BOX_H):
                        hit = o
                        break
                if hit is not None:
                    self._choose(hit)
                    break

        if self.invuln <= 0:
            # enemy bullets -> player
            for q in self.ebullets:
                if _overlap(q["x"], q["y"], 8, 8, self.x, PLAYER_Y, HIT_W, HIT_H):
                    self._hit_player()
                    break
        if self.invuln <= 0:
            # enemy bodies -> player (the enemy is destroyed too, no points)
            for e in self.enemies:
                spec = ENEMIES[e["k"]]
                if _overlap(e["x"], e["y"], spec["w"] - 6, spec["h"] - 6,
                            self.x, PLAYER_Y, HIT_W, HIT_H):
                    e["hp"] = 0
                    self.effects.append([e["x"], e["y"], 0.0, 0.4, (255, 150, 60)])
                    self._hit_player()
                    break
            self.enemies = [e for e in self.enemies if e["hp"] > 0]

    def _kill(self, e):
        spec = ENEMIES[e["k"]]
        self.score += spec["points"]
        self.kills += 1
        self.effects.append([e["x"], e["y"], 0.0, 0.45, (255, 200, 80)])
        if self.mp and e["native"]:
            fx = _clamp((e["x"] - 40) / float(SW - 80), 0.0, 1.0)
            self.kills_unsent.append((e["k"], fx))

    def _hit_player(self):
        self.ebullets = []
        if self.shield > 0:                          # shield takes the hit
            self.shield -= 1
            self.shield_timer = 0.0
            self.invuln = 1.0
            self.effects.append([self.x, PLAYER_Y, 0.0, 0.5, (120, 200, 255)])
            return
        self.lives -= 1
        self.invuln = INVULN_TIME
        self.effects.append([self.x, PLAYER_Y, 0.0, 0.6, (255, 90, 90)])
        if self.lives <= 0:
            self.game_over = True

    def _update_effects(self, dt):
        alive = []
        for fx in self.effects:
            fx[2] += dt
            if fx[2] < fx[3]:
                alive.append(fx)
        self.effects = alive[-40:]
