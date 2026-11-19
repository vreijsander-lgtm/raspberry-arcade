"""
Screens, menus and drawing for Pulsar (the paddle game).
This is a mixin like the other *_ui files: main.py's App inherits from it.

Multiplayer: the host runs pulsar.PulsarVersus and sends snapshots. Player 2
plays the TOP paddle, but sees the field turned round (their paddle at the
bottom), so everything is drawn through fx()/fy() which flip it for them.
"""
import math
import time

import pygame

import pulsar as pu
from common import W, H, WHITE, GOLD, RED

MINE_COL = (80, 170, 255)            # your energy paddle (blue)
OTHER_COL = (255, 70, 70)            # the computer's / the other player's (red)
BALL_COL = (255, 235, 200)
BRICK_COLS = [(255, 90, 90), (255, 160, 60), (245, 220, 80), (110, 225, 110),
              (80, 210, 235), (100, 130, 255), (190, 110, 255)]
POWER_COLS = {"multi": (255, 190, 80), "wide": (90, 200, 255), "fire": (255, 110, 40),
              "freeze": (160, 230, 255), "smash": (255, 240, 120),
              "shield": (180, 140, 255), "life": (255, 110, 170), "mini": (255, 60, 60)}


def _mix(a, b, f):
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


class PulsarUI:
    # ------------------------------------------------------------------
    # Single player flow
    # ------------------------------------------------------------------
    def start_pulsar(self):
        self.game = pu.Pulsar(mode=self.mode_of("pulsar"))
        self.set_state("pu_play")

    def handle_pu_main(self, presses):
        r = self.menus["pu_main"].handle(presses)
        if not r:
            return
        kind, idx = r
        if self.mode_menu_input("pu_main", kind, idx):
            return
        if idx > 1:
            idx -= 1                      # (item 1 is MODE)
        if kind == "back":
            self.set_state("games", reset=False)
        elif kind == "ok":
            if idx == 0:
                self.start_pulsar()
            elif idx == 1:
                self.mp_game = "pulsar"
                self.set_state("mp")
            elif idx == 2:
                self.show_scores("pu_main", game=self.board_key("pulsar", self.mode_of("pulsar")))
            elif idx == 3:
                self.set_state("games", reset=False)

    def handle_pu_play(self, presses):
        if "button1" in presses:          # BUTTON1 = menu (like the others)
            self.set_state("pu_pause")
            return
        self.__dict__.setdefault("_pu_presses", []).extend(presses)

    def handle_pu_pause(self, presses):
        r = self.menus["pu_pause"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "back" or (kind == "ok" and idx == 0):
            self.set_state("pu_play")
        elif kind == "ok":
            if idx == 1:
                self.start_pulsar()
            elif idx == 2:
                self.show_scores("pu_pause", game=self.board_key("pulsar", self.game.mode))
            elif idx == 3:
                self.set_state("pu_main")

    def handle_pu_over(self, presses):
        r = self.menus["pu_over"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "ok":
            if idx == 0:
                self.start_pulsar()
            elif idx == 1:
                self.show_scores("pu_over", game=self.board_key("pulsar", self.game.mode))
            elif idx == 2:
                self.set_state("pu_main")

    def update_pu_play(self, dt):
        g = self.game
        held = self.input.held
        g.update(dt, "left" in held, "right" in held, self.__dict__.pop("_pu_presses", []))
        if g.game_over:
            lines = g.broken if g.mode == "BRICKS" else g.points
            self.finish_run("pulsar", g, lines, g.level, "pu_over")

    # ------------------------------------------------------------------
    # Multiplayer (the host runs the game, see multiplayer.py)
    # ------------------------------------------------------------------
    def pu_begin_versus(self, msg, seed):
        names = msg.get("names")
        sides = msg.get("sides")
        if not (isinstance(names, list) and len(names) == 2):
            names = ["P1", "P2"]
        me = None
        if isinstance(sides, list) and self.client and self.client.cid in sides:
            me = sides.index(self.client.cid)
        self.__dict__["_fg_sent"] = (None, 0.0)
        return pu.PulsarVersus(seed, names, me, mode=str(msg.get("gm", "CLASSIC")))

    def draw_pu_host_watch(self):
        h = self.host
        if h.fight is None:
            return
        self.draw_pulsar_world(h.fight)
        if self.host_menu_open:
            self.screen.blit(self.overlay, (0, 0))
            self.draw_menu(self.menus["host_pause"], "HOST MENU", top=330)

    # ------------------------------------------------------------------
    # Screens
    # ------------------------------------------------------------------
    def draw_pu_main(self):
        self.draw_game_menu("pu_main", self.menus["pu_main"], top=340)

    def draw_pu_play(self):
        self.draw_pulsar_world(self.game)

    def draw_pu_pause(self):
        self.draw_pulsar_world(self.game)
        self.screen.blit(self.overlay, (0, 0))
        self.draw_menu(self.menus["pu_pause"], "PAUSED", top=290)

    def draw_pu_over(self):
        self.draw_pulsar_world(self.game)
        self.screen.blit(self.overlay, (0, 0))
        g = self.game
        if g.mode == "BRICKS":
            line = "WALL  %d      BRICKS  %d" % (g.wall, g.broken)
        else:
            line = "POINTS  %d      BEST RALLY  %d" % (g.points, g.best_rally)
        self.draw_menu(self.menus["pu_over"], "GAME OVER",
                       lines=["SCORE  %d" % g.score, line], top=360)

    # ------------------------------------------------------------------
    # The arena
    # ------------------------------------------------------------------
    def _pu_flip(self, g):
        return g.versus and g.me == 1

    def draw_pulsar_world(self, g):
        scr = self.screen
        t = time.monotonic()
        flip = self._pu_flip(g)

        def fx(x):
            return pu.SW - x if flip else x

        def fy(y):
            return pu.TOP + pu.BOTTOM - y if flip else y

        self.draw_backdrop(grid=False)
        sp = g.speed_frac()
        edge = _mix((60, 110, 200), (255, 120, 60), sp)       # walls warm up with speed
        arena = pygame.Rect(pu.LEFT - 4, pu.TOP, pu.RIGHT - pu.LEFT + 8, pu.BOTTOM - pu.TOP)
        dark = self.__dict__.get("_pu_dark")
        if dark is None:
            dark = self.__dict__["_pu_dark"] = pygame.Surface(arena.size, pygame.SRCALPHA)
            dark.fill((2, 6, 18, 150))
        scr.blit(dark, arena)
        pygame.draw.line(scr, edge, (pu.LEFT - 2, pu.TOP), (pu.LEFT - 2, pu.BOTTOM), 3)
        pygame.draw.line(scr, edge, (pu.RIGHT + 2, pu.TOP), (pu.RIGHT + 2, pu.BOTTOM), 3)
        mid = (pu.TOP + pu.BOTTOM) // 2
        bricks = g.mode == "BRICKS"
        if bricks:
            pygame.draw.line(scr, edge, (pu.LEFT - 2, pu.TOP), (pu.RIGHT + 2, pu.TOP), 3)
            for br in g.bricks:
                self.draw_brick(br)
        else:
            for x in range(pu.LEFT + 6, pu.RIGHT, 28):
                pygame.draw.line(scr, (50, 70, 120), (x, mid), (x + 14, mid), 2)
            pygame.draw.circle(scr, (40, 60, 110), (W // 2, mid), 60, 2)
        # goal glow when someone scores (green = good for you)
        if g.flash:
            kind, left = g.flash
            wy = pu.TOP if kind == "point" else pu.BOTTOM - 6
            if g.versus and g.me is None:
                col = GOLD
            else:
                good = (kind == "point") != flip
                col = (110, 255, 140) if good else (255, 70, 70)
            glow = pygame.Surface((arena.w, 6), pygame.SRCALPHA)
            glow.fill(col + (max(0, int(200 * left / 0.6)),))
            scr.blit(glow, (arena.x, min(fy(wy), fy(wy) - 6 if flip else fy(wy))))
        # paddles: yours is blue (and at the bottom), the other one red;
        # icy while frozen, white while a smash is ready
        bottom_col, top_col = (OTHER_COL, MINE_COL) if flip else (MINE_COL, OTHER_COL)
        icy = POWER_COLS["freeze"]
        if not bricks:
            self.draw_energy_paddle(fx(g.cx), fy(pu.CPU_Y), g.top_w(),
                                    icy if g.freeze_t[1] > 0 else top_col, t,
                                    charged=g.smash2_t > 0 or g.auto_smash[1])
        self.draw_energy_paddle(fx(g.px), fy(pu.PLAYER_Y), g.pad_w(),
                                icy if g.freeze_t[0] > 0 else bottom_col, t,
                                charged=g.smash_t > 0 or g.auto_smash[0])
        if g.versus:                                    # names next to the paddles
            for name, wx, wy, col in ((g.names[1], g.cx, pu.CPU_Y, top_col),
                                      (g.names[0], g.px, pu.PLAYER_Y, bottom_col)):
                mine = g.me is not None and col == MINE_COL
                y = fy(wy)
                self.text("YOU" if mine else name, self.font_tiny, GOLD if mine else col,
                          (int(fx(wx)), int(y + (24 if y > mid else -24))), "center")
        # shields, falling power-ups (BRICKS) and orbs (POWER)
        pulse = 0.6 + 0.4 * math.sin(t * 6)
        for on, wy in ((g.shield, pu.SHIELD_Y), (g.shield2, pu.SHIELD2_Y)):
            if on:
                y = int(fy(wy))
                col = _mix((90, 60, 160), POWER_COLS["shield"], pulse)
                pygame.draw.line(scr, col, (pu.LEFT, y), (pu.RIGHT, y), 4)
                pygame.draw.line(scr, (240, 230, 255), (pu.LEFT, y), (pu.RIGHT, y), 1)
        for d in g.drops:
            self.draw_capsule(d["x"], d["y"], d["kind"], t)
        for o in g.orbs:
            self.draw_orb(fx(o["x"]), fy(o["y"]), o["kind"], t, o.get("age", 0.0))
        # balls (burning while FIRE runs)
        for b in g.balls:
            if bricks and g.fire_t > 0:
                flick = int(4 * math.sin(t * 30))
                self.draw_aura(b["x"], b["y"], pu.BALL_R * 3 + flick, (255, 90, 30), 90)
            self.draw_plasma_ball(b, fx, fy)
        if g.phase == "serve":
            f = g.phase_t / pu.SERVE_TIME
            sy = mid if not bricks else 620
            pygame.draw.circle(scr, BALL_COL, (W // 2, int(fy(sy))), max(2, int(pu.BALL_R * f)))
            self.draw_aura(W // 2, fy(sy), int(26 * f) + 2, (255, 200, 120), 60)
        # effects
        for kind, x, y, age, max_age in g.effects:
            f = age / max_age
            x, y = fx(x), fy(y)
            if kind in ("hit", "cpu", "smash"):
                col = {"hit": bottom_col, "cpu": top_col, "smash": (255, 255, 255)}[kind]
                r = int((10 if kind != "smash" else 16) + 34 * f)
                pygame.draw.circle(scr, _mix(col, (20, 20, 40), f), (int(x), int(y)), r,
                                   max(1, int(4 * (1 - f))))
            elif kind == "wall":
                pygame.draw.circle(scr, _mix(edge, (20, 20, 40), f), (int(x), int(y)), int(6 + 12 * f), 2)
            elif kind == "orb":
                for i in range(10):
                    a = i * math.tau / 10 + f * 2
                    d = 8 + 46 * f
                    pygame.draw.circle(scr, _mix((255, 255, 255), (60, 60, 90), f),
                                       (int(x + math.cos(a) * d), int(y + math.sin(a) * d)),
                                       max(1, int(4 * (1 - f))))
            elif kind == "power":
                pygame.draw.circle(scr, _mix((255, 255, 255), (60, 60, 90), f), (int(x), int(y)),
                                   int(14 + 50 * f), max(1, int(4 * (1 - f))))
            elif kind == "shield":
                pygame.draw.line(scr, _mix((255, 255, 255), (60, 40, 100), f),
                                 (int(x - 80 * (1 - f)), int(y)), (int(x + 80 * (1 - f)), int(y)), 6)
            elif kind in ("brick", "dent"):
                n = 8 if kind == "brick" else 4
                for i in range(n):
                    a = i * math.tau / n + 0.4
                    d = 6 + (40 if kind == "brick" else 16) * f
                    pygame.draw.circle(scr, _mix((255, 230, 180), (40, 30, 60), f),
                                       (int(x + math.cos(a) * d), int(y + math.sin(a) * d)),
                                       max(1, int(4 * (1 - f))))
            else:
                good = (kind == "goal") != flip
                col = (110, 255, 140) if good else (255, 70, 70)
                for i in range(8):
                    a = math.pi * (i / 7.0) * (1 if y < mid else -1)
                    d = 10 + 60 * f
                    pygame.draw.circle(scr, _mix(col, (20, 20, 40), f),
                                       (int(x + math.cos(a) * d), int(y + math.sin(a) * d)),
                                       max(1, int(5 * (1 - f))))
        for text, x, y, age in g.popups:
            self.text(text, self.font_med, GOLD, (int(fx(x)), int(fy(y) - age * 40)), "center")
        self.draw_pulsar_hud(g, t)

    def draw_orb(self, x, y, kind, t, age=0.0):
        """POWER: a floating orb with its power written on it (blinks before it goes)."""
        if age > pu.ORB_LIFE - 2.0 and int(t * 10) % 2:
            return
        col = POWER_COLS[kind]
        r = pu.ORB_R + int(2 * math.sin(t * 5 + x))
        self.draw_aura(x, y, r + 12, col, 55)
        pygame.draw.circle(self.screen, _mix(col, (0, 0, 0), 0.5), (int(x), int(y)), r)
        pygame.draw.circle(self.screen, col, (int(x), int(y)), r - 3)
        pygame.draw.circle(self.screen, (255, 255, 255), (int(x - r * 0.35), int(y - r * 0.35)), 3)
        label = pu.ORBS[kind][0]
        self.text(label, self.font_tiny if len(label) > 3 else self.font_small, (25, 20, 35),
                  (int(x), int(y)), "center")

    def draw_capsule(self, x, y, kind, t):
        """A falling power-up: a glowing pill with its name on it."""
        col = POWER_COLS[kind]
        r = pygame.Rect(0, 0, pu.DROP_W, pu.DROP_H)
        r.center = (int(x), int(y))
        self.draw_aura(x, y, 24, col, 50 if kind != "mini" else 70)
        pygame.draw.rect(self.screen, _mix(col, (0, 0, 0), 0.45), r, border_radius=10)
        pygame.draw.rect(self.screen, col, r.inflate(-4, -4), border_radius=8)
        shine = int((t * 60) % (r.w + 20)) - 10                 # a glint running along it
        if 0 < shine < r.w - 6:
            pygame.draw.line(self.screen, (255, 255, 255), (r.x + shine, r.y + 4),
                             (r.x + shine + 4, r.bottom - 4), 2)
        self.text(pu.POWERUPS[kind][0], self.font_tiny, (25, 20, 35), r.center, "center")

    def draw_brick(self, br):
        r = pygame.Rect(int(br["x"]), int(br["y"]), int(br["w"]), int(br["h"]))
        col = BRICK_COLS[br["row"] % len(BRICK_COLS)]
        if br["max"] > 1:                               # armoured: metal with a coloured core
            pygame.draw.rect(self.screen, (120, 125, 140), r, border_radius=4)
            pygame.draw.rect(self.screen, col, r.inflate(-12, -10), border_radius=3)
            if br["hp"] < br["max"]:                    # cracked after the first hit
                pygame.draw.lines(self.screen, (40, 40, 50), False,
                                  [(r.x + 8, r.y + 3), (r.x + 18, r.centery), (r.x + 12, r.bottom - 3)], 2)
        else:
            pygame.draw.rect(self.screen, _mix(col, (0, 0, 0), 0.35), r, border_radius=4)
            pygame.draw.rect(self.screen, col, r.inflate(-4, -4), border_radius=3)
        pygame.draw.line(self.screen, _mix(col, (255, 255, 255), 0.5), (r.x + 4, r.y + 3),
                         (r.right - 5, r.y + 3), 2)

    def draw_energy_paddle(self, x, y, w, col, t, charged=False):
        r = pygame.Rect(0, 0, int(w), pu.PAD_H)
        r.center = (int(x), int(y))
        glow = pygame.Surface((r.w + 28, r.h + 28), pygame.SRCALPHA)
        pygame.draw.rect(glow, col + (60,), glow.get_rect(), border_radius=16)
        self.screen.blit(glow, (r.x - 14, r.y - 14))
        pygame.draw.rect(self.screen, _mix(col, (0, 0, 0), 0.4), r, border_radius=8)
        inner = r.inflate(-4, -6)
        pygame.draw.rect(self.screen, (255, 255, 255) if charged else col, inner, border_radius=6)
        pygame.draw.line(self.screen, (255, 255, 255), (inner.x + 6, inner.centery),
                         (inner.right - 6, inner.centery), 2)
        for ex in (r.x, r.right):                       # emitters on both ends
            pygame.draw.circle(self.screen, (170, 175, 190), (ex, r.centery), 6)
            pygame.draw.circle(self.screen, col, (ex, r.centery), 3)

    def draw_plasma_ball(self, b, fx=lambda v: v, fy=lambda v: v):
        smash = b.get("smash")
        col = (255, 255, 255) if smash else (255, 190, 90)
        n = len(b["trail"])
        for i, (x, y) in enumerate(b["trail"]):
            f = (i + 1) / float(n + 1)
            self.draw_aura(fx(x), fy(y), max(2, int(pu.BALL_R * f)), col, int(50 * f) + 10)
        x, y = int(fx(b["x"])), int(fy(b["y"]))
        self.draw_aura(x, y, pu.BALL_R * 2 + 4, (255, 160, 70) if not smash else (180, 220, 255), 70)
        pygame.draw.circle(self.screen, BALL_COL, (x, y), pu.BALL_R)
        pygame.draw.circle(self.screen, WHITE, (x - 2, y - 2), pu.BALL_R // 2)

    def draw_pulsar_hud(self, g, t):
        scr = self.screen
        cx = W // 2
        self.draw_glass(pygame.Rect(8, 6, W - 16, 112), 14)
        if g.versus:
            flip = self._pu_flip(g)
            mine, theirs = (g.cpu_points, g.points) if flip else (g.points, g.cpu_points)
            me_name, other = (g.names[1], g.names[0]) if flip else (g.names[0], g.names[1])
            if g.me is None:
                me_name, other = g.names[0], g.names[1]
            self.text(("YOU" if g.me is not None else me_name)[:10], self.font_small,
                      MINE_COL, (22, 16))
            self.text(other[:10], self.font_small, OTHER_COL, (W - 22, 16), "topright")
            self.text("%d : %d" % (mine, theirs), self.font_big, WHITE, (cx, 32), "midtop")
            self.text("FIRST TO %d" % pu.WIN_POINTS, self.font_tiny, (140, 170, 230), (cx, 14), "midtop")
        else:
            self.text("SCORE", self.font_tiny, (140, 170, 230), (22, 14))
            self.text(str(g.score), self.font_big, GOLD, (22, 32))
            if g.mode == "BRICKS":
                self.text("WALL %d" % g.wall, self.font_tiny, (140, 170, 230), (cx, 14), "midtop")
                self.text("%d LEFT" % len(g.bricks), self.font_big, WHITE, (cx, 32), "midtop")
            else:
                self.text("POINTS", self.font_tiny, (140, 170, 230), (cx, 14), "midtop")
                self.text("%d : %d" % (g.points, g.cpu_points), self.font_big, WHITE, (cx, 32), "midtop")
            self.text("LIVES", self.font_tiny, (140, 170, 230), (W - 22, 14), "topright")
            for i in range(pu.START_LIVES):
                col = MINE_COL if i < g.lives else (60, 60, 90)
                pygame.draw.rect(scr, col, (W - 40 - i * 34, 40, 26, 8), border_radius=4)
        # speed meter: fills up the longer nobody scores (not in BRICKS: steady speed)
        if g.mode == "BRICKS":
            self.draw_bricks_bar(g)
            return self.draw_pulsar_messages(g, t)
        self.text("SPEED", self.font_tiny, (140, 170, 230), (22, 98), "midleft")
        bar = pygame.Rect(82, 92, W - 104, 12)
        pygame.draw.rect(scr, (20, 24, 50), bar, border_radius=5)
        f = g.speed_frac()
        if f > 0:
            fill = bar.copy()
            fill.w = max(6, int(bar.w * f))
            pygame.draw.rect(scr, _mix((80, 200, 255), (255, 90, 50), f), fill, border_radius=5)
        pygame.draw.rect(scr, (110, 120, 170), bar, 1, border_radius=5)
        self.text("x%.1f" % (g.ball_speed() / pu.BALL_SPEED), self.font_tiny, WHITE,
                  (bar.right - 6, bar.centery), "midright")
        self.draw_pulsar_messages(g, t)

    def draw_bricks_bar(self, g):
        """BRICKS: instead of a speed bar, how much of the wall is gone."""
        total = max(1, g.wall_size)
        bar = pygame.Rect(82, 92, W - 104, 12)
        self.text("WALL", self.font_tiny, (140, 170, 230), (22, 98), "midleft")
        pygame.draw.rect(self.screen, (20, 24, 50), bar, border_radius=5)
        done = 1 - len(g.bricks) / float(total)
        if done > 0:
            fill = bar.copy()
            fill.w = max(6, int(bar.w * done))
            pygame.draw.rect(self.screen, (120, 230, 140), fill, border_radius=5)
        pygame.draw.rect(self.screen, (110, 120, 170), bar, 1, border_radius=5)

    def draw_pulsar_messages(self, g, t):
        scr = self.screen
        cx = W // 2
        mid = (pu.TOP + pu.BOTTOM) // 2
        first_serve = g.phase == "serve" and g.points == 0 and g.cpu_points == 0 and g.wall <= 1
        if first_serve and not (g.versus and g.me is None):        # (not on the host's view)
            self.draw_glass(pygame.Rect(30, 914, W - 60, 42), 12)
            self.text("LEFT / RIGHT : MOVE      B2 AS IT ARRIVES : SMASH", self.font_tiny, WHITE,
                      (cx, 935), "center")
        if g.mode == "MULTIBALL" and g.phase == "serve" and g.points >= 5:
            n = 1 + min(2, g.points // 5)
            self.text("%d BALLS!" % n, self.font_med, GOLD, (cx, mid - 50), "center")
        if g.mode == "BRICKS" and g.phase == "serve":
            self.text("WALL %d" % g.wall, self.font_big, GOLD, (cx, 560), "center")
        if g.mode in ("BRICKS", "POWER"):               # your running power-ups (bottom right)
            x = W - 20
            mine = 1 if self._pu_flip(g) else 0
            wide, mini = (g.wide2_t, g.mini2_t) if mine else (g.wide_t, g.mini_t)
            for label, left, col in (("WIDE", wide, POWER_COLS["wide"]),
                                     ("MINI", mini, POWER_COLS["mini"]),
                                     ("FIRE", g.fire_t, POWER_COLS["fire"]),
                                     ("FROZEN", g.freeze_t[mine], POWER_COLS["freeze"])):
                if left > 0:
                    self.text("%s %d" % (label, math.ceil(left)), self.font_small, col,
                              (x, 936), "midright")
                    x -= 100
            if len(g.balls) > 1:
                self.text("BALLS x%d" % len(g.balls), self.font_small, POWER_COLS["multi"],
                          (20, 936), "midleft")
        if g.versus and g.phase == "matchover":
            w = g.match_winner()
            if g.me is None:
                title = "%s WINS!" % g.names[w] if w is not None else "DRAW"
            else:
                title = "YOU WIN!" if w == g.me else "YOU LOSE"
            img = self.neon_title(title, (255, 170, 40) if "WIN" in title else (255, 70, 70), 80)
            scr.blit(img, img.get_rect(center=(cx, mid)))

    # ------------------------------------------------------------------
    # The start screen card icon and the menu background
    # ------------------------------------------------------------------
    def draw_pulsar_icon(self, box, t):
        ph = (t * 0.9) % 2.0 if t else 0.6
        up = ph < 1.0
        f = ph if up else 2.0 - ph
        bx = box.x + 20 + (box.w - 40) * (0.5 + 0.4 * math.sin(f * 3.0))
        by = box.bottom - 22 - (box.h - 44) * f
        pygame.draw.rect(self.screen, OTHER_COL, (box.centerx - 18 + int(10 * math.sin(t * 2)), box.y + 10, 36, 6),
                         border_radius=3)
        pygame.draw.rect(self.screen, MINE_COL, (int(bx) - 18, box.bottom - 16, 36, 6), border_radius=3)
        self.draw_aura(bx, by, 9, (255, 160, 70), 80)
        pygame.draw.circle(self.screen, BALL_COL, (int(bx), int(by)), 5)

    def draw_pulsar_scene(self, t):
        """Pulsar menu: a rally between two paddles near the bottom."""
        top, bottom = 700, 800
        ph = (t * 0.8) % 2.0
        f = ph if ph < 1.0 else 2.0 - ph
        bx = W // 2 + 140 * math.sin(t * 1.3)
        by = bottom - 12 - (bottom - top - 24) * f
        self.draw_energy_paddle(W // 2 + 140 * math.sin(t * 1.3 - 0.3), top, 90, OTHER_COL, t)
        self.draw_energy_paddle(W // 2 + 140 * math.sin(t * 1.3 + 0.3), bottom, 90, MINE_COL, t)
        self.draw_plasma_ball({"x": bx, "y": by, "trail": [], "smash": False})
