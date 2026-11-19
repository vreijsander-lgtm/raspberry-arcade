"""
The Nova Arcade - the animated start screen (the games menu), plus the main
menus of the games, in a space-saga style: deep space, ringed planets, a gold
title and hologram-blue panels.

This is a mixin like shooter_ui: main.py's App inherits from it, so it can use
App's helpers (self.text, self.sprite, self.draw_player_ship, self.scores, ...).

Everything expensive (gradient background, glowing logo, star burst) is drawn
once and cached; each frame only blits those and draws a few lines, so it stays
smooth on a Raspberry Pi 4. Only plain pygame 2 features are used (the Pi's
apt package is not pygame-ce).
"""
import math
import random
import time

import pygame

from common import W, H, WHITE, GOLD
from tetris import COLORS, ROTATIONS

ARCADE_NAME = "THE NOVA ARCADE"

# (the names are from the old neon look; the colours are the space-saga theme)
NEON_CYAN = (90, 185, 255)       # hologram blue
NEON_PINK = (255, 175, 50)       # saga gold
NEON_PURPLE = (110, 130, 255)
SKY_TOP = (1, 2, 10)
SKY_BOTTOM = (12, 18, 46)
PANEL_EDGE = (60, 90, 150)       # thin border of panels and buttons
PANEL_FILL = (6, 12, 30)

NOVA_Y = 250                     # centre line of the big NOVA word
CARD_W, CARD_H = 460, 124
CARD_YS = (505, 650)             # card centres (two games)
# three or more games: smaller cards so they all fit above the grid
CARD_H_SMALL = 104
CARD_STEP_SMALL = 116
CARD_Y0_SMALL = 500
# four or more games: smaller still
CARD_H_TINY = 88
CARD_STEP_TINY = 94
CARD_Y0_TINY = 478
# five or more games
CARD_H_MINI = 74
CARD_STEP_MINI = 80
CARD_Y0_MINI = 470
# six or more games
CARD_H_SIX = 62
CARD_STEP_SIX = 66
CARD_Y0_SIX = 466
# seven or more games
CARD_H_SEVEN = 54
CARD_STEP_SEVEN = 57
CARD_Y0_SEVEN = 458
# eight or more games
CARD_H_EIGHT = 47
CARD_STEP_EIGHT = 50
CARD_Y0_EIGHT = 452
HORIZON = 838                    # top of the neon grid at the bottom

# the games' main menus
MENU_W, MENU_H = 400, 56         # one neon button
MENU_STEP = 70

# all other screens
GRID_Y = 880                     # their neon grid sits a bit lower
HUD_LABEL = (140, 170, 230)
MEDALS = ((255, 205, 60), (205, 215, 235), (220, 140, 80))   # gold, silver, bronze


# what each game's card says: state -> (tag line, which scoreboard)
CARD_INFO = {
    "main": ("STACK THE BLOCKS", "tetris"),
    "sh_main": ("BLAST THE ALIENS", "shooter"),
    "pf_main": ("JUMP TO THE STARS", "platformer"),
    "fg_main": ("DUEL YOUR WAY UP", "fighter"),
    "gb_main": ("EAT THE LIGHT", "glowbug"),
    "pu_main": ("FASTER EVERY POINT", "pulsar"),
    "st_main": ("SPIN, THROW, FLY HIGH", "toss"),
}


def _mix(a, b, f):
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


def _draw_planet(surf, cx, cy, r, light, dark, ring=None, bands=True):
    """A shaded planet (light from the top right), maybe with a ring."""
    if ring:                                       # back half of the ring
        rr = pygame.Rect(0, 0, int(r * 3.4), int(r * 0.8))
        rr.center = (cx, cy)
        pygame.draw.ellipse(surf, ring, rr, max(2, r // 18))
    for i in range(r, 0, -2):
        f = i / float(r)
        pygame.draw.circle(surf, _mix(light, dark, f ** 1.6),
                           (int(cx + (1 - f) * r * 0.35), int(cy - (1 - f) * r * 0.35)), i)
    if bands:
        for k in range(-3, 4):
            y = cy + k * r // 4
            half = int(math.sqrt(max(0, r * r - (y - cy) ** 2)) * 0.92)
            if half > 4:
                pygame.draw.line(surf, _mix(dark, light, 0.35), (cx - half, y), (cx + half, y), 2)
    pygame.draw.circle(surf, _mix(light, (255, 255, 255), 0.4), (cx, cy), r, 2)
    if ring:                                       # front half of the ring
        rr = pygame.Rect(0, 0, int(r * 3.4), int(r * 0.8))
        rr.center = (cx, cy)
        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(0, cy, surf.get_width(), surf.get_height()))
        pygame.draw.ellipse(surf, ring, rr, max(2, r // 18))
        surf.set_clip(clip)


def _blur(surf, factor):
    """Cheap blur: shrink and grow again (works in every pygame 2)."""
    w, h = surf.get_size()
    small = pygame.transform.smoothscale(surf, (max(1, w // factor), max(1, h // factor)))
    return pygame.transform.smoothscale(small, (w, h))


class TitleUI:
    # ------------------------------------------------------------------
    # Cached artwork
    # ------------------------------------------------------------------
    def _spaced(self, font, text, color, spacing):
        """Text with extra room between the letters."""
        imgs = [font.render(ch, True, color) for ch in text]
        w = sum(i.get_width() for i in imgs) + spacing * (len(imgs) - 1)
        h = max(i.get_height() for i in imgs)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        x = 0
        for img in imgs:
            surf.blit(img, (x, 0))
            x += img.get_width() + spacing
        return surf

    def _neon(self, core, glow_color, pad=28, strength=3):
        """Put a soft neon glow around an already rendered text surface.
        glow_color None = every letter glows in its own colour."""
        w, h = core.get_size()
        out = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
        tinted = core.copy()
        if glow_color is not None:
            tinted.fill(glow_color + (255,), special_flags=pygame.BLEND_RGBA_MULT)
        glow = pygame.Surface(out.get_size(), pygame.SRCALPHA)
        glow.blit(tinted, (pad, pad))
        glow = _blur(glow, 7)
        for _ in range(strength):
            out.blit(glow, (0, 0))
        out.blit(core, (pad, pad))
        return out

    def _gradient_text(self, font, text, top, bottom, spacing):
        mask = self._spaced(font, text, WHITE, spacing)
        w, h = mask.get_size()
        grad = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            f = max(0.0, min(1.0, (y - h * 0.18) / (h * 0.62)))
            pygame.draw.line(grad, _mix(top, bottom, f) + (255,), (0, y), (w, y))
        grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return grad

    def _title_assets(self):
        a = self.__dict__.get("_title_art")
        if a:
            return a
        a = {}
        # sky
        bg = pygame.Surface((W, H)).convert()
        for y in range(H):
            pygame.draw.line(bg, _mix(SKY_TOP, SKY_BOTTOM, y / float(H)), (0, y), (W, y))
        _draw_planet(bg, 470, 640, 120, (120, 150, 220), (14, 20, 60), ring=(150, 170, 220))
        _draw_planet(bg, 70, 455, 34, (230, 190, 140), (60, 35, 25), bands=False)
        a["bg"] = bg
        # stars: (x, y, speed, brightness, size)
        rng = random.Random(7)
        a["stars"] = [(rng.uniform(0, W), rng.uniform(0, H), rng.choice((10, 22, 40)),
                       rng.randint(110, 255), rng.choice((1, 1, 2)))
                      for _ in range(140)]
        # soft glow of the nova
        R = 250
        glow = pygame.Surface((R * 2, R * 2), pygame.SRCALPHA)
        for r in range(R, 0, -3):
            f = 1 - r / float(R)
            color = _mix((40, 70, 180), (255, 245, 220), f ** 2)
            pygame.draw.circle(glow, color + (int(150 * f ** 2.2),), (R, R), r)
        a["glow"] = glow
        # star burst rays (rotated every frame)
        S = 520
        rays = pygame.Surface((S, S), pygame.SRCALPHA)
        c = S // 2
        for i in range(16):
            ang = i * math.tau / 16
            length = c if i % 2 == 0 else c * 0.62
            half = 0.05 if i % 2 == 0 else 0.035
            pts = [(c + math.cos(ang - half) * 18, c + math.sin(ang - half) * 18),
                   (c + math.cos(ang) * length, c + math.sin(ang) * length),
                   (c + math.cos(ang + half) * 18, c + math.sin(ang + half) * 18)]
            pygame.draw.polygon(rays, (255, 210, 150, 46 if i % 2 == 0 else 30), pts)
        a["rays"] = _blur(rays, 2)
        # logo
        f_the = pygame.font.Font(None, 48)
        f_nova = pygame.font.Font(None, 205)
        f_arcade = pygame.font.Font(None, 76)
        a["the"] = self._neon(self._spaced(f_the, "THE", (220, 240, 255), 18), NEON_CYAN, 22, 2)
        nova = self._gradient_text(f_nova, "NOVA", (255, 250, 215), (225, 130, 20), 6)
        shadow = self._spaced(f_nova, "NOVA", (45, 25, 0), 6)
        both = pygame.Surface((nova.get_width(), nova.get_height() + 8), pygame.SRCALPHA)
        both.blit(shadow, (0, 8))
        both.blit(nova, (0, 0))
        a["nova"] = self._neon(both, NEON_PINK, 34, 3)
        a["arcade"] = self._neon(self._spaced(f_arcade, "ARCADE", (225, 240, 255), 16),
                                 NEON_CYAN, 26, 3)
        # the nova star sits inside the "O" of NOVA: work out where that is
        o_img = f_nova.render("O", True, WHITE)
        total = sum(f_nova.size(ch)[0] for ch in "NOVA") + 6 * 3
        dx = f_nova.size("N")[0] + 6 + o_img.get_width() / 2.0 - total / 2.0
        dy = o_img.get_bounding_rect().centery - o_img.get_height() / 2.0 - 4
        a["o_offset"] = (int(round(dx)), int(round(dy)))
        # the glow never moves, so paint it into the sky once
        gx, gy = W // 2 + a["o_offset"][0], NOVA_Y + a["o_offset"][1]
        bg.blit(glow, glow.get_rect(center=(gx, gy)))
        a["rays_cache"] = (None, None)
        # fonts and the card panel
        a["f_card"] = pygame.font.Font(None, 52)
        a["f_card_s"] = pygame.font.Font(None, 42)       # for the slimmest cards
        a["f_card_xs"] = pygame.font.Font(None, 36)
        panel = pygame.Surface((CARD_W, CARD_H), pygame.SRCALPHA)
        pygame.draw.rect(panel, PANEL_FILL + (225,), panel.get_rect(), border_radius=18)
        a["panel"] = panel
        self.__dict__["_title_art"] = a
        return a

    # ------------------------------------------------------------------
    # The screen
    # ------------------------------------------------------------------
    def draw_games(self):
        a = self._title_assets()
        scr = self.screen
        t = time.monotonic()
        scr.blit(a["bg"], (0, 0))
        # drifting, twinkling stars
        for sx, sy, sp, br, size in a["stars"]:
            y = (sy + t * sp) % H
            if y > HORIZON:
                continue
            b = int(br * (0.65 + 0.35 * math.sin(t * 2.5 + sx)))
            pygame.draw.rect(scr, (b, b, min(255, b + 20)), (int(sx), int(y), size, size))

        # the nova: a slowly turning star burst coming out of the "O"
        cx = W // 2
        ox, oy = a["o_offset"]
        sx, sy = cx + ox, NOVA_Y + oy
        angle = round((t * 7) % 45 * 2) / 2.0      # 16 rays repeat every 45 degrees
        if a["rays_cache"][0] != angle:            # only re-turn when it changed
            a["rays_cache"] = (angle, pygame.transform.rotate(a["rays"], angle))
        rays = a["rays_cache"][1]
        scr.blit(rays, rays.get_rect(center=(sx, sy)))

        # the logo, gently floating; the star shines through the O
        bob = int(4 * math.sin(t * 1.6))
        pulse = 0.5 + 0.5 * math.sin(t * 2.4)
        pygame.draw.circle(scr, (150, 200, 255), (sx, sy + bob), int(19 + 4 * pulse))
        pygame.draw.circle(scr, (240, 248, 255), (sx, sy + bob), int(11 + 3 * pulse))
        scr.blit(a["the"], a["the"].get_rect(center=(cx, 128 + bob)))
        scr.blit(a["nova"], a["nova"].get_rect(center=(cx, NOVA_Y + bob)))
        scr.blit(a["arcade"], a["arcade"].get_rect(center=(cx, 360 + bob)))
        self.draw_sparkles(t)

        self.text("-  CHOOSE YOUR GAME  -", self.font_small, (190, 180, 230),
                  (cx, 432 if len(self.games) < 4 else 416 if len(self.games) < 7 else
                       410 if len(self.games) < 8 else 404),
                  "center")
        for i, (name, state) in enumerate(self.games):
            self.draw_game_card(i, name, state, t, a)

        # blinking call to action
        if int(t * 2.2) % 3 and len(self.games) < 5:     # 5+ cards: no room left
            self.text("PRESS  B2  TO PLAY", self.font_med, GOLD,
                      (cx, 782 if len(self.games) <= 2 else 808 if len(self.games) == 3 else 822),
                      "center")
        self.draw_neon_grid(t)
        self.draw_random_button(t)
        self.text("UP / DOWN : CHOOSE        B2 : PLAY", self.font_tiny, (200, 190, 240),
                  (cx, H - 22), "center")

    def draw_random_button(self, t):
        """RANDOM GAME button on the floor below the cards."""
        scr = self.screen
        roll = getattr(self, "roll", None)
        sel = self.menus["games"].sel == len(self.games) or roll is not None
        rect = pygame.Rect(0, 0, 300, 50)
        rect.center = (W // 2, 878)
        if sel:
            glow_col = _mix(NEON_CYAN, NEON_PINK, 0.5 + 0.5 * math.sin(t * 3))
            for grow, shade in ((14, 0.25), (8, 0.5)):
                pygame.draw.rect(scr, _mix(SKY_BOTTOM, glow_col, shade), rect.inflate(grow, grow),
                                 3, border_radius=20)
        panel = self.__dict__.get("_random_panel")
        if panel is None:
            panel = self.__dict__["_random_panel"] = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(panel, PANEL_FILL + (235,), panel.get_rect(), border_radius=16)
        scr.blit(panel, rect)
        pygame.draw.rect(scr, glow_col if sel else PANEL_EDGE, rect, 3 if sel else 2, border_radius=16)
        # a die (it tumbles while the roulette spins)
        spin = (t * 9) if roll else (math.sin(t * 2) * 0.25 if sel else 0.0)
        face = (int(t * 12) % 6) + 1 if roll else 5
        self.draw_die(rect.x + 34, rect.centery, 15, spin, face)
        label = "ROLLING..." if roll else "RANDOM GAME"
        self.text(label, self.font_med, GOLD if sel else (195, 190, 225), (rect.centerx + 16, rect.centery),
                  "center")
        if sel and not roll:
            ax = rect.x - 22 + int(4 * math.sin(t * 6))
            pygame.draw.polygon(scr, GOLD, [(ax, rect.centery - 11), (ax + 14, rect.centery),
                                            (ax, rect.centery + 11)])

    def draw_die(self, cx, cy, half, angle, face):
        scr = self.screen
        c, s_ = math.cos(angle), math.sin(angle)

        def rot(dx, dy):
            return (cx + dx * c - dy * s_, cy + dx * s_ + dy * c)
        corners = [rot(-half, -half), rot(half, -half), rot(half, half), rot(-half, half)]
        pygame.draw.polygon(scr, (240, 240, 250), corners)
        pygame.draw.polygon(scr, NEON_PINK, corners, 2)
        k = half * 0.5
        pips = {1: [(0, 0)], 2: [(-k, -k), (k, k)], 3: [(-k, -k), (0, 0), (k, k)],
                4: [(-k, -k), (k, -k), (-k, k), (k, k)],
                5: [(-k, -k), (k, -k), (0, 0), (-k, k), (k, k)],
                6: [(-k, -k), (k, -k), (-k, 0), (k, 0), (-k, k), (k, k)]}[face]
        for dx, dy in pips:
            px, py = rot(dx, dy)
            pygame.draw.circle(scr, (30, 30, 50), (int(px), int(py)), max(2, half // 6))

    def draw_darkness(self, x, y, radius):
        """LIGHTS OUT modes: everything dark except a soft circle of light."""
        cache = self.__dict__.setdefault("_dark_cache", {})
        surf = cache.get(radius)
        if surf is None:
            surf = pygame.Surface((W * 2, H * 2), pygame.SRCALPHA)
            surf.fill((0, 0, 6, 246))
            inner, outer = int(radius * 0.55), int(radius * 1.6)
            for r in range(outer, 0, -2):
                f = max(0.0, min(1.0, (r - inner) / float(outer - inner)))
                pygame.draw.circle(surf, (0, 0, 6, int(246 * f)), (W, H), r)
            cache[radius] = surf
        self.screen.blit(surf, (int(x) - W, int(y) - H))

    def draw_sparkles(self, t, ymax=400):
        """A few little twinkles that pop up around the logo."""
        for i in range(6):
            phase = (t * 0.7 + i * 0.37) % 1.0
            rng = random.Random(int(t * 0.7 + i * 0.37) * 31 + i)
            x = rng.uniform(60, W - 60)
            y = rng.uniform(95, ymax)
            s = int(9 * math.sin(phase * math.pi))
            if s <= 1:
                continue
            col = (255, 250, 220)
            pygame.draw.line(self.screen, col, (x - s, y), (x + s, y), 2)
            pygame.draw.line(self.screen, col, (x, y - s), (x, y + s), 2)

    def card_layout(self, i):
        """(card height, centre y) of game card i."""
        if len(self.games) <= 2:
            return CARD_H, CARD_YS[i]
        if len(self.games) >= 8:
            return CARD_H_EIGHT, CARD_Y0_EIGHT + i * CARD_STEP_EIGHT
        if len(self.games) >= 7:
            return CARD_H_SEVEN, CARD_Y0_SEVEN + i * CARD_STEP_SEVEN
        if len(self.games) >= 6:
            return CARD_H_SIX, CARD_Y0_SIX + i * CARD_STEP_SIX
        if len(self.games) >= 5:
            return CARD_H_MINI, CARD_Y0_MINI + i * CARD_STEP_MINI
        if len(self.games) >= 4:
            return CARD_H_TINY, CARD_Y0_TINY + i * CARD_STEP_TINY
        return CARD_H_SMALL, CARD_Y0_SMALL + i * CARD_STEP_SMALL

    def draw_card_icon(self, state, box, t):
        if state == "main":
            self.draw_tetris_icon(box, t)
        elif state == "pf_main":
            self.draw_platformer_icon(box, t)
        elif state == "fg_main":
            self.draw_fighter_icon(box, t)
        elif state == "gb_main":
            self.draw_glowbug_icon(box, t)
        elif state == "pu_main":
            self.draw_pulsar_icon(box, t)
        elif state == "st_main":
            self.draw_toss_icon(box, t)
        else:
            self.draw_shooter_icon(box, t)

    def draw_game_card(self, i, name, state, t, a):
        scr = self.screen
        sel = self.menus["games"].sel == i
        card_h, card_y = self.card_layout(i)
        small = card_h < CARD_H
        rect = pygame.Rect(0, 0, CARD_W, card_h)
        rect.center = (W // 2, card_y)
        if sel:                                   # glow + pulsing neon frame
            glow_col = _mix(NEON_CYAN, NEON_PINK, 0.5 + 0.5 * math.sin(t * 3))
            for grow, shade in ((14, 0.25), (8, 0.5)):
                pygame.draw.rect(scr, _mix(SKY_BOTTOM, glow_col, shade),
                                 rect.inflate(grow, grow), 3, border_radius=22)
        if small:
            panel = a.get("panel_small")
            if panel is None:
                panel = a["panel_small"] = pygame.Surface((CARD_W, card_h), pygame.SRCALPHA)
                pygame.draw.rect(panel, PANEL_FILL + (225,), panel.get_rect(), border_radius=18)
            scr.blit(panel, rect)
        else:
            scr.blit(a["panel"], rect)
        if sel:
            pygame.draw.rect(scr, glow_col, rect, 4, border_radius=18)
        else:
            pygame.draw.rect(scr, PANEL_EDGE, rect, 2, border_radius=18)

        size = card_h - 24
        icon = pygame.Rect(rect.x + 14, rect.y + 12, size, size)
        pygame.draw.rect(scr, (6, 6, 20), icon, border_radius=12)
        if size == 100:
            scr.set_clip(icon)
            try:
                self.draw_card_icon(state, icon, t if sel else 0.0)
            finally:
                scr.set_clip(None)
        else:
            # the icons are made for 100 x 100: draw them there, then shrink
            tmp = a.get("icon_tmp")
            if tmp is None:
                tmp = a["icon_tmp"] = pygame.Surface((100, 100)).convert()
            tmp.fill((6, 6, 20))
            real = self.screen
            self.screen = tmp
            try:
                self.draw_card_icon(state, pygame.Rect(0, 0, 100, 100), t if sel else 0.0)
            finally:
                self.screen = real
            small_img = pygame.transform.smoothscale(tmp, (size, size))
            scr.blit(small_img, icon)
        pygame.draw.rect(scr, (50, 70, 120), icon, 2, border_radius=12)

        tag, board = CARD_INFO.get(state, ("", None))
        tag_font = self.font_tiny if card_h <= CARD_H_EIGHT else self.font_small
        tx = icon.right + 18
        name_color = WHITE if sel else (185, 180, 215)
        tiny = card_h <= CARD_H_TINY
        six = card_h <= CARD_H_SIX
        seven = card_h <= CARD_H_SEVEN
        eight = card_h <= CARD_H_EIGHT
        ty = ((2, 27, 29) if eight else (4, 31, 34) if seven else (2, 36, 39) if six else (4, 36, 55) if card_h <= CARD_H_MINI else
              (8, 44, 66) if tiny else (12, 52, 78) if small else (18, 64, 92))
        img = a["f_card_xs" if eight else "f_card_s" if seven else "f_card"].render(name, True, name_color)
        scr.blit(img, (tx, rect.y + ty[0]))
        self.text(tag, tag_font, NEON_CYAN if sel else (120, 140, 170),
                  (tx, rect.y + ty[1]))
        boards = {"tetris": self.scores, "shooter": self.scores_sh,
                  "platformer": getattr(self, "scores_pf", None),
                  "fighter": getattr(self, "scores_fg", None),
                  "glowbug": getattr(self, "scores_gb", None),
                  "pulsar": getattr(self, "scores_pu", None),
                  "toss": getattr(self, "scores_st", None)}
        scores = boards.get(board)
        best = scores.best() if scores else 0
        if six:                                   # slim card: top score on the right
            line = "TOP %d" % best if best else "NEW!"
            self.text(line, self.font_tiny, GOLD if sel else (150, 130, 80),
                      (rect.right - 14, rect.y + ty[2]), "topright")
        else:
            line = "TOP SCORE  %d" % best if best else "NO HIGH SCORE YET - BE FIRST!"
            self.text(line, self.font_tiny, GOLD if sel else (150, 130, 80),
                      (tx, rect.y + ty[2]))

        if sel:                                   # bouncing arrow
            ax = rect.x - 22 + int(4 * math.sin(t * 6))
            ay = rect.centery
            pygame.draw.polygon(scr, GOLD, [(ax, ay - 11), (ax + 14, ay), (ax, ay + 11)])

    def draw_tetris_icon(self, box, t):
        cell = 18
        x0, y0 = box.x + 5, box.y + 1
        # a little stack at the bottom
        stack = [".....", "J...L", "JZZ.L", "JJZZL", "OOTIT"]
        for r, row in enumerate(stack):
            for c, ch in enumerate(row):
                if ch != ".":
                    self.screen.blit(self.sprite(COLORS[ch], cell),
                                     (x0 + c * cell, y0 + (r + 0.5) * cell))
        # a T piece falling into the gap, again and again
        fall = (t * 1.2) % 1.0 if t else 0.35
        py = y0 - 2 * cell + int(fall * 3.2 * cell)
        spr = self.sprite(COLORS["T"], cell)
        for c, r in ((2, 0), (3, 0), (4, 0), (3, 1)):
            self.screen.blit(spr, (x0 + c * cell - cell, py + r * cell))

    def draw_shooter_icon(self, box, t):
        cx = box.centerx
        # enemy sliding left and right
        ex = cx + int(26 * math.sin(t * 2.2))
        ey = box.y + 22
        self.draw_enemy(0, ex, ey, False)
        # laser bolts flying up
        for k in range(3):
            by = box.bottom - 34 - ((t * 160 + k * 33) % 70)
            self.draw_laser_bolt(cx, by, (255, 80, 60), 12, 3)
        self.draw_player_ship(cx, box.bottom - 26)

    def draw_neon_grid(self, t, horizon=HORIZON):
        """Retro perspective grid scrolling towards you."""
        scr = self.screen
        pygame.draw.rect(scr, (3, 7, 20), (0, horizon, W, H - horizon))
        cx = W // 2
        depth = H - horizon
        for i in range(-9, 10):                   # lines running into the distance
            xb = cx + i * 90
            pygame.draw.line(scr, (30, 70, 140), (cx + i * 10, horizon), (xb, H), 2)
        phase = (t * 0.55) % 1.0
        for j in range(9):                        # lines coming closer
            d = (j + phase) / 9.0
            y = horizon + int(depth * d * d)
            col = _mix((12, 30, 70), NEON_CYAN, d)
            pygame.draw.line(scr, col, (0, y), (W, y), 1 if d < 0.35 else 2)
        pygame.draw.line(scr, NEON_CYAN, (0, horizon), (W, horizon), 3)
        pygame.draw.line(scr, (200, 235, 255), (0, horizon - 2), (W, horizon - 2), 1)

    # ------------------------------------------------------------------
    # The games' main menus, in the same style
    # ------------------------------------------------------------------
    def _menu_assets(self):
        m = self.__dict__.get("_menu_art")
        if m:
            return m
        a = self._title_assets()
        m = {}
        # same sky, with the soft glow behind the game logo instead of the O
        bg = pygame.Surface((W, H)).convert()
        for y in range(H):
            pygame.draw.line(bg, _mix(SKY_TOP, SKY_BOTTOM, y / float(H)), (0, y), (W, y))
        bg.blit(a["glow"], a["glow"].get_rect(center=(W // 2, 175)))
        _draw_planet(bg, 505, 252, 34, (200, 120, 90), (40, 15, 20), ring=(220, 170, 130))
        m["bg"] = bg
        m["brand"] = self._neon(self._spaced(self.font_tiny, "THE NOVA ARCADE",
                                             (220, 240, 255), 6), NEON_CYAN, 12, 2)
        # TETRIS: every letter in the colour of a block, glowing in its own colour
        f = pygame.font.Font(None, 150)
        letters = [(ch, COLORS[k]) for ch, k in zip("TETRIS", "TOSZIL")]
        letters[1] = ("E", (235, 200, 95))       # soft gold instead of bright yellow
        # each letter: light at the top -> its block colour -> deeper at the bottom
        imgs = [self._gradient_text(f, ch, _mix(col, (255, 255, 255), 0.55),
                                    tuple(min(255, int(c * 1.1)) for c in col), 0)
                for ch, col in letters]
        shadows = [f.render(ch, True, (40, 0, 50)) for ch, _ in letters]
        gap = 6
        w = sum(i.get_width() for i in imgs) + gap * (len(imgs) - 1)
        core = pygame.Surface((w, imgs[0].get_height() + 8), pygame.SRCALPHA)
        x = 0
        for img, sh in zip(imgs, shadows):
            core.blit(sh, (x, 8))
            core.blit(img, (x, 0))
            x += img.get_width() + gap
        m["logo_main"] = [self._neon(core, None, 30, 3)]
        # SPACE / SHOOTER: two gradient words, cyan and pink neon
        f = pygame.font.Font(None, 118)
        words = []
        for word, top, bottom, glow in (("SPACE", (225, 245, 255), (60, 140, 255), NEON_CYAN),
                                        ("SHOOTER", (255, 250, 215), (225, 130, 20), NEON_PINK)):
            grad = self._gradient_text(f, word, top, bottom, 5)
            shadow = self._spaced(f, word, (40, 0, 50), 5)
            both = pygame.Surface((grad.get_width(), grad.get_height() + 6), pygame.SRCALPHA)
            both.blit(shadow, (0, 6))
            both.blit(grad, (0, 0))
            words.append(self._neon(both, glow, 26, 3))
        m["logo_sh_main"] = words
        # SKY / HOPPER: green and gold neon
        words = []
        for word, top, bottom, glow in (("SKY", (230, 255, 230), (80, 220, 130), (90, 255, 150)),
                                        ("HOPPER", (255, 248, 190), (255, 110, 80), (255, 150, 60))):
            grad = self._gradient_text(f, word, top, bottom, 5)
            shadow = self._spaced(f, word, (40, 0, 50), 5)
            both = pygame.Surface((grad.get_width(), grad.get_height() + 6), pygame.SRCALPHA)
            both.blit(shadow, (0, 6))
            both.blit(grad, (0, 0))
            words.append(self._neon(both, glow, 26, 3))
        m["logo_pf_main"] = words
        # SABER / BRAWL: blue blade-glow and red-gold
        words = []
        for word, top, bottom, glow in (("SABER", (235, 245, 255), (70, 150, 255), NEON_CYAN),
                                        ("BRAWL", (255, 248, 190), (255, 60, 50), (255, 70, 60))):
            grad = self._gradient_text(f, word, top, bottom, 5)
            shadow = self._spaced(f, word, (40, 0, 50), 5)
            both = pygame.Surface((grad.get_width(), grad.get_height() + 6), pygame.SRCALPHA)
            both.blit(shadow, (0, 6))
            both.blit(grad, (0, 0))
            words.append(self._neon(both, glow, 26, 3))
        m["logo_fg_main"] = words
        # GLOW / BUG: lime and gold neon
        words = []
        for word, top, bottom, glow in (("GLOW", (245, 255, 220), (150, 255, 70), (160, 255, 90)),
                                        ("BUG", (255, 250, 200), (255, 180, 40), (255, 200, 60))):
            grad = self._gradient_text(f, word, top, bottom, 5)
            shadow = self._spaced(f, word, (40, 0, 50), 5)
            both = pygame.Surface((grad.get_width(), grad.get_height() + 6), pygame.SRCALPHA)
            both.blit(shadow, (0, 6))
            both.blit(grad, (0, 0))
            words.append(self._neon(both, glow, 26, 3))
        m["logo_gb_main"] = words
        # PULSAR: one word, blue-white with a violet glow
        f_big = pygame.font.Font(None, 150)
        grad = self._gradient_text(f_big, "PULSAR", (240, 245, 255), (90, 140, 255), 6)
        shadow = self._spaced(f_big, "PULSAR", (20, 10, 50), 6)
        both = pygame.Surface((grad.get_width(), grad.get_height() + 8), pygame.SRCALPHA)
        both.blit(shadow, (0, 8))
        both.blit(grad, (0, 0))
        m["logo_pu_main"] = [self._neon(both, (170, 110, 255), 30, 3)]
        # STAR / TOSS: gold and green
        words = []
        for word, top, bottom, glow in (("STAR", (255, 252, 220), (255, 190, 50), NEON_PINK),
                                        ("TOSS", (230, 255, 240), (80, 220, 170), (90, 230, 180))):
            grad = self._gradient_text(f, word, top, bottom, 5)
            shadow = self._spaced(f, word, (40, 0, 50), 5)
            both = pygame.Surface((grad.get_width(), grad.get_height() + 6), pygame.SRCALPHA)
            both.blit(shadow, (0, 6))
            both.blit(grad, (0, 0))
            words.append(self._neon(both, glow, 26, 3))
        m["logo_st_main"] = words
        panel = pygame.Surface((MENU_W, MENU_H), pygame.SRCALPHA)
        pygame.draw.rect(panel, PANEL_FILL + (238,), panel.get_rect(), border_radius=16)
        m["panel"] = panel
        self.__dict__["_menu_art"] = m
        return m

    def draw_game_menu(self, which, menu, top):
        """Main menu of one game ("main" = Tetris, "sh_main" = Space Shooter,
        "pf_main" = Sky Hopper)."""
        a = self._title_assets()
        m = self._menu_assets()
        scr = self.screen
        t = time.monotonic()
        cx = W // 2
        scr.blit(m["bg"], (0, 0))
        for sx, sy, sp, br, size in a["stars"]:
            y = (sy + t * sp) % H
            if y > HORIZON:
                continue
            b = int(br * (0.65 + 0.35 * math.sin(t * 2.5 + sx)))
            pygame.draw.rect(scr, (b, b, min(255, b + 20)), (int(sx), int(y), size, size))
        if which == "main":
            self.draw_falling_pieces(t)
        elif which == "pf_main":
            self.draw_hopper_scene(t)
        elif which == "fg_main":
            self.draw_brawl_scene(t)
        elif which == "gb_main":
            self.draw_glowbug_scene(t)
        elif which == "pu_main":
            self.draw_pulsar_scene(t)
        elif which == "st_main":
            self.draw_toss_scene(t)
        else:
            self.draw_space_fight(t)

        bob = int(4 * math.sin(t * 1.6))
        scr.blit(m["brand"], m["brand"].get_rect(center=(cx, 42)))
        logo = m["logo_" + which]
        if len(logo) == 1:
            scr.blit(logo[0], logo[0].get_rect(center=(cx, 160 + bob)))
        else:
            scr.blit(logo[0], logo[0].get_rect(center=(cx, 125 + bob)))
            scr.blit(logo[1], logo[1].get_rect(center=(cx, 222 + bob)))
        self.draw_sparkles(t, 280)

        for i, item in enumerate(menu.items):
            self.draw_menu_button(self.menu_label(i, item), menu.sel == i,
                                  top + i * MENU_STEP, t, m)
        self.draw_neon_grid(t)
        desc = self.mode_desc(which) if hasattr(self, "mode_desc") else ""
        if desc:
            self.text("MODE: " + desc, self.font_tiny, GOLD, (cx, H - 50), "center")
        self.text("UP / DOWN : CHOOSE     B2 : OK     B1 : BACK", self.font_tiny,
                  (200, 190, 240), (cx, H - 22), "center")

    def draw_menu_button(self, label, sel, y, t, m):
        scr = self.screen
        rect = pygame.Rect(0, 0, MENU_W, MENU_H)
        rect.center = (W // 2, y)
        if sel:
            glow_col = _mix(NEON_CYAN, NEON_PINK, 0.5 + 0.5 * math.sin(t * 3))
            for grow, shade in ((14, 0.25), (8, 0.5)):
                pygame.draw.rect(scr, _mix(SKY_BOTTOM, glow_col, shade),
                                 rect.inflate(grow, grow), 3, border_radius=20)
        scr.blit(m["panel"], rect)
        if sel:
            pygame.draw.rect(scr, glow_col, rect, 3, border_radius=16)
            ax = rect.x - 22 + int(4 * math.sin(t * 6))
            pygame.draw.polygon(scr, GOLD, [(ax, y - 11), (ax + 14, y), (ax, y + 11)])
        else:
            pygame.draw.rect(scr, PANEL_EDGE, rect, 2, border_radius=16)
        self.text(label, self.font_med, GOLD if sel else (195, 190, 225), (W // 2, y), "center")

    def draw_falling_pieces(self, t):
        """Tetris menu: dim blocks slowly falling behind everything."""
        cell = 18
        kinds = "ITSZOLJ"
        for i in range(9):
            kind = kinds[i % 7]
            spr = self.sprite(_mix(SKY_BOTTOM, COLORS[kind], 0.30), cell)
            speed = 28 + (i * 13) % 30
            x = 18 + (i * 61) % (W - 90)
            y = (i * 197 + t * speed) % (HORIZON + 120) - 100
            for c, r in ROTATIONS[kind][(int(t * 0.25) + i) % 4]:
                py = y + r * cell
                if py < HORIZON - cell:
                    self.screen.blit(spr, (x + c * cell, int(py)))

    def draw_space_fight(self, t):
        """Space Shooter menu: a ship near the bottom shooting at an alien."""
        ex = W // 2 + int(150 * math.sin(t * 0.9))
        ey = 728
        sx = W // 2 + int(150 * math.sin(t * 0.9 - 0.5))
        sy = 785
        for k in range(4):
            by = sy - 30 - ((t * 220 + k * 18) % 55)
            self.draw_laser_bolt(sx, by, (255, 80, 60), 14)
        self.draw_enemy(0, ex, ey, False)
        self.draw_player_ship(sx, sy)

    # ------------------------------------------------------------------
    # Shared pieces for all the other screens
    # ------------------------------------------------------------------
    def _screen_assets(self):
        s = self.__dict__.get("_screen_art")
        if s:
            return s
        s = {}
        sky = pygame.Surface((W, H)).convert()
        for y in range(H):
            pygame.draw.line(sky, _mix(SKY_TOP, SKY_BOTTOM, y / float(H)), (0, y), (W, y))
        s["sky"] = sky
        space = pygame.Surface((W, H)).convert()
        for y in range(H):
            pygame.draw.line(space, _mix((1, 2, 10), (10, 14, 36), y / float(H)), (0, y), (W, y))
        _draw_planet(space, 70, 300, 110, (60, 80, 130), (6, 9, 26), ring=(50, 65, 100))
        s["space"] = space
        s["titles"] = {}
        s["glass"] = {}
        s["fonts"] = {}
        self.__dict__["_screen_art"] = s
        return s

    def space_bg(self):
        """Background of the Space Shooter playfield (a dark gradient)."""
        return self._screen_assets()["space"]

    def draw_backdrop(self, grid=True):
        """Nova sky + drifting stars (+ the neon grid) behind a screen."""
        a = self._title_assets()
        s = self._screen_assets()
        scr = self.screen
        t = time.monotonic()
        scr.blit(s["sky"], (0, 0))
        bottom = GRID_Y if grid else H
        for sx, sy, sp, br, size in a["stars"]:
            y = (sy + t * sp) % H
            if y > bottom:
                continue
            b = int(br * (0.65 + 0.35 * math.sin(t * 2.5 + sx)))
            pygame.draw.rect(scr, (b, b, min(255, b + 20)), (int(sx), int(y), size, size))
        if grid:
            self.draw_neon_grid(t, GRID_Y)

    def font_size(self, size):
        fonts = self._screen_assets()["fonts"]
        if size not in fonts:
            fonts[size] = pygame.font.Font(None, size)
        return fonts[size]

    def neon_title(self, text, glow=NEON_PINK, size=84, color=WHITE):
        """Big glowing title text (made once, then reused)."""
        cache = self._screen_assets()["titles"]
        key = (text, glow, size, color)
        img = cache.get(key)
        if img is None:
            core = self._spaced(self.font_size(size), text, color, 4)
            img = cache[key] = self._neon(core, glow, 24, 3)
        return img

    def draw_glass(self, rect, radius=14, border=PANEL_EDGE):
        """See-through dark panel with a thin border."""
        cache = self._screen_assets()["glass"]
        key = (rect.w, rect.h, radius)
        surf = cache.get(key)
        if surf is None:
            surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            pygame.draw.rect(surf, PANEL_FILL + (215,), surf.get_rect(), border_radius=radius)
            cache[key] = surf
        self.screen.blit(surf, rect)
        if border:
            pygame.draw.rect(self.screen, border, rect, 2, border_radius=radius)

    def draw_neon_frame(self, rect, width=3, radius=6):
        """Pulsing cyan/pink frame with a soft glow (selected things, the board)."""
        t = time.monotonic()
        col = _mix(NEON_CYAN, NEON_PINK, 0.5 + 0.5 * math.sin(t * 2))
        for grow, shade in ((12, 0.22), (6, 0.45)):
            pygame.draw.rect(self.screen, _mix(SKY_BOTTOM, col, shade),
                             rect.inflate(grow, grow), 2, border_radius=radius + grow // 2)
        pygame.draw.rect(self.screen, col, rect, width, border_radius=radius)

    # ------------------------------------------------------------------
    # The black bars beside the game (wide fullscreen monitors)
    # ------------------------------------------------------------------
    def _side_background(self, size):
        dw, dh = size
        bg = pygame.Surface(size).convert()
        for y in range(dh):
            pygame.draw.line(bg, _mix(SKY_TOP, SKY_BOTTOM, y / float(dh)), (0, y), (dw, y))
        rng = random.Random(11)
        for _ in range(int(dw * dh / 3500)):
            x, y = rng.uniform(0, dw), rng.uniform(0, HORIZON)
            b = rng.randint(90, 230)
            pygame.draw.rect(bg, (b, b, min(255, b + 20)), (int(x), int(y), rng.choice((1, 1, 2)), 2))
        # static neon grid, vanishing in the middle of the screen
        _draw_planet(bg, dw // 6, dh // 3, dh // 7, (120, 150, 220), (14, 20, 60),
                     ring=(150, 170, 220))
        pygame.draw.rect(bg, (3, 7, 20), (0, HORIZON, dw, dh - HORIZON))
        cx = dw // 2
        for i in range(-30, 31):
            pygame.draw.line(bg, (30, 70, 140), (cx + i * 10, HORIZON), (cx + i * 90, dh), 2)
        for j in range(1, 10):
            d = j / 9.0
            y = HORIZON + int((dh - HORIZON) * d * d)
            pygame.draw.line(bg, _mix((12, 30, 70), NEON_CYAN, d), (0, y), (dw, y), 1 if d < 0.35 else 2)
        pygame.draw.line(bg, NEON_CYAN, (0, HORIZON), (dw, HORIZON), 3)
        return bg

    def draw_sides(self, disp, off):
        """Fill the bars left and right of the game with the starry sky. It is
        drawn once; every frame only the glowing edges are redrawn."""
        key = (disp.get_size(), off)
        if self.__dict__.get("_sides_key") != key:
            self.__dict__["_sides_key"] = key
            disp.blit(self._side_background(disp.get_size()), (0, 0))
        t = time.monotonic()
        col = _mix(NEON_CYAN, NEON_PINK, 0.5 + 0.5 * math.sin(t * 2))
        h = disp.get_height()
        for x, inward in ((off - 1, -1), (off + W, 1)):
            for k, shade in ((6, 0.2), (3, 0.45)):
                xx = x - inward * k
                pygame.draw.line(disp, _mix(SKY_BOTTOM, col, shade), (xx, 0), (xx, h), 2)
            pygame.draw.line(disp, col, (x, 0), (x, h), 2)
