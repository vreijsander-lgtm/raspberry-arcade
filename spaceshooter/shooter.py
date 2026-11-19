"""
Space Shooter - game logic (no pygame in here, so it can be tested anywhere).

Controls (see main.py): LEFT/RIGHT move, BUTTON2 shoots (hold = keep firing),
BUTTON1 opens the menu - the same buttons as in Tetris.

Multiplayer: every enemy you kill that appeared on your own screen is sent to
another random player. Enemies that were sent to you do not get passed on again.

Upgrades: after every wave the screen is cleared and three big boxes fly in.
Shooting is locked for a moment, then you get one plain bullet per shot (your
extra bullets come back after the choice). Shoot one box to pick that upgrade -
it lasts for the whole run and upgrades stack.

Rare upgrades: sometimes a box is a gold RARE one (much more often after a
boss). Rare upgrades are strong, one of a kind and change how you play.

Coins: every killed enemy has a small chance to drop a coin that flies to you
by itself. While choosing, shoot the little reroll cube (far left) to spend a
coin and get three new upgrades to pick from.

Bosses: every 5th wave (5, 10, 15...) is a boss fight instead of normal enemies.
Beat it to get two upgrade picks in a row. Enemies (and bosses) get more HP
every wave - see hp_scale().

Special enemies (they show up from later waves on): splitters break into two
minis, divers stop, aim and dash at you, rocks can't be destroyed (dodge them;
they block your shots) and curse eyes have an aura - inside it you can't shoot.
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

WAVE_TIME = 20.0                  # seconds per wave

# Enemy HP grows every wave: hp = base hp * hp_scale(wave).
# Gentle at the start, faster later on (you get an upgrade every wave).
HP_LINEAR = 0.06
HP_QUAD = 0.022

# Boss (after every BOSS_EVERY waves)
BOSS_EVERY = 5
BOSS_PICKS = 2                    # free upgrade picks for beating it
BOSS_W, BOSS_H = 190, 110
BOSS_Y = 190                      # where it stops and fights
BOSS_HP = 75                      # times hp_scale(wave), +50% per boss number
BOSS_POINTS = 300                 # times the boss number
BOSS_COINS = 3

# Upgrade boxes (offered after every wave)
PICK_DELAY = 2.0                  # seconds you can't shoot after the boxes appear
BOX_W, BOX_H = 150, 140
BOX_Y = 260                       # where the boxes stop and wait
BOX_XS = (90, 270, 450)
BOX_ARM_TIME = 0.5                # boxes can't be hit right after arriving
AFTER_PICK_PAUSE = 1.2            # calm moment before enemies come again
RARE_CHANCE = 0.045               # chance that a box is a rare upgrade
BOSS_RARE_CHANCE = 0.40           # ... in the boxes after beating a boss

# Coins and rerolling
COIN_CHANCE = 0.10                # chance that a killed enemy drops a coin
COIN_R = 9                        # coin radius (for drawing)
REROLL_COST = 1
REROLL_X, REROLL_Y = 40, 480      # the little reroll cube (far left, under the boxes)
REROLL_SIZE = 56
REROLL_ARM = 0.4                  # new boxes can't be hit right after a reroll

# Special enemies and rare upgrades
CURSE_R = 160                     # curse aura radius: no shooting inside it
HALO_R = 120                      # holy halo: burns enemies this close
HALO_DPS = 1.5                    # times your bullet damage, per second
BEAM_CHARGE = 0.7                 # mega laser: seconds of holding fire to charge
BEAM_TIME = 0.5                   # how long the beam lasts
BEAM_POWER = 3.0                  # beam damage compared to normal shooting
BOOM_R = 70                       # boom shots: explosion radius
BOOM_DMG = 0.5                    # explosion damage (times the bullet damage)
SLOW_ENEMY = 0.85                 # slow time: enemy speed factor
SLOW_SHOTS = 0.65                 # slow time: enemy bullet speed factor
WING_OFFSET = 52                  # wingman distance from the ship

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
    # rare ones: one of each per run
    "laser":   {"name": ("MEGA", "LASER"),   "desc": "HOLD TO CHARGE A BEAM", "max": 1, "rare": True},
    "wingman": {"name": ("WING", "MAN"),     "desc": "A HELPER SHIP",  "max": 1, "rare": True},
    "phase":   {"name": ("PHASE", "SHOTS"),  "desc": "SHOTS GO THROUGH ALL", "max": 1, "rare": True},
    "boom":    {"name": ("BOOM", "SHOTS"),   "desc": "EXPLODING SHOTS", "max": 1, "rare": True},
    "halo":    {"name": ("HOLY", "HALO"),    "desc": "BURN AURA + NO CURSE", "max": 1, "rare": True},
    "phoenix": {"name": ("PHOENIX", ""),     "desc": "REVIVE ONCE",    "max": 1, "rare": True},
    "slow":    {"name": ("SLOW", "TIME"),    "desc": "SLOWER ENEMIES", "max": 1, "rare": True},
}
UPGRADE_KINDS = tuple(UPGRADES)
NORMAL_KINDS = tuple(k for k in UPGRADE_KINDS if not UPGRADES[k].get("rare"))
RARE_KINDS = tuple(k for k in UPGRADE_KINDS if UPGRADES[k].get("rare"))

ENEMIES = {
    "drone":    {"hp": 1, "w": 38, "h": 34, "speed": 140.0, "points": 10, "fire": None},
    "fighter":  {"hp": 2, "w": 46, "h": 40, "speed": 110.0, "points": 25, "fire": (1.3, 2.4)},
    "tank":     {"hp": 7, "w": 70, "h": 56, "speed": 62.0,  "points": 60, "fire": (1.5, 2.6)},
    "splitter": {"hp": 3, "w": 46, "h": 42, "speed": 95.0,  "points": 30, "fire": None},
    "mini":     {"hp": 1, "w": 24, "h": 22, "speed": 175.0, "points": 5,  "fire": None},
    "diver":    {"hp": 2, "w": 40, "h": 46, "speed": 120.0, "points": 35, "fire": None},
    "rock":     {"hp": 1, "w": 64, "h": 60, "speed": 115.0, "points": 0,  "fire": None,
                 "solid": True},                    # can't be destroyed
    "curse":    {"hp": 5, "w": 52, "h": 52, "speed": 50.0,  "points": 60, "fire": None},
}
ENEMY_KINDS = tuple(ENEMIES)
ENEMY_CODE = {k: i for i, k in enumerate(ENEMY_KINDS)}   # drone=0 ... curse=7

# special enemies: (kind, first wave, extra chance per wave, max chance)
SPECIALS = (("splitter", 3, 0.03, 0.10),
            ("diver", 4, 0.025, 0.10),
            ("rock", 6, 0.015, 0.06),
            ("curse", 7, 0.01, 0.04))


def hp_scale(wave):
    """How much tougher enemies are on this wave (1.0 on wave 1)."""
    w = max(0, wave - 1)
    return 1.0 + HP_LINEAR * w + HP_QUAD * w * w


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _overlap(ax, ay, aw, ah, bx, by, bw, bh):
    """Axis aligned boxes given by centre and size."""
    return abs(ax - bx) * 2 < aw + bw and abs(ay - by) * 2 < ah + bh


def _solid(e):
    return ENEMIES[e["k"]].get("solid", False)


MODES = ("CLASSIC", "BOSS RUSH", "ONE LIFE")


class Shooter:
    def __init__(self, seed=None, multiplayer=False, mode="CLASSIC"):
        self.rng = random.Random(seed)
        self.mp = multiplayer
        self.mode = mode if mode in MODES else "CLASSIC"
        # BOSS RUSH: a boss every wave. ONE LIFE: 1 life, no extra lives, double points
        self.boss_every = 1 if self.mode == "BOSS RUSH" else BOSS_EVERY
        self.score_mult = 2 if self.mode == "ONE LIFE" else 1
        self.x = SW / 2.0
        self.lives = 1 if self.mode == "ONE LIFE" else START_LIVES
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
        self.offered_wave = 1             # last wave that got its upgrade choice
        self.pick_lock = 0.0              # no shooting while > 0 (choice just opened)
        self.coins = 0                    # coins collected (spent on rerolls)
        self.coin_drops = []              # coins flying to the player
        self.rerolls = 0
        self.picks_left = 0               # upgrade picks left in this choice
        self.picks_total = 0              # picks in this choice (2 after a boss)
        self.boss = None                  # the boss while it is alive
        self.bosses_beaten = 0
        self.boss_wave = 0                # last wave that was a boss wave
        self.cursed = False               # inside a curse aura: can't shoot
        self.beam_charge = 0.0            # mega laser charge (seconds)
        self.beam_time = 0.0              # > 0 while the beam is firing
        self.wing_x = self.x + WING_OFFSET
        self.wing_cool = 0.0
        self.phoenix_used = False
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
        if self.mode == "BOSS RUSH":             # a head start: 3 free upgrades
            for _ in range(3):
                kinds = [k for k in self.available_upgrades() if k != "life"]
                k = self.rng.choice(kinds)
                self.ups[k] += 1
                if k == "shield":
                    self.shield = self.ups["shield"]
            self.invuln = 3.0

    @property
    def wave(self):
        return 1 + int(self.elapsed // WAVE_TIME)

    @property
    def choosing(self):
        """True while the upgrade boxes are on screen."""
        return bool(self.boxes)

    @property
    def upgrade_progress(self):
        """0..1 - how far the current wave is (the choice comes at the end)."""
        if self.choosing or self.boss:
            return 1.0
        return _clamp((self.elapsed % WAVE_TIME) / WAVE_TIME, 0.0, 1.0)

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
        if self.choosing:                 # only one bullet while picking a box
            return 1
        return 1 + self.ups["bullets"]

    def beam_active(self):
        return self.beam_time > 0

    def beam_charge_time(self):
        return BEAM_CHARGE * (0.88 ** self.ups["rate"])

    def beam_width(self):
        return 22 * (1 + 0.35 * self.ups["size"]) + 8 * self.ups["bullets"]

    def beam_dps(self):
        return (BEAM_POWER * self.bullet_damage() * (1 + 0.6 * self.ups["bullets"])
                / BASE_COOL * (1.1 ** self.ups["rate"]))

    def available_upgrades(self):
        """Normal upgrades that aren't maxed out yet."""
        out = []
        for k in NORMAL_KINDS:
            if k == "life":
                if self.mode != "ONE LIFE" and self.lives < START_LIVES + UPGRADES["life"]["max"]:
                    out.append(k)
            elif self.ups[k] < UPGRADES[k]["max"]:
                out.append(k)
        return out

    def available_rares(self):
        return [k for k in RARE_KINDS if self.ups[k] == 0]

    def _rare_chance(self):
        return BOSS_RARE_CHANCE if self.picks_total > 1 else RARE_CHANCE

    def _pick_box_kinds(self, n, exclude=()):
        """n different upgrades for the boxes; each box may be a rare one."""
        normal = [k for k in self.available_upgrades() if k not in exclude]
        rares = [k for k in self.available_rares() if k not in exclude]
        chance = self._rare_chance()
        picks = []
        for _ in range(n):
            if rares and (self.rng.random() < chance or not normal):
                k = self.rng.choice(rares)
                rares.remove(k)
            elif normal:
                k = self.rng.choice(normal)
                normal.remove(k)
            else:
                break
            picks.append(k)
        return picks

    def can_reroll(self):
        """True if the reroll cube works right now (choosing, enough coins and
        there are other upgrades left to show)."""
        return (self.choosing and self.coins >= REROLL_COST
                and len(self.available_upgrades()) + len(self.available_rares())
                > len(self.boxes))

    def _reroll(self):
        old = [o["k"] for o in self.boxes]
        # prefer upgrades that weren't on screen, fill up with old ones if needed
        picks = self._pick_box_kinds(len(self.boxes), exclude=old)
        rest = [k for k in old]
        self.rng.shuffle(rest)
        picks += rest[:len(self.boxes) - len(picks)]
        self.rng.shuffle(picks)
        for o, k in zip(self.boxes, picks):
            o["k"] = k
            o["arm"] = REROLL_ARM
            self.effects.append([o["x"], o["y"], 0.0, 0.35, (255, 205, 60)])
        self.coins -= REROLL_COST
        self.rerolls += 1
        self.bullets = []
        self.effects.append([REROLL_X, REROLL_Y, 0.0, 0.4, (255, 205, 60)])

    def _clear_screen(self):
        for e in self.enemies:
            self.effects.append([e["x"], e["y"], 0.0, 0.35, (90, 90, 140)])
        self.enemies = []
        self.ebullets = []

    def _offer_upgrades(self):
        picks = self._pick_box_kinds(3)
        if not picks:
            self.picks_left = 0
            return
        # clear the screen: enemies vanish (no points), all shots disappear
        self._clear_screen()
        self.bullets = []
        self.beam_time = self.beam_charge = 0.0
        self.pick_lock = PICK_DELAY
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
            if k == "wingman":
                self.wing_x = self.x
        self.upgrades_taken += 1
        rare = UPGRADES[k].get("rare")
        self.effects.append([box["x"], box["y"], 0.0, 0.6,
                             (255, 215, 80) if rare else (120, 255, 160)])
        for other in self.boxes:
            if other is not box:
                self.effects.append([other["x"], other["y"], 0.0, 0.3, (90, 90, 140)])
        self.boxes = []
        self.bullets = []
        self.banner = (UPGRADES[k]["desc"], 2.4 if rare else 1.8)
        self.calm = AFTER_PICK_PAUSE
        self.picks_left = max(0, self.picks_left - 1)
        if self.picks_left > 0:                   # boss reward: pick again
            self._offer_upgrades()

    # ------------------------------------------------------------------
    # Boss
    # ------------------------------------------------------------------
    def _start_boss(self, wave):
        n = self.bosses_beaten + 1
        self._clear_screen()
        hp = int(round(BOSS_HP * hp_scale(wave) * (1 + 0.5 * (n - 1))))
        if self.mode == "BOSS RUSH":              # one after another: a bit less tough
            hp = int(hp * 0.6)
        self.boss = {"x": SW / 2.0, "y": -BOSS_H, "hp": hp, "max": hp, "n": n,
                     "t": 0.0, "fire": 2.2, "pattern": 0, "burst": 0,
                     "flash": 0.0}
        self.banner = ("BOSS %d!" % n, 2.0)

    def _move_boss(self, dt):
        b = self.boss
        if not b:
            return
        b["flash"] = max(0.0, b["flash"] - dt)
        if b["y"] < BOSS_Y:                        # fly in
            b["y"] = min(BOSS_Y, b["y"] + 160 * dt)
            return
        b["t"] += dt
        n = b["n"]
        b["x"] = SW / 2.0 + math.sin(b["t"] * (0.55 + 0.05 * n)) * 150
        b["fire"] -= dt
        if b["fire"] > 0:
            return
        if b["burst"] > 0:                         # quick aimed shots
            b["burst"] -= 1
            self._boss_aimed(b, 0, 300 + 15 * n)
            b["fire"] = 0.16
            return
        pattern = b["pattern"] % (3 if n >= 2 else 2)
        b["pattern"] += 1
        if pattern == 0:                           # aimed fan
            for ang in (-24, -12, 0, 12, 24):
                self._boss_aimed(b, ang, 250 + 12 * n)
        elif pattern == 1:                         # ring with a gap
            count = 12 + 2 * n
            rot = self.rng.uniform(0, 360)
            for i in range(count):
                if i in (0, 1):                    # the gap to slip through
                    continue
                rad = math.radians(rot + i * 360.0 / count)
                self.ebullets.append({"x": b["x"], "y": b["y"] + 20,
                                      "vx": math.cos(rad) * 190,
                                      "vy": math.sin(rad) * 190})
        else:                                      # burst of aimed shots
            b["burst"] = 2 + min(3, n)
        b["fire"] = max(0.9, 1.9 - 0.15 * (n - 1))

    def _boss_aimed(self, b, ang, speed):
        dx, dy = self.x - b["x"], PLAYER_Y - (b["y"] + 40)
        base = math.atan2(dy, dx) + math.radians(ang)
        self.ebullets.append({"x": b["x"], "y": b["y"] + 40,
                              "vx": math.cos(base) * speed, "vy": math.sin(base) * speed})

    def _damage_boss(self, amount):
        bo = self.boss
        if not bo or bo["hp"] <= 0:
            return
        bo["hp"] -= amount
        bo["flash"] = 0.06
        if bo["hp"] <= 0:
            self._kill_boss()

    def _kill_boss(self):
        b = self.boss
        self.boss = None
        self.bosses_beaten += 1
        self.score += BOSS_POINTS * b["n"] * self.score_mult
        self.kills += 1
        self.ebullets = []
        self.bullets = []
        self.beam_time = 0.0
        for i in range(8):
            self.effects.append([b["x"] + self.rng.uniform(-80, 80),
                                 b["y"] + self.rng.uniform(-45, 45),
                                 -0.06 * i, 0.6, (255, 200, 80)])
        for i in range(BOSS_COINS):
            self.coin_drops.append({"x": b["x"], "y": b["y"], "t": -0.1 * i,
                                    "vx": self.rng.uniform(-160, 160), "vy": -300.0})
        # the boss was the whole wave: go straight on to the next wave
        # (the 2 boss picks replace the normal pick at the end of this wave)
        self.elapsed = self.boss_wave * WAVE_TIME
        self.offered_wave = self.boss_wave + 1
        self.picks_left = self.picks_total = BOSS_PICKS
        self._offer_upgrades()
        self.banner = ("BOSS DEFEATED!", 2.0)

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
            "z": ([int(self.boss["x"]), int(self.boss["y"]),
                   int(100 * self.boss["hp"] / self.boss["max"])]
                  if self.boss else None),
            "lz": int(self.beam_width()) if self.beam_active() else 0,
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
        if not self.choosing and not self.boss:
            self.elapsed += dt            # waves pause while choosing / boss
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

        self.pick_lock = max(0.0, self.pick_lock - dt)
        if not self.choosing and not self.boss:
            if self.wave > self.offered_wave:
                self.offered_wave = self.wave      # end of a wave: pick an upgrade
                self.picks_left = self.picks_total = 1
                self._offer_upgrades()
            elif self.wave % self.boss_every == 0 and self.boss_wave < self.wave:
                self.boss_wave = self.wave         # wave 5, 10, 15...: boss fight
                self._start_boss(self.wave)

        # curse aura: no shooting while inside one (the holy halo protects you)
        self.cursed = (not self.ups["halo"] and any(
            e["k"] == "curse" and math.hypot(e["x"] - self.x, e["y"] - PLAYER_Y) < CURSE_R
            for e in self.enemies))
        can_fire = fire and self.pick_lock <= 0 and not self.cursed

        self.cool = max(0.0, self.cool - dt)
        if self.ups["laser"] and not self.choosing:
            self._update_beam(dt, can_fire)
        elif can_fire and self.cool <= 0:
            self._shoot()
            self.cool = self.cooldown()
        self._update_wingman(dt, can_fire)
        if self.ups["halo"]:
            self._halo_burn(dt)

        self._spawn(dt)
        self._move_bullets(dt)
        self._move_enemies(dt)
        self._move_boss(dt)
        self._move_ebullets(dt)
        self._move_boxes(dt)
        self._move_coins(dt)
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
                             "phase": bool(self.ups["phase"]) and not self.choosing,
                             "boom": bool(self.ups["boom"]),
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

    def _update_beam(self, dt, firing):
        """Mega laser: hold fire to charge, then a beam fires by itself."""
        if self.beam_time > 0:
            self.beam_time = max(0.0, self.beam_time - dt)
            self._beam_damage(dt)
            return
        if firing:
            self.beam_charge += dt
            if self.beam_charge >= self.beam_charge_time():
                self.beam_charge = 0.0
                self.beam_time = BEAM_TIME
        else:
            self.beam_charge = max(0.0, self.beam_charge - dt * 2)

    def _beam_damage(self, dt):
        half = self.beam_width() / 2
        dmg = self.beam_dps() * dt
        for e in self.enemies:
            spec = ENEMIES[e["k"]]
            if (not _solid(e) and e["y"] < PLAYER_Y and e["y"] > -spec["h"]
                    and abs(e["x"] - self.x) < half + spec["w"] / 2):
                self._damage(e, dmg)
        self.enemies = [e for e in self.enemies if e["hp"] > 0]
        bo = self.boss
        if bo and abs(bo["x"] - self.x) < half + BOSS_W / 2 and bo["y"] > 0:
            self._damage_boss(dmg)

    def _update_wingman(self, dt, firing):
        if not self.ups["wingman"]:
            return
        side = WING_OFFSET if self.x < SW - 90 else -WING_OFFSET
        self.wing_x += (self.x + side - self.wing_x) * min(1.0, 8 * dt)
        self.wing_cool = max(0.0, self.wing_cool - dt)
        if firing and self.wing_cool <= 0 and not self.choosing:
            self._bullet(self.wing_x, PLAYER_Y - 6, 0, -BULLET_SPEED)
            self.wing_cool = self.cooldown()

    def _halo_burn(self, dt):
        dmg = HALO_DPS * self.bullet_damage() * dt
        for e in self.enemies:
            if not _solid(e) and math.hypot(e["x"] - self.x, e["y"] - PLAYER_Y) < HALO_R:
                self._damage(e, dmg)
        self.enemies = [e for e in self.enemies if e["hp"] > 0]

    def _move_bullets(self, dt):
        alive = []
        for b in self.bullets:
            if b["homing"] and not self.choosing:    # don't steer into the boxes
                target = None
                best = 1e12
                for e in self.enemies + ([self.boss] if self.boss else []):
                    if (e["y"] > 0 and e["y"] < b["y"] + 40 and id(e) not in b["hit"]
                            and not ("k" in e and _solid(e))):
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
        w = self.wave
        r = self.rng.random()
        acc = 0.0
        for kind, first, step, cap in SPECIALS:
            p = min(cap, max(0.0, (w - first + 1) * step))
            if r < acc + p:
                if kind == "curse" and any(e["k"] == "curse" for e in self.enemies):
                    break                          # only one curse eye at a time
                return kind
            acc += p
        t = self.elapsed
        # more fighters/tanks over time; full mix around wave 8-9
        w_tank = min(0.14, max(0.0, (t - 35) / 900.0))
        w_fighter = min(0.38, max(0.0, (t - 15) / 350.0))
        r = self.rng.random()
        if r < w_tank:
            return "tank"
        if r < w_tank + w_fighter:
            return "fighter"
        return "drone"

    def _spawn(self, dt):
        if self.choosing or self.boss or self.calm > 0:   # quiet while picking / boss
            return
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            # spawns speed up slowly; full speed around wave 10
            self.spawn_timer = (max(0.40, 1.15 - self.elapsed / 240.0)
                                * self.rng.uniform(0.8, 1.2))
            if len(self.enemies) < MAX_ENEMIES:
                self._spawn_enemy(self._pick_kind(), None, True)
        if self.incoming:
            self.incoming_timer -= dt
            if self.incoming_timer <= 0 and len(self.enemies) < MAX_ENEMIES:
                kind, fx = self.incoming.pop(0)
                self.incoming_timer = 0.3          # sent enemies arrive one by one
                self._spawn_enemy(kind, fx, False)

    def _spawn_enemy(self, kind, fx, native, x=None, y=None, vx=0.0):
        spec = ENEMIES[kind]
        if x is None:
            if fx is None:
                fx = self.rng.random()
            x = 40 + fx * (SW - 80)
        speed = spec["speed"] * (1 + min(0.8, self.elapsed / 300.0))
        fire = spec["fire"]
        # enemies get tougher every wave so the upgrades stay useful
        hp = 1 if spec.get("solid") else max(1, int(round(spec["hp"] * hp_scale(self.wave))))
        e = {
            "k": kind, "x": x, "bx": x, "y": -spec["h"] if y is None else y,
            "hp": hp, "max": hp, "t": 0.0, "speed": speed,
            "fire": self.rng.uniform(*fire) if fire else None,
            "native": native,
            "phase": self.rng.uniform(0, 6.28),
            "drift": self.rng.uniform(-35, 35),
            "vx": vx,
        }
        if kind == "diver":
            e["mode"] = "down"
            e["stop"] = self.rng.uniform(220, 420)  # where it stops to aim
            e["aim"] = 0.0
        self.enemies.append(e)
        return e

    def _move_enemies(self, dt):
        alive = []
        slow = SLOW_ENEMY if self.ups["slow"] else 1.0
        for e in self.enemies:
            spec = ENEMIES[e["k"]]
            k = e["k"]
            e["t"] += dt
            edt = dt * slow
            if k == "diver":
                self._move_diver(e, edt)
            else:
                e["y"] += e["speed"] * edt
            if k == "drone":
                e["x"] = _clamp(e["bx"] + math.sin(e["t"] * 2.2 + e["phase"]) * 55,
                                22, SW - 22)
            elif k == "fighter":
                e["x"] = _clamp(e["bx"] + e["drift"] * e["t"], 26, SW - 26)
            elif k == "mini":
                e["x"] = _clamp(e["x"] + e["vx"] * edt, 14, SW - 14)
            elif k == "rock":
                e["x"] = _clamp(e["x"] + e["drift"] * 0.5 * edt, 34, SW - 34)
            elif k == "curse":                     # slowly follows you
                step = 45.0 * edt
                e["x"] += _clamp(self.x - e["x"], -step, step)
            if e["fire"] is not None and 10 < e["y"] < SH * 0.72:
                e["fire"] -= dt
                if e["fire"] <= 0:
                    e["fire"] = self.rng.uniform(*spec["fire"])
                    self._enemy_fire(e)
            if e["y"] < SH + 70 and -90 < e["x"] < SW + 90 and e["y"] > -200:
                alive.append(e)
        self.enemies = alive

    def _move_diver(self, e, dt):
        """Falls in, stops, aims at you (blinking) and then dashes."""
        if e["mode"] == "down":
            e["y"] += e["speed"] * dt
            if e["y"] >= e["stop"]:
                e["mode"] = "aim"
                e["aim"] = 0.7
        elif e["mode"] == "aim":
            e["aim"] -= dt
            if e["aim"] <= 0:
                dx, dy = self.x - e["x"], PLAYER_Y - e["y"]
                dist = math.hypot(dx, dy) or 1.0
                e["vx"], e["vy"] = dx / dist * 560, dy / dist * 560
                e["mode"] = "dash"
        else:
            e["x"] += e["vx"] * dt
            e["y"] += e["vy"] * dt

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
        if self.ups["slow"]:
            dt *= SLOW_SHOTS
        for q in self.ebullets:
            q["x"] += q["vx"] * dt
            q["y"] += q["vy"] * dt
            if -20 < q["x"] < SW + 20 and q["y"] < SH + 20:
                alive.append(q)
        self.ebullets = alive

    def _move_coins(self, dt):
        """Coins pop up a little, then fly to the ship faster and faster."""
        alive = []
        for c in self.coin_drops:
            c["t"] += dt
            dx, dy = self.x - c["x"], PLAYER_Y - c["y"]
            dist = math.hypot(dx, dy) or 1.0
            if c["t"] > 0.25:                      # short pop, then home in
                speed = min(1400.0, 300.0 + 1200.0 * (c["t"] - 0.25))
                c["vx"], c["vy"] = dx / dist * speed, dy / dist * speed
            else:
                c["vy"] += 900.0 * dt              # the pop slows down
            step = math.hypot(c["vx"], c["vy"]) * dt
            if dist <= max(22.0, step):            # reached the ship
                self.coins += 1
                self.effects.append([self.x, PLAYER_Y, 0.0, 0.3, (255, 205, 60)])
                continue
            c["x"] += c["vx"] * dt
            c["y"] += c["vy"] * dt
            alive.append(c)
        self.coin_drops = alive

    def _move_boxes(self, dt):
        for o in self.boxes:
            if o["y"] < BOX_Y:                       # fly in, then wait
                o["y"] = min(BOX_Y, o["y"] + 520 * dt)
            else:
                o["arm"] = max(0.0, o["arm"] - dt)

    # ------------------------------------------------------------------
    # Collisions
    # ------------------------------------------------------------------
    def _damage(self, e, amount):
        """Hurt an enemy; kills it (once) when its HP runs out."""
        if _solid(e) or e["hp"] <= 0:
            return
        e["hp"] -= amount
        if e["hp"] <= 0:
            self._kill(e)

    def _explode(self, x, y, dmg, skip):
        self.effects.append([x, y, 0.0, 0.3, (255, 140, 40)])
        for e in self.enemies:
            if e is not skip and math.hypot(e["x"] - x, e["y"] - y) < BOOM_R:
                self._damage(e, dmg * BOOM_DMG)

    def _collisions(self):
        # player bullets -> enemies
        remaining = []
        for b in self.bullets:
            used = False
            for e in self.enemies:
                if e["hp"] <= 0 or id(e) in b["hit"]:
                    continue
                spec = ENEMIES[e["k"]]
                if not _overlap(b["x"], b["y"], b["w"], b["h"],
                                e["x"], e["y"], spec["w"], spec["h"]):
                    continue
                b["hit"].add(id(e))
                if _solid(e):                       # rocks block shots
                    if not b["phase"]:
                        self.effects.append([b["x"], b["y"], 0.0, 0.15, (150, 150, 160)])
                        used = True
                        break
                    continue
                self._damage(e, b["dmg"])
                if b["boom"]:
                    self._explode(e["x"], e["y"], b["dmg"], e)
                if b["phase"]:
                    continue                        # goes through everything
                if b["pierce"] > 0:
                    b["pierce"] -= 1
                else:
                    used = True
                    break
            if not used:
                remaining.append(b)
        self.bullets = remaining
        self.enemies = [e for e in self.enemies if e["hp"] > 0]

        # player bullets -> boss
        if self.boss:
            bo = self.boss
            remaining = []
            for b in self.bullets:
                if (bo["hp"] > 0 and id(bo) not in b["hit"] and _overlap(
                        b["x"], b["y"], b["w"], b["h"], bo["x"], bo["y"], BOSS_W, BOSS_H)):
                    b["hit"].add(id(bo))
                    if b["boom"]:
                        self.effects.append([b["x"], b["y"], 0.0, 0.3, (255, 140, 40)])
                    if b["phase"] or b["pierce"] > 0:
                        if not b["phase"]:
                            b["pierce"] -= 1
                        remaining.append(b)
                    self._damage_boss(b["dmg"] * (1.5 if b["boom"] else 1))
                    if not self.boss:               # it died
                        remaining = []
                        break
                else:
                    remaining.append(b)
            self.bullets = remaining

        # player bullets -> reroll cube (only works with enough coins)
        if self.boxes and self.can_reroll():
            for b in self.bullets:
                if _overlap(b["x"], b["y"], b["w"], b["h"],
                            REROLL_X, REROLL_Y, REROLL_SIZE, REROLL_SIZE):
                    self._reroll()
                    break

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
            # enemy bodies -> player (the enemy is destroyed too, no points;
            # rocks stay - they can't be destroyed)
            for e in self.enemies:
                spec = ENEMIES[e["k"]]
                if _overlap(e["x"], e["y"], spec["w"] - 6, spec["h"] - 6,
                            self.x, PLAYER_Y, HIT_W, HIT_H):
                    if not _solid(e):
                        e["hp"] = 0
                    self.effects.append([e["x"], e["y"], 0.0, 0.4, (255, 150, 60)])
                    self._hit_player()
                    break
            self.enemies = [e for e in self.enemies if e["hp"] > 0]

    def _kill(self, e):
        spec = ENEMIES[e["k"]]
        self.score += spec["points"] * self.score_mult
        self.kills += 1
        self.effects.append([e["x"], e["y"], 0.0, 0.45, (255, 200, 80)])
        if self.rng.random() < COIN_CHANCE:
            self.coin_drops.append({"x": e["x"], "y": e["y"], "t": 0.0,
                                    "vx": self.rng.uniform(-80, 80), "vy": -260.0})
        if e["k"] == "splitter":                    # breaks into two minis
            for side in (-1, 1):
                if len(self.enemies) < MAX_ENEMIES + 4:
                    self._spawn_enemy("mini", None, e["native"],
                                      x=e["x"] + side * 14, y=e["y"], vx=side * 90.0)
        if self.mp and e["native"] and e["k"] != "mini":
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
            if self.ups["phoenix"] and not self.phoenix_used:
                self.phoenix_used = True             # rise again, once
                self.lives = 1
                self.invuln = 3.0
                if not self.boss:
                    self._clear_screen()
                self.banner = ("PHOENIX!", 2.0)
                for i in range(6):
                    self.effects.append([self.x, PLAYER_Y, -0.08 * i, 0.7, (255, 150, 40)])
                return
            self.game_over = True

    def _update_effects(self, dt):
        alive = []
        for fx in self.effects:
            fx[2] += dt
            if fx[2] < fx[3]:
                alive.append(fx)
        self.effects = alive[-40:]
