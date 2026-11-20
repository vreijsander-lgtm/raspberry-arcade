#!/usr/bin/env python3
"""
Pi Tetris - a pygame Tetris for Raspberry Pi 4 (64-bit OS).
Portrait (vertical) screen, fullscreen, scoreboard and LAN multiplayer.

Six inputs (keyboard, USB arcade stick / gamepad and/or GPIO buttons):
    UP       menu: move up
    DOWN     menu: move down        | in game: soft drop (hold)
    LEFT     menu: change value     | in game: move left
    RIGHT    menu: change value     | in game: move right
    BUTTON1  open the menu (in game) / go back
    BUTTON2  rotate piece (in game) / OK (in menus)
"""
import hashlib
import json
import math
import os
import queue
import random
import socket
import sys
import time
import uuid

import pygame

# The games live in their own folders next to this one (picade/tetris, picade/spaceshooter).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _game in ("tetris", "spaceshooter", "platformer", "fighter", "glowbug", "pulsar",
              "startoss"):
    sys.path.insert(0, os.path.join(_ROOT, _game))

import multiplayer as mp
import shooter as sh
from common import W, H, WHITE, GREY, GOLD, RED, GREEN
from shooter import Shooter
from shooter_ui import ShooterUI
from platformer import Platformer
from platformer_ui import PlatformerUI
from fighter_ui import FighterUI
from glowbug_ui import GlowbugUI
from pulsar_ui import PulsarUI
from toss_ui import TossUI
from title_ui import TitleUI, ARCADE_NAME, HUD_LABEL, MEDALS, NEON_CYAN, NEON_PINK
from tetris import Tetris, BOARD_X, BOARD_Y, CELL, COLORS, COLS, DAS_DELAY, DAS_RATE, MAX_SCORES, MAX_START_LEVEL, NAME_CHARS, NAME_LEN, ROTATIONS, ROWS
from name_filter import is_allowed
from shared_scores import ScoreSync

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SCORES_PATH = os.path.join(BASE_DIR, "highscores.json")
SCORES_SHOOTER_PATH = os.path.join(BASE_DIR, "highscores_shooter.json")
SCORES_PLATFORMER_PATH = os.path.join(BASE_DIR, "highscores_platformer.json")
SCORES_FIGHTER_PATH = os.path.join(BASE_DIR, "highscores_fighter.json")
SCORES_GLOWBUG_PATH = os.path.join(BASE_DIR, "highscores_glowbug.json")
SCORES_PULSAR_PATH = os.path.join(BASE_DIR, "highscores_pulsar.json")
SCORES_TOSS_PATH = os.path.join(BASE_DIR, "highscores_toss.json")

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
    # USB arcade stick / gamepad. The stick (left analog stick or d-pad) is
    # the 4 directions; these button numbers are BUTTON1 / BUTTON2. Run
    # stick_test.py to see which number each of your buttons has.
    "joy_buttons": {
        "button1": [1, 3],
        "button2": [0, 2],
    },
    "joy_deadzone": 0.5,
    # Shared scoreboard between all arcade Pis on the network (same group).
    "shared_scores": True,
    "score_group": "nova-arcade",
    "score_peers": [],          # extra IPs, only if the network blocks broadcasts
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
            entries = [e for e in (clean_entry(e) for e in data) if e]
            self.entries = sorted(entries, key=sort_key)[:MAX_SCORES]
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
        """Add a score; returns its id (to highlight it on the scoreboard)."""
        entry = {"name": name, "score": score, "lines": lines, "level": level,
                 "t": round(time.time(), 2), "id": uuid.uuid4().hex[:16]}
        self.entries.append(entry)
        self.entries.sort(key=sort_key)                # equal score: older first
        self.entries = self.entries[:MAX_SCORES]
        self.save()
        return entry["id"]

    def merge(self, entries):
        """Add scores from another Pi (shared scoreboard). True if it changed."""
        known = {e["id"] for e in self.entries}
        before = [e["id"] for e in self.entries]
        if not isinstance(entries, list):
            return False
        for raw in entries[:MAX_SCORES]:
            e = clean_entry(raw)
            if e and e["id"] not in known:
                known.add(e["id"])
                self.entries.append(e)
        self.entries.sort(key=sort_key)
        self.entries = self.entries[:MAX_SCORES]
        if [e["id"] for e in self.entries] != before:
            self.save()
            return True
        return False


    def best(self):
        return self.entries[0]["score"] if self.entries else 0


def sort_key(e):
    return (-e["score"], e["t"])


def clean_entry(e):
    """A safe score entry (from the file or the network), or None."""
    try:
        name = "".join(ch for ch in str(e["name"]).upper() if ch in NAME_CHARS)
        name = " ".join(name.split())[:NAME_LEN]
        entry = {"name": name, "score": int(e["score"]),
                 "lines": int(e.get("lines", 0)), "level": int(e.get("level", 1)),
                 "t": float(e.get("t", 0))}
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if not name or not is_allowed(name) or not 0 < entry["score"] < 10 ** 9:
        return None
    # old entries have no id: make one from the entry itself
    entry["id"] = str(e.get("id") or hashlib.md5(
        ("%s|%d|%d|%d" % (name, entry["score"], entry["lines"], entry["level"]))
        .encode("utf-8")).hexdigest()[:16])[:40]
    return entry


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
        self._buttons = []          # keep references alive
        if cfg.get("gpio_enabled"):
            self._setup_gpio(cfg)
        # USB sticks / gamepads
        self.joy_map = {}
        for action, numbers in cfg.get("joy_buttons", {}).items():
            for n in numbers:
                self.joy_map[int(n)] = action
        self.deadzone = cfg.get("joy_deadzone", 0.5)
        self._sticks = {}           # instance id -> Joystick (keep alive)
        self._joy_dir = {}          # (instance id, source) -> held direction
        pygame.joystick.init()
        for i in range(pygame.joystick.get_count()):
            self._add_stick(i)

    def _add_stick(self, index):
        try:
            js = pygame.joystick.Joystick(index)
            js.init()
            if js.get_instance_id() not in self._sticks:
                self._sticks[js.get_instance_id()] = js
                print("Stick connected:", js.get_name())
        except pygame.error as exc:
            print("Could not open stick %d: %s" % (index, exc))

    def _set_dir(self, key, action, presses):
        """Stick moved: release the old direction, press the new one."""
        old = self._joy_dir.get(key)
        if old == action:
            return
        if old:
            self.held.discard(old)
        if action:
            self.held.add(action)
            presses.append(action)
        self._joy_dir[key] = action

    def _joy_event(self, event, presses):
        if event.type == pygame.JOYDEVICEADDED:
            self._add_stick(event.device_index)
        elif event.type == pygame.JOYDEVICEREMOVED:
            self._sticks.pop(event.instance_id, None)
            for key in [k for k in self._joy_dir if k[0] == event.instance_id]:
                self._set_dir(key, None, presses)
        elif event.type == pygame.JOYAXISMOTION and event.axis in (0, 1):
            v = event.value
            if event.axis == 0:
                action = "left" if v < -self.deadzone else "right" if v > self.deadzone else None
            else:
                action = "up" if v < -self.deadzone else "down" if v > self.deadzone else None
            self._set_dir((event.instance_id, "axis%d" % event.axis), action, presses)
        elif event.type == pygame.JOYHATMOTION:
            x, y = event.value
            self._set_dir((event.instance_id, "hatx"),
                          "left" if x < 0 else "right" if x > 0 else None, presses)
            self._set_dir((event.instance_id, "haty"),
                          "up" if y > 0 else "down" if y < 0 else None, presses)
        elif event.type == pygame.JOYBUTTONDOWN:
            action = self.joy_map.get(event.button)
            if action:
                self.held.add(action)
                presses.append(action)
        elif event.type == pygame.JOYBUTTONUP:
            action = self.joy_map.get(event.button)
            if action:
                self.held.discard(action)

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
                # Alt+F4 is the only way out of the game. Most desktops turn it
                # into a QUIT event (above); this catches it when they don't.
                if event.key == pygame.K_F4 and event.mod & pygame.KMOD_ALT:
                    self.quit = True
                action = KEYMAP.get(event.key)
                if action:
                    self.held.add(action)
                    presses.append(action)
            elif event.type == pygame.KEYUP:
                action = KEYMAP.get(event.key)
                if action:
                    self.held.discard(action)
            elif event.type in (pygame.JOYAXISMOTION, pygame.JOYHATMOTION,
                                pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP,
                                pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED):
                self._joy_event(event, presses)
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
GAMES = [("TETRIS", "main"), ("SPACE SHOOTER", "sh_main"), ("SKY HOPPER", "pf_main"),
         ("SABER BRAWL", "fg_main"), ("GLOWBUG", "gb_main"), ("PULSAR", "pu_main"),
         ("STAR TOSS", "st_main")]

# Game modes: (name, what it is). The first one is the normal game. Every
# mode has its own scoreboard (see board_key).
GAME_MODES = {
    "tetris": [("CLASSIC", "THE NORMAL GAME"),
               ("CHAOS", "EVERY BLOCK IS A RANDOM NEW SHAPE!")],
    "shooter": [("CLASSIC", "THE NORMAL GAME"),
                ("BOSS RUSH", "A BOSS FIGHT EVERY WAVE"),
                ("ONE LIFE", "NO EXTRA LIVES")],
    "platformer": [("CLASSIC", "THE NORMAL GAME"),
                   ("TURBO", "THE SCREEN RISES FAST")],
    "fighter": [("CLASSIC", "THE NORMAL GAME"),
                ("GLASS JAW", "EVERY HIT DOES TRIPLE DAMAGE")],
    "glowbug": [("CLASSIC", "THE NORMAL GAME"),
                ("FRENZY", "FAST SPIDERS, ALL AT ONCE")],
    "pulsar": [("CLASSIC", "THE LONGER NOBODY SCORES, THE FASTER THE BALL"),
               ("POWER", "POWER-UP ORBS: HIT THE BALL THROUGH THEM"),
               ("MULTIBALL", "AN EXTRA BALL FOR EVERY 5 POINTS (UP TO 3)"),
               ("SHRINK", "YOUR PADDLE SHRINKS WITH EVERY POINT"),
               ("BRICKS", "BREAK WALLS OF BRICKS - A SMASH PLOWS THROUGH")],
}
# modes that work in multiplayer (the host picks one in the lobby)
MP_MODES = {game: [m for m, _d in modes if not (game == "pulsar" and m == "BRICKS")]
            for game, modes in GAME_MODES.items()}
MP_NOTES = {}

MENU_GAME = {"main": "tetris", "sh_main": "shooter", "pf_main": "platformer",
             "fg_main": "fighter", "gb_main": "glowbug", "pu_main": "pulsar"}

# how each game starts a single player round (used by RANDOM on the start screen)
GAME_STARTS = {"main": "start_game", "sh_main": "start_shooter", "pf_main": "start_platformer",
               "fg_main": "start_fighter", "gb_main": "start_glowbug", "pu_main": "start_pulsar",
               "st_main": "start_toss"}
RANDOM_ITEM = "RANDOM"

# screens that paint their whole background themselves
OWN_BACKGROUND = ("games", "main", "sh_main", "pf_main", "pf_play", "pf_pause", "pf_over",
                  "fg_main", "fg_play", "fg_pause", "fg_over", "fg_help_pause",
                  "gb_main", "gb_play", "gb_pause", "gb_over",
                  "pu_main", "pu_play", "pu_pause", "pu_over",
                  "st_main", "st_play", "st_pause", "st_over")
# screens that show a game: sky behind it, but no neon grid
GAME_VIEWS = ("play", "pause", "gameover", "sh_play", "sh_pause", "sh_over",
              "mp_play", "mp_countdown", "host_watch")

# multiplayer: names and main menus of the games
GAME_TITLES = {"tetris": "TETRIS", "shooter": "SPACE SHOOTER", "platformer": "SKY HOPPER",
               "fighter": "SABER BRAWL", "glowbug": "GLOWBUG", "pulsar": "PULSAR",
               "toss": "STAR TOSS"}
GAME_MENUS = {"tetris": "main", "shooter": "sh_main", "platformer": "pf_main",
              "fighter": "fg_main", "glowbug": "gb_main", "pulsar": "pu_main"}

GUARDED_STATES = ("entry", "gameover", "sh_over", "pf_over", "fg_over", "gb_over", "pu_over", "st_over", "mp_results",
                  "host_results")


class App(ShooterUI, PlatformerUI, FighterUI, GlowbugUI, PulsarUI, TossUI, TitleUI):
    def __init__(self):
        self.cfg = load_config()
        pygame.display.init()
        pygame.font.init()
        self.display = None
        self.rot = 0
        self.apply_display()
        pygame.display.set_caption(ARCADE_NAME.title())
        # everything is drawn on this canvas, then shown (maybe rotated)
        self.canvas = pygame.Surface((W, H)).convert()
        self.screen = self.canvas

        self.font_huge = pygame.font.Font(None, 110)
        self.font_big = pygame.font.Font(None, 60)
        self.font_med = pygame.font.Font(None, 38)
        self.font_small = pygame.font.Font(None, 27)
        self.font_tiny = pygame.font.Font(None, 20)
        self.overlay = pygame.Surface((W, H), pygame.SRCALPHA).convert_alpha()
        self.overlay.fill((2, 6, 18, 215))
        self.sprites = {}
        self.dim_cache = {}
        self.board_bg = None

        self.input = Input(self.cfg)
        self.scores = Scores(SCORES_PATH)
        self.scores_sh = Scores(SCORES_SHOOTER_PATH)
        self.scores_pf = Scores(SCORES_PLATFORMER_PATH)
        self.scores_fg = Scores(SCORES_FIGHTER_PATH)
        self.scores_gb = Scores(SCORES_GLOWBUG_PATH)
        self.scores_pu = Scores(SCORES_PULSAR_PATH)
        self.scores_st = Scores(SCORES_TOSS_PATH)
        # the other game modes: one scoreboard each (highscores_tetris_chaos.json, ...)
        self.mode_idx = {game: 0 for game in GAME_MODES}
        self.mode_boards = {}
        for game, modes in GAME_MODES.items():
            for mode, _desc in modes[1:]:
                key = self.board_key(game, mode)
                self.mode_boards[key] = Scores(os.path.join(BASE_DIR, "highscores_%s.json" % key))
        self.sync = None                  # shared scoreboard (shared_scores.py)
        self.sync_timer = 1000
        if self.cfg.get("shared_scores", True):
            try:
                self.sync = ScoreSync(self.cfg.get("score_group", "nova-arcade"),
                                      self.cfg.get("score_peers", []))
            except OSError as exc:
                print("Shared scores off:", exc)
        self.player_name = mp.clean_name(
            self.cfg.get("player_name") or socket.gethostname())
        self.menus = {
            "games": Menu([name for name, _state in GAMES] + [RANDOM_ITEM]),
            "main": Menu(["SINGLE PLAYER", "MODE", "LEVEL", "MULTIPLAYER",
                          "SCOREBOARD", "BACK"]),
            "pause": Menu(["RESUME", "RESTART", "SCOREBOARD", "MAIN MENU"]),
            "gameover": Menu(["PLAY AGAIN", "SCOREBOARD", "MAIN MENU"]),
            "sh_main": Menu(["SINGLE PLAYER", "MODE", "MULTIPLAYER", "SCOREBOARD",
                             "BACK"]),
            "sh_pause": Menu(["RESUME", "RESTART", "SCOREBOARD", "MAIN MENU"]),
            "sh_over": Menu(["PLAY AGAIN", "SCOREBOARD", "MAIN MENU"]),
            "pf_main": Menu(["SINGLE PLAYER", "MODE", "MULTIPLAYER", "SCOREBOARD", "BACK"]),
            "pf_pause": Menu(["RESUME", "RESTART", "SCOREBOARD", "MAIN MENU"]),
            "pf_over": Menu(["PLAY AGAIN", "SCOREBOARD", "MAIN MENU"]),
            "fg_main": Menu(["SINGLE PLAYER", "MODE", "MULTIPLAYER", "HOW TO PLAY",
                             "SCOREBOARD", "BACK"]),
            "fg_pause": Menu(["RESUME", "RESTART", "HOW TO PLAY", "MAIN MENU"]),
            "fg_over": Menu(["PLAY AGAIN", "SCOREBOARD", "MAIN MENU"]),
            "gb_main": Menu(["SINGLE PLAYER", "MODE", "MULTIPLAYER", "HOW TO PLAY",
                             "SCOREBOARD", "BACK"]),
            "gb_pause": Menu(["RESUME", "RESTART", "SCOREBOARD", "MAIN MENU"]),
            "gb_over": Menu(["PLAY AGAIN", "SCOREBOARD", "MAIN MENU"]),
            "pu_main": Menu(["SINGLE PLAYER", "MODE", "MULTIPLAYER", "SCOREBOARD", "BACK"]),
            "pu_pause": Menu(["RESUME", "RESTART", "SCOREBOARD", "MAIN MENU"]),
            "pu_over": Menu(["PLAY AGAIN", "SCOREBOARD", "MAIN MENU"]),
            "st_main": Menu(["SINGLE PLAYER", "SCOREBOARD", "BACK"]),
            "st_pause": Menu(["RESUME", "RESTART", "SCOREBOARD", "MAIN MENU"]),
            "st_over": Menu(["PLAY AGAIN", "SCOREBOARD", "MAIN MENU"]),
            "mp": Menu(["HOST (SPECTATE)", "PLAY WITHOUT HOST", "JOIN A GAME", "BACK"]),
            "mp_pause": Menu(["RESUME", "LEAVE GAME"]),
            "host_pause": Menu(["RESUME VIEW", "END THIS ROUND", "STOP HOSTING"]),
            "join": Menu(["BACK"]),
        }
        self.games = GAMES                # shown on the start screen (title_ui.py)
        self.roll = None                  # RANDOM: the roulette running on the start screen
        self.start_level = 1
        self.game = None
        self.running = True
        self.state = "games"
        self.state_age = 0
        self.das_dir = 0
        self.das_timer = 0
        self.entry = ["A"] + [" "] * (NAME_LEN - 1)
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
        self.mp_self = False              # "play without host": this Pi hosts AND plays

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
        # On a wide monitor the tall game leaves bars left and right: make the
        # window as wide as the monitor and draw arcade art there instead.
        self.side = 0
        if fullscreen and rot in (0, 180) and self.cfg.get("fill_sides", True):
            dw, dh = self.desktop_size()
            if dw * H > dh * W * 1.02:
                self.side = (int(round(H * dw / float(dh))) - W) // 2
                size = (W + 2 * self.side, H)
        self.__dict__.pop("_sides_key", None)
        self.display = pygame.display.set_mode(size, flags)
        pygame.mouse.set_visible(not fullscreen)

    def desktop_size(self):
        if not hasattr(self, "_desktop"):
            try:
                self._desktop = pygame.display.get_desktop_sizes()[0]
            except (AttributeError, IndexError, pygame.error):
                info = pygame.display.Info()
                self._desktop = (info.current_w, info.current_h)
        return self._desktop

    def present(self):
        if self.side:
            self.draw_sides(self.display, self.side)
        if self.rot == 0:
            self.display.blit(self.canvas, (self.side, 0))
        else:
            self.display.blit(pygame.transform.rotate(self.canvas, self.rot), (self.side, 0))
        pygame.display.flip()

    # -- state helpers
    def set_state(self, name, reset=True):
        self.state = name
        self.state_age = 0
        if reset and name in self.menus:
            self.menus[name].sel = 0

    # -- game modes
    @staticmethod
    def board_key(game, mode="CLASSIC"):
        """Scoreboard name: "tetris" for the normal game, "tetris_chaos" ..."""
        return game if mode == "CLASSIC" else "%s_%s" % (game, mode.lower().replace(" ", ""))

    def board(self, key):
        base = {"tetris": self.scores, "shooter": self.scores_sh, "platformer": self.scores_pf,
                "fighter": self.scores_fg, "glowbug": self.scores_gb, "pulsar": self.scores_pu,
                "toss": self.scores_st}
        return base[key] if key in base else self.mode_boards.get(key, self.scores)

    def mode_of(self, game):
        return GAME_MODES[game][self.mode_idx[game]][0]

    def mode_desc(self, which):
        game = MENU_GAME.get(which)
        return GAME_MODES[game][self.mode_idx[game]][1] if game else ""

    def mode_menu_input(self, which, kind, idx):
        """MODE item: LEFT / RIGHT (or B2) picks the next mode."""
        if self.menus[which].items[idx] != "MODE" or kind not in ("left", "right", "ok"):
            return False
        game = MENU_GAME[which]
        step = -1 if kind == "left" else 1
        self.mode_idx[game] = (self.mode_idx[game] + step) % len(GAME_MODES[game])
        return True

    def finish_run(self, game, g, lines, level, ret):
        """A single player run ended: name entry if it made that mode's top 10."""
        key = self.board_key(game, getattr(g, "mode", "CLASSIC"))
        scores = self.board(key)
        if scores.qualifies(g.score):
            self.entry_ctx = {"scores": scores, "score": g.score, "lines": lines,
                              "level": level, "ret": ret, "game": key}
            self.cursor = 0
            self.set_state("entry")
        else:
            self.set_state(ret)

    def say(self, text, secs=4.0):
        self.notice = (text, time.monotonic() + secs)

    def start_game(self):
        self.game = Tetris(self.start_level, mode=self.mode_of("tetris"))
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
            self.state_age += dt
            self.handle(presses)
            self.update(dt)
            self.draw()
            self.present()
        self.shutdown()

    def shutdown(self):
        if self.sync:
            self.sync.stop()
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
        if self.roll:
            return                        # the roulette is spinning
        r = self.menus["games"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "ok" and idx < len(GAMES):
            self.set_state(GAMES[idx][1])
        elif kind == "ok" and idx == len(GAMES):
            self.start_roll()

    # -- RANDOM: the highlight spins over the game cards, slows down and
    #    stops on a random game, which then starts in single player
    def start_roll(self):
        pick = random.randrange(len(GAMES))
        times, t, gap = [], 0.0, 55.0
        while t < 1300:
            times.append(t)
            t += gap
            gap *= 1.16
        n = len(times)
        steps = [(tt, (pick - (n - 1 - k)) % len(GAMES)) for k, tt in enumerate(times)]
        self.roll = {"t": 0.0, "steps": steps, "pick": pick, "end": t + 450}

    def update_roll(self, dt):
        roll = self.roll
        roll["t"] += dt
        for tt, idx in roll["steps"]:
            if tt <= roll["t"]:
                self.menus["games"].sel = idx
        if roll["t"] >= roll["end"]:
            self.roll = None
            name, state = GAMES[roll["pick"]]
            self.menus["games"].sel = roll["pick"]
            self.set_state(state)                 # BACK from the game leads to its menu
            getattr(self, GAME_STARTS[state])()

    def handle_main(self, presses):
        r = self.menus["main"].handle(presses)
        if not r:
            return
        kind, idx = r
        if self.mode_menu_input("main", kind, idx):
            return
        if idx > 1:
            idx -= 1                      # (item 1 is MODE)
        if kind == "back":
            self.set_state("games", reset=False)
        elif kind == "ok":
            if idx == 0:
                self.start_game()
            elif idx == 2:
                self.mp_game = "tetris"
                self.set_state("mp")
            elif idx == 3:
                self.show_scores("main", game=self.board_key("tetris", self.mode_of("tetris")))
            elif idx == 4:
                self.set_state("games", reset=False)
        elif kind in ("left", "right"):
            if idx == 1:
                step = -1 if kind == "left" else 1
                self.start_level = max(1, min(MAX_START_LEVEL, self.start_level + step))

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
                self.show_scores("pause", game=self.board_key("tetris", self.game.mode))
            elif idx == 3:
                self.set_state("main")

    def handle_gameover(self, presses):
        r = self.menus["gameover"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "ok":
            if idx == 0:
                self.start_game()
            elif idx == 1:
                self.show_scores("gameover", game=self.board_key("tetris", self.game.mode))
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
                self.cursor = min(NAME_LEN - 1, self.cursor + 1)
            elif a == "button2":
                name = " ".join("".join(self.entry).split())
                if not name:
                    self.say("TYPE A NAME FIRST", 2.5)
                    return
                if not is_allowed(name):
                    self.say("THAT NAME IS NOT ALLOWED", 3.0)
                    return
                ctx = self.entry_ctx
                hl = ctx["scores"].add(name, ctx["score"], ctx["lines"], ctx["level"])
                self.sync_timer = 0            # tell the other Pis right away
                self.show_scores(ctx["ret"], highlight=hl, game=ctx["game"])
                return

    # -- multiplayer menu
    def handle_mp(self, presses):
        r = self.menus["mp"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "back" or (kind == "ok" and idx == 3):
            self.set_state(GAME_MENUS.get(self.mp_game, "main"), reset=False)
        elif kind == "ok":
            if idx == 0:
                self.start_hosting()
            elif idx == 1:
                self.start_self_host()
            elif idx == 2:
                self.start_joining()

    # -- play without host: this Pi runs the game server in the background and
    #    joins it itself, so there's no spectator Pi needed.
    def start_self_host(self):
        try:
            self.host = mp.HostSession(self.player_name, self.mp_game)
        except OSError as exc:
            self.host = None
            self.say("COULD NOT START GAME: %s" % exc)
            return
        self.mp_level = self.start_level
        self.mp_init_mode()
        self.mp_self = True
        self.client = mp.ClientSession("127.0.0.1", self.host.port, self.player_name)
        self.set_state("connecting")

    # -- hosting (spectator Pi)
    def start_hosting(self):
        try:
            self.host = mp.HostSession(self.player_name, self.mp_game)
        except OSError as exc:
            self.host = None
            self.say("COULD NOT START HOST: %s" % exc)
            return
        self.mp_level = self.start_level
        self.mp_init_mode()
        self.host_menu_open = False
        self.set_state("host_lobby")

    # -- game modes in multiplayer: the host picks one in the lobby
    def mp_init_mode(self):
        """Start with the mode picked in the game's own menu (if it works online)."""
        game = self.mp_game
        mode = self.mode_of(game) if game in GAME_MODES else "CLASSIC"
        if mode not in MP_MODES.get(game, ["CLASSIC"]):
            mode = "CLASSIC"
        self.host.set_mode(mode)

    def mp_step_mode(self, step):
        modes = MP_MODES.get(self.mp_game, ["CLASSIC"])
        cur = self.host.game_mode
        i = modes.index(cur) if cur in modes else 0
        mode = modes[(i + step) % len(modes)]
        self.host.set_mode(mode)
        names = [m for m, _d in GAME_MODES.get(self.mp_game, [])]
        if mode in names:                          # the game's menu follows along
            self.mode_idx[self.mp_game] = names.index(mode)

    def mode_text(self, game, mode):
        desc = dict(GAME_MODES.get(game, [])).get(mode, "")
        return MP_NOTES.get((game, mode), desc)

    def draw_lobby_mode(self, mode, y, can_change):
        cx = W // 2
        if can_change:
            self.text("MODE  <  %s  >" % mode, self.font_med, GOLD, (cx, y), "center")
        else:
            self.text("MODE:  %s" % mode, self.font_med, GOLD, (cx, y), "center")
        self.text(self.mode_text(self.mp_game, mode), self.font_tiny, (200, 190, 240),
                  (cx, y + 28), "center")

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
            elif a in ("left", "right"):          # LEFT / RIGHT: the game mode
                self.mp_step_mode(-1 if a == "left" else 1)
            elif a == "down" and self.mp_game == "tetris":     # UP / DOWN: Tetris level
                self.mp_level = max(1, self.mp_level - 1)
            elif a == "up" and self.mp_game == "tetris":
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
            return
        if not self.mp_self or not self.host:
            return
        for a in presses:                  # we are the one who starts the round
            if a in ("left", "right"):            # LEFT / RIGHT: the game mode
                self.mp_step_mode(-1 if a == "left" else 1)
            elif a == "down" and self.mp_game == "tetris":     # UP / DOWN: Tetris level
                self.mp_level = max(1, self.mp_level - 1)
            elif a == "up" and self.mp_game == "tetris":
                self.mp_level = min(MAX_START_LEVEL, self.mp_level + 1)
            elif a == "button2":
                if len(self.host.players) < 2:
                    self.say("WAITING FOR OTHER PLAYERS...")
                else:
                    self.host.start_game(self.mp_level if self.mp_game == "tetris" else 1)
                return

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
        if self.mp_game == "fighter":
            self.handle_fighter_mp(presses)
            return
        if self.mp_game in ("glowbug", "pulsar"):
            self.handle_fighter_mp(presses)       # same: B1 = menu, the rest goes to the host
            return
        if self.mp_game == "platformer":
            for a in presses:
                if a == "button1":
                    self.mp_menu_open = True
                    self.menus["mp_pause"].sel = 0
                    return
                if not self.game.game_over:
                    self.game.press(a)
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
            if self.mp_self and self.host and self.host.phase == "results":
                self.host.back_to_lobby()
            if self.client:
                self.set_state("client_lobby")
            else:
                self.set_state("mp", reset=False)

    def leave_client(self):
        if self.client:
            self.client.close()
            self.client = None
        if self.mp_self:                   # our own server goes too
            self.mp_self = False
            self.stop_hosting()

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
        gm = str(msg.get("gm", "CLASSIC"))
        if msg.get("game") == "shooter":
            self.mp_game = "shooter"
            self.game = Shooter(seed, multiplayer=True, mode=gm)
        elif msg.get("game") == "platformer":
            self.mp_game = "platformer"
            self.game = Platformer(seed, mode=gm)
            self.pf_ghosts = {}
        elif msg.get("game") == "fighter":
            self.mp_game = "fighter"
            self.game = self.fg_begin_versus(msg, seed)
        elif msg.get("game") == "glowbug":
            self.mp_game = "glowbug"
            self.game = self.gb_begin_race(msg, seed)
        elif msg.get("game") == "pulsar":
            self.mp_game = "pulsar"
            self.game = self.pu_begin_versus(msg, seed)
        else:
            self.mp_game = "tetris"
            self.game = Tetris(level, seed, mode=gm)
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
            elif kind == "fs":
                if self.mp_game in ("fighter", "glowbug", "pulsar") and self.state in ("mp_play",
                                                                             "mp_countdown"):
                    self.game.apply(msg)
            elif kind == "ghosts":
                if self.mp_game == "platformer" and self.state in ("mp_play", "mp_countdown"):
                    self.pf_take_ghosts(msg.get("p"))
            elif kind == "over":
                if self.state in ("mp_play", "mp_countdown"):
                    ranking = msg.get("ranking", [])
                    self.mp_ranking = ranking if isinstance(ranking, list) else []
                    self.mp_menu_open = False
                    self.set_state("mp_results")

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def sync_scores(self, dt):
        """Shared scoreboard: take in other Pis' scores, send ours now and then."""
        if not self.sync:
            return
        for boards in self.sync.poll():
            for key, board in self.mode_boards.items():
                board.merge(boards.get(key))
            self.scores.merge(boards.get("tetris"))
            self.scores_sh.merge(boards.get("shooter"))
            self.scores_pf.merge(boards.get("platformer"))
            self.scores_fg.merge(boards.get("fighter"))
            self.scores_gb.merge(boards.get("glowbug"))
            self.scores_pu.merge(boards.get("pulsar"))
            self.scores_st.merge(boards.get("toss"))
        self.sync_timer -= dt
        if self.sync_timer <= 0:
            self.sync_timer = 5000
            out = {key: b.entries for key, b in self.mode_boards.items() if b.entries}
            self.sync.send({**out, "tetris": self.scores.entries, "shooter": self.scores_sh.entries,
                            "platformer": self.scores_pf.entries,
                            "fighter": self.scores_fg.entries,
                            "glowbug": self.scores_gb.entries,
                            "pulsar": self.scores_pu.entries,
                            "toss": self.scores_st.entries})

    def update(self, dt):
        self.sync_scores(dt)
        if self.client is not None:
            self.pump_client()
        if self.host is not None:
            self.host.poll()
            if self.state == "host_watch" and self.host.phase == "results":
                self.host_menu_open = False
                self.set_state("host_results")

        s = self.state
        if s == "games" and self.roll:
            self.update_roll(dt)
        if s == "play":
            self.update_single(dt)
        elif s == "sh_play":
            self.update_sh_play(dt)
        elif s == "pf_play":
            self.update_pf_play(dt)
        elif s == "fg_play":
            self.update_fg_play(dt)
        elif s == "gb_play":
            self.update_gb_play(dt)
        elif s == "pu_play":
            self.update_pu_play(dt)
        elif s == "st_play":
            self.update_st_play(dt)
        elif s == "mp_countdown":
            if self.state_age / 1000.0 >= self.countdown:
                self.set_state("mp_play")
        elif s == "mp_play":
            self.update_mp_play(dt)
        elif s == "join":
            self.update_join()
        elif s == "host_watch" and self.host and self.host.game == "platformer":
            self.update_pf_host(dt)
        elif s == "host_watch" and self.host and self.host.game == "fighter" and self.host.fight:
            self.fg_animate(dt, self.host.fight)

    def update_single(self, dt):
        g = self.game
        self.update_piece(dt, True)
        if g.game_over:
            self.finish_run("tetris", g, g.lines, g.level, "gameover")

    def update_mp_play(self, dt):
        if self.mp_game == "shooter":
            self.update_shooter_mp(dt)
            return
        if self.mp_game == "platformer":
            self.update_platformer_mp(dt)
            return
        if self.mp_game == "fighter":
            self.update_fighter_mp(dt)
            return
        if self.mp_game in ("glowbug", "pulsar"):
            self.send_mp_buttons()
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
            # a starship hull panel: metal plate tinted with the piece colour,
            # a glowing light strip in that colour, rivets in the corners
            def mix(a, b, f):
                return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))
            spr = pygame.Surface((size, size)).convert()
            edge = max(1, size // 12)
            plate = mix((84, 90, 104), color, 0.55)
            spr.fill(mix((22, 25, 32), color, 0.15))
            pygame.draw.rect(spr, plate, (edge, edge, size - 2 * edge, size - 2 * edge))
            light = mix(plate, (255, 255, 255), 0.35)
            shade = mix(plate, (0, 0, 0), 0.35)
            pygame.draw.line(spr, light, (edge, edge), (size - edge - 1, edge))
            pygame.draw.line(spr, light, (edge, edge), (edge, size - edge - 1))
            pygame.draw.line(spr, shade, (edge, size - edge - 1), (size - edge - 1, size - edge - 1))
            pygame.draw.line(spr, shade, (size - edge - 1, edge), (size - edge - 1, size - edge - 1))
            if size >= 10:
                sw = max(2, size // 5)
                strip = pygame.Rect(size // 5, size // 2 - sw // 2, size - 2 * (size // 5), sw)
                pygame.draw.rect(spr, mix(plate, color, 0.55), strip.inflate(4, 4), border_radius=2)
                pygame.draw.rect(spr, mix(color, (255, 255, 255), 0.35), strip, border_radius=1)
                if sw >= 4:
                    pygame.draw.line(spr, mix(color, (255, 255, 255), 0.6),
                                     (strip.x + 1, strip.centery), (strip.right - 2, strip.centery))
            if size >= 18:
                r = max(1, size // 18)
                for rx in (edge + 3, size - edge - 4):
                    for ry in (edge + 3, size - edge - 4):
                        pygame.draw.circle(spr, shade, (rx, ry), r + 1)
                        pygame.draw.circle(spr, light, (rx, ry), r)
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
        self.draw_neon_frame(frame.inflate(6, 6), 3, 4)

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
        if item == "MODE" and self.state in MENU_GAME:
            return "MODE  <  %s  >" % self.mode_of(MENU_GAME[self.state])
        if self.state in ("main", "sh_main"):
            if item == "LEVEL":
                return "LEVEL  <  %d  >" % self.start_level
        return item

    def draw_menu(self, menu, title=None, lines=(), top=300, step=68):
        cx = W // 2
        t = time.monotonic()
        if title:
            glow = (255, 60, 90) if title in ("GAME OVER", "YOU ARE OUT!") else NEON_PINK
            img = self.neon_title(title, glow)
            self.screen.blit(img, img.get_rect(center=(cx, 105)))
        for i, line in enumerate(lines):
            self.text(line, self.font_med if i == 0 else self.font_small,
                      GOLD if i == 0 else (190, 180, 230), (cx, 168 + i * 34), "center")
        m = self._menu_assets()
        for i, item in enumerate(menu.items):
            self.draw_menu_button(self.menu_label(i, item), i == menu.sel,
                                  top + i * step, t, m)
        self.text("UP / DOWN : CHOOSE     B2 : OK", self.font_tiny, (200, 190, 240),
                  (cx, H - 22), "center")

    def draw_notice(self):
        text, until = self.notice
        if text and time.monotonic() < until:
            img = self.font_small.render(text, True, (255, 110, 120))
            box = img.get_rect(center=(W // 2, H - 80)).inflate(36, 20)
            self.draw_glass(box, 12, RED)
            self.screen.blit(img, img.get_rect(center=box.center))

    # ------------------------------------------------------------------
    # Drawing screens
    # ------------------------------------------------------------------
    def draw(self):
        fn = getattr(self, "draw_" + self.state, None)
        if self.state in OWN_BACKGROUND:
            pass                            # these paint the whole screen themselves
        else:
            self.draw_backdrop(grid=self.state not in GAME_VIEWS)
        if fn:
            fn()
        self.draw_notice()

    def draw_main(self):
        self.draw_game_menu("main", self.menus["main"], top=345)

    def draw_play(self, extra=None):
        g = self.game
        self.draw_board(g)
        # next piece
        self.draw_glass(pygame.Rect(8, 4, W - 16, 128))
        self.text("NEXT", self.font_small, HUD_LABEL, (20, 12))
        box = pygame.Rect(20, 36, 124, 88)
        pygame.draw.rect(self.screen, (8, 8, 14), box, border_radius=8)
        pygame.draw.rect(self.screen, (75, 60, 130), box, 2, border_radius=8)
        cells = g.next_rots[0]
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
        self.text("SCORE", self.font_small, HUD_LABEL, (175, 12))
        self.text(str(g.score), self.font_med, GOLD, (175, 36))
        self.text("LEVEL", self.font_small, HUD_LABEL, (175, 78))
        self.text(str(g.level), self.font_med, WHITE, (175, 100))
        self.text("LINES", self.font_small, HUD_LABEL, (295, 78))
        self.text(str(g.lines), self.font_med, WHITE, (295, 100))
        if extra:
            label, value = extra
        else:
            label, value = "BEST", str(self.board(self.board_key("tetris", g.mode)).best())
        self.text(label, self.font_small, HUD_LABEL, (410, 78))
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
        key = self.scores_game
        base = key.split("_")[0]
        shooter = base == "shooter"
        platformer = base == "platformer"
        fighter = base == "fighter"
        glowbug = base == "glowbug"
        scores = self.board(key)
        mode = next((m for m, _d in GAME_MODES.get(base, [])
                     if self.board_key(base, m) == key), "CLASSIC")
        img = self.neon_title("SCOREBOARD", (255, 170, 40), color=(255, 240, 200))
        self.screen.blit(img, img.get_rect(center=(cx, 62)))
        self.text(GAME_TITLES.get(base, "TETRIS") + ("" if mode == "CLASSIC" else "  -  " + mode),
                  self.font_small, NEON_CYAN,
                  (cx, 112), "center")
        self.text("NAME", self.font_small, HUD_LABEL, (100, 140))
        self.text("SCORE", self.font_small, HUD_LABEL, (380, 140), "topright")
        self.text("KILLS" if shooter else "METRES" if platformer else "WINS" if fighter else
                  "LEVEL" if glowbug else "POINTS" if base == "pulsar" else
                  "METRES" if base == "toss" else "LINES",
                  self.font_small, HUD_LABEL,
                  (500, 140), "topright")
        if not scores.entries:
            self.draw_glass(pygame.Rect(40, 360, W - 80, 90))
            self.text("NO SCORES YET - GO PLAY!", self.font_med, WHITE, (cx, 405), "center")
        for i, e in enumerate(scores.entries):
            y = 195 + i * 60
            row = pygame.Rect(24, y - 26, W - 48, 52)
            mine = self.highlight is not None and e["id"] == self.highlight
            self.draw_glass(row, 12, None if mine else (55, 45, 100))
            if mine:
                self.draw_neon_frame(row, 3, 12)
            if i < 3:                                   # medals for the top 3
                pygame.draw.circle(self.screen, MEDALS[i], (58, y), 17)
                pygame.draw.circle(self.screen, (255, 255, 255), (58, y), 17, 2)
                self.text(str(i + 1), self.font_small, (40, 20, 40), (58, y + 1), "center")
            else:
                self.text(str(i + 1), self.font_med, (160, 150, 200), (58, y), "center")
            col = MEDALS[i] if i < 3 else WHITE
            self.text(e["name"], self.font_med if len(e["name"]) <= 6 else self.font_small,
                      col, (100, y), "midleft")
            self.text(str(e["score"]), self.font_med, col, (380, y), "midright")
            self.text(str(e["lines"]), self.font_med, (190, 180, 230), (500, y), "midright")
        self.text("B1 / B2 : BACK", self.font_tiny, (200, 190, 240), (cx, H - 22), "center")

    def draw_entry(self):
        cx = W // 2
        t = time.monotonic()
        img = self.neon_title("NEW HIGH SCORE!", (255, 170, 40), 62, (255, 240, 200))
        self.screen.blit(img, img.get_rect(center=(cx, 140 + int(4 * math.sin(t * 2)))))
        self.draw_sparkles(t, 260)
        self.text("SCORE  %d" % self.entry_ctx["score"], self.font_big, GOLD,
                  (cx, 222), "center")
        self.text("ENTER YOUR NAME", self.font_small, NEON_CYAN, (cx, 290), "center")
        bob = int(4 * math.sin(t * 6))
        step = 50
        for i, ch in enumerate(self.entry):
            x = cx + int((i - (NAME_LEN - 1) / 2.0) * step)
            sel = i == self.cursor
            slot = pygame.Rect(0, 0, 44, 70)
            slot.center = (x, 450)
            self.draw_glass(slot, 9, None if sel else (75, 60, 130))
            if sel:
                self.draw_neon_frame(slot, 3, 9)
            if ch == " ":
                pygame.draw.line(self.screen, GOLD if sel else (90, 80, 140),
                                 (x - 10, 468), (x + 10, 468), 3)
            else:
                self.text(ch, self.font_big, GOLD if sel else WHITE, (x, 453), "center")
            if sel:
                pygame.draw.polygon(self.screen, GOLD, [(x - 12, 400 - bob), (x + 12, 400 - bob),
                                                        (x, 386 - bob)])
                pygame.draw.polygon(self.screen, GOLD, [(x - 12, 500 + bob), (x + 12, 500 + bob),
                                                        (x, 514 + bob)])
        name = " ".join("".join(self.entry).split())
        self.text(name or "-", self.font_med, NEON_CYAN, (cx, 565), "center")
        self.draw_glass(pygame.Rect(50, 640, W - 100, 160))
        self.text("UP / DOWN : LETTER", self.font_small, WHITE, (cx, 672), "center")
        self.text("(DOWN FROM A = SPACE)", self.font_tiny, (190, 180, 230), (cx, 700), "center")
        self.text("LEFT / RIGHT : MOVE", self.font_small, WHITE, (cx, 730), "center")
        self.text("B2 : SAVE", self.font_small, GOLD, (cx, 768), "center")

    # -- multiplayer screens
    def draw_mp(self):
        self.draw_menu(self.menus["mp"], "MULTIPLAYER",
                       lines=[GAME_TITLES.get(self.mp_game, "TETRIS"),
                              "PLAY WITH OTHER PIS ON THIS NETWORK",
                              "HOST = SPECTATOR SCREEN, SEES EVERYONE",
                              "PLAY WITHOUT HOST = THIS PI HOSTS AND PLAYS",
                              "JOIN = PLAY AGAINST THE OTHERS"],
                       top=420)

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
        self.text("HOSTING " + GAME_TITLES.get(h.game, "TETRIS").split()[-1],
                  self.font_big, GOLD, (cx, 100), "center")
        self.text("NAME: %s" % h.name, self.font_small, WHITE, (cx, 200), "center")
        self.text("IP: %s" % h.ip, self.font_small, WHITE, (cx, 232), "center")
        self.text("PLAYERS  (%d/%d)" % (len(h.players), h.max_players),
                  self.font_med, GOLD, (cx, 300), "center")
        names = [(p["name"], False) for p in h.players.values()]
        self.draw_roster(names, 345)
        self.draw_lobby_mode(h.game_mode, 728, True)
        if h.game == "tetris":
            self.text("START LEVEL  (UP / DOWN)  %d" % self.mp_level, self.font_small, WHITE,
                      (cx, 796), "center")
        if h.game in ("fighter", "pulsar") and len(h.players) == 1:
            self.text("WAITING FOR A 2ND PLAYER...", self.font_med, GREY, (cx, 840), "center")
        elif h.players:
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
        if h.game == "platformer":
            self.draw_pf_host_watch()
            return
        if h.game == "fighter":
            self.draw_fg_host_watch()
            return
        if h.game == "glowbug":
            self.draw_gb_host_watch()
            return
        if h.game == "pulsar":
            self.draw_pu_host_watch()
            return
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
        self.text("JOIN " + GAME_TITLES.get(self.mp_game, "TETRIS").split()[-1],
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
        if self.mp_self and self.host:
            self.text("YOUR GAME", self.font_big, GREEN, (cx, 100), "center")
            self.text("OTHERS JOIN: MULTIPLAYER > JOIN A GAME > %s" % self.host.name,
                      self.font_tiny, WHITE, (cx, 150), "center")
        else:
            self.text("CONNECTED", self.font_big, GREEN, (cx, 100), "center")
            self.text("HOST: %s" % (c.host_name or "?"), self.font_small, WHITE,
                      (cx, 150), "center")
        self.text("PLAYERS", self.font_med, GOLD, (cx, 230), "center")
        names = [(p.get("name", "?"), p.get("cid") == c.cid) for p in c.roster]
        self.draw_roster(names, 275)
        if self.mp_self and self.host:
            self.draw_lobby_mode(self.host.game_mode, 700, True)
            if self.mp_game == "tetris":
                self.text("START LEVEL  (UP / DOWN)  %d" % self.mp_level, self.font_small, WHITE,
                          (cx, 768), "center")
            if len(self.host.players) >= 2:
                self.text("B2: START GAME", self.font_med, GREEN, (cx, 820), "center")
            else:
                self.text("WAITING FOR OTHER PLAYERS...", self.font_small, WHITE,
                          (cx, 820), "center")
        else:
            self.draw_lobby_mode(c.game_mode, 720, False)
            self.text("WAITING FOR THE HOST TO START...", self.font_small, WHITE,
                      (cx, 800), "center")
        self.text("B1: LEAVE", self.font_small, GREY, (cx, H - 35), "center")

    def draw_mp_countdown(self):
        if self.mp_game == "pulsar":
            self.draw_pulsar_world(self.game)
            return
        if self.mp_game == "glowbug":
            self.draw_glowbug_world(self.game)
            return
        if self.mp_game == "fighter":
            self.draw_fighter_world(self.game)
            return
        if self.mp_game == "platformer":
            self.draw_platformer_world(self.game, mp=True)
        elif self.mp_game == "shooter":
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
        if self.mp_game in ("fighter", "glowbug", "pulsar"):
            if self.mp_game == "fighter":
                self.draw_fighter_world(g)
            elif self.mp_game == "pulsar":
                self.draw_pulsar_world(g)
            else:
                self.draw_glowbug_world(g)
            if self.mp_menu_open:
                self.screen.blit(self.overlay, (0, 0))
                self.draw_menu(self.menus["mp_pause"], "MENU",
                               lines=["THE GAME KEEPS GOING!"], top=330)
            return
        if self.mp_game == "platformer":
            self.draw_platformer_world(g, mp=True)
            if g.game_over and not self.mp_menu_open:
                self.draw_glass(pygame.Rect(40, 395, W - 80, 125), 16, RED)
                self.text("YOU FELL BEHIND!" if g.fell else "YOU ARE OUT!", self.font_big, RED,
                          (W // 2, 440), "center")
                self.text("WATCHING THE OTHERS...", self.font_small, WHITE,
                          (W // 2, 490), "center")
            if self.mp_menu_open:
                self.screen.blit(self.overlay, (0, 0))
                self.draw_menu(self.menus["mp_pause"], "MENU",
                               lines=["THE GAME KEEPS RUNNING!"], top=330)
            return
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
