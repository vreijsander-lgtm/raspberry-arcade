"""
Screens, menus and drawing for Glowbug (the maze game).
This is a mixin like platformer_ui: main.py's App inherits from it, so
everything here can use App's helpers (self.text, self.draw_menu, ...).
"""
import math
import time

import pygame

import glowbug as gb
from common import W, H, WHITE, GOLD, RED

CELL = 31
MAZE_X = (W - gb.COLS * CELL) // 2
MAZE_Y = 136
# neon wall colour per level (repeats)
WALL_COLORS = [(80, 200, 255), (255, 70, 190), (110, 255, 140), (255, 170, 40),
               (170, 110, 255)]
BUG_BODY = (200, 255, 90)
BUG_GLOW = (220, 255, 120)
SPIDER_COLORS = [(185, 90, 255), (255, 85, 60), (50, 220, 200), (255, 195, 40)]
SCARED_BODY = (160, 160, 175)            # pale and trembling
GEM_COLORS = [(255, 90, 160), (90, 220, 255), (150, 255, 110), (255, 210, 70)]
# multiplayer: every player's bug has its own colour
RACE_COLORS = [(200, 255, 90), (90, 220, 255), (255, 120, 200), (240, 240, 255)]


def _mix(a, b, f):
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


def _blur(surf, factor):
    w, h = surf.get_size()
    small = pygame.transform.smoothscale(surf, (max(1, w // factor), max(1, h // factor)))
    return pygame.transform.smoothscale(small, (w, h))


def to_screen(x, y):
    return (MAZE_X + x * CELL + CELL // 2, MAZE_Y + y * CELL + CELL // 2)


class GlowbugUI:
    # ------------------------------------------------------------------
    # Single player flow
    # ------------------------------------------------------------------
    def start_glowbug(self):
        self.game = gb.Glowbug(mode=self.mode_of("glowbug"))
        self.set_state("gb_play")

    def handle_gb_main(self, presses):
        r = self.menus["gb_main"].handle(presses)
        if not r:
            return
        kind, idx = r
        if self.mode_menu_input("gb_main", kind, idx):
            return
        if idx > 1:
            idx -= 1                      # (item 1 is MODE)
        if kind == "back":
            self.set_state("games", reset=False)
        elif kind == "ok":
            if idx == 0:
                self.start_glowbug()
            elif idx == 1:
                self.mp_game = "glowbug"
                self.set_state("mp")
            elif idx == 2:
                self.set_state("gb_help")
            elif idx == 3:
                self.show_scores("gb_main", game=self.board_key("glowbug", self.mode_of("glowbug")))
            elif idx == 4:
                self.set_state("games", reset=False)

    def handle_gb_help(self, presses):
        if any(a in ("button1", "button2") for a in presses):
            self.set_state("gb_main", reset=False)

    def handle_gb_play(self, presses):
        for a in presses:
            if a == "button1":                    # BUTTON1 = menu (like the others)
                self.set_state("gb_pause")
                return
            self.game.press(a)

    def handle_gb_pause(self, presses):
        r = self.menus["gb_pause"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "back" or (kind == "ok" and idx == 0):
            self.set_state("gb_play")
        elif kind == "ok":
            if idx == 1:
                self.start_glowbug()
            elif idx == 2:
                self.show_scores("gb_pause", game=self.board_key("glowbug", self.game.mode))
            elif idx == 3:
                self.set_state("gb_main")

    def handle_gb_over(self, presses):
        r = self.menus["gb_over"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "ok":
            if idx == 0:
                self.start_glowbug()
            elif idx == 1:
                self.show_scores("gb_over", game=self.board_key("glowbug", self.game.mode))
            elif idx == 2:
                self.set_state("gb_main")

    # ------------------------------------------------------------------
    # Multiplayer: the light race (the host runs it, see multiplayer.py)
    # ------------------------------------------------------------------
    def gb_begin_race(self, msg, seed):
        names = msg.get("names")
        sides = msg.get("sides")
        if not (isinstance(names, list) and 1 <= len(names) <= gb.MAX_RACERS):
            names = ["P1", "P2"]
        me = None
        if isinstance(sides, list) and self.client and self.client.cid in sides:
            me = sides.index(self.client.cid)
        self.__dict__["_fg_sent"] = (None, 0.0)
        return gb.GlowRace(seed, [str(n)[:12] for n in names], me, mode=str(msg.get("gm", "CLASSIC")))

    def draw_gb_host_watch(self):
        h = self.host
        if h.fight is None:
            return
        self.draw_glowbug_world(h.fight)
        if self.host_menu_open:
            self.screen.blit(self.overlay, (0, 0))
            self.draw_menu(self.menus["host_pause"], "HOST MENU", top=330)

    def update_gb_play(self, dt):
        g = self.game
        g.update(dt, self.input.held)
        if g.game_over:
            self.finish_run("glowbug", g, g.level, g.level, "gb_over")

    # ------------------------------------------------------------------
    # Screens
    # ------------------------------------------------------------------
    def draw_gb_main(self):
        self.draw_game_menu("gb_main", self.menus["gb_main"], top=340)

    def draw_gb_play(self):
        self.draw_glowbug_world(self.game)

    def draw_gb_pause(self):
        self.draw_glowbug_world(self.game)
        self.screen.blit(self.overlay, (0, 0))
        self.draw_menu(self.menus["gb_pause"], "PAUSED", top=290)

    def draw_gb_over(self):
        self.draw_glowbug_world(self.game)
        self.screen.blit(self.overlay, (0, 0))
        g = self.game
        self.draw_menu(self.menus["gb_over"], "GAME OVER",
                       lines=["SCORE  %d" % g.score, "LEVEL  %d" % g.level], top=360)

    def draw_gb_help(self):
        cx = W // 2
        t = time.monotonic()
        img = self.neon_title("HOW TO PLAY", (150, 255, 90), 74)
        self.screen.blit(img, img.get_rect(center=(cx, 80)))
        box = pygame.Rect(22, 140, W - 44, 600)
        self.draw_glass(box, 16)
        rows = [
            ("STICK", "MOVE (TURN EARLY, IT'S REMEMBERED)"),
            ("B2", "FLASH: STUNS SPIDERS CLOSE BY"),
            ("B1", "MENU"),
        ]
        for i, (k, what) in enumerate(rows):
            y = box.y + 32 + i * 40
            self.text(k, self.font_small, GOLD, (box.x + 22, y), "midleft")
            self.text(what, self.font_small, WHITE, (box.x + 100, y), "midleft")
        y = box.y + 170
        lines = [("EAT EVERY LIGHT TO CLEAR THE MAZE", None),
                 ("SPARKS SCARE THE SPIDERS - CATCH THEM!", "spark"),
                 ("A FLASH CHARGE FOR EVERY 60 LIGHTS", "flash"),
                 ("GRAB THE GEMS FOR BONUS POINTS", "gem")]
        for text, icon in lines:
            if icon == "spark":
                self.draw_light(box.x + 34, y, True, t)
            elif icon == "gem":
                self.draw_gem(box.x + 34, y, 0, t)
            elif icon == "flash":
                pygame.draw.circle(self.screen, BUG_GLOW, (box.x + 34, y), 9, 3)
            else:
                self.draw_light(box.x + 34, y, False, t)
            self.text(text, self.font_small, WHITE, (box.x + 62, y), "midleft")
            y += 44
        y += 20
        self.text("THE SPIDER DROIDS", self.font_med, GOLD, (cx, y), "center")
        y += 46
        info = ["GOES STRAIGHT FOR YOU", "CUTS YOU OFF AHEAD",
                "GUARDS THE SPARKS", "FOLLOWS YOUR TRAIL"]
        for i, (name, what) in enumerate(zip(gb.SPIDERS, info)):
            self.draw_spider_at(box.x + 40, y, SPIDER_COLORS[i], (1, 0), t * 6, scale=0.8)
            self.text(name, self.font_small, SPIDER_COLORS[i], (box.x + 70, y), "midleft")
            self.text(what, self.font_small, WHITE, (box.x + 170, y), "midleft")
            y += 44
        self.text("B1 / B2 : BACK", self.font_tiny, (200, 190, 240), (cx, H - 22), "center")

    # ------------------------------------------------------------------
    # The maze
    # ------------------------------------------------------------------
    def _gb_maze_art(self, g, color=None):
        """The walls of this maze in this level's colour (cached)."""
        color = color or WALL_COLORS[(g.level - 1) % len(WALL_COLORS)]
        cache = self.__dict__.setdefault("_gb_mazes", {})
        key = (g.maze_no, color)
        art = cache.get(key)
        if art is not None:
            return art
        rows = gb.MAZES[g.maze_no]
        w, h = gb.COLS * CELL, gb.ROWS * CELL
        lines = pygame.Surface((w, h), pygame.SRCALPHA)
        fill = pygame.Surface((w, h), pygame.SRCALPHA)

        def wall(x, y):
            return 0 <= y < gb.ROWS and 0 <= x < gb.COLS and rows[y][x] == "#"

        def solid(x, y):                     # wall or nothing: no line on this side
            if not (0 <= y < gb.ROWS and 0 <= x < gb.COLS):
                return True
            return rows[y][x] in "#X"

        ins = 6
        for y in range(gb.ROWS):
            for x in range(gb.COLS):
                if not wall(x, y):
                    continue
                r = pygame.Rect(x * CELL, y * CELL, CELL, CELL)
                pygame.draw.rect(fill, _mix((0, 0, 0), color, 0.13) + (255,), r)
                L, R, T, B = r.left + ins, r.right - ins - 1, r.top + ins, r.bottom - ins - 1
                # a line on every side that faces a corridor; it runs on into
                # neighbouring walls so the outline is one unbroken stroke
                if not solid(x, y - 1):
                    pygame.draw.line(lines, color, (L if not wall(x - 1, y) else r.left, T),
                                     (R if not wall(x + 1, y) else r.right, T), 3)
                if not solid(x, y + 1):
                    pygame.draw.line(lines, color, (L if not wall(x - 1, y) else r.left, B),
                                     (R if not wall(x + 1, y) else r.right, B), 3)
                if not solid(x - 1, y):
                    pygame.draw.line(lines, color, (L, T if not wall(x, y - 1) else r.top),
                                     (L, B if not wall(x, y + 1) else r.bottom), 3)
                if not solid(x + 1, y):
                    pygame.draw.line(lines, color, (R, T if not wall(x, y - 1) else r.top),
                                     (R, B if not wall(x, y + 1) else r.bottom), 3)
        glow = _blur(lines, 4)
        art = pygame.Surface((w, h), pygame.SRCALPHA)
        art.blit(fill, (0, 0))
        for _ in range(2):
            art.blit(glow, (0, 0))
        art.blit(lines, (0, 0))
        # nest door
        for y in range(gb.ROWS):
            for x in range(gb.COLS):
                if rows[y][x] == "-":
                    pygame.draw.rect(art, (255, 150, 220), (x * CELL + 2, y * CELL + CELL // 2 - 2,
                                                            CELL - 4, 5), border_radius=2)
        cache[key] = art
        return art

    def draw_glowbug_world(self, g):
        scr = self.screen
        t = time.monotonic()
        self.draw_backdrop(grid=False)
        if not g.race and g.phase == "clear" and int(g.phase_t * 6) % 2:   # walls blink
            art = self._gb_maze_art(g, (235, 235, 255))
        else:
            art = self._gb_maze_art(g)
        scr.blit(art, (MAZE_X, MAZE_Y))
        # lights
        for y, row in enumerate(g.grid):
            for x, c in enumerate(row):
                if c in ".o":
                    sx, sy = to_screen(x, y)
                    self.draw_light(sx, sy, c == "o", t)
        if g.gem:
            sx, sy = to_screen(g.gem[0], g.gem[1])
            if g.gem[2] > 2 or int(t * 8) % 2:
                self.draw_gem(sx, sy, g.gem[3], t)
        # spiders, then the bug on top
        if g.phase != "clear":
            for s in g.spiders:
                self.draw_spider(g, s, t)
        for b in g.bugs():
            self.draw_bug(g, b, t)
        for kind, x, y, age, max_age in g.effects:
            sx, sy = to_screen(x, y)
            f = age / max_age
            if kind == "caught":                     # race: a bug got caught
                for i in range(8):
                    a = i * math.tau / 8 + f
                    d = 4 + 40 * f
                    pygame.draw.circle(scr, _mix((255, 255, 255), (90, 60, 120), f),
                                       (int(sx + math.cos(a) * d), int(sy + math.sin(a) * d)),
                                       max(1, int(4 * (1 - f))))
            elif kind == "flash":
                r = int(CELL * gb.FLASH_RADIUS * (0.3 + 0.7 * f))
                pygame.draw.circle(scr, _mix((255, 255, 255), BUG_GLOW, f), (sx, sy), r,
                                   max(2, int(10 * (1 - f))))
            else:
                r = int(8 + 26 * f)
                pygame.draw.circle(scr, _mix((255, 255, 255), GOLD, f), (sx, sy), r, 3)
        for text, x, y, age in g.popups:
            sx, sy = to_screen(x, y)
            self.text(text, self.font_small, GOLD, (sx, sy - 14 - int(age * 24)), "center")
        if g.race:
            self.draw_race_hud(g, t)
        else:
            self.draw_glowbug_hud(g, t)

    def draw_light(self, x, y, spark, t):
        if spark:
            r = 7 + int(2 * math.sin(t * 6))
            self.draw_aura(x, y, r + 8, (255, 240, 160), 70)
            pygame.draw.circle(self.screen, (255, 245, 190), (x, y), r)
            pygame.draw.line(self.screen, WHITE, (x - r - 4, y), (x + r + 4, y), 2)
            pygame.draw.line(self.screen, WHITE, (x, y - r - 4), (x, y + r + 4), 2)
        else:
            pygame.draw.circle(self.screen, (255, 230, 170), (x, y), 3)

    def draw_gem(self, x, y, kind, t):
        col = GEM_COLORS[kind % len(GEM_COLORS)]
        bob = int(2 * math.sin(t * 4))
        pts = [(x, y - 11 + bob), (x + 9, y - 3 + bob), (x, y + 11 + bob), (x - 9, y - 3 + bob)]
        self.draw_aura(x, y + bob, 16, col, 60)
        pygame.draw.polygon(self.screen, col, pts)
        pygame.draw.polygon(self.screen, WHITE, pts, 2)
        pygame.draw.line(self.screen, WHITE, (x - 9, y - 3 + bob), (x + 9, y - 3 + bob), 1)

    def draw_bug(self, g, b, t):
        x, y = to_screen(b.x, b.y)
        if g.race:
            if not b.active():
                return
            if b.safe > 0 and int(t * 10) % 2:              # just came back: blinking
                return
            body = RACE_COLORS[b.idx % len(RACE_COLORS)]
            self.draw_bug_at(x, y, b.facing, t, moving=b.dir != (0, 0) and b.freeze <= 0,
                             body=body)
            if b.freeze > 0:                                 # dazzled by a flash
                for k in range(3):
                    a = t * 7 + k * math.tau / 3
                    pygame.draw.circle(self.screen, WHITE, (int(x + math.cos(a) * 14),
                                                            int(y - 14 + math.sin(a) * 4)), 2)
            me = g.me is not None and b.idx == g.me
            label = "YOU" if me else b.name[:8]
            self.text(label, self.font_tiny, GOLD if me else body, (x, y - 24), "center")
            return
        if g.phase == "dying":
            f = min(1.0, g.phase_t / (gb.DEATH_TIME * 0.8))
            for i in range(8):                       # bursts into sparkles
                a = i * math.tau / 8 + f
                d = 4 + 40 * f
                c = _mix(BUG_GLOW, (60, 40, 90), f)
                pygame.draw.circle(self.screen, c, (int(x + math.cos(a) * d),
                                                    int(y + math.sin(a) * d)), max(1, int(4 * (1 - f))))
            if f < 0.5:
                self.draw_bug_at(x, y, b.facing, t, scale=1 - f * 1.6)
            return
        self.draw_bug_at(x, y, b.facing, t, moving=b.dir != (0, 0))

    def draw_bug_at(self, x, y, facing, t, scale=1.0, moving=True, body=BUG_BODY):
        """You: a little hover droid - round metal shell with a glowing ring in
        your colour, one big eye looking where you go and two side fins."""
        scr = self.screen
        s = scale
        glow = _mix(body, (255, 255, 200), 0.3)
        fx, fy = facing
        px, py = -fy, fx                             # sideways
        hover = 1.5 * s * math.sin(t * (14 if moving else 6))
        y = y + hover
        self.draw_aura(x, y, int(22 * s), glow, 45)
        for side in (-1, 1):                         # fins
            fx0 = x + px * side * 10 * s - fx * 2 * s
            fy0 = y + py * side * 10 * s - fy * 2 * s
            tip = (fx0 + px * side * 6 * s - fx * 6 * s, fy0 + py * side * 6 * s - fy * 6 * s)
            pygame.draw.line(scr, (150, 155, 170), (fx0, fy0), tip, max(2, int(4 * s)))
        r = max(3, int(11 * s))
        pygame.draw.circle(scr, (40, 44, 56), (int(x), int(y)), r + 1)
        pygame.draw.circle(scr, (215, 220, 230), (int(x), int(y)), r)
        pygame.draw.circle(scr, body, (int(x), int(y)), r, max(2, int(3 * s)))   # light ring
        ex, ey = int(x + fx * 4 * s), int(y + fy * 4 * s)
        pygame.draw.circle(scr, (20, 26, 40), (ex, ey), max(2, int(5 * s)))
        pygame.draw.circle(scr, glow, (int(ex + fx * s), int(ey + fy * s)), max(1, int(3 * s)))
        pygame.draw.circle(scr, (255, 255, 255), (int(ex + fx * 2 * s), int(ey + fy * 2 * s) - 1),
                           max(1, int(1 * s)))

    def draw_spider(self, g, s, t):
        x, y = to_screen(s.x, s.y)
        if s.state == "home":
            y += int(4 * math.sin(s.bob * 4))
        if s.state == "web":                          # a web ball rolling home
            r = 8
            pygame.draw.circle(self.screen, (230, 230, 250), (x, y), r, 2)
            a = t * 10
            for k in range(3):
                ang = a + k * math.pi / 3
                pygame.draw.line(self.screen, (230, 230, 250),
                                 (x - math.cos(ang) * r, y - math.sin(ang) * r),
                                 (x + math.cos(ang) * r, y + math.sin(ang) * r), 1)
            return
        col = SPIDER_COLORS[s.idx]
        if s.scared:
            flash = g.scare_t < 2.0 and int(t * 8) % 2
            col = (255, 255, 255) if flash else SCARED_BODY
            x += int(1.5 * math.sin(t * 60 + s.idx))                  # trembling
            y += int(1.5 * math.cos(t * 47 + s.idx))
        if s.stun > 0:
            col = _mix(col, (120, 120, 140), 0.6)
        self.draw_spider_at(x, y, col, s.dir if s.dir != (0, 0) else (0, 1), s.walk * 3,
                            scared=s.scared, stunned=s.stun > 0, t=t)

    def draw_spider_at(self, x, y, col, facing, walk, scale=1.0, scared=False, stunned=False, t=0.0):
        """A spider droid: metal legs, an armoured body with a stripe in its
        colour and a red sensor eye."""
        scr = self.screen
        s = scale
        fx, fy = facing
        px, py = -fy, fx
        leg = (120, 125, 140)
        for side in (-1, 1):                         # 4 legs a side, stepping
            for i in range(4):
                along = (i - 1.5) * 4.5 * s
                swing = math.sin(walk + i * 1.7 + (side > 0) * math.pi) * 3 * s
                bx_ = x + fx * along + px * side * 6 * s
                by_ = y + fy * along + py * side * 6 * s
                kx = bx_ + px * side * 8 * s + fx * (along * 0.4 + swing)
                ky = by_ + py * side * 8 * s + fy * (along * 0.4 + swing)
                tx = kx + px * side * 5 * s + fx * (along * 0.5 + swing)
                ty = ky + py * side * 5 * s + fy * (along * 0.5 + swing)
                pygame.draw.lines(scr, leg, False, [(bx_, by_), (kx, ky - 3 * s * (fx != 0)), (tx, ty)],
                                  max(1, int(2 * s)))
                pygame.draw.circle(scr, (70, 74, 86), (int(kx), int(ky)), max(1, int(2 * s)))
        ab = (int(x - fx * 5 * s), int(y - fy * 5 * s))
        metal = (175, 175, 190) if scared else (70, 74, 88)
        pygame.draw.circle(scr, (25, 27, 34), ab, int(10 * s) + 1)
        pygame.draw.circle(scr, metal, ab, int(10 * s))
        pygame.draw.line(scr, col, (ab[0] - px * 8 * s, ab[1] - py * 8 * s),
                         (ab[0] + px * 8 * s, ab[1] + py * 8 * s), max(2, int(4 * s)))
        hd = (int(x + fx * 7 * s), int(y + fy * 7 * s))
        pygame.draw.circle(scr, (25, 27, 34), hd, int(7 * s) + 1)
        pygame.draw.circle(scr, _mix(metal, col, 0.3), hd, int(7 * s))
        eye = (int(hd[0] + fx * 3 * s), int(hd[1] + fy * 3 * s))
        if scared:
            pygame.draw.circle(scr, (120, 120, 140), eye, max(1, int(2 * s)))
        else:
            self.draw_aura(eye[0], eye[1], max(3, int(6 * s)), (255, 50, 50), 70)
            pygame.draw.circle(scr, (255, 60, 60), eye, max(2, int(3 * s)))
            pygame.draw.circle(scr, (255, 220, 210), eye, max(1, int(1 * s)))
        if stunned:                                   # sparks circling
            for k in range(3):
                a = t * 6 + k * math.tau / 3
                pygame.draw.circle(scr, (140, 200, 255), (int(x + math.cos(a) * 13 * s),
                                                          int(y - 12 * s + math.sin(a) * 4 * s)), 2)

    def draw_glowbug_hud(self, g, t):
        cx = W // 2
        self.draw_glass(pygame.Rect(8, 6, W - 16, 112), 14)
        self.text("SCORE", self.font_tiny, (140, 170, 230), (22, 16))
        self.text(str(g.score), self.font_big, GOLD, (22, 34))
        self.text("BEST", self.font_tiny, (140, 170, 230), (cx, 16), "midtop")
        best = self.board(self.board_key("glowbug", g.mode)).best()
        self.text(str(max(g.score, best)), self.font_med, WHITE, (cx, 36), "midtop")
        self.text("LEVEL", self.font_tiny, (140, 170, 230), (W - 22, 16), "topright")
        self.text(str(g.level), self.font_big, WHITE, (W - 22, 34), "topright")
        # lives (little bugs) and flash charges
        for i in range(min(6, max(0, g.lives - 1))):          # spare lives
            self.draw_bug_at(34 + i * 30, 98, (1, 0), 0.0, scale=0.6, moving=False)
        self.text("FLASH", self.font_tiny, (140, 170, 230), (W - 22 - 3 * 24 - 8, 98), "midright")
        for i in range(gb.MAX_FLASH):
            fx = W - 30 - i * 24
            if i < g.flash:
                self.draw_aura(fx, 98, 10, BUG_GLOW, 70)
                pygame.draw.circle(self.screen, BUG_GLOW, (fx, 98), 6)
            else:
                pygame.draw.circle(self.screen, (70, 70, 100), (fx, 98), 6, 2)
        # messages
        my = MAZE_Y + gb.GEM_TILE[1] * CELL + CELL // 2
        if g.phase == "ready":
            self.text("LEVEL %d" % g.level, self.font_med, WHITE, (cx, my - 4), "center")
            self.text("GET READY!", self.font_med, GOLD, (cx, my + 26), "center")
        elif g.phase == "clear":
            self.text("MAZE CLEAR!", self.font_big, GOLD, (cx, my), "center")
        if g.level == 1 and g.phase in ("ready", "play") and g.eaten < 25:
            self.draw_glass(pygame.Rect(30, 812, W - 60, 64), 12)
            self.text("STICK : MOVE      B2 : FLASH (STUN SPIDERS)", self.font_small, WHITE,
                      (cx, 834), "center")
            self.text("BIG SPARKS MAKE THE SPIDERS RUN - CATCH THEM!", self.font_tiny,
                      (200, 190, 240), (cx, 860), "center")

    def draw_race_hud(self, g, t):
        scr = self.screen
        cx = W // 2
        self.draw_glass(pygame.Rect(8, 6, W - 16, 118), 14)
        self.text("ROUND", self.font_tiny, (140, 170, 230), (22, 14))
        self.text("%d / %d" % (g.round_no, gb.RACE_ROUNDS), self.font_med, WHITE, (22, 30))
        sec = int(math.ceil(g.timer))
        self.text(str(sec), self.font_big, WHITE if sec > 10 else (255, 120, 120), (cx, 40), "center")
        self.text("MOST PICKUPS WINS", self.font_tiny, (140, 170, 230),
                  (W - 22, 14), "topright")
        # everybody's pickups (total, this round in brackets), best first
        n = len(g.racers)
        w = (W - 40) // max(1, n)
        for k, i in enumerate(g.standings()):
            b = g.racers[i]
            col = RACE_COLORS[i % len(RACE_COLORS)]
            x0 = 20 + k * w
            me = g.me == i
            if me:
                pygame.draw.rect(scr, (60, 50, 20), (x0 - 4, 70, w - 4, 48), border_radius=8)
            pygame.draw.circle(scr, col, (x0 + 8, 82), 6)
            self.text(("YOU" if me else b.name)[:9], self.font_tiny, GOLD if me else col,
                      (x0 + 20, 82), "midleft")
            self.text(str(b.total), self.font_med, WHITE, (x0 + 4, 104), "midleft")
            self.text("+%d" % b.picks, self.font_tiny, (170, 165, 210), (x0 + w - 12, 106),
                      "midright")
        # my flash charges
        mine = g.mine()
        if mine is not None:
            self.text("FLASH", self.font_tiny, (140, 170, 230), (W - 22 - 3 * 24 - 8, 908), "midright")
            for i in range(gb.MAX_FLASH):
                fx = W - 30 - i * 24
                if i < mine.flash:
                    self.draw_aura(fx, 908, 10, BUG_GLOW, 70)
                    pygame.draw.circle(scr, BUG_GLOW, (fx, 908), 6)
                else:
                    pygame.draw.circle(scr, (70, 70, 100), (fx, 908), 6, 2)
            if not mine.active() and g.phase == "play":
                self.text("CAUGHT! BACK IN A MOMENT...", self.font_small, RED, (cx, 840), "center")
        else:
            self.text("LIVE VIEW", self.font_small, GOLD, (22, 908), "midleft")
        my = MAZE_Y + gb.GEM_TILE[1] * CELL + CELL // 2
        if g.phase == "ready":
            self.text("ROUND %d" % g.round_no, self.font_med, WHITE, (cx, my - 4), "center")
            self.text("GET READY!", self.font_med, GOLD, (cx, my + 26), "center")
            if g.round_no == 1:
                self.draw_glass(pygame.Rect(30, 812, W - 60, 64), 12)
                self.text("EAT MORE LIGHTS THAN THE OTHERS!", self.font_small, WHITE,
                          (cx, 834), "center")
                self.text("B2 FLASH STUNS SPIDERS AND DAZZLES OTHER BUGS", self.font_tiny,
                          (200, 190, 240), (cx, 860), "center")
        elif g.phase in ("roundover", "matchover"):
            self.draw_race_results(g, t)

    def draw_race_results(self, g, t):
        scr = self.screen
        cx = W // 2
        over = g.phase == "matchover"
        scr.blit(self.overlay, (0, 0))
        if over:
            win = g.winners()
            if len(win) > 1:
                title, sub = "DRAW!", " & ".join(b.name for b in win)
            elif g.me is not None and win[0].idx == g.me:
                title, sub = "YOU WIN!", "MOST PICKUPS"
            else:
                title, sub = "%s WINS!" % win[0].name, "MOST PICKUPS"
            img = self.neon_title(title, (255, 170, 40), 84 if len(title) <= 9 else 62,
                                  (255, 240, 200))
        else:
            sub = "TIME UP!" if g.timer <= 0 else "ALL LIGHTS GONE!"
            img = self.neon_title("ROUND %d DONE" % g.round_no, (150, 255, 90), 70)
        scr.blit(img, img.get_rect(center=(cx, 250)))
        self.text(sub, self.font_small, WHITE, (cx, 305), "center")
        box = pygame.Rect(40, 340, W - 80, 70 + 52 * len(g.racers))
        self.draw_glass(box, 16)
        self.text("THIS ROUND", self.font_tiny, (140, 170, 230), (box.right - 130, box.y + 22), "center")
        self.text("TOTAL", self.font_tiny, (140, 170, 230), (box.right - 45, box.y + 22), "center")
        for k, i in enumerate(g.standings()):
            b = g.racers[i]
            y = box.y + 62 + k * 52
            col = RACE_COLORS[i % len(RACE_COLORS)]
            me = g.me == i
            self.text("%d." % (k + 1), self.font_med, GOLD if k == 0 else WHITE, (box.x + 20, y), "midleft")
            self.draw_bug_at(box.x + 72, y, (1, 0), t, scale=0.8, body=col)
            self.text(b.name + ("  (YOU)" if me else ""), self.font_small, GOLD if me else WHITE,
                      (box.x + 98, y), "midleft")
            self.text("+%d" % b.picks, self.font_med, (190, 180, 230), (box.right - 130, y), "center")
            self.text(str(b.total), self.font_med, GOLD, (box.right - 45, y), "center")
        if not over:
            left = gb.RACE_ROUNDS - g.round_no
            self.text("%d ROUND%s TO GO" % (left, "" if left == 1 else "S") if left else
                      "THAT WAS THE LAST ROUND!", self.font_small, (200, 190, 240),
                      (cx, box.bottom + 30), "center")

    # ------------------------------------------------------------------
    # The start screen card icon and the menu background
    # ------------------------------------------------------------------
    def draw_glowbug_icon(self, box, t):
        y = box.centery
        pygame.draw.line(self.screen, (80, 200, 255), (box.x, y - 18), (box.right, y - 18), 2)
        pygame.draw.line(self.screen, (80, 200, 255), (box.x, y + 18), (box.right, y + 18), 2)
        ph = (t * 0.5) % 1.0 if t else 0.4
        bx = box.x - 10 + ph * (box.w + 20)
        for k in range(6):
            lx = box.x + 8 + k * 17
            if lx > bx:
                pygame.draw.circle(self.screen, (255, 230, 170), (lx, y), 3)
        self.draw_spider_at(bx - 34, y, SPIDER_COLORS[1], (1, 0), t * 20, scale=0.75)
        self.draw_bug_at(bx, y, (1, 0), t or 0.3, scale=0.9)

    def draw_glowbug_scene(self, t):
        """Glowbug menu: the bug eating its way across, spiders behind it."""
        y = 790
        pygame.draw.line(self.screen, (60, 120, 170), (0, y - 24), (W, y - 24), 2)
        pygame.draw.line(self.screen, (60, 120, 170), (0, y + 24), (W, y + 24), 2)
        span = W + 260
        bx = (t * 120) % span - 60
        for k in range(18):
            lx = 15 + k * 30
            if lx > bx or bx > span - 80:
                if k % 6 == 3:
                    self.draw_light(lx, y, True, t)
                else:
                    pygame.draw.circle(self.screen, (255, 230, 170), (lx, y), 3)
        for i in range(4):
            self.draw_spider_at(bx - 50 - i * 44, y, SPIDER_COLORS[i], (1, 0), t * 18 + i, scale=1.0)
        self.draw_bug_at(bx, y, (1, 0), t, scale=1.2)
