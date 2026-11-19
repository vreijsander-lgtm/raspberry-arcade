"""
Screens, menus and drawing for Sky Hopper (the platformer).
This is a mixin like shooter_ui: main.py's App inherits from it, so everything
here can use App's helpers (self.text, self.draw_menu, self.set_state, ...).
"""
import math
import random
import time

import pygame

try:
    import multiplayer as mp
except ImportError:                          # only needed for multiplayer
    mp = None

import platformer as pf
from common import W, H, WHITE, GREY, GOLD, RED

# sky colours per zone (top, bottom); after the last one they repeat from ZONE_LOOP
ZONE_SKIES = [
    ((40, 20, 90), (235, 105, 140)),     # 1 sunset
    ((22, 14, 72), (150, 60, 165)),      # 2 dusk
    ((8, 6, 40), (62, 26, 112)),         # 3 night
    ((4, 18, 40), (26, 110, 120)),       # 4 aurora
    ((3, 2, 14), (24, 6, 40)),           # 5 space
]
ZONE_LOOP = 2

PLAT_COLORS = {                           # (top, body, edge)
    "normal": ((140, 255, 150), (60, 175, 105), (25, 90, 70)),
    "move": ((255, 170, 230), (225, 70, 170), (110, 25, 90)),
    "crumble": ((255, 210, 130), (215, 125, 50), (110, 55, 20)),
    "floor": ((150, 120, 255), (55, 40, 110), (25, 18, 60)),
}
HOPPER_SUIT = (255, 150, 50)
# multiplayer: every player gets their own colour (by player number)
GHOST_SUITS = [(255, 150, 50), (90, 200, 255), (130, 235, 110), (255, 95, 170),
               (190, 140, 255), (255, 225, 80), (90, 230, 200), (240, 240, 250)]
GHOST_ALPHA = 120                         # how see-through the other players are
GHOST_RATE = 1 / 15.0                     # seconds between position updates we send


def _mix(a, b, f):
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


class PlatformerUI:
    # ------------------------------------------------------------------
    # Single player flow
    # ------------------------------------------------------------------
    def start_platformer(self):
        self.game = pf.Platformer(mode=self.mode_of("platformer"))
        self.__dict__.pop("_pf_fade", None)
        self.set_state("pf_play")

    def handle_pf_main(self, presses):
        r = self.menus["pf_main"].handle(presses)
        if not r:
            return
        kind, idx = r
        if self.mode_menu_input("pf_main", kind, idx):
            return
        if idx > 1:
            idx -= 1                      # (item 1 is MODE)
        if kind == "back":
            self.set_state("games", reset=False)
        elif kind == "ok":
            if idx == 0:
                self.start_platformer()
            elif idx == 1:
                self.mp_game = "platformer"
                self.set_state("mp")
            elif idx == 2:
                self.show_scores("pf_main", game=self.board_key("platformer", self.mode_of("platformer")))
            elif idx == 3:
                self.set_state("games", reset=False)

    def handle_pf_play(self, presses):
        for a in presses:
            if a == "button1":                   # BUTTON1 = menu (like the others)
                self.set_state("pf_pause")
                return
            self.game.press(a)

    def handle_pf_pause(self, presses):
        r = self.menus["pf_pause"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "back" or (kind == "ok" and idx == 0):
            self.set_state("pf_play")
        elif kind == "ok":
            if idx == 1:
                self.start_platformer()
            elif idx == 2:
                self.show_scores("pf_pause", game=self.board_key("platformer", self.game.mode))
            elif idx == 3:
                self.set_state("pf_main")

    def handle_pf_over(self, presses):
        r = self.menus["pf_over"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "ok":
            if idx == 0:
                self.start_platformer()
            elif idx == 1:
                self.show_scores("pf_over", game=self.board_key("platformer", self.game.mode))
            elif idx == 2:
                self.set_state("pf_main")

    def update_pf_play(self, dt):
        g = self.game
        held = self.input.held
        g.update(dt, "left" in held, "right" in held,
                 "button2" in held or "up" in held)
        if g.game_over:
            self.finish_run("platformer", g, g.meters, g.zone, "pf_over")

    # ------------------------------------------------------------------
    # Drawing: menus
    # ------------------------------------------------------------------
    def draw_pf_main(self):
        self.draw_game_menu("pf_main", self.menus["pf_main"], top=330)

    def draw_pf_play(self):
        self.draw_platformer_world(self.game)

    def draw_pf_pause(self):
        self.draw_platformer_world(self.game)
        self.screen.blit(self.overlay, (0, 0))
        self.draw_menu(self.menus["pf_pause"], "PAUSED", top=290)

    def draw_pf_over(self):
        self.draw_platformer_world(self.game)
        self.screen.blit(self.overlay, (0, 0))
        self.draw_menu(self.menus["pf_over"], "GAME OVER",
                       lines=["SCORE  %d" % self.game.score,
                              "HEIGHT  %d M" % self.game.meters], top=360)

    # ------------------------------------------------------------------
    # Drawing: the world
    # ------------------------------------------------------------------
    def _pf_assets(self):
        a = self.__dict__.get("_pf_art")
        if a:
            return a
        a = {"skies": {}}
        # soft clouds (a few sizes)
        clouds = []
        for w, h in ((150, 46), (210, 60), (120, 38)):
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            for i in range(5):
                cx = int(w * (0.2 + 0.15 * i))
                r = int(h * (0.35 + 0.15 * math.sin(i * 1.7) ** 2))
                pygame.draw.circle(s, (255, 255, 255, 34), (cx, h - r), r)
            pygame.draw.ellipse(s, (255, 255, 255, 30), (0, h // 2, w, h // 2))
            clouds.append(s)
        a["clouds"] = clouds
        rng = random.Random(5)
        a["stars"] = [(rng.uniform(0, W), rng.uniform(0, 1400), rng.choice((1, 1, 2)),
                       rng.randint(120, 255)) for _ in range(110)]
        # red danger glow along the bottom of the screen
        glow = pygame.Surface((W, 70), pygame.SRCALPHA)
        for y in range(70):
            f = y / 69.0
            pygame.draw.line(glow, (255, 50, 90, int(150 * f ** 2)), (0, y), (W, y))
        a["danger"] = glow
        self.__dict__["_pf_art"] = a
        return a

    def _pf_sky(self, zone):
        a = self._pf_assets()
        n = len(ZONE_SKIES)
        idx = zone - 1 if zone <= n else ZONE_LOOP + (zone - 1 - ZONE_LOOP) % (n - ZONE_LOOP)
        sky = a["skies"].get(idx)
        if sky is None:
            top, bottom = ZONE_SKIES[idx]
            sky = pygame.Surface((W, H)).convert()
            for y in range(H):
                pygame.draw.line(sky, _mix(top, bottom, y / float(H)), (0, y), (W, y))
            a["skies"][idx] = sky
        return sky

    def draw_platformer_world(self, g, mp=False, spectator=False):
        """mp: also draw the other players as ghosts and the race ranking.
        spectator: the host's view - every player drawn, no own player."""
        scr = self.screen
        a = self._pf_assets()
        t = time.monotonic()
        cam = round(g.cam_y)         # whole pixels: the world scrolls as one piece

        # sky: cross-fade to the new colours when a zone starts
        fade = self.__dict__.get("_pf_fade")
        if fade is None or fade[0] is not g:
            fade = self.__dict__["_pf_fade"] = [g, g.zone, g.zone, 0.0]
        if fade[2] != g.zone:
            fade[1], fade[2], fade[3] = fade[2], g.zone, t
        scr.blit(self._pf_sky(g.zone), (0, 0))
        if t - fade[3] < 1.5 and fade[1] != fade[2]:
            old = self._pf_sky(fade[1])
            old.set_alpha(int(255 * (1 - (t - fade[3]) / 1.5)))
            scr.blit(old, (0, 0))
            old.set_alpha(None)

        # stars (brighter higher up), then clouds - both slower than the world
        star_f = min(1.0, 0.25 + 0.25 * (g.zone - 1))
        for sx, sy, size, br in a["stars"]:
            y = (sy - cam * 0.12) % 1400 - 220
            if 0 <= y < H:
                b = int(br * star_f * (0.7 + 0.3 * math.sin(t * 2.3 + sx)))
                pygame.draw.rect(scr, (b, b, min(255, b + 25)), (int(sx), int(y), size, size))
        clouds = a["clouds"]
        span = 6 * 230
        for k in range(6):
            y = (k * 230 - cam * 0.35) % span - 120
            x = (k * 197 + 40 * math.sin(k * 2.1 + t * 0.15)) % (W + 100) - 100
            scr.blit(clouds[k % 3], (int(x), int(y)))

        # the world
        for p in g.plats:
            self.draw_platform(p, cam, t)
        for s in g.springs:
            p = s["p"]
            self.draw_spring(p["x"] + s["off"], p["y"] - cam, s["t"] > 0)
        for e in g.enemies:
            if e["k"] == "walker":
                self.draw_walker(e, cam)
            else:
                self.draw_flyer(e, cam)
        for x, y, age, max_age, color in g.effects:
            r = int(6 + 30 * age / max_age)
            pygame.draw.circle(scr, color, (int(x), int(y - cam)), r, 3)

        if mp:
            self.draw_pf_ghosts(cam, spectator)
        if spectator:
            self.draw_pf_race(None)
            return

        # the player (glowing while spring-powered)
        if g.powered and not g.dead:
            px, py = int(g.x + pf.PW / 2), int(g.y + pf.PH / 2 - cam)
            self.draw_aura(px, py, 34, (120, 255, 200), 60)
            pygame.draw.circle(scr, (120, 255, 200), (px, py), 34 + int(3 * math.sin(t * 20)), 2)
            for i in range(1, 4):                            # speed streaks below
                pygame.draw.line(scr, (180, 255, 225), (px - 10 + i * 5, py + 30 + i * 6),
                                 (px - 10 + i * 5, py + 50 + i * 10), 2)
        blink = g.invuln > 0 and int(g.invuln * 12) % 2 == 0
        if not blink and not (g.dead and g.fell):
            self.draw_hopper(g.x + pf.PW / 2, g.y + pf.PH - cam, g.face,
                             0.0 if g.dead else g.squash,
                             g.run_t if g.ground is not None else None,
                             dead=g.dead, air=g.ground is None, suit=self.pf_my_suit(mp))
        for x, y, text, age in g.popups:
            self.text(text, self.font_small, GOLD, (int(x), int(y - cam)), "center")

        if g.mode == "LIGHTS OUT" and not g.dead:     # only a light around you
            self.draw_darkness(g.x + pf.PW / 2, g.y + pf.PH / 2 - cam, 135)
        if g.scroll_speed() > 0:                 # the bottom is dangerous
            pulse = 0.6 + 0.4 * math.sin(t * 5)
            glow = a["danger"]
            glow.set_alpha(int(255 * pulse))
            scr.blit(glow, (0, H - 70))
            glow.set_alpha(None)
        self.draw_platformer_hud(g)
        if mp:
            self.draw_pf_race(g)

    def draw_platformer_hud(self, g):
        scr = self.screen
        self.draw_glass(pygame.Rect(8, 6, W - 16, 66), 14)
        self.text("SCORE", self.font_tiny, (140, 170, 230), (22, 14))
        self.text(str(g.score), self.font_med, GOLD, (22, 30))
        self.text("HEIGHT", self.font_tiny, (140, 170, 230), (170, 14))
        self.text("%d M" % g.meters, self.font_med, WHITE, (170, 30))
        self.text("ZONE", self.font_tiny, (140, 170, 230), (300, 14))
        self.text(str(g.zone), self.font_med, WHITE, (300, 30))
        for i in range(pf.START_HEARTS):
            self.draw_heart(W - 36 - i * 38, 39, i < g.hearts)
        if g.meters < 3 and not g.dead:
            self.text("B2 / UP : JUMP  (HOLD = HIGHER)", self.font_small, WHITE,
                      (W // 2, 112), "center")
            self.text("DOWN : DROP THROUGH", self.font_tiny, (220, 215, 255),
                      (W // 2, 140), "center")
        if g.banner:
            img = self.neon_title(g.banner[0], (120, 255, 160), 84)
            scr.blit(img, img.get_rect(center=(W // 2, 300)))

    def pf_my_suit(self, mp=False):
        """Our colour: orange alone, our player colour in multiplayer."""
        if mp and self.client and self.client.cid:
            return GHOST_SUITS[(self.client.cid - 1) % len(GHOST_SUITS)]
        return HOPPER_SUIT

    def draw_heart(self, x, y, full):
        col = (255, 70, 110) if full else (70, 60, 100)
        pygame.draw.circle(self.screen, col, (x - 7, y - 4), 8)
        pygame.draw.circle(self.screen, col, (x + 7, y - 4), 8)
        pygame.draw.polygon(self.screen, col, [(x - 15, y - 1), (x + 15, y - 1), (x, y + 15)])
        if full:
            pygame.draw.circle(self.screen, (255, 190, 210), (x - 9, y - 7), 3)

    def draw_platform(self, p, cam, t):
        y = p["y"] - cam
        if y < -30 or y > H + 10:
            return
        scr = self.screen
        top, body, edge = PLAT_COLORS[p["kind"]]
        x, w = p["x"], p["w"]
        if p["kind"] == "crumble" and p["crumble"] >= 0 and p["fall"] == 0:
            x += 3 * math.sin(t * 60)                       # shaking
        if p["kind"] == "floor":
            rect = pygame.Rect(int(x), int(y), int(w), H)
            pygame.draw.rect(scr, body, rect)
            pygame.draw.line(scr, top, (0, int(y)), (W, int(y)), 4)
            for gx in range(0, W, 45):
                pygame.draw.line(scr, edge, (gx, int(y) + 22), (gx + 20, int(y) + 22), 3)
            return
        rect = pygame.Rect(int(x), int(y), int(w), pf.PLAT_H)
        pygame.draw.rect(scr, edge, rect.move(0, 3), border_radius=8)
        pygame.draw.rect(scr, body, rect, border_radius=8)
        pygame.draw.rect(scr, top, (rect.x + 3, rect.y + 2, rect.w - 6, 5), border_radius=3)
        if p["kind"] == "move":                             # arrows = it moves
            cy = rect.centery + 2
            for sx, d in ((rect.x + 12, -1), (rect.right - 12, 1)):
                pygame.draw.polygon(scr, top, [(sx + d * 5, cy), (sx - d * 2, cy - 4),
                                               (sx - d * 2, cy + 4)])
        elif p["kind"] == "crumble":                        # cracks
            for i in range(1, int(w // 40) + 1):
                cx = rect.x + i * w / (int(w // 40) + 1)
                pygame.draw.lines(scr, edge, False, [(cx, rect.y + 6), (cx - 4, rect.y + 11),
                                                     (cx + 2, rect.bottom - 1)], 2)
        else:                                               # little studs
            for i in range(int(w // 34)):
                pygame.draw.circle(scr, edge, (int(rect.x + 17 + i * 34), rect.y + 12), 2)

    def draw_spring(self, x, y, fired):
        scr = self.screen
        x, y = int(x), int(y)
        hgt = 24 if fired else 13
        pygame.draw.rect(scr, (90, 90, 120), (x + 2, y - 4, 26, 4))
        pts = []
        for i in range(7):
            pts.append((x + (6 if i % 2 else 24), y - 4 - i * (hgt - 4) / 6.0))
        pygame.draw.lines(scr, (200, 210, 230), False, pts, 3)
        pygame.draw.rect(scr, (120, 255, 200), (x, y - hgt - 5, 30, 6), border_radius=3)
        pygame.draw.rect(scr, WHITE, (x + 3, y - hgt - 5, 24, 2))

    def draw_walker(self, e, cam):
        scr = self.screen
        x, y = int(e["x"]), int(e["y"] - cam)
        if y < -40 or y > H + 10:
            return
        w, h = pf.WALKER_W, pf.WALKER_H
        if e["dead"] > 0:                                   # squashed flat
            pygame.draw.ellipse(scr, (120, 60, 200), (x - 4, y + h - 9, w + 8, 9))
            return
        step = math.sin(e["t"] * 12)
        for fx in (x + 7, x + w - 13):                      # feet
            pygame.draw.ellipse(scr, (60, 25, 110),
                                (fx + int(3 * step * (1 if fx < x + 15 else -1)), y + h - 7, 10, 7))
        body = pygame.Rect(x, y + 2, w, h - 5)
        pygame.draw.ellipse(scr, (150, 70, 255), body)
        pygame.draw.ellipse(scr, (190, 130, 255), body, 2)
        look = 3 * e["dir"]
        for ex in (x + 11, x + 23):                          # angry eyes
            pygame.draw.circle(scr, WHITE, (ex, y + 14), 5)
            pygame.draw.circle(scr, (20, 10, 30), (ex + look, y + 15), 2)
        pygame.draw.line(scr, (40, 10, 70), (x + 6, y + 7), (x + 15, y + 10), 2)
        pygame.draw.line(scr, (40, 10, 70), (x + 28, y + 7), (x + 19, y + 10), 2)

    def draw_flyer(self, e, cam):
        scr = self.screen
        x, y = int(e["x"]), int(e["y"] - cam)
        if y < -40 or y > H + 10:
            return
        w, h = pf.FLYER_W, pf.FLYER_H
        cx, cy = x + w // 2, y + h // 2
        if e["dead"] > 0:
            pygame.draw.circle(scr, (120, 40, 50), (cx, cy + int(e["dead"] * 200)), 8)
            return
        flap = math.sin(e["t"] * 16)
        for side in (-1, 1):
            tip = (cx + side * 26, cy - 6 - int(10 * flap))
            pygame.draw.polygon(scr, (110, 30, 60), [(cx + side * 5, cy - 4), tip,
                                                     (cx + side * 20, cy + 6)])
        pygame.draw.circle(scr, (210, 60, 90), (cx, cy), 11)
        pygame.draw.circle(scr, (255, 130, 150), (cx, cy), 11, 2)
        pygame.draw.circle(scr, (255, 240, 120), (cx + 4 * e["dir"], cy - 2), 3)

    def draw_hopper(self, x, y, face=1, squash=0.0, run_t=None, dead=False, air=False, scale=1.0,
                    suit=HOPPER_SUIT):
        """The player: a little scout droid - an egg-shaped metal body with a
        coloured panel (suit), a glowing visor eye, an antenna and a jet pack
        that fires while it is in the air. x, y = middle of the feet (bottom)."""
        scr = self.screen
        s = scale
        t = time.monotonic()
        bw = pf.PW * s * (1 + 0.22 * squash)
        bh = (pf.PH - 6) * s * (1 - 0.18 * squash)
        x, y = float(x), float(y)
        metal = (150, 150, 165) if dead else (226, 230, 238)
        dark = (90, 95, 110)
        # feet: two little metal pads (stepping when running)
        if run_t is not None:
            k = math.sin(run_t * 2.2)
            offs = (-8 * s + 4 * s * k, 8 * s - 4 * s * k)
            lift = (max(0, k) * 4 * s, max(0, -k) * 4 * s)
        else:
            offs, lift = (-7 * s, 7 * s), (3 * s if air else 0, 3 * s if air else 0)
        for o, l in zip(offs, lift):
            pygame.draw.line(scr, dark, (x + o * 0.6, y - 10 * s), (x + o, y - 4 * s - l), max(2, int(3 * s)))
            pygame.draw.rect(scr, dark, (int(x + o - 6 * s), int(y - 5 * s - l), int(12 * s), int(5 * s)),
                             border_radius=2)
        body = pygame.Rect(0, 0, int(bw), int(bh))
        body.midbottom = (int(x), int(y - 6 * s))
        # jet pack on the back, firing in the air
        pack = pygame.Rect(0, 0, int(9 * s), int(bh * 0.55))
        pack.center = (int(body.centerx - face * bw * 0.5), int(body.centery + 2 * s))
        if air and not dead:
            fl = (8 + 6 * abs(math.sin(t * 30))) * s
            pygame.draw.polygon(scr, (90, 170, 255), [(pack.left, pack.bottom), (pack.right, pack.bottom),
                                                      (pack.centerx, pack.bottom + fl)])
            pygame.draw.polygon(scr, (230, 245, 255), [(pack.left + 2, pack.bottom), (pack.right - 2, pack.bottom),
                                                       (pack.centerx, pack.bottom + fl * 0.5)])
        pygame.draw.rect(scr, dark, pack, border_radius=3)
        # body + coloured panel
        pygame.draw.ellipse(scr, (40, 44, 56), body.inflate(int(3 * s), int(3 * s)))
        pygame.draw.ellipse(scr, metal, body)
        panel = pygame.Rect(0, 0, int(bw * 0.62), int(bh * 0.38))
        panel.midbottom = (body.centerx + int(face * 2 * s), body.bottom - int(3 * s))
        pygame.draw.ellipse(scr, (150, 150, 160) if dead else suit, panel)
        pygame.draw.line(scr, dark, (panel.left + 4 * s, panel.centery), (panel.right - 4 * s, panel.centery), 1)
        # visor with one glowing eye looking where it goes
        visor = pygame.Rect(0, 0, int(bw * 0.78), max(4, int(9 * s)))
        visor.center = (body.centerx + int(face * 2 * s), body.y + int(bh * 0.34))
        pygame.draw.rect(scr, (18, 24, 40), visor, border_radius=max(2, int(4 * s)))
        ex = visor.centerx + int(face * bw * 0.18)
        if dead:
            pygame.draw.line(scr, (255, 80, 80), (ex - 4 * s, visor.top + 1), (ex + 4 * s, visor.bottom - 1), 2)
            pygame.draw.line(scr, (255, 80, 80), (ex - 4 * s, visor.bottom - 1), (ex + 4 * s, visor.top + 1), 2)
        else:
            pygame.draw.circle(scr, (80, 200, 255), (ex, visor.centery), max(2, int(4 * s)))
            pygame.draw.circle(scr, (230, 250, 255), (ex, visor.centery), max(1, int(2 * s)))
        # antenna with a blinking light
        ax = body.centerx - face * 5 * s
        top = body.y - 10 * s
        pygame.draw.line(scr, dark, (ax, body.y + 2 * s), (ax, top), max(1, int(2 * s)))
        on = int(t * 3) % 2 == 0
        pygame.draw.circle(scr, (255, 80, 60) if on else (120, 40, 40), (int(ax), int(top)),
                           max(2, int(3 * s)))

    # ------------------------------------------------------------------
    # The start screen card icon and the menu background
    # ------------------------------------------------------------------
    def draw_platformer_icon(self, box, t):
        scr = self.screen
        for px, py, pw, kind in ((box.x + 6, box.bottom - 18, 44, "normal"),
                                 (box.x + 52, box.y + 44, 42, "move")):
            top, body, edge = PLAT_COLORS[kind]
            pygame.draw.rect(scr, body, (px, py, pw, 10), border_radius=5)
            pygame.draw.rect(scr, top, (px + 2, py + 1, pw - 4, 3), border_radius=2)
        # hop from the low platform to the high one, again and again
        ph = (t * 0.8) % 1.0 if t else 0.45
        sx, sy = box.x + 28, box.bottom - 18
        ex, ey = box.x + 73, box.y + 44
        x = sx + (ex - sx) * ph
        y = sy + (ey - sy) * ph - 46 * math.sin(ph * math.pi)
        self.draw_hopper(x, y, 1, -0.6 if ph < 0.3 else 0.0, None, air=0.05 < ph < 0.95, scale=0.75)

    def draw_hopper_scene(self, t):
        """Platformer menu: the hopper bouncing between platforms near the bottom."""
        plats = ((60, 790, 130), (210, 735, 120), (360, 790, 130))
        for px, py, pw in plats:
            top, body, edge = PLAT_COLORS["normal"]
            dim_body = _mix((40, 8, 62), body, 0.55)
            pygame.draw.rect(self.screen, dim_body, (px, py, pw, 14), border_radius=7)
            pygame.draw.rect(self.screen, _mix((40, 8, 62), top, 0.6),
                             (px + 3, py + 2, pw - 6, 4), border_radius=3)
        # hop 0 -> 1 -> 2 -> 1 -> 0 ...
        cycle = (t * 0.9) % 4.0
        seg = int(cycle)
        ph = cycle - seg
        order = (0, 1, 2, 1, 0)
        a, b = plats[order[seg]], plats[order[seg + 1]]
        ax, ay = a[0] + a[2] / 2, a[1]
        bx, by = b[0] + b[2] / 2, b[1]
        x = ax + (bx - ax) * ph
        y = ay + (by - ay) * ph - 90 * math.sin(ph * math.pi)
        self.draw_hopper(x, y, 1 if bx >= ax else -1, -0.5 if ph < 0.2 else
                         (0.6 if ph > 0.92 else 0.0), None, air=0.04 < ph < 0.96)

    # ------------------------------------------------------------------
    # Multiplayer (players and the host's live view)
    # ------------------------------------------------------------------
    def pf_merge_ghosts(self, store, entries, skip=None):
        """Take the positions the host sent; store = {cid: ghost}."""
        if not isinstance(entries, list):
            return
        seen = set()
        for e in entries[:12]:
            try:
                cid = int(e["cid"])
                b = e["b"]
                x, y, c = float(b["x"]), float(b["y"]), float(b["c"])
                info = {"name": mp.clean_name(e.get("name", "?")) if mp else "?",
                        "alive": bool(e.get("alive")) and not b.get("d"),
                        "f": 1 if b.get("f", 1) >= 0 else -1, "w": bool(b.get("w")),
                        "m": int(b.get("m", 0)), "g": bool(b.get("g")), "c": c,
                        "tx": x, "ty": y}
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
            if cid == skip:
                continue
            seen.add(cid)
            old = store.get(cid)
            if old is None:
                info["x"], info["y"], info["run"] = x, y, 0.0
                store[cid] = info
            else:
                old.update(info)
        for cid in [k for k in store if k not in seen]:
            del store[cid]

    def pf_ease_ghosts(self, store, dt):
        """Glide the ghosts to their last known spot (updates come 15x a second)."""
        k = 1 - math.exp(-14.0 * dt / 1000.0)
        for gh in store.values():
            dx = gh["tx"] - gh["x"]
            if abs(dx) > 250 or abs(gh["ty"] - gh["y"]) > 400:     # jumped far: snap
                gh["x"], gh["y"] = gh["tx"], gh["ty"]
            else:
                gh["x"] += dx * k
                gh["y"] += (gh["ty"] - gh["y"]) * k
            if gh["g"] and abs(dx) > 0.5:
                gh["run"] += dt / 1000.0 * min(300.0, abs(dx) * 14) / 40.0

    def pf_take_ghosts(self, entries):
        me = self.client.cid if self.client else None
        self.pf_merge_ghosts(self.__dict__.setdefault("pf_ghosts", {}), entries, me)

    def update_platformer_mp(self, dt):
        g = self.game
        c = self.client
        if c is None:
            return
        ghosts = self.__dict__.setdefault("pf_ghosts", {})
        # the screen follows the highest living player
        cams = [gh["c"] for gh in ghosts.values() if gh["alive"]]
        g.set_leader_cam(min(cams) if cams else None)
        held = self.input.held
        active = not self.mp_menu_open and not g.game_over
        g.update(dt, active and "left" in held, active and "right" in held,
                 active and ("button2" in held or "up" in held))
        self.pf_ease_ghosts(ghosts, dt)
        now = time.monotonic()
        if g.game_over:
            if not self.mp_sent_dead:
                self.mp_sent_dead = True
                c.send_dead(g.snapshot(), g.score, g.meters, g.zone)
        elif now - self.last_state_send >= GHOST_RATE:
            self.last_state_send = now
            c.send_state(g.snapshot(), g.score, g.meters, g.zone)

    def draw_pf_ghosts(self, cam, spectator):
        ghosts = self.pf_host_ghosts if spectator else self.__dict__.get("pf_ghosts", {})
        for cid, gh in sorted(ghosts.items()):
            if not gh["alive"]:
                continue
            x = gh["x"] + pf.PW / 2
            y = gh["y"] + pf.PH - cam
            if y < -60 or y > H + 60:
                continue
            suit = GHOST_SUITS[(cid - 1) % len(GHOST_SUITS)]
            run = gh["run"] if gh["g"] else None
            if spectator:                                   # host: real colours
                if gh["w"]:
                    self.draw_aura(int(x), int(y - pf.PH / 2), 34, (120, 255, 200), 60)
                self.draw_hopper(x, y, gh["f"], 0.0, run, air=not gh["g"], suit=suit)
            else:
                self.draw_ghost(x, y, gh["f"], run, not gh["g"], suit)
            self.text(gh["name"], self.font_tiny, suit if spectator else (235, 235, 255),
                      (int(x), int(y - pf.PH - 18)), "center")

    def draw_ghost(self, x, y, face, run, air, suit):
        """A see-through copy of a player (drawn on its own surface, then faded)."""
        tmp = self.__dict__.get("_pf_ghost_tmp")
        if tmp is None:
            tmp = self.__dict__["_pf_ghost_tmp"] = pygame.Surface((80, 80), pygame.SRCALPHA)
        tmp.fill((0, 0, 0, 0))
        real = self.screen
        self.screen = tmp
        try:
            self.draw_hopper(40, 72, face, 0.0, run, air=air, suit=suit)
        finally:
            self.screen = real
        tmp.set_alpha(GHOST_ALPHA)
        self.screen.blit(tmp, (int(x) - 40, int(y) - 72))
        tmp.set_alpha(None)

    def draw_pf_race(self, g):
        """Little ranking on the right: who is how high (you = gold)."""
        ghosts = self.pf_host_ghosts if g is None else self.__dict__.get("pf_ghosts", {})
        rows = []
        for cid, gh in ghosts.items():
            rows.append((gh["m"], gh["name"], gh["alive"], False,
                         GHOST_SUITS[(cid - 1) % len(GHOST_SUITS)]))
        if g is not None:
            me = self.client.cid if self.client else 1
            rows.append((g.meters, "YOU", not g.game_over, True,
                         GHOST_SUITS[((me or 1) - 1) % len(GHOST_SUITS)]))
        if not rows:
            return
        rows.sort(key=lambda r: (not r[2], -r[0]))
        top = 80 if g is not None else 84
        box = pygame.Rect(W - 186, top, 178, 14 + 24 * len(rows))
        self.draw_glass(box, 10)
        for i, (m, name, alive, mine, suit) in enumerate(rows):
            y = box.y + 18 + i * 24
            col = GOLD if mine else (WHITE if alive else (110, 105, 140))
            pygame.draw.circle(self.screen, suit if alive else (90, 85, 110), (box.x + 16, y), 6)
            self.text("%d." % (i + 1), self.font_tiny, col, (box.x + 28, y), "midleft")
            self.text(name[:9] if alive else name[:6] + " X", self.font_tiny, col,
                      (box.x + 50, y), "midleft")
            self.text("%d M" % m, self.font_tiny, col, (box.right - 10, y), "midright")

    # -- the host's live view: one big screen following the leader
    def update_pf_host(self, dt):
        h = self.host
        view = self.__dict__.get("pf_view")
        if view is None or self.__dict__.get("pf_view_seed") != h.seed:
            view = self.pf_view = pf.Platformer(h.seed)
            self.pf_view_seed = h.seed
            self.pf_host_ghosts = {}
        entries = [{"cid": c, "name": p["name"], "alive": p["alive"], "b": p["board"]}
                   for c, p in h.players.items() if isinstance(p["board"], dict)]
        self.pf_merge_ghosts(self.pf_host_ghosts, entries)
        if time.monotonic() < h.t_go:
            return
        cams = [gh["c"] for gh in self.pf_host_ghosts.values() if gh["alive"]]
        view.advance_world(dt, min(cams) if cams else None)
        best = max([gh["m"] for gh in self.pf_host_ghosts.values()] or [0])
        view.zone = 1 + best // pf.ZONE_M                   # sky colour of the leader
        self.pf_ease_ghosts(self.pf_host_ghosts, dt)

    def draw_pf_host_watch(self):
        h = self.host
        if self.__dict__.get("pf_view") is None or self.__dict__.get("pf_view_seed") != h.seed:
            self.update_pf_host(0)
        now = time.monotonic()
        cx = W // 2
        self.draw_platformer_world(self.pf_view, mp=True, spectator=True)
        players = list(h.players.values())
        alive = sum(1 for p in players if p["alive"])
        elapsed = int(max(0, now - h.t_go))
        self.draw_glass(pygame.Rect(8, 6, W - 16, 66), 14)
        self.text("LIVE VIEW", self.font_med, GOLD, (22, 22))
        self.text("%d OF %d ALIVE   %d:%02d" % (alive, len(players), elapsed // 60, elapsed % 60),
                  self.font_small, WHITE, (22, 50))
        remaining = h.t_go - now
        if remaining > 0:
            self.screen.blit(self.overlay, (0, 0))
            self.text(str(int(math.ceil(remaining))), self.font_huge, WHITE,
                      (cx, H // 2), "center")
        if self.host_menu_open:
            self.screen.blit(self.overlay, (0, 0))
            self.draw_menu(self.menus["host_pause"], "HOST MENU", top=330)
