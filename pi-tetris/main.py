#!/usr/bin/env python3
"""
Pi Tetris - a pygame Tetris for Raspberry Pi 4 (64-bit OS).
Portrait (vertical) screen, fullscreen, scoreboard and LAN multiplayer.

Six inputs (keyboard and/or GPIO buttons):
    UP       menu: move up
    DOWN     menu: move down        | in game: soft drop (hold)
    LEFT     menu: change value     | in game: move left
    RIGHT    menu: change value     | in game: move right
    BUTTON1  open the menu (in game) / go back
    BUTTON2  rotate piece (in game) / OK (in menus)
"""
import json
import math
import os
import queue
import random
import socket
import sys
import time

import pygame

import multiplayer as mp
import shooter as sh
from common import W, H, BG, WHITE, GREY, GOLD, RED, GREEN
from shooter import Shooter
from shooter_ui import ShooterUI

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SCORES_PATH = os.path.join(BASE_DIR, "highscores.json")
SCORES_SHOOTER_PATH = os.path.join(BASE_DIR, "highscores_shooter.json")

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "fullscreen": True,
    # 0 = the monitor is already turned vertical (or you rotated it in the
    # Raspberry Pi OS screen settings). 90 / 270 = the monitor is a normal
    # landscape one and the game should rotate its picture itself.
    "rotate": 0,
    "player_name": "",          # multiplayer name; empty = the Pi's hostname
    "gpio_enabled": True,
    # BCM numbers. Each button connects the GPIO pin to GND (internal pull-up).
    "gpio_pins": {
        "up": 5,
        "down": 6,
        "left": 13,
        "right": 19,
        "button1": 26,
        "button2": 21,
    },
    "gpio_debounce_ms": 30,
}


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user = json.load(f)
        for key, value in user.items():
            if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                cfg[key].update(value)
            else:
                cfg[key] = value
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        print("Could not read config.json, using defaults:", exc)
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError as exc:
        print("Could not save config.json:", exc)


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
NAME_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

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


# ----------------------------------------------------------------------------
# Game logic (no pygame needed)
# ----------------------------------------------------------------------------
class Tetris:
    def __init__(self, start_level=1, seed=None):
        self.rng = random.Random(seed)   # same seed = same pieces for everyone
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
        self.next_kind = self._draw()
        self._spawn()

    # -- helpers
    def _draw(self):
        if not self.bag:
            self.bag = list(PIECES.keys())
            self.rng.shuffle(self.bag)
        return self.bag.pop()

    def _spawn(self):
        self.kind = self.next_kind
        self.next_kind = self._draw()
        self.rot = 0
        self.x = (COLS - BOX[self.kind]) // 2
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
        return [(x + cx, y + cy) for cx, cy in ROTATIONS[self.kind][rot]]

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


# ----------------------------------------------------------------------------
# Scoreboard
# ----------------------------------------------------------------------------
class Scores:
    def __init__(self, path):
        self.path = path
        self.entries = []
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = []
            for e in data:
                entries.append({
                    "name": str(e["name"])[:3],
                    "score": int(e["score"]),
                    "lines": int(e.get("lines", 0)),
                    "level": int(e.get("level", 1)),
                })
            self.entries = sorted(entries, key=lambda e: -e["score"])[:MAX_SCORES]
        except FileNotFoundError:
            self.entries = []
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print("Could not read highscores.json, starting empty:", exc)
            self.entries = []

    def save(self):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, indent=2)
            os.replace(tmp, self.path)
        except OSError as exc:
            print("Could not save highscores:", exc)

    def qualifies(self, score):
        if score <= 0:
            return False
        return len(self.entries) < MAX_SCORES or score > self.entries[-1]["score"]

    def add(self, name, score, lines, level):
        entry = {"name": name, "score": score, "lines": lines, "level": level}
        self.entries.append(entry)
        self.entries.sort(key=lambda e: -e["score"])   # stable: older wins ties
        self.entries = self.entries[:MAX_SCORES]
        self.save()
        for i, e in enumerate(self.entries):
            if e is entry:
                return i
        return None

    def best(self):
        return self.entries[0]["score"] if self.entries else 0


# ----------------------------------------------------------------------------
# Input: keyboard + GPIO buttons -> six abstract actions
# ----------------------------------------------------------------------------
KEYMAP = {
    pygame.K_UP: "up",
    pygame.K_DOWN: "down",
    pygame.K_LEFT: "left",
    pygame.K_RIGHT: "right",
    pygame.K_ESCAPE: "button1",
    pygame.K_TAB: "button1",
    pygame.K_SPACE: "button2",
    pygame.K_RETURN: "button2",
    pygame.K_z: "button2",
    pygame.K_x: "button2",
}


class Input:
    def __init__(self, cfg):
        self.q = queue.Queue()      # filled by GPIO threads
        self.held = set()
        self.quit = False
        self.toggle_fullscreen = False
        self._buttons = []          # keep references alive
        if cfg.get("gpio_enabled"):
            self._setup_gpio(cfg)

    def _setup_gpio(self, cfg):
        try:
            from gpiozero import Button
        except Exception as exc:
            print("GPIO not available (keyboard only):", exc)
            return
        bounce = max(0, cfg.get("gpio_debounce_ms", 30)) / 1000.0
        for name, pin in cfg["gpio_pins"].items():
            try:
                btn = Button(int(pin), pull_up=True, bounce_time=bounce)
                btn.when_pressed = lambda n=name: self.q.put(("press", n))
                btn.when_released = lambda n=name: self.q.put(("release", n))
                self._buttons.append(btn)
            except Exception as exc:
                print("Could not set up GPIO %s for %s: %s" % (pin, name, exc))
        if self._buttons:
            print("GPIO buttons ready:", len(self._buttons))

    def poll(self):
        """Return the list of newly pressed actions this frame."""
        presses = []
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit = True
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    self.toggle_fullscreen = True
                action = KEYMAP.get(event.key)
                if action:
                    self.held.add(action)
                    presses.append(action)
            elif event.type == pygame.KEYUP:
                action = KEYMAP.get(event.key)
                if action:
                    self.held.discard(action)
        while True:
            try:
                kind, name = self.q.get_nowait()
            except queue.Empty:
                break
            if kind == "press":
                self.held.add(name)
                presses.append(name)
            else:
                self.held.discard(name)
        return presses


# ----------------------------------------------------------------------------
# Menu
# ----------------------------------------------------------------------------
class Menu:
    def __init__(self, items):
        self.items = items
        self.sel = 0

    def handle(self, presses):
        for a in presses:
            if a == "up":
                self.sel = (self.sel - 1) % len(self.items)
            elif a == "down":
                self.sel = (self.sel + 1) % len(self.items)
            elif a == "button2":
                return ("ok", self.sel)
            elif a == "button1":
                return ("back", self.sel)
            elif a in ("left", "right"):
                return (a, self.sel)
        return None


# ----------------------------------------------------------------------------
# Application
# ----------------------------------------------------------------------------
# Games shown in the start menu: (name, state that opens the game).
# To add a game later, add an entry here plus its own handle_/draw_ methods.
GAMES = [("TETRIS", "main"), ("SPACE SHOOTER", "sh_main")]

GUARDED_STATES = ("entry", "gameover", "sh_over", "mp_results", "host_results")


class App(ShooterUI):
    def __init__(self):
        self.cfg = load_config()
        pygame.display.init()
        pygame.font.init()
        self.display = None
        self.rot = 0
        self.apply_display()
        pygame.display.set_caption("Pi Tetris")
        # everything is drawn on this canvas, then shown (maybe rotated)
        self.canvas = pygame.Surface((W, H)).convert()
        self.screen = self.canvas

        self.font_huge = pygame.font.Font(None, 110)
        self.font_big = pygame.font.Font(None, 60)
        self.font_med = pygame.font.Font(None, 38)
        self.font_small = pygame.font.Font(None, 27)
        self.font_tiny = pygame.font.Font(None, 20)
        self.overlay = pygame.Surface((W, H), pygame.SRCALPHA).convert_alpha()
        self.overlay.fill((0, 0, 0, 175))
        self.sprites = {}
        self.dim_cache = {}
        self.board_bg = None

        self.input = Input(self.cfg)
        self.scores = Scores(SCORES_PATH)
        self.scores_sh = Scores(SCORES_SHOOTER_PATH)
        self.player_name = mp.clean_name(
            self.cfg.get("player_name") or socket.gethostname())
        self.menus = {
            "games": Menu([name for name, _state in GAMES] + ["EXIT TO DESKTOP"]),
            "main": Menu(["SINGLE PLAYER", "LEVEL", "MULTIPLAYER",
                          "SCOREBOARD", "FULLSCREEN", "BACK"]),
            "pause": Menu(["RESUME", "RESTART", "SCOREBOARD", "MAIN MENU", "QUIT"]),
            "gameover": Menu(["PLAY AGAIN", "SCOREBOARD", "MAIN MENU"]),
            "sh_main": Menu(["SINGLE PLAYER", "MULTIPLAYER", "SCOREBOARD",
                             "FULLSCREEN", "BACK"]),
            "sh_pause": Menu(["RESUME", "RESTART", "SCOREBOARD", "MAIN MENU"]),
            "sh_over": Menu(["PLAY AGAIN", "SCOREBOARD", "MAIN MENU"]),
            "mp": Menu(["HOST (SPECTATE)", "JOIN A GAME", "BACK"]),
            "mp_pause": Menu(["RESUME", "LEAVE GAME"]),
            "host_pause": Menu(["RESUME VIEW", "END THIS ROUND", "STOP HOSTING"]),
            "join": Menu(["BACK"]),
        }
        self.start_level = 1
        self.game = None
        self.running = True
        self.state = "games"
        self.state_age = 0
        self.das_dir = 0
        self.das_timer = 0
        self.entry = ["A", "A", "A"]
        self.cursor = 0
        self.highlight = None
        self.scores_return = "main"
        self.scores_game = "tetris"       # which scoreboard the scores screen shows
        self.entry_ctx = None             # what the name-entry screen is saving
        self.notice = ("", 0.0)

        # multiplayer
        self.host = None
        self.client = None
        self.finder = None
        self.join_hosts = []
        self.mp_game = "tetris"           # which game multiplayer is about
        self.mp_level = 1
        self.mp_menu_open = False
        self.host_menu_open = False
        self.mp_sent_dead = False
        self.last_state_send = 0.0
        self.countdown = 3.0
        self.mp_ranking = []

    # -- display
    def apply_display(self):
        rot = int(self.cfg.get("rotate", 0)) % 360
        if rot not in (0, 90, 180, 270):
            rot = 0
        self.rot = rot
        size = (W, H) if rot in (0, 180) else (H, W)
        flags = pygame.SCALED
        fullscreen = bool(self.cfg.get("fullscreen"))
        if fullscreen:
            flags |= pygame.FULLSCREEN
        self.display = pygame.display.set_mode(size, flags)
        pygame.mouse.set_visible(not fullscreen)

    def toggle_fullscreen(self):
        self.cfg["fullscreen"] = not self.cfg.get("fullscreen")
        self.apply_display()
        save_config(self.cfg)

    def present(self):
        if self.rot == 0:
            self.display.blit(self.canvas, (0, 0))
        else:
            self.display.blit(pygame.transform.rotate(self.canvas, self.rot), (0, 0))
        pygame.display.flip()

    # -- state helpers
    def set_state(self, name, reset=True):
        self.state = name
        self.state_age = 0
        if reset and name in self.menus:
            self.menus[name].sel = 0

    def say(self, text, secs=4.0):
        self.notice = (text, time.monotonic() + secs)

    def start_game(self):
        self.game = Tetris(self.start_level)
        self.das_dir = 0
        self.das_timer = 0
        self.set_state("play")

    def show_scores(self, return_to, highlight=None, game="tetris"):
        self.scores_return = return_to
        self.scores_game = game
        self.highlight = highlight
        self.set_state("scores")

    # -- main loop
    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            dt = min(clock.tick(60), 100)
            presses = self.input.poll()
            if self.input.quit:
                break
            if self.input.toggle_fullscreen:
                self.input.toggle_fullscreen = False
                self.toggle_fullscreen()
            self.state_age += dt
            self.handle(presses)
            self.update(dt)
            self.draw()
            self.present()
        self.shutdown()

    def shutdown(self):
        self.stop_finder()
        self.stop_hosting()
        self.leave_client()
        pygame.quit()

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------
    def handle(self, presses):
        s = self.state
        if s in GUARDED_STATES and self.state_age < 700:
            return  # ignore button mashing right after a round ends
        fn = getattr(self, "handle_" + s, None)
        if fn:
            fn(presses)

    def handle_games(self, presses):
        r = self.menus["games"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "ok":
            if idx < len(GAMES):
                self.set_state(GAMES[idx][1])
            else:
                self.running = False

    def handle_main(self, presses):
        r = self.menus["main"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "back":
            self.set_state("games", reset=False)
        elif kind == "ok":
            if idx == 0:
                self.start_game()
            elif idx == 2:
                self.mp_game = "tetris"
                self.set_state("mp")
            elif idx == 3:
                self.show_scores("main")
            elif idx == 4:
                self.toggle_fullscreen()
            elif idx == 5:
                self.set_state("games", reset=False)
        elif kind in ("left", "right"):
            if idx == 1:
                step = -1 if kind == "left" else 1
                self.start_level = max(1, min(MAX_START_LEVEL, self.start_level + step))
            elif idx == 4:
                self.toggle_fullscreen()

    # -- piece control shared by single player and multiplayer
    def piece_input(self, presses):
        """Apply this frame's presses. Returns True if BUTTON1 was pressed."""
        g = self.game
        for a in presses:
            if a == "button1":
                return True
            if a == "button2":
                g.rotate()
            elif a == "left":
                g.move(-1)
                self.das_dir = -1
                self.das_timer = DAS_RATE - DAS_DELAY
            elif a == "right":
                g.move(1)
                self.das_dir = 1
                self.das_timer = DAS_RATE - DAS_DELAY
        return False

    def update_piece(self, dt, enabled):
        g = self.game
        held = self.input.held
        if enabled:
            if self.das_dir == -1 and "left" not in held:
                self.das_dir = 0
            if self.das_dir == 1 and "right" not in held:
                self.das_dir = 0
            if self.das_dir == 0:
                if "left" in held and "right" not in held:
                    self.das_dir, self.das_timer = -1, DAS_RATE - DAS_DELAY
                elif "right" in held and "left" not in held:
                    self.das_dir, self.das_timer = 1, DAS_RATE - DAS_DELAY
            if self.das_dir:
                self.das_timer += dt
                while self.das_timer >= DAS_RATE:
                    self.das_timer -= DAS_RATE
                    g.move(self.das_dir)
        else:
            self.das_dir = 0
        g.update(dt, enabled and "down" in held)

    # -- single player
    def handle_play(self, presses):
        if self.piece_input(presses):
            self.set_state("pause")

    def handle_pause(self, presses):
        r = self.menus["pause"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "back" or (kind == "ok" and idx == 0):
            self.das_dir = 0
            self.set_state("play")
        elif kind == "ok":
            if idx == 1:
                self.start_game()
            elif idx == 2:
                self.show_scores("pause")
            elif idx == 3:
                self.set_state("main")
            elif idx == 4:
                self.running = False

    def handle_gameover(self, presses):
        r = self.menus["gameover"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "ok":
            if idx == 0:
                self.start_game()
            elif idx == 1:
                self.show_scores("gameover")
            elif idx == 2:
                self.set_state("main")

    def handle_scores(self, presses):
        if any(a in ("button1", "button2") for a in presses):
            self.set_state(self.scores_return, reset=False)

    def handle_entry(self, presses):
        for a in presses:
            if a == "up":
                i = NAME_CHARS.index(self.entry[self.cursor])
                self.entry[self.cursor] = NAME_CHARS[(i + 1) % len(NAME_CHARS)]
            elif a == "down":
                i = NAME_CHARS.index(self.entry[self.cursor])
                self.entry[self.cursor] = NAME_CHARS[(i - 1) % len(NAME_CHARS)]
            elif a == "left":
                self.cursor = max(0, self.cursor - 1)
            elif a == "right":
                self.cursor = min(2, self.cursor + 1)
            elif a == "button2":
                ctx = self.entry_ctx
                idx = ctx["scores"].add("".join(self.entry), ctx["score"],
                                        ctx["lines"], ctx["level"])
                self.show_scores(ctx["ret"], highlight=idx, game=ctx["game"])
                return

    # -- multiplayer menu
    def handle_mp(self, presses):
        r = self.menus["mp"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "back" or (kind == "ok" and idx == 2):
            self.set_state("main" if self.mp_game == "tetris" else "sh_main",
                           reset=False)
        elif kind == "ok":
            if idx == 0:
                self.start_hosting()
            elif idx == 1:
                self.start_joining()

    # -- hosting (spectator Pi)
    def start_hosting(self):
        try:
            self.host = mp.HostSession(self.player_name, self.mp_game)
        except OSError as exc:
            self.host = None
            self.say("COULD NOT START HOST: %s" % exc)
            return
        self.mp_level = self.start_level
        self.host_menu_open = False
        self.set_state("host_lobby")

    def stop_hosting(self):
        if self.host:
            self.host.close()
            self.host = None

    def handle_host_lobby(self, presses):
        h = self.host
        for a in presses:
            if a == "button1":
                self.stop_hosting()
                self.set_state("mp", reset=False)
                return
            elif a == "left" and self.mp_game == "tetris":
                self.mp_level = max(1, self.mp_level - 1)
            elif a == "right" and self.mp_game == "tetris":
                self.mp_level = min(MAX_START_LEVEL, self.mp_level + 1)
            elif a == "button2":
                if h.start_game(self.mp_level if self.mp_game == "tetris" else 1):
                    self.host_menu_open = False
                    self.set_state("host_watch")
                else:
                    self.say("WAITING FOR PLAYERS...")
                return

    def handle_host_watch(self, presses):
        h = self.host
        if not self.host_menu_open:
            if "button1" in presses:
                self.host_menu_open = True
                self.menus["host_pause"].sel = 0
            return
        r = self.menus["host_pause"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "back" or (kind == "ok" and idx == 0):
            self.host_menu_open = False
        elif kind == "ok":
            if idx == 1:
                h.finish()
                self.host_menu_open = False
            elif idx == 2:
                self.stop_hosting()
                self.set_state("mp", reset=False)

    def handle_host_results(self, presses):
        if any(a in ("button1", "button2") for a in presses):
            self.host.back_to_lobby()
            self.set_state("host_lobby")

    # -- joining (playing Pi)
    def start_joining(self):
        self.stop_finder()
        self.finder = mp.Finder()
        self.finder.start()
        self.join_hosts = []
        self.menus["join"].items = ["BACK"]
        self.set_state("join")

    def stop_finder(self):
        if self.finder:
            self.finder.stop()
            self.finder = None

    def handle_join(self, presses):
        r = self.menus["join"].handle(presses)
        if not r:
            return
        kind, idx = r
        hosts = self.join_hosts
        if kind == "back" or (kind == "ok" and idx >= len(hosts)):
            self.stop_finder()
            self.set_state("mp", reset=False)
        elif kind == "ok":
            host = hosts[idx]
            if host.get("phase") != "lobby":
                self.say("THAT GAME HAS ALREADY STARTED")
                return
            self.stop_finder()
            self.client = mp.ClientSession(host["ip"], host["port"], self.player_name)
            self.set_state("connecting")

    def handle_connecting(self, presses):
        if "button1" in presses:
            self.leave_client()
            self.start_joining()

    def handle_client_lobby(self, presses):
        if "button1" in presses:
            self.leave_client()
            self.set_state("mp", reset=False)

    def handle_mp_countdown(self, presses):
        if "button1" in presses:
            self.leave_client()
            self.set_state("mp", reset=False)

    def handle_mp_play(self, presses):
        if self.mp_menu_open:
            r = self.menus["mp_pause"].handle(presses)
            if not r:
                return
            kind, idx = r
            if kind == "back" or (kind == "ok" and idx == 0):
                self.mp_menu_open = False
            elif kind == "ok" and idx == 1:
                self.leave_client()
                self.set_state("mp", reset=False)
            return
        shooter = self.mp_game == "shooter"
        if self.game.game_over or shooter:       # shooter: BUTTON1 = menu, BUTTON2 = fire
            if "button1" in presses:
                self.mp_menu_open = True
                self.menus["mp_pause"].sel = 0
            return
        if self.piece_input(presses):
            self.mp_menu_open = True
            self.menus["mp_pause"].sel = 0
            self.das_dir = 0

    def handle_mp_results(self, presses):
        if any(a in ("button1", "button2") for a in presses):
            if self.client:
                self.set_state("client_lobby")
            else:
                self.set_state("mp", reset=False)

    def leave_client(self):
        if self.client:
            self.client.close()
            self.client = None

    def drop_client(self, text):
        self.leave_client()
        self.say(text)
        self.set_state("mp", reset=False)

    def begin_mp_round(self, msg):
        try:
            seed = int(msg.get("seed", 1))
            level = max(1, min(30, int(msg.get("level", 1))))
            self.countdown = float(msg.get("countdown", 3.0))
        except (TypeError, ValueError):
            seed, level, self.countdown = 1, 1, 3.0
        if msg.get("game") == "shooter":
            self.mp_game = "shooter"
            self.game = Shooter(seed, multiplayer=True)
        else:
            self.mp_game = "tetris"
            self.game = Tetris(level, seed)
        self.das_dir = 0
        self.das_timer = 0
        self.mp_menu_open = False
        self.mp_sent_dead = False
        self.last_state_send = 0.0
        self.set_state("mp_countdown")

    def pump_client(self):
        c = self.client
        for kind, msg in c.poll():
            if self.client is not c:
                break
            if kind == "connected":
                if self.state == "connecting":
                    self.set_state("client_lobby")
            elif kind == "failed":
                self.drop_client("COULD NOT CONNECT")
            elif kind == "full":
                self.drop_client("GAME FULL OR ALREADY STARTED")
            elif kind == "closed":
                self.drop_client("LOST CONNECTION TO HOST")
            elif kind == "start":
                if self.state in ("client_lobby", "mp_results"):
                    self.begin_mp_round(msg)
            elif kind == "garbage":
                if (self.state == "mp_play" and self.mp_game == "tetris"
                        and self.game and not self.game.game_over):
                    self.game.queue_garbage(msg.get("hole", 0))
            elif kind == "enemy":
                if (self.state == "mp_play" and self.mp_game == "shooter"
                        and self.game and not self.game.game_over):
                    self.game.queue_enemy(msg.get("k"), msg.get("fx", 0.5))
            elif kind == "over":
                if self.state in ("mp_play", "mp_countdown"):
                    ranking = msg.get("ranking", [])
                    self.mp_ranking = ranking if isinstance(ranking, list) else []
                    self.mp_menu_open = False
                    self.set_state("mp_results")

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(self, dt):
        if self.client is not None:
            self.pump_client()
        if self.host is not None:
            self.host.poll()
            if self.state == "host_watch" and self.host.phase == "results":
                self.host_menu_open = False
                self.set_state("host_results")

        s = self.state
        if s == "play":
            self.update_single(dt)
        elif s == "sh_play":
            self.update_sh_play(dt)
        elif s == "mp_countdown":
            if self.state_age / 1000.0 >= self.countdown:
                self.set_state("mp_play")
        elif s == "mp_play":
            self.update_mp_play(dt)
        elif s == "join":
            self.update_join()

    def update_single(self, dt):
        g = self.game
        self.update_piece(dt, True)
        if g.game_over:
            if self.scores.qualifies(g.score):
                self.entry_ctx = {"scores": self.scores, "score": g.score,
                                  "lines": g.lines, "level": g.level,
                                  "ret": "gameover", "game": "tetris"}
                self.cursor = 0
                self.set_state("entry")
            else:
                self.set_state("gameover")

    def update_mp_play(self, dt):
        if self.mp_game == "shooter":
            self.update_shooter_mp(dt)
            return
        g = self.game
        c = self.client
        if c is None:
            return
        self.update_piece(dt, not self.mp_menu_open and not g.game_over)
        if g.clears_unsent:
            c.send_clear(g.clears_unsent)
            g.clears_unsent = 0
        now = time.monotonic()
        if g.game_over:
            if not self.mp_sent_dead:
                self.mp_sent_dead = True
                c.send_dead(g.snapshot(), g.score, g.lines, g.level)
        elif now - self.last_state_send >= 0.1:
            self.last_state_send = now
            c.send_state(g.snapshot(), g.score, g.lines, g.level)

    def update_join(self):
        f = self.finder
        hosts = [h for h in (f.get_hosts() if f else [])
                 if h.get("mode", "tetris") == self.mp_game]
        self.join_hosts = hosts
        items = []
        for h in hosts:
            tag = "%d IN" % h["players"] if h["phase"] == "lobby" else "STARTED"
            items.append("%s  [%s]" % (h["name"], tag))
        items.append("BACK")
        menu = self.menus["join"]
        menu.items = items
        menu.sel = min(menu.sel, len(items) - 1)

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------
    def text(self, s, font, color, pos, anchor="topleft"):
        img = font.render(s, True, color)
        self.screen.blit(img, img.get_rect(**{anchor: pos}))

    def sprite(self, color, size):
        key = (color, size)
        spr = self.sprites.get(key)
        if spr is None:
            spr = pygame.Surface((size, size)).convert()
            dark = tuple(max(0, c - 90) for c in color)
            light = tuple(min(255, c + 60) for c in color)
            edge = max(1, size // 10)
            spr.fill(dark)
            pygame.draw.rect(spr, color, (edge, edge, size - 2 * edge, size - 2 * edge))
            pygame.draw.line(spr, light, (edge, edge), (size - edge - 1, edge))
            pygame.draw.line(spr, light, (edge, edge), (edge, size - edge - 1))
            self.sprites[key] = spr
        return spr

    def dim(self, w, h, x, y):
        key = (w, h)
        surf = self.dim_cache.get(key)
        if surf is None:
            surf = pygame.Surface((w, h), pygame.SRCALPHA).convert_alpha()
            surf.fill((0, 0, 0, 165))
            self.dim_cache[key] = surf
        self.screen.blit(surf, (x, y))

    def get_board_bg(self):
        if self.board_bg is None:
            bg = pygame.Surface((COLS * CELL, ROWS * CELL)).convert()
            bg.fill((8, 8, 14))
            for c in range(1, COLS):
                pygame.draw.line(bg, (26, 26, 40), (c * CELL, 0), (c * CELL, ROWS * CELL))
            for r in range(1, ROWS):
                pygame.draw.line(bg, (26, 26, 40), (0, r * CELL), (COLS * CELL, r * CELL))
            self.board_bg = bg
        return self.board_bg

    def draw_board(self, g):
        self.screen.blit(self.get_board_bg(), (BOARD_X, BOARD_Y))
        for r in range(ROWS):
            row = g.grid[r]
            for c in range(COLS):
                kind = row[c]
                if kind:
                    self.screen.blit(self.sprite(COLORS[kind], CELL),
                                     (BOARD_X + c * CELL, BOARD_Y + r * CELL))
        if not g.game_over:
            gy = g.ghost_y()
            col = COLORS[g.kind]
            for gx, cy in g.cells(y=gy):
                if cy >= 0:
                    pygame.draw.rect(self.screen, col,
                                     (BOARD_X + gx * CELL + 3, BOARD_Y + cy * CELL + 3,
                                      CELL - 6, CELL - 6), 2)
            spr = self.sprite(col, CELL)
            for gx, cy in g.cells():
                if cy >= 0:
                    self.screen.blit(spr, (BOARD_X + gx * CELL, BOARD_Y + cy * CELL))
        frame = pygame.Rect(BOARD_X, BOARD_Y, COLS * CELL, ROWS * CELL)
        pygame.draw.rect(self.screen, GREY, frame.inflate(6, 6), 3)

    def draw_snapshot(self, board, x, y, cell):
        """Draw a board string (200 chars) - used for the host's spectator view."""
        pygame.draw.rect(self.screen, (8, 8, 14), (x, y, COLS * cell, ROWS * cell))
        if not board:
            return
        for i, ch in enumerate(board):
            if ch != "." and ch in COLORS:
                r, c = divmod(i, COLS)
                self.screen.blit(self.sprite(COLORS[ch], cell), (x + c * cell, y + r * cell))

    def menu_label(self, i, item):
        if self.state in ("main", "sh_main"):
            if item == "LEVEL":
                return "LEVEL  <  %d  >" % self.start_level
            if item == "FULLSCREEN":
                return "FULLSCREEN  <  %s  >" % ("ON" if self.cfg.get("fullscreen") else "OFF")
        return item

    def draw_menu(self, menu, title=None, lines=(), top=300, step=68):
        cx = W // 2
        if title:
            self.text(title, self.font_big, WHITE, (cx, 110), "center")
        for i, line in enumerate(lines):
            self.text(line, self.font_small, GOLD if i == 0 else GREY,
                      (cx, 165 + i * 32), "center")
        for i, item in enumerate(menu.items):
            y = top + i * step
            selected = i == menu.sel
            rect = (cx - 225, y - 27, 450, 54)
            if selected:
                pygame.draw.rect(self.screen, (45, 45, 90), rect, border_radius=10)
                pygame.draw.rect(self.screen, GOLD, rect, 3, border_radius=10)
            self.text(self.menu_label(i, item), self.font_med,
                      GOLD if selected else WHITE, (cx, y), "center")
        self.text("UP/DOWN: SELECT      B2: OK", self.font_small, GREY,
                  (cx, H - 35), "center")

    def draw_notice(self):
        text, until = self.notice
        if text and time.monotonic() < until:
            self.text(text, self.font_small, RED, (W // 2, H - 80), "center")

    # ------------------------------------------------------------------
    # Drawing screens
    # ------------------------------------------------------------------
    def draw(self):
        fn = getattr(self, "draw_" + self.state, None)
        self.screen.fill(BG)
        if fn:
            fn()
        self.draw_notice()

    def draw_games(self):
        self.draw_menu(self.menus["games"], "GAMES", top=300)

    def draw_main(self):
        cx = W // 2
        letters = "TETRIS"
        colors = [COLORS[k] for k in "TOSZIL"]
        widths = [self.font_huge.size(c)[0] for c in letters]
        x = (W - sum(widths)) // 2
        for ch, col, w in zip(letters, colors, widths):
            self.text(ch, self.font_huge, col, (x, 90))
            x += w
        self.draw_menu(self.menus["main"], top=300)

    def draw_play(self, extra=None):
        g = self.game
        self.draw_board(g)
        # next piece
        self.text("NEXT", self.font_small, GREY, (20, 12))
        box = pygame.Rect(20, 36, 124, 92)
        pygame.draw.rect(self.screen, (8, 8, 14), box)
        pygame.draw.rect(self.screen, GREY, box, 2)
        cells = ROTATIONS[g.next_kind][0]
        minx = min(c[0] for c in cells)
        maxx = max(c[0] for c in cells)
        miny = min(c[1] for c in cells)
        maxy = max(c[1] for c in cells)
        cs = 24
        ox = box.centerx - ((maxx - minx + 1) * cs) // 2
        oy = box.centery - ((maxy - miny + 1) * cs) // 2
        spr = self.sprite(COLORS[g.next_kind], cs)
        for cx_, cy_ in cells:
            self.screen.blit(spr, (ox + (cx_ - minx) * cs, oy + (cy_ - miny) * cs))
        # stats
        self.text("SCORE", self.font_small, GREY, (175, 12))
        self.text(str(g.score), self.font_med, WHITE, (175, 36))
        self.text("LEVEL", self.font_small, GREY, (175, 78))
        self.text(str(g.level), self.font_med, WHITE, (175, 100))
        self.text("LINES", self.font_small, GREY, (295, 78))
        self.text(str(g.lines), self.font_med, WHITE, (295, 100))
        label, value = extra if extra else ("BEST", str(self.scores.best()))
        self.text(label, self.font_small, GREY, (410, 78))
        self.text(value, self.font_med, WHITE, (410, 100))
        # incoming garbage bar (multiplayer)
        if g.pending_garbage:
            n = min(ROWS, len(g.pending_garbage))
            pygame.draw.rect(self.screen, RED,
                             (BOARD_X - 20, BOARD_Y + (ROWS - n) * CELL, 12, n * CELL))

    def draw_pause(self):
        self.draw_play()
        self.screen.blit(self.overlay, (0, 0))
        self.draw_menu(self.menus["pause"], "PAUSED", top=290)

    def draw_gameover(self):
        self.draw_play()
        self.screen.blit(self.overlay, (0, 0))
        self.draw_menu(self.menus["gameover"], "GAME OVER",
                       lines=["SCORE  %d" % self.game.score], top=330)

    def draw_scores(self):
        cx = W // 2
        shooter = self.scores_game == "shooter"
        scores = self.scores_sh if shooter else self.scores
        self.text("SCOREBOARD", self.font_big, GOLD, (cx, 60), "center")
        self.text("SPACE SHOOTER" if shooter else "TETRIS", self.font_small, GREY,
                  (cx, 102), "center")
        self.text("NAME", self.font_small, GREY, (125, 135))
        self.text("SCORE", self.font_small, GREY, (370, 135), "topright")
        self.text("KILLS" if shooter else "LINES", self.font_small, GREY,
                  (470, 135), "topright")
        if not scores.entries:
            self.text("NO SCORES YET - GO PLAY!", self.font_med, WHITE, (cx, 400), "center")
        for i, e in enumerate(scores.entries):
            y = 175 + i * 52
            col = GOLD if i == self.highlight else WHITE
            self.text("%2d." % (i + 1), self.font_med, col, (50, y))
            self.text(e["name"], self.font_med, col, (125, y))
            self.text(str(e["score"]), self.font_med, col, (370, y), "topright")
            self.text(str(e["lines"]), self.font_med, col, (470, y), "topright")
        self.text("PRESS B1 OR B2 TO GO BACK", self.font_small, GREY, (cx, H - 35), "center")

    def draw_entry(self):
        cx = W // 2
        self.text("NEW HIGH SCORE!", self.font_big, GOLD, (cx, 150), "center")
        self.text("SCORE  %d" % self.entry_ctx["score"], self.font_med, WHITE, (cx, 215), "center")
        self.text("ENTER YOUR NAME", self.font_small, GREY, (cx, 290), "center")
        for i, ch in enumerate(self.entry):
            x = cx + (i - 1) * 130
            sel = i == self.cursor
            self.text(ch, self.font_huge, GOLD if sel else WHITE, (x, 450), "center")
            pygame.draw.line(self.screen, GOLD if sel else GREY,
                             (x - 40, 510), (x + 40, 510), 5)
            if sel:
                self.text("^", self.font_big, GOLD, (x, 375), "center")
                self.text("v", self.font_big, GOLD, (x, 545), "center")
        self.text("UP/DOWN: LETTER", self.font_small, GREY, (cx, 700), "center")
        self.text("LEFT/RIGHT: MOVE CURSOR", self.font_small, GREY, (cx, 735), "center")
        self.text("B2: SAVE", self.font_small, GREY, (cx, 770), "center")

    # -- multiplayer screens
    def draw_mp(self):
        self.draw_menu(self.menus["mp"], "MULTIPLAYER",
                       lines=["TETRIS" if self.mp_game == "tetris" else "SPACE SHOOTER",
                              "PLAY WITH OTHER PIS ON THIS NETWORK",
                              "HOST = SPECTATOR SCREEN, SEES EVERYONE",
                              "JOIN = PLAY AGAINST THE OTHERS"],
                       top=400)

    def draw_roster(self, names, y0, me=None):
        cx = W // 2
        if not names:
            self.text("NOBODY YET...", self.font_med, GREY, (cx, y0 + 20), "center")
        for i, (name, is_me) in enumerate(names):
            label = name + ("  (YOU)" if is_me else "")
            self.text("%d. %s" % (i + 1, label), self.font_med,
                      GOLD if is_me else WHITE, (90, y0 + i * 48))

    def draw_host_lobby(self):
        h = self.host
        cx = W // 2
        self.text("HOSTING TETRIS" if h.game == "tetris" else "HOSTING SHOOTER",
                  self.font_big, GOLD, (cx, 100), "center")
        self.text("NAME: %s" % h.name, self.font_small, WHITE, (cx, 200), "center")
        self.text("IP: %s" % h.ip, self.font_small, WHITE, (cx, 232), "center")
        self.text("PLAYERS  (%d/%d)" % (len(h.players), mp.MAX_PLAYERS),
                  self.font_med, GOLD, (cx, 300), "center")
        names = [(p["name"], False) for p in h.players.values()]
        self.draw_roster(names, 345)
        if h.game == "tetris":
            self.text("START LEVEL  <  %d  >" % self.mp_level, self.font_med, WHITE,
                      (cx, 780), "center")
        if h.players:
            self.text("B2: START GAME", self.font_med, GREEN, (cx, 840), "center")
        else:
            self.text("WAITING FOR PLAYERS...", self.font_med, GREY, (cx, 840), "center")
        self.text("B1: STOP HOSTING", self.font_small, GREY, (cx, H - 35), "center")

    def host_layout(self, n, uw=COLS, uh=ROWS, integer=True):
        """Best (scale, columns, rows) to fit n screens of uw x uh units.

        Tetris: units are cells (scale = cell size in pixels, whole numbers).
        Shooter: units are playfield pixels (scale is a fraction)."""
        area_w, area_h = W - 20, H - 130
        n = max(1, n)
        best, best_scale = (4 if integer else 0.1, 1, n), -1
        for cols in range(1, n + 1):
            rows = -(-n // cols)
            scale = min((area_w / cols - 12) / uw, (area_h / rows - 56) / uh)
            if integer:
                scale = int(scale)
            if scale > best_scale:
                best_scale = scale
                best = (max(4 if integer else 0.1, scale), cols, rows)
        return best

    def draw_host_watch(self):
        h = self.host
        now = time.monotonic()
        cx = W // 2
        players = list(h.players.values())
        alive = sum(1 for p in players if p["alive"])
        elapsed = int(max(0, now - h.t_go))
        self.text("LIVE VIEW", self.font_big, GOLD, (cx, 38), "center")
        self.text("%d OF %d ALIVE      %d:%02d" % (alive, len(players), elapsed // 60, elapsed % 60),
                  self.font_small, WHITE, (cx, 85), "center")
        shooter = h.game == "shooter"
        if shooter:
            scale, cols, rows = self.host_layout(len(players), sh.SW, sh.SH, False)
            bw, bh = int(sh.SW * scale), int(sh.SH * scale)
        else:
            scale, cols, rows = self.host_layout(len(players))
            bw, bh = COLS * scale, ROWS * scale
        header = 56
        area_top = 118
        tile_w = (W - 20) / cols
        tile_h = (H - area_top - 10) / rows
        font = self.font_small if bw >= 170 else self.font_tiny
        for i, p in enumerate(players):
            col, row = i % cols, i // cols
            x = int(10 + col * tile_w + (tile_w - bw) / 2)
            y = int(area_top + row * tile_h + (tile_h - bh - header) / 2) + header
            info = str(p["score"])
            if shooter and isinstance(p["board"], dict):
                info += "  x%s" % p["board"].get("l", "?")
            self.text(p["name"], font, WHITE, (x + bw // 2, y - header + 2), "midtop")
            self.text(info, font, GOLD,
                      (x + bw // 2, y - header + 4 + font.get_height()), "midtop")
            if shooter:
                self.draw_shooter_snapshot(p["board"], x, y, scale)
            else:
                self.draw_snapshot(p["board"], x, y, scale)
            if now - p["hit"] < 0.6:
                border = RED
            elif now - p["sent"] < 0.6:
                border = GREEN
            else:
                border = GREY
            pygame.draw.rect(self.screen, border, (x - 3, y - 3, bw + 6, bh + 6), 3)
            if not p["alive"]:
                self.dim(bw, bh, x, y)
                self.text("LEFT" if p["gone"] else "OUT", self.font_med if bw < 170 else self.font_big,
                          RED, (x + bw // 2, y + bh // 2), "center")
        if not players:
            self.text("NO PLAYERS", self.font_med, GREY, (cx, H // 2), "center")
        remaining = h.t_go - now
        if remaining > 0:
            self.screen.blit(self.overlay, (0, 0))
            self.text(str(int(math.ceil(remaining))), self.font_huge, WHITE,
                      (cx, H // 2), "center")
        if self.host_menu_open:
            self.screen.blit(self.overlay, (0, 0))
            self.draw_menu(self.menus["host_pause"], "HOST MENU", top=330)

    def draw_ranking(self, ranking, me):
        cx = W // 2
        self.text("ROUND OVER", self.font_big, GOLD, (cx, 100), "center")
        for i, r in enumerate(ranking[:mp.MAX_PLAYERS]):
            y = 190 + i * 62
            mine = me is not None and r.get("cid") == me
            col = GOLD if i == 0 else (GREEN if mine else WHITE)
            self.text("%s." % r.get("place", i + 1), self.font_big, col, (60, y))
            self.text(str(r.get("name", "?")) + ("  (YOU)" if mine else ""),
                      self.font_med, col, (130, y + 8))
            self.text(str(r.get("score", 0)), self.font_med, col, (490, y + 8), "topright")
        if ranking:
            self.text("WINNER: %s" % ranking[0].get("name", "?"), self.font_med, GOLD,
                      (cx, 760), "center")

    def draw_host_results(self):
        self.draw_ranking(self.host.ranking, None)
        self.text("B1/B2: BACK TO LOBBY", self.font_small, GREY, (W // 2, H - 35), "center")

    def draw_mp_results(self):
        me = self.client.cid if self.client else None
        self.draw_ranking(self.mp_ranking, me)
        self.text("B1/B2: BACK TO LOBBY", self.font_small, GREY, (W // 2, H - 35), "center")

    def draw_join(self):
        cx = W // 2
        self.text("JOIN TETRIS" if self.mp_game == "tetris" else "JOIN SHOOTER",
                  self.font_big, WHITE, (cx, 100), "center")
        if self.finder and self.finder.error:
            self.text("CANNOT LISTEN: %s" % self.finder.error[:30], self.font_small,
                      RED, (cx, 170), "center")
        elif not self.join_hosts:
            dots = "." * (int(time.monotonic() * 2) % 4)
            self.text("SEARCHING FOR GAMES" + dots, self.font_med, GOLD, (cx, 180), "center")
            self.text("(THE HOST MUST BE IN ITS LOBBY)", self.font_small, GREY,
                      (cx, 220), "center")
        else:
            self.text("GAMES FOUND:", self.font_small, GOLD, (cx, 180), "center")
        self.draw_menu(self.menus["join"], top=290)

    def draw_connecting(self):
        cx = W // 2
        dots = "." * (int(time.monotonic() * 2) % 4)
        self.text("CONNECTING" + dots, self.font_big, GOLD, (cx, 400), "center")
        self.text("B1: CANCEL", self.font_small, GREY, (cx, H - 35), "center")

    def draw_client_lobby(self):
        c = self.client
        cx = W // 2
        self.text("CONNECTED", self.font_big, GREEN, (cx, 100), "center")
        self.text("HOST: %s" % (c.host_name or "?"), self.font_small, WHITE, (cx, 150), "center")
        self.text("PLAYERS", self.font_med, GOLD, (cx, 230), "center")
        names = [(p.get("name", "?"), p.get("cid") == c.cid) for p in c.roster]
        self.draw_roster(names, 275)
        self.text("WAITING FOR THE HOST TO START...", self.font_small, WHITE,
                  (cx, 800), "center")
        self.text("B1: LEAVE", self.font_small, GREY, (cx, H - 35), "center")

    def draw_mp_countdown(self):
        if self.mp_game == "shooter":
            self.draw_shooter_world(self.game, ("ALIVE", self.alive_text()))
        else:
            self.draw_play(("ALIVE", self.alive_text()))
        self.screen.blit(self.overlay, (0, 0))
        remaining = self.countdown - self.state_age / 1000.0
        self.text(str(max(1, int(math.ceil(remaining)))), self.font_huge, WHITE,
                  (W // 2, H // 2), "center")
        self.text("GET READY!", self.font_big, GOLD, (W // 2, H // 2 - 120), "center")

    def alive_text(self):
        roster = self.client.roster if self.client else []
        if not roster:
            return "-"
        return "%d/%d" % (sum(1 for p in roster if p.get("alive")), len(roster))

    def draw_mp_play(self):
        g = self.game
        if self.mp_game == "shooter":
            self.draw_shooter_world(g, ("ALIVE", self.alive_text()))
            if g.game_over and not self.mp_menu_open:
                self.screen.blit(self.overlay, (0, 0))
        else:
            self.draw_play(("ALIVE", self.alive_text()))
            if g.game_over and not self.mp_menu_open:
                self.dim(COLS * CELL, ROWS * CELL, BOARD_X, BOARD_Y)
        if g.game_over and not self.mp_menu_open:
            self.text("YOU ARE OUT!", self.font_big, RED, (W // 2, 480), "center")
            self.text("WAITING FOR THE OTHERS...", self.font_small, WHITE,
                      (W // 2, 530), "center")
        if self.mp_menu_open:
            self.screen.blit(self.overlay, (0, 0))
            self.draw_menu(self.menus["mp_pause"], "MENU",
                           lines=["THE GAME KEEPS RUNNING!"], top=330)


def main():
    app = App()
    try:
        app.run()
    except KeyboardInterrupt:
        app.shutdown()
    sys.exit(0)


if __name__ == "__main__":
    main()
