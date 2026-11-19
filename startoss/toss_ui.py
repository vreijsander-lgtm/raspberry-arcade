"""
Screens, menus and drawing for Star Toss (the throwing game).
This is a mixin like the other *_ui files: main.py's App inherits from it.
"""
import math
import random
import time

import pygame

import toss as ts
from common import W, H, WHITE, GOLD, RED

GROUND_Y = 900                      # screen y of height 0 (when the camera is at the bottom)
HELPER_COL = (80, 220, 170)
GRUMPY_COL = (235, 70, 70)
SUIT_COLS = [(255, 150, 60), (120, 230, 120), (255, 110, 170), (250, 220, 90)]
STAR_COL = (255, 230, 120)
LOW_SKY = (40, 60, 120)
HIGH_SKY = (2, 3, 12)


def _mix(a, b, f):
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


class TossUI:
    # ------------------------------------------------------------------
    # Single player flow
    # ------------------------------------------------------------------
    def start_toss(self):
        self.game = ts.StarToss()
        self.set_state("st_play")

    def handle_st_main(self, presses):
        r = self.menus["st_main"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "back":
            self.set_state("games", reset=False)
        elif kind == "ok":
            if idx == 0:
                self.start_toss()
            elif idx == 1:
                self.show_scores("st_main", game="toss")
            elif idx == 2:
                self.set_state("games", reset=False)

    def handle_st_play(self, presses):
        if "button1" in presses:          # BUTTON1 = menu (like the others)
            self.set_state("st_pause")
            return
        self.__dict__.setdefault("_st_presses", []).extend(presses)

    def handle_st_pause(self, presses):
        r = self.menus["st_pause"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "back" or (kind == "ok" and idx == 0):
            self.set_state("st_play")
        elif kind == "ok":
            if idx == 1:
                self.start_toss()
            elif idx == 2:
                self.show_scores("st_pause", game="toss")
            elif idx == 3:
                self.set_state("st_main")

    def handle_st_over(self, presses):
        r = self.menus["st_over"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "ok":
            if idx == 0:
                self.start_toss()
            elif idx == 1:
                self.show_scores("st_over", game="toss")
            elif idx == 2:
                self.set_state("st_main")

    def update_st_play(self, dt):
        g = self.game
        held = self.input.held
        g.update(dt, "left" in held, "right" in held, "button2" in held,
                 self.__dict__.pop("_st_presses", []))
        if g.game_over:
            self.finish_run("toss", g, sum(g.heights), len(g.heights), "st_over")

    # ------------------------------------------------------------------
    # Screens
    # ------------------------------------------------------------------
    def draw_st_main(self):
        self.draw_game_menu("st_main", self.menus["st_main"], top=380)

    def draw_st_play(self):
        self.draw_toss_world(self.game)

    def draw_st_pause(self):
        self.draw_toss_world(self.game)
        self.screen.blit(self.overlay, (0, 0))
        self.draw_menu(self.menus["st_pause"], "PAUSED", top=290)

    def draw_st_over(self):
        self.draw_toss_world(self.game)
        self.screen.blit(self.overlay, (0, 0))
        g = self.game
        self.draw_menu(self.menus["st_over"], "GAME OVER",
                       lines=["SCORE  %d" % g.score,
                              "THROWS  " + "  +  ".join("%d M" % m for m in g.heights)], top=360)

    # ------------------------------------------------------------------
    # The shaft
    # ------------------------------------------------------------------
    def _st_sky(self, f):
        """Sky colour for a height (0 = ground, 1 = deep space), cached in steps."""
        cache = self.__dict__.setdefault("_st_skies", {})
        k = int(f * 20)
        surf = cache.get(k)
        if surf is None:
            surf = pygame.Surface((W, H)).convert()
            top = _mix(LOW_SKY, HIGH_SKY, min(1.0, (k + 1) / 20.0))
            bottom = _mix(LOW_SKY, HIGH_SKY, k / 20.0)
            for y in range(H):
                pygame.draw.line(surf, _mix(top, bottom, y / float(H)), (0, y), (W, y))
            cache[k] = surf
        return surf

    def draw_toss_world(self, g):
        scr = self.screen
        t = time.monotonic()
        cam = g.cam

        def sy(h):                                    # height -> screen y
            return GROUND_Y - (h - cam)

        f = min(1.0, cam / 9000.0)
        scr.blit(self._st_sky(f), (0, 0))
        # stars appear as you get higher; clouds near the ground
        rng = random.Random(3)
        for _ in range(90):
            x, y0, size = rng.uniform(0, W), rng.uniform(0, 3000), rng.choice((1, 1, 2))
            y = (y0 + cam * 0.08) % 3000 - 1000
            b = int(255 * min(1.0, f * 2.5) * (0.6 + 0.4 * math.sin(t * 2 + x)))
            if 0 <= y < H and b > 10:
                pygame.draw.rect(scr, (b, b, min(255, b + 20)), (int(x), int(y), size, size))
        if cam < 3000:
            a = int(70 * (1 - cam / 3000.0))
            cl = self.__dict__.get("_st_cloud")
            if cl is None:
                cl = self.__dict__["_st_cloud"] = pygame.Surface((180, 50), pygame.SRCALPHA)
                for i in range(5):
                    pygame.draw.circle(cl, (255, 255, 255, 255), (30 + i * 30, 30 - (i % 2) * 8), 20)
            cl.set_alpha(a)
            for k in range(4):
                y = sy(400 + k * 650) * 0.6 + 200
                scr.blit(cl, (int((k * 170 + t * 8) % (W + 180) - 180), int(y)))
            cl.set_alpha(None)
        # the shaft walls with seams, lights and height marks
        for wx0, wx1 in ((0, ts.WALL_L), (ts.WALL_R, W)):
            pygame.draw.rect(scr, (52, 58, 74), (wx0, 0, wx1 - wx0, H))
            pygame.draw.line(scr, (120, 130, 155), (ts.WALL_L if wx0 == 0 else ts.WALL_R, 0),
                             (ts.WALL_L if wx0 == 0 else ts.WALL_R, H), 3)
        seam0 = int(cam // 120) * 120
        for h in range(seam0 - 120, int(cam + H + 240), 120):
            y = sy(h)
            pygame.draw.line(scr, (34, 38, 50), (0, y), (ts.WALL_L, y), 2)
            pygame.draw.line(scr, (34, 38, 50), (ts.WALL_R, y), (W, y), 2)
            on = (h // 120 + int(t * 2)) % 4 == 0
            pygame.draw.circle(scr, (255, 200, 80) if on else (90, 70, 40), (ts.WALL_L - 10, int(y + 60)), 3)
            pygame.draw.circle(scr, (255, 200, 80) if on else (90, 70, 40), (ts.WALL_R + 10, int(y + 60)), 3)
        mark = ts.PX_PER_M * 10
        for h in range(int(cam // mark) * mark, int(cam + H + mark), mark):
            if h <= 0:
                continue
            y = sy(h)
            self.text("%d" % (h // ts.PX_PER_M), self.font_tiny, (200, 210, 230), (ts.WALL_L // 2, int(y)), "center")
            self.text("%d" % (h // ts.PX_PER_M), self.font_tiny, (200, 210, 230), ((ts.WALL_R + W) // 2, int(y)), "center")
        # the best height of this throw: a little flag on the wall
        if g.best_h > 300:
            y = sy(g.best_h)
            if -10 < y < H:
                pygame.draw.line(scr, GOLD, (ts.WALL_R - 26, y), (ts.WALL_R, y), 2)
        # the ground and the launcher
        gy = sy(0)
        if gy < H + 40:
            pygame.draw.rect(scr, (30, 34, 46), (0, gy, W, H))
            pygame.draw.line(scr, (140, 150, 175), (0, gy), (W, gy), 3)
            self.draw_launcher(g, sy, t)
        # helpers, stars, the astronaut
        for hp in g.helpers:
            y = sy(hp["h"])
            if -60 < y < H + 60:
                self.draw_helper(hp, y, t)
        for s in g.stars:
            y = sy(s["h"])
            if -30 < y < H + 30:
                self.draw_bonus_star(s["x"], y, t, 0.0)
        for st in g.stations:
            y = sy(st["h"])
            if -80 < y < H + 80:
                self.draw_station(st, y, t, g)
        if g.phase == "spin":
            hx, hy = g.hub[0], sy(g.hub[1])
            pygame.draw.line(scr, (200, 220, 255), (hx, hy), (g.x, sy(g.h)), 3)
        self.draw_pup(g.x, sy(g.h), g.phase_t * 9 if g.phase == "fly" else g.angle, 0,
                      -g.vh if g.phase == "fly" else -1, t)
        if g.phase == "spin":
            self.draw_throw_arrow(g, sy, t)
        for kind, x, h, age, max_age in g.effects:
            k = age / max_age
            y = sy(h)
            col = {"perfect": (255, 255, 255), "boost": HELPER_COL, "swat": GRUMPY_COL,
                   "star": (255, 230, 120), "release": (180, 220, 255)}.get(kind, WHITE)
            pygame.draw.circle(scr, _mix(col, (20, 20, 40), k), (int(x), int(y)), int(12 + 50 * k),
                               max(1, int(4 * (1 - k))))
        for text, x, h, age in g.popups:
            px = max(110, min(W - 110, int(x)))          # keep it on screen near the walls
            self.text(text, self.font_med, GOLD, (px, int(sy(h) - age * 40)), "center")
        self.draw_toss_hud(g, t)

    def draw_launcher(self, g, sy, t):
        scr = self.screen
        hx, hy = int(ts.HUB[0]), int(sy(ts.HUB[1]))
        base = int(sy(0))
        pygame.draw.polygon(scr, (70, 76, 96), [(hx - 60, base), (hx + 60, base), (hx + 26, hy + 30),
                                                (hx - 26, hy + 30)])
        pygame.draw.polygon(scr, (140, 150, 175), [(hx - 60, base), (hx + 60, base), (hx + 26, hy + 30),
                                                   (hx - 26, hy + 30)], 2)
        pygame.draw.rect(scr, (90, 96, 118), (hx - 14, hy, 28, 34))
        spin = g.angle if g.phase == "spin" and g.hub == ts.HUB else t
        pygame.draw.circle(scr, (60, 64, 80), (hx, hy), 18)
        for k in range(3):                                  # the turning hub
            a = spin + k * math.tau / 3
            pygame.draw.line(scr, (200, 210, 230), (hx, hy), (hx + math.cos(a) * 15, hy + math.sin(a) * 15), 3)
        glow = g.spin_power() if g.phase == "spin" and g.hub == ts.HUB else 0.0
        pygame.draw.circle(scr, _mix((90, 170, 255), (255, 120, 60), glow), (hx, hy), 7)

    def draw_throw_arrow(self, g, sy, t):
        """While spinning: which way it would fly, and how hard (green = up)."""
        dx, up = g.throw_dir()
        x, y = g.x, sy(g.h)
        good = up > 0.85
        col = (110, 255, 140) if good else ((255, 200, 80) if up > 0.3 else (255, 80, 80))
        n = 30 + 60 * g.spin_power()
        ex, ey = x + dx * n, y - up * n
        pygame.draw.line(self.screen, col, (x, y), (ex, ey), 3)
        a = math.atan2(-up, dx)
        pygame.draw.polygon(self.screen, col, [(ex + math.cos(a) * 10, ey + math.sin(a) * 10),
                                               (ex + math.cos(a + 2.5) * 9, ey + math.sin(a + 2.5) * 9),
                                               (ex + math.cos(a - 2.5) * 9, ey + math.sin(a - 2.5) * 9)])
        # power meter
        bar = pygame.Rect(60, H - 44, W - 120, 16)
        pygame.draw.rect(self.screen, (20, 24, 50), bar, border_radius=6)
        p = g.spin_power()
        if p > 0:
            fill = bar.copy()
            fill.w = max(6, int(bar.w * p))
            pygame.draw.rect(self.screen, _mix((90, 200, 255), (255, 110, 60), p), fill, border_radius=6)
        pygame.draw.rect(self.screen, (140, 150, 200), bar, 2, border_radius=6)
        self.text("POWER", self.font_tiny, WHITE, (bar.centerx, bar.centery), "center")

    def draw_station(self, st, y, t, g):
        """A spin station: girders from both walls to a turning hub in the middle."""
        scr = self.screen
        y = int(y)
        cx = W // 2
        active = g.phase == "spin" and g.hub[1] == st["h"]
        col = (255, 200, 80) if not st["used"] or active else (110, 100, 80)
        for x0, x1 in ((ts.WALL_L, cx - 22), (cx + 22, ts.WALL_R)):
            pygame.draw.line(scr, (90, 96, 118), (x0, y), (x1, y), 6)
            for k in range(x0 + 12, x1, 24):                       # truss
                pygame.draw.line(scr, (70, 76, 96), (k, y - 6), (k + 12, y + 6), 2)
        if not st["used"]:                                         # it grabs you anywhere here
            a = 30 + int(25 * (0.5 + 0.5 * math.sin(t * 4)))
            band = pygame.Surface((ts.WALL_R - ts.WALL_L, 8), pygame.SRCALPHA)
            band.fill((255, 200, 80, a))
            scr.blit(band, (ts.WALL_L, y - 4))
        pygame.draw.circle(scr, (40, 44, 58), (cx, y), 22)
        pygame.draw.circle(scr, col, (cx, y), 22, 3)
        spin = g.angle if active else t * 2
        for k in range(3):
            a = spin + k * math.tau / 3
            pygame.draw.line(scr, col, (cx, y), (cx + math.cos(a) * 17, y + math.sin(a) * 17), 3)
        self.text("%d M" % (st["h"] // ts.PX_PER_M), self.font_small, col, (cx, y + 38), "center")

    def draw_pup(self, x, y, spin, look, vy, t, scale=1.0):
        """An astronaut pup: round white suit, a coloured backpack and
        stripes, a big glass helmet with a little face, tumbling as it flies."""
        scr = self.screen
        s = scale
        suit = SUIT_COLS[look % len(SUIT_COLS)]
        x, y = float(x), float(y)
        r = ts.PUP_R * s
        # arms and legs flail (tumbling with the spin)
        for k in range(4):
            a = spin + k * math.pi / 2 + 0.6 * math.sin(t * 9 + k)
            ex, ey = x + math.cos(a) * r * 1.05, y + math.sin(a) * r * 1.05
            pygame.draw.line(scr, (215, 220, 235), (x, y), (ex, ey), max(2, int(6 * s)))
            pygame.draw.circle(scr, suit, (int(ex), int(ey)), max(2, int(4 * s)))
        pygame.draw.circle(scr, (40, 44, 60), (int(x), int(y)), int(r) + 2)
        pygame.draw.circle(scr, (235, 238, 248), (int(x), int(y)), int(r))
        pygame.draw.circle(scr, suit, (int(x), int(y)), int(r), max(2, int(4 * s)))
        # helmet glass with a face (eyes look where it is going)
        hx, hy = int(x), int(y - r * 0.15)
        hr = int(r * 0.62)
        pygame.draw.circle(scr, (30, 60, 110), (hx, hy), hr)
        pygame.draw.circle(scr, (120, 190, 255), (hx, hy), hr, 2)
        look_y = -2 if vy < 0 else 2
        for side in (-1, 1):
            pygame.draw.circle(scr, (255, 255, 255), (hx + side * int(hr * 0.4), hy + look_y), max(1, int(3 * s)))
        pygame.draw.arc(scr, (255, 255, 255), (hx - hr // 3, hy + 1, hr * 2 // 3, hr // 2),
                        math.pi * 1.1 if vy < 0 else 0.2, math.pi * 1.9 if vy < 0 else math.pi - 0.2, 1)
        pygame.draw.circle(scr, (255, 255, 255), (hx - hr // 2, hy - hr // 2), max(1, int(2 * s)))

    def draw_bonus_star(self, x, y, t, age):
        if age > 7.0 and int(t * 10) % 2:                   # blinks before it goes
            return
        r = ts.STAR_R + 3 * math.sin(t * 5)
        self.draw_aura(x, y, int(r + 12), STAR_COL, 50)
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5 + t * 1.5
            d = r if i % 2 == 0 else r * 0.45
            pts.append((x + math.cos(a) * d, y + math.sin(a) * d))
        pygame.draw.polygon(self.screen, STAR_COL, pts)
        pygame.draw.polygon(self.screen, (255, 255, 255), pts, 1)

    def draw_helper(self, hp, y, t):
        """A droid on a ledge in the wall: green helpers throw you up, red grumpy ones swat."""
        scr = self.screen
        left = hp["side"] == 0
        wall = ts.WALL_L if left else ts.WALL_R
        x = ts.HELPER_X[hp["side"]]
        d = 1 if left else -1
        y = int(y)
        pygame.draw.rect(scr, (110, 118, 140), (min(wall, wall + d * 44), y + 14, 44, 8))   # ledge
        col = GRUMPY_COL if hp["kind"] == "grumpy" else HELPER_COL
        if hp["anim"] <= 0:                                           # tired after throwing you
            col = _mix(col, (60, 60, 80), min(0.7, 0.25 * hp.get("uses", 0)))
        body = pygame.Rect(0, 0, 30, 30)
        body.midbottom = (x, y + 14)
        pygame.draw.rect(scr, (30, 34, 46), body.inflate(4, 4), border_radius=9)
        pygame.draw.rect(scr, col, body, border_radius=8)
        # visor eye(s)
        pygame.draw.rect(scr, (20, 26, 40), (body.x + 5, body.y + 7, 20, 9), border_radius=4)
        if hp["kind"] == "grumpy":
            pygame.draw.line(scr, (255, 220, 200), (body.x + 7, body.y + 9), (body.x + 13, body.y + 12), 2)
            pygame.draw.line(scr, (255, 220, 200), (body.right - 7, body.y + 9), (body.right - 13, body.y + 12), 2)
        else:
            pygame.draw.circle(scr, (180, 255, 230), (body.centerx + d * 4, body.y + 11), 3)
        # arms: ready (out towards the shaft), or swinging up after a throw
        up = hp["anim"] > 0
        for k in (-1, 1):
            sx = body.centerx + k * 13
            ex = sx + d * (8 if up else 18)
            ey = body.y - 14 if up else body.y + 12
            pygame.draw.line(scr, (200, 205, 220), (sx, body.y + 14), (ex, ey), 4)
            pygame.draw.circle(scr, col, (int(ex), int(ey)), 4)

    def draw_toss_hud(self, g, t):
        scr = self.screen
        cx = W // 2
        self.draw_glass(pygame.Rect(8, 6, W - 16, 96), 14)
        self.text("THROW", self.font_tiny, (140, 170, 230), (22, 14))
        self.text("%d / %d" % (g.throw_no, ts.THROWS), self.font_med, WHITE, (22, 32))
        self.text("HEIGHT", self.font_tiny, (140, 170, 230), (cx, 14), "midtop")
        self.text("%d M" % max(0, int(g.h / ts.PX_PER_M)), self.font_big, GOLD, (cx, 32), "midtop")
        self.text("SCORE", self.font_tiny, (140, 170, 230), (W - 22, 14), "topright")
        self.text(str(g.score), self.font_med, WHITE, (W - 22, 32), "topright")
        shown = "   ".join("%d M" % m for m in g.heights)
        if shown:
            self.text(shown, self.font_tiny, (190, 180, 230), (22, 86), "midleft")
        if g.phase == "fly" and g.chain >= 1:          # the helper chain and how hard the next throw is
            hot = min(1.0, (g.chain_mult() - 1.0))
            self.text("CHAIN x%d   NEXT THROW +%d%%" % (g.chain, round((g.chain_mult() - 1) * 100)),
                      self.font_small, _mix((140, 255, 200), (255, 140, 60), hot), (W - 22, 86), "midright")
        if g.phase == "spin" and g.hub == ts.HUB:
            if g.throw_no == 1 and g.held_t == 0:
                self.draw_glass(pygame.Rect(30, 130, W - 60, 76), 12)
                self.text("HOLD B2 TO SPIN - LET GO TO THROW", self.font_small, WHITE, (cx, 155), "center")
                self.text("A SLIGHTLY SLANTED THROW REACHES THE HELPERS ON THE WALLS", self.font_tiny,
                          (200, 190, 240), (cx, 184), "center")
        if g.phase == "spin" and g.hub != ts.HUB and g.held_t == 0:
            self.draw_glass(pygame.Rect(30, 130, W - 60, 50), 12)
            self.text("SPIN STATION!  HOLD B2, LET GO TO THROW", self.font_small, GOLD, (cx, 155), "center")
        elif g.phase == "fly" and g.throw_no == 1 and g.best_h < 900:
            self.text("TAP B2 JUST AS A GREEN HELPER GRABS YOU: PERFECT THROW", self.font_tiny,
                      WHITE, (cx, 120), "center")
        elif g.phase == "result":
            box = pygame.Rect(60, 380, W - 120, 120)
            self.draw_glass(box, 16)
            self.text("THROW %d" % g.throw_no, self.font_med, WHITE, (cx, 415), "center")
            self.text("%d M" % (g.heights[-1] if g.heights else 0), self.font_big, GOLD, (cx, 462), "center")

    # ------------------------------------------------------------------
    # The start screen card icon and the menu background
    # ------------------------------------------------------------------
    def draw_toss_icon(self, box, t):
        cx, cy = box.centerx, box.centery + 12
        a = t * 8 if t else 2.6
        px, py = cx + math.cos(a) * 26, cy + math.sin(a) * 26
        pygame.draw.line(self.screen, (200, 220, 255), (cx, cy), (px, py), 2)
        pygame.draw.circle(self.screen, (140, 150, 175), (cx, cy), 6)
        self.draw_pup(px, py, a, 0, -1, t or 0.0, scale=0.6)

    def draw_toss_scene(self, t):
        """Star Toss menu: the launcher spinning a pup near the bottom."""
        cx, cy = W // 2, 740
        a = t * 6
        px, py = cx + math.cos(a) * 70, cy + math.sin(a) * 70
        pygame.draw.polygon(self.screen, (70, 76, 96), [(cx - 60, 830), (cx + 60, 830), (cx + 22, cy + 24),
                                                       (cx - 22, cy + 24)])
        pygame.draw.line(self.screen, (200, 220, 255), (cx, cy), (px, py), 3)
        pygame.draw.circle(self.screen, (90, 96, 118), (cx, cy), 14)
        self.draw_pup(px, py, a, 2, -1, t)
        for side, col in ((-1, HELPER_COL), (1, GRUMPY_COL)):
            hx = cx + side * 190
            pygame.draw.rect(self.screen, col, (hx - 15, 640, 30, 30), border_radius=8)
            pygame.draw.rect(self.screen, (20, 26, 40), (hx - 10, 647, 20, 9), border_radius=4)
