"""
Glowbug - game logic (no pygame in here, so it can be tested anywhere).

A maze game for the tall screen. You are a glowbug: eat every speck of
light in the neon maze while four spiders hunt you. Eat a SPARK (the big
pulsing lights) and for a few seconds the spiders are scared of you: catch
them and they curl up into a web ball and roll back to their nest.

Controls (see main.py) - the same six buttons as the other games:
    UP / DOWN / LEFT / RIGHT   move (press a turn a bit early: it is remembered
                               until the next crossing)
    BUTTON2                    FLASH - a burst of light that stuns the spiders
                               close to you for a moment. You get a flash for
                               every 60 lights you eat (max 3).
    BUTTON1                    menu

The spiders each hunt in their own way:
    VIOLA   (violet)  goes straight for you
    EMBER   (red)     tries to cut you off a few tiles ahead
    TEAL    (teal)    guards the sparks you are near, chases you up close
    AMBER   (amber)   follows the trail you leave behind
Every level the maze changes colour, the spiders get faster and the scare
time gets shorter. 3 lives, an extra one at 10000 points.

Multiplayer (GlowRace): up to 4 bugs in the same maze, 5 rounds. Every
pickup counts (light 1, spark 2, spider 3, gem 5); most pickups in total
wins. Caught by a spider = out for a moment. Your FLASH also dazzles the
other bugs close to you.
"""
import math
import random
from collections import deque

# Mazes: half rows (the middle column is the last character), mirrored to
# 17 columns. # wall, . light, o spark, ' ' empty floor, X nothing,
# - nest door, N nest. The row with open ends is a tunnel to the other side.
_MAZES = [
    [
        "#########",
        "#o......#",
        "#.##.##.#",
        "#........",
        "#.##.#.##",
        "#....#...",
        "####.###.",
        "XXX#.#...",
        "####.###-",
        "    .##NN",
        "####.####",
        "XXX#.....",
        "####.#.##",
        "#.......#",
        "#.##.##.#",
        "#o.#.....",
        "##.#.#.##",
        "#....#...",
        "#.######.",
        "#........",
        "#########",
    ],
    [
        "#########",
        "#........",
        "#.###.###",
        "#o#.....#",
        "#.#.###.#",
        "#........",
        "###.#.###",
        "XX#.#....",
        "###.#.##-",
        "    ..#NN",
        "###.#.###",
        "XX#.#....",
        "###.#.#.#",
        "#.....#..",
        "#.###...#",
        "#o..#.#..",
        "###.#.#.#",
        "#.......#",
        "#.###.###",
        "#........",
        "#########",
    ],
]
MAZES = [[h + h[:8][::-1] for h in m] for m in _MAZES]
COLS, ROWS = 17, 21

PLAYER_START = (8, 15)
NEST_EXIT = (8, 7)              # the tile just above the nest door
NEST_HOME = [(8, 7), (7, 9), (8, 9), (9, 9)]   # where each spider starts
NEST_CENTER = (8, 9)
GEM_TILE = (8, 11)
TUNNEL_ROW = 9

DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
SPIDERS = ("VIOLA", "EMBER", "TEAL", "AMBER")

START_LIVES = 3
EXTRA_LIFE = 10000
FLASH_EVERY = 60                # lights eaten per flash charge
MAX_FLASH = 3
FLASH_RADIUS = 4.0              # tiles
STUN_TIME = 2.2
DEATH_TIME = 1.7
READY_TIME = 1.8
CLEAR_TIME = 2.2
CATCH_DIST = 0.6


def _is_center(v):
    return abs(v - round(v)) < 1e-6


def _wrap_dist(a, b):
    dx = abs(a.x - b.x)
    return min(dx, COLS - dx) + abs(a.y - b.y)


class Actor:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.dir = (0, 0)
        self.walk = 0.0                     # for the leg / wing animation

    @property
    def tile(self):
        return (int(round(self.x)) % COLS, int(round(self.y)))


class Bug(Actor):
    """A player's glowbug."""

    def __init__(self, x, y, idx=0, name=""):
        super().__init__(x, y)
        self.idx = idx                      # player number (colour)
        self.name = name
        self.want = None                    # the turn asked for
        self.facing = (-1, 0)
        self.trail = deque(maxlen=14)       # tiles it was on (AMBER follows these)
        self.flash = 1
        self.lights = 0                     # lights eaten (flash charges)
        self.picks = 0                      # race: pickups this round
        self.total = 0                      # race: pickups in all rounds
        self.out_t = 0.0                    # race: caught, back in a moment
        self.freeze = 0.0                   # race: dazzled by someone's flash
        self.safe = 0.0                     # race: just came back, spiders can't catch it

    def active(self):
        return self.out_t <= 0


class Spider(Actor):
    def __init__(self, idx, x, y):
        super().__init__(x, y)
        self.idx = idx
        self.name = SPIDERS[idx]
        self.state = "home"                 # home, leave, chase, web
        self.scared = False
        self.stun = 0.0
        self.release = 0.0                  # seconds until it leaves the nest
        self.bob = random.random() * 6


MODES = ("CLASSIC", "FRENZY")
FRENZY_SPEED = 1.75              # FRENZY: the whole game runs this much faster


class Glowbug:
    """Single player: lives, levels and a score.
    FRENZY: the whole game runs much faster, the spiders even more,
    and they all come out of the nest at once."""
    race = False
    mode = "CLASSIC"

    def __init__(self, seed=None, mode="CLASSIC"):
        self.rng = random.Random(seed)
        self.mode = mode if mode in MODES else "CLASSIC"
        self.score = 0
        self.level = 1
        self.lives = START_LIVES
        self.next_life = EXTRA_LIFE
        self.game_over = False
        self.effects = []                   # [kind, x, y, age, max_age]
        self.popups = []                    # [text, x, y, age]
        self.bug = None
        self.start_level()

    @property
    def flash(self):
        return self.bug.flash

    @flash.setter
    def flash(self, value):
        self.bug.flash = value

    def bugs(self):
        return [self.bug]

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    def new_maze(self, maze_no):
        self.maze_no = maze_no
        self.grid = [list(r) for r in MAZES[maze_no]]
        self.lights_left = sum(r.count(".") + r.count("o") for r in self.grid)
        self.eaten = 0
        self.gem = None                      # [x, y, time left, kind]
        self.gems_given = 0
        self._dist_cache = {}

    def start_level(self):
        self.new_maze((self.level - 1) % len(MAZES))
        self.reset_actors()

    def reset_spiders(self):
        self.spiders = [Spider(i, *NEST_HOME[i]) for i in range(4)]
        quick = max(0.35, 1.0 - 0.12 * (self.level - 1))
        if self.mode == "FRENZY":
            quick *= 0.15
        for s, wait in zip(self.spiders, (0.0, 1.5, 5.0, 9.0)):
            s.release = wait * quick
            if s.idx == 0:
                s.state = "chase"
                s.dir = (-1, 0)
        self.scare_t = 0.0
        self.chain = 0                       # spiders caught during one scare

    def reset_actors(self):
        old = self.bug
        self.bug = Bug(*PLAYER_START)
        if old is not None:
            self.bug.flash, self.bug.lights = old.flash, old.lights
        self.reset_spiders()
        self.phase = "ready"
        self.phase_t = 0.0

    # ------------------------------------------------------------------
    # the maze
    # ------------------------------------------------------------------
    def cell(self, x, y):
        if y < 0 or y >= ROWS:
            return "X"
        return self.grid[y][x % COLS]

    def open_for(self, x, y, spider=None):
        c = self.cell(x, y)
        if c in ".o ":
            return True
        if spider is not None and c in "-N":
            return spider.state in ("home", "leave", "web")
        return False

    def tunnel(self, x, y):
        return y == TUNNEL_ROW and (x % COLS <= 3 or x % COLS >= COLS - 4)

    def dist_map(self, target, nest=True):
        """Steps from every tile to `target` (spiders can use the nest)."""
        key = (target, nest)
        d = self._dist_cache.get(key)
        if d is not None:
            return d
        d = {target: 0}
        q = deque([target])
        ok = ".o -N" if nest else ".o "
        while q:
            x, y = q.popleft()
            for dx, dy in DIRS.values():
                n = ((x + dx) % COLS, y + dy)
                if n not in d and self.cell(*n) in ok:
                    d[n] = d[(x, y)] + 1
                    q.append(n)
        self._dist_cache[key] = d
        return d

    # ------------------------------------------------------------------
    # speeds (tiles per second)
    # ------------------------------------------------------------------
    def bug_speed(self):
        return min(9.0, 7.2 + 0.25 * (self.level - 1))

    def spider_speed(self, s):
        if s.state == "web":
            return 13.0
        if s.state in ("home", "leave"):
            return 4.0
        tx, ty = s.tile
        if self.tunnel(tx, ty):
            return 3.6
        if s.scared:
            return 4.2
        fast = 1.25 if self.mode == "FRENZY" else 1.0
        return min(8.6, 6.3 + 0.3 * (self.level - 1)) * fast

    def scare_time(self):
        return max(1.8, 7.0 - 0.6 * (self.level - 1))

    # ------------------------------------------------------------------
    # moving along the grid
    # ------------------------------------------------------------------
    def advance(self, a, dist, choose):
        """Move actor a `dist` tiles; choose(a) picks a direction at every
        tile centre (it may set a.dir to (0, 0) = stop)."""
        guard = 0
        while dist > 1e-9 and guard < 8:
            guard += 1
            if _is_center(a.x) and _is_center(a.y):
                a.x, a.y = float(round(a.x)), float(round(a.y))
                choose(a)
            dx, dy = a.dir
            if dx == 0 and dy == 0:
                return
            cur = a.x if dx else a.y
            step = dx or dy
            nxt = (math.floor(cur) + 1 if step > 0 else math.ceil(cur) - 1) \
                if not _is_center(cur) else round(cur) + step
            to_go = abs(nxt - cur)
            if dist < to_go:
                if dx:
                    a.x += dx * dist
                else:
                    a.y += dy * dist
                a.walk += dist
                return
            if dx:
                a.x = float(nxt)
            else:
                a.y = float(nxt)
            a.walk += to_go
            dist -= to_go
            if a.x < -0.5:
                a.x += COLS
            elif a.x > COLS - 0.5:
                a.x -= COLS
            a.x = float(round(a.x)) if _is_center(a.x) else a.x
            if dist <= 1e-9:
                choose(a)                    # stop right at a wall

    def choose_bug(self, a):
        x, y = int(round(a.x)) % COLS, int(round(a.y))
        if a.want and self.open_for(x + a.want[0], y + a.want[1]):
            a.dir = a.want
        elif a.dir != (0, 0) and not self.open_for(x + a.dir[0], y + a.dir[1]):
            a.dir = (0, 0)
        if a.dir != (0, 0):
            a.facing = a.dir

    def prey(self, s):
        """The bug spider s is after."""
        return self.bug

    def spider_target(self, s):
        b = self.prey(s)
        bx, by = b.tile
        if s.state == "leave":
            return NEST_EXIT
        if s.state == "web":
            return NEST_CENTER
        if s.idx == 0:                                        # straight at you
            return (bx, by)
        if s.idx == 1:                                        # a few tiles ahead
            fx, fy = b.facing
            tx, ty = bx, by
            for _ in range(4):
                if self.open_for(tx + fx, ty + fy):
                    tx, ty = (tx + fx) % COLS, ty + fy
                else:
                    break
            return (tx, ty)
        if s.idx == 2:                                        # guards the sparks
            near = self.dist_map((bx, by), nest=False)
            sparks = [(x, y) for y in range(ROWS) for x in range(COLS) if self.grid[y][x] == "o"]
            if near.get(s.tile, 99) <= 6 or not sparks:
                return (bx, by)
            return min(sparks, key=lambda p: near.get(p, 99))
        if b.trail:                                           # your trail
            return b.trail[0]
        return (bx, by)

    def choose_spider(self, s):
        x, y = int(round(s.x)) % COLS, int(round(s.y))
        if s.state == "leave" and (x, y) == NEST_EXIT:
            s.state = "chase"
        if s.state == "web" and (x, y) == NEST_CENTER:
            s.state = "leave"
            s.scared = False
        back = (-s.dir[0], -s.dir[1])
        options = [d for d in DIRS.values()
                   if self.open_for(x + d[0], y + d[1], s) and d != back]
        if not options:
            options = [back] if self.open_for(x + back[0], y + back[1], s) else []
        if not options:
            s.dir = (0, 0)
            return
        if len(options) == 1:
            s.dir = options[0]
            return
        if s.scared and s.state == "chase":                   # run away from the bug
            far = self.dist_map(self.prey(s).tile)
            self.rng.shuffle(options)
            s.dir = max(options, key=lambda d: far.get(((x + d[0]) % COLS, y + d[1]), 0)
                        + self.rng.random() * 3)
            return
        wobble = max(0.04, 0.2 - 0.03 * self.level)
        if s.state == "chase" and self.rng.random() < wobble:
            s.dir = self.rng.choice(options)
            return
        dm = self.dist_map(self.spider_target(s))
        s.dir = min(options, key=lambda d: (dm.get(((x + d[0]) % COLS, y + d[1]), 999),
                                            self.rng.random()))

    # ------------------------------------------------------------------
    # input
    # ------------------------------------------------------------------
    def press(self, action, bug=None):
        bug = bug or self.bug
        if action in DIRS:
            d = DIRS[action]
            bug.want = d
            if d == (-bug.dir[0], -bug.dir[1]) and d != (0, 0):
                bug.dir = d                                   # turn around any time
                bug.facing = d
        elif action == "button2":
            self.use_flash(bug)

    def use_flash(self, bug):
        if bug.flash <= 0 or self.phase != "play":
            return
        bug.flash -= 1
        self.effects.append(["flash", bug.x, bug.y, 0.0, 0.5])
        for s in self.spiders:
            if s.state == "chase" and math.hypot(s.x - bug.x, s.y - bug.y) <= FLASH_RADIUS:
                s.stun = STUN_TIME
        for other in self.bugs():                             # race: dazzles the others too
            if other is not bug and other.active() and \
                    math.hypot(other.x - bug.x, other.y - bug.y) <= FLASH_RADIUS:
                other.freeze = FREEZE_TIME

    @staticmethod
    def held_want(bug, held):
        """A direction that is held keeps being wanted (so holding works too)."""
        held_dirs = [a for a in ("up", "down", "left", "right") if a in held]
        if held_dirs and (bug.want is None or not any(DIRS[a] == bug.want for a in held_dirs)):
            bug.want = DIRS[held_dirs[-1]]

    # ------------------------------------------------------------------
    # the frame
    # ------------------------------------------------------------------
    def tick_common(self, dt_ms):
        dt = min(dt_ms, 50) / 1000.0
        if self.mode == "FRENZY":
            dt *= FRENZY_SPEED
        self._dist_cache = {}
        for e in self.effects:
            e[3] += dt
        self.effects = [e for e in self.effects if e[3] < e[4]]
        for p in self.popups:
            p[3] += dt
        self.popups = [p for p in self.popups if p[3] < 1.0]
        self.phase_t += dt
        return dt

    def move_bug(self, bug, dt):
        old_tile = bug.tile
        self.advance(bug, self.bug_speed() * dt, self.choose_bug)
        if bug.tile != old_tile:
            bug.trail.append(old_tile)
        self.eat(bug, *bug.tile)

    def move_world(self, dt):
        """Spiders, the scare and the gem."""
        if self.scare_t > 0:
            self.scare_t -= dt
            if self.scare_t <= 0:
                for s in self.spiders:
                    s.scared = False
        for s in self.spiders:
            if s.stun > 0:
                s.stun -= dt
                continue
            if s.state == "home":
                s.bob += dt
                s.release -= dt
                if s.release <= 0:
                    s.state = "leave"
                continue
            self.advance(s, self.spider_speed(s) * dt, self.choose_spider)
        if self.gem:
            self.gem[2] -= dt
            if self.gem[2] <= 0:
                self.gem = None

    def update(self, dt_ms, held=()):
        dt = self.tick_common(dt_ms)
        if self.phase == "ready":
            if self.phase_t >= READY_TIME:
                self.phase, self.phase_t = "play", 0.0
            return
        if self.phase == "dying":
            if self.phase_t >= DEATH_TIME:
                self.lives -= 1
                if self.lives <= 0:
                    self.game_over = True
                    self.phase_t = -999.0
                else:
                    self.reset_actors()
            return
        if self.phase == "clear":
            if self.phase_t >= CLEAR_TIME:
                self.level += 1
                self.flash = max(self.flash, 1)
                self.start_level()
            return
        self.held_want(self.bug, held)
        self.move_bug(self.bug, dt)
        self.move_world(dt)
        self.check_catch()
        if self.phase == "play" and self.lights_left <= 0:
            self.phase, self.phase_t = "clear", 0.0

    # ------------------------------------------------------------------
    # eating and catching
    # ------------------------------------------------------------------
    def eat(self, bug, x, y):
        if self.gem and (x, y) == (self.gem[0], self.gem[1]):
            self.collect(bug, "gem", x, y)
            self.effects.append(["burst", x, y, 0.0, 0.4])
            self.gem = None
        c = self.cell(x, y)
        if c not in ".o":
            return
        self.grid[y][x % COLS] = " "
        self.lights_left -= 1
        self.eaten += 1
        bug.lights += 1
        if c == ".":
            self.collect(bug, "light", x, y)
        else:
            self.collect(bug, "spark", x, y)
            self.effects.append(["burst", x, y, 0.0, 0.4])
            self.scare_t = self.scare_time()
            self.chain = 0
            for s in self.spiders:
                if s.state == "chase":
                    s.scared = True
                    s.dir = (-s.dir[0], -s.dir[1])        # they turn and flee
        every = FLASH_EVERY_RACE if self.race else FLASH_EVERY
        if bug.lights % every == 0 and bug.flash < MAX_FLASH:
            bug.flash += 1
            self.popups.append(["+FLASH", x, y, 0.0])
        if self.gems_given < 2 and self.eaten in (55, 120):
            self.gems_given += 1
            self.gem = [GEM_TILE[0], GEM_TILE[1], 9.0, self.level % 4]

    def collect(self, bug, kind, x, y):
        if kind == "light":
            self.add_score(10)
        elif kind == "spark":
            self.add_score(50)
        elif kind == "gem":
            pts = 300 + 200 * min(self.level, 8)
            self.add_score(pts)
            self.popups.append([str(pts), x, y, 0.0])
        elif kind == "spider":
            self.chain += 1
            pts = 200 * 2 ** min(3, self.chain - 1)
            self.add_score(pts)
            self.popups.append([str(pts), x, y, 0.0])

    def add_score(self, pts):
        self.score += pts
        if self.score >= self.next_life:
            self.lives += 1
            self.next_life += EXTRA_LIFE
            self.popups.append(["1UP!", self.bug.x, self.bug.y, 0.0])

    def check_catch(self):
        for b in self.bugs():
            if not b.active():
                continue
            for s in self.spiders:
                if s.state not in ("chase", "leave") or _wrap_dist(s, b) > CATCH_DIST:
                    continue
                if s.scared:
                    self.collect(b, "spider", s.x, s.y)
                    self.effects.append(["burst", s.x, s.y, 0.0, 0.4])
                    s.state = "web"
                    s.scared = False
                    s.stun = 0.0
                elif s.stun > 0 or b.safe > 0:
                    continue                                  # harmless right now
                else:
                    self.bug_caught(b)
                    if not self.race:
                        return
                    break

    def bug_caught(self, bug):
        self.phase, self.phase_t = "dying", 0.0


# ----------------------------------------------------------------------------
# Multiplayer: the light race (several bugs in one maze, 5 rounds)
# ----------------------------------------------------------------------------
RACE_ROUNDS = 5
RACE_TIME = 75.0                 # seconds per round (or until every light is gone)
RACE_SPAWNS = [(3, 19), (13, 19), (3, 3), (13, 3)]
MAX_RACERS = len(RACE_SPAWNS)
FLASH_EVERY_RACE = 30
FREEZE_TIME = 1.3                # hit by another bug's flash
OUT_TIME = 2.5                   # caught by a spider: back after this
SAFE_TIME = 1.5
ROUND_READY = 2.2
ROUND_OVER_TIME = 4.5
MATCH_OVER_TIME = 5.0
# pickups: what each thing counts for
PICKS = {"light": 1, "spark": 2, "gem": 5, "spider": 3}
ACTIONS = ("up", "down", "left", "right", "button2")
PHASES = ("ready", "play", "roundover", "matchover")
SPIDER_STATES = ("home", "leave", "chase", "web")


class GlowRace(Glowbug):
    """Everybody in the same maze; most pickups after 5 rounds wins.
    The host runs it (update with everybody's buttons) and sends snapshot()
    every frame; the players' Pis only show it (apply). me = which bug is
    yours (None = the host watching)."""
    race = True

    def __init__(self, seed=None, names=("P1", "P2"), me=None, mode="CLASSIC"):
        self.rng = random.Random(seed)
        self.me = me
        self.mode = mode if mode in MODES else "CLASSIC"     # FRENZY works here too
        self.racers = [Bug(*RACE_SPAWNS[i], idx=i, name=str(n)[:12])
                       for i, n in enumerate(list(names)[:MAX_RACERS])]
        self.bug = self.racers[0]
        self.score = 0
        self.lives = 1
        self.next_life = 10 ** 9
        self.level = 1
        self.round_no = 0
        self.timer = RACE_TIME
        self.game_over = False
        self.effects = []
        self.popups = []
        self.round_results = []          # per round: pickups of every bug
        self.next_round()

    def bugs(self):
        return self.racers

    def mine(self):
        return self.racers[self.me] if self.me is not None and self.me < len(self.racers) else None

    def next_round(self):
        self.round_no += 1
        self.level = 1 + (self.round_no - 1) // 2
        self.new_maze((self.round_no - 1) % len(MAZES))
        for b, (x, y) in zip(self.racers, RACE_SPAWNS):
            b.x, b.y = float(x), float(y)
            b.dir, b.want, b.facing = (0, 0), None, (1 if x < COLS // 2 else -1, 0)
            b.trail.clear()
            b.picks, b.lights, b.flash = 0, 0, 1
            b.out_t = b.freeze = b.safe = 0.0
        self.reset_spiders()
        self.timer = RACE_TIME
        self.phase, self.phase_t = "ready", 0.0

    def prey(self, s):
        live = [b for b in self.racers if b.active()] or self.racers
        return min(live, key=lambda b: _wrap_dist(s, b))

    def bug_speed(self):
        return 7.4

    # -- host side
    def update(self, dt_ms, inputs=()):
        """inputs: (held buttons, new presses) for every bug, in order."""
        dt = self.tick_common(dt_ms)
        if self.phase == "ready":
            if self.phase_t >= ROUND_READY:
                self.phase, self.phase_t = "play", 0.0
            return
        if self.phase == "roundover":
            if self.phase_t >= ROUND_OVER_TIME:
                if self.round_no >= RACE_ROUNDS:
                    self.phase, self.phase_t = "matchover", 0.0
                else:
                    self.next_round()
            return
        if self.phase == "matchover":
            if self.phase_t >= MATCH_OVER_TIME:
                self.game_over = True
                self.phase_t = -999.0
            return
        self.timer = max(0.0, self.timer - dt)
        inputs = list(inputs) + [((), ())] * (len(self.racers) - len(inputs))
        for b, (held, presses) in zip(self.racers, inputs):
            if b.out_t > 0:
                b.out_t -= dt
                if b.out_t <= 0:                              # back at its start
                    x, y = RACE_SPAWNS[b.idx]
                    b.x, b.y, b.dir, b.want = float(x), float(y), (0, 0), None
                    b.safe = SAFE_TIME
                continue
            b.safe = max(0.0, b.safe - dt)
            if b.freeze > 0:
                b.freeze -= dt
                continue
            for a in presses:
                if a in ACTIONS:
                    self.press(a, b)
            self.held_want(b, held)
            self.move_bug(b, dt)
        self.move_world(dt)
        self.check_catch()
        if self.lights_left <= 0 or self.timer <= 0:
            self.round_results.append([b.picks for b in self.racers])
            self.phase, self.phase_t = "roundover", 0.0

    def collect(self, bug, kind, x, y):
        n = PICKS[kind]
        bug.picks += n
        bug.total += n
        if n > 1:
            self.popups.append(["+%d" % n, x, y, 0.0])

    def bug_caught(self, bug):
        bug.out_t = OUT_TIME
        bug.freeze = 0.0
        self.effects.append(["caught", bug.x, bug.y, 0.0, 1.0])

    def standings(self):
        """Bug indexes, best first (most pickups in total)."""
        return sorted(range(len(self.racers)), key=lambda i: -self.racers[i].total)

    def winners(self):
        best = max(b.total for b in self.racers)
        return [b for b in self.racers if b.total == best]

    # -- network
    def snapshot(self):
        return {
            "ph": self.phase, "pt": round(self.phase_t, 3), "tm": round(self.timer, 2),
            "rn": self.round_no, "mz": self.maze_no, "lv": self.level,
            "g": "".join("".join(r) for r in self.grid),
            "gem": self.gem and [self.gem[0], self.gem[1], round(self.gem[2], 2), self.gem[3]],
            "sc": round(self.scare_t, 2),
            "b": [[round(b.x, 3), round(b.y, 3), list(b.dir), list(b.facing), b.flash,
                   b.picks, b.total, round(b.out_t, 2), round(b.freeze, 2), round(b.safe, 2),
                   round(b.walk, 2)] for b in self.racers],
            "s": [[round(s.x, 3), round(s.y, 3), list(s.dir), s.state, s.scared,
                   round(s.stun, 2), round(s.walk, 2), round(s.bob, 2)] for s in self.spiders],
            "fx": [[e[0], round(e[1], 2), round(e[2], 2), round(e[3], 3), e[4]]
                   for e in self.effects[:10]],
            "pop": [[p[0], round(p[1], 2), round(p[2], 2), round(p[3], 2)] for p in self.popups[:8]],
            "rr": self.round_results,
        }

    def apply(self, snap):
        """Show the host's race (ignores anything broken)."""
        try:
            grid = str(snap["g"])
            if len(grid) != COLS * ROWS:
                return
            rows = [list(grid[r * COLS:(r + 1) * COLS]) for r in range(ROWS)]
            phase = snap["ph"] if snap["ph"] in PHASES else "play"
            bugs = []
            for b, d in zip(self.racers, snap["b"]):
                bugs.append((b, float(d[0]), float(d[1]), (int(d[2][0]), int(d[2][1])),
                             (int(d[3][0]), int(d[3][1])), int(d[4]), int(d[5]), int(d[6]),
                             float(d[7]), float(d[8]), float(d[9]), float(d[10])))
            spiders = []
            for s, d in zip(self.spiders, snap["s"]):
                spiders.append((s, float(d[0]), float(d[1]), (int(d[2][0]), int(d[2][1])),
                                d[3] if d[3] in SPIDER_STATES else "chase", bool(d[4]),
                                float(d[5]), float(d[6]), float(d[7])))
            gem = snap.get("gem")
            gem = [int(gem[0]), int(gem[1]), float(gem[2]), int(gem[3])] if gem else None
            effects = [[str(k), float(x), float(y), float(a), float(m)]
                       for k, x, y, a, m in snap.get("fx", [])[:10]]
            popups = [[str(t)[:8], float(x), float(y), float(a)]
                      for t, x, y, a in snap.get("pop", [])[:8]]
            results = [[int(v) for v in r][:MAX_RACERS] for r in snap.get("rr", [])[:RACE_ROUNDS]]
            vals = (float(snap["pt"]), float(snap["tm"]), int(snap["rn"]),
                    int(snap["mz"]) % len(MAZES), int(snap["lv"]), float(snap["sc"]))
        except (KeyError, TypeError, ValueError, IndexError):
            return
        self.phase_t, self.timer, self.round_no, self.maze_no, self.level, self.scare_t = vals
        self.phase, self.grid, self.gem = phase, rows, gem
        for (b, x, y, d, f, fl, pk, tot, out, frz, safe, walk) in bugs:
            b.x, b.y, b.dir, b.facing, b.flash = x, y, d, f, fl
            b.picks, b.total, b.out_t, b.freeze, b.safe, b.walk = pk, tot, out, frz, safe, walk
        for (s, x, y, d, st, sc, stun, walk, bob) in spiders:
            s.x, s.y, s.dir, s.state, s.scared, s.stun, s.walk, s.bob = x, y, d, st, sc, stun, walk, bob
        self.effects, self.popups, self.round_results = effects, popups, results
