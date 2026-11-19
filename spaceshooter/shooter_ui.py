"""
Screens, menus and drawing for the Space Shooter.
This is a mixin: main.py's App inherits from it, so everything here can use
App's helpers (self.text, self.draw_menu, self.set_state, ...).
"""
import math
import time

import pygame

import shooter as sh
from common import W, H, WHITE, GREY, GOLD, RED, GREEN

SPACE_BG = (5, 5, 16)
SENT_COLOR = (255, 60, 200)            # outline of enemies sent by another player
# by enemy code: 0 drone, 1 fighter, 2 tank, 3 splitter, 4 mini, 5 diver, 6 rock, 7 curse
ENEMY_COLORS = {0: (230, 70, 70), 1: (240, 150, 40), 2: (160, 80, 210),
                3: (80, 200, 110), 4: (150, 240, 150), 5: (255, 110, 60),
                6: (130, 125, 120), 7: (150, 60, 200)}
ENEMY_SIZE = {code: (sh.ENEMIES[k]["w"], sh.ENEMIES[k]["h"])
              for k, code in sh.ENEMY_CODE.items()}
CURSE_COLOR = (150, 60, 200)
UPGRADE_COLORS = {
    "bullets": (255, 220, 70),
    "damage": (255, 100, 90),
    "rate": (255, 160, 50),
    "pierce": (120, 255, 200),
    "homing": (255, 130, 220),
    "size": (200, 150, 255),
    "speed": (90, 220, 255),
    "shield": (110, 170, 255),
    "life": (110, 255, 120),
    # rare ones
    "laser": (255, 70, 70),
    "wingman": (120, 230, 255),
    "phase": (190, 140, 255),
    "boom": (255, 140, 40),
    "halo": (255, 230, 120),
    "phoenix": (255, 120, 40),
    "slow": (130, 180, 255),
}
UPGRADE_SHORT = {"bullets": "BUL", "damage": "DMG", "rate": "RATE", "pierce": "PRC",
                 "homing": "HOM", "size": "BIG", "speed": "SPD", "shield": "SHD",
                 "laser": "LASER", "wingman": "WING", "phase": "PHASE", "boom": "BOOM",
                 "halo": "HALO", "phoenix": "PHOENIX", "slow": "SLOW"}


def _dim(c):
    return tuple(v // 3 for v in c)


def _light(c, amount=70):
    return tuple(min(255, v + amount) for v in c)


class ShooterUI:
    # ------------------------------------------------------------------
    # Single player flow
    # ------------------------------------------------------------------
    def start_shooter(self):
        self.game = sh.Shooter(mode=self.mode_of("shooter"))
        self.set_state("sh_play")

    def handle_sh_main(self, presses):
        r = self.menus["sh_main"].handle(presses)
        if not r:
            return
        kind, idx = r
        if self.mode_menu_input("sh_main", kind, idx):
            return
        if idx > 1:
            idx -= 1                      # (item 1 is MODE)
        if kind == "back":
            self.set_state("games", reset=False)
        elif kind == "ok":
            if idx == 0:
                self.start_shooter()
            elif idx == 1:
                self.mp_game = "shooter"
                self.set_state("mp")
            elif idx == 2:
                self.show_scores("sh_main", game=self.board_key("shooter", self.mode_of("shooter")))
            elif idx == 3:
                self.set_state("games", reset=False)

    def handle_sh_play(self, presses):
        if "button1" in presses:                 # BUTTON1 = menu (like Tetris)
            self.set_state("sh_pause")

    def handle_sh_pause(self, presses):
        r = self.menus["sh_pause"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "back" or (kind == "ok" and idx == 0):
            self.set_state("sh_play")
        elif kind == "ok":
            if idx == 1:
                self.start_shooter()
            elif idx == 2:
                self.show_scores("sh_pause", game=self.board_key("shooter", self.game.mode))
            elif idx == 3:
                self.set_state("sh_main")

    def handle_sh_over(self, presses):
        r = self.menus["sh_over"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "ok":
            if idx == 0:
                self.start_shooter()
            elif idx == 1:
                self.show_scores("sh_over", game=self.board_key("shooter", self.game.mode))
            elif idx == 2:
                self.set_state("sh_main")

    def update_sh_play(self, dt):
        g = self.game
        held = self.input.held
        g.update(dt, "left" in held, "right" in held, "button2" in held)
        if g.game_over:
            self.finish_run("shooter", g, g.kills, g.wave, "sh_over")

    # ------------------------------------------------------------------
    # Multiplayer (player side)
    # ------------------------------------------------------------------
    def update_shooter_mp(self, dt):
        g = self.game
        c = self.client
        if c is None:
            return
        held = self.input.held
        active = not self.mp_menu_open and not g.game_over
        g.update(dt, active and "left" in held, active and "right" in held,
                 active and "button2" in held)
        for kind, fx in g.kills_unsent:
            c.send_kill(kind, fx)
        g.kills_unsent = []
        now = time.monotonic()
        if g.game_over:
            if not self.mp_sent_dead:
                self.mp_sent_dead = True
                c.send_dead(g.snapshot(), g.score, g.kills, g.wave)
        elif now - self.last_state_send >= 0.066:       # ~15 updates per second
            self.last_state_send = now
            c.send_state(g.snapshot(), g.score, g.kills, g.wave)

    # ------------------------------------------------------------------
    # Drawing: menus
    # ------------------------------------------------------------------
    def draw_sh_main(self):
        self.draw_game_menu("sh_main", self.menus["sh_main"], top=345)

    def draw_sh_play(self):
        self.draw_shooter_world(self.game)

    def draw_sh_pause(self):
        self.draw_shooter_world(self.game)
        self.screen.blit(self.overlay, (0, 0))
        self.draw_menu(self.menus["sh_pause"], "PAUSED", top=290)

    def draw_sh_over(self):
        self.draw_shooter_world(self.game)
        self.screen.blit(self.overlay, (0, 0))
        self.draw_menu(self.menus["sh_over"], "GAME OVER",
                       lines=["SCORE  %d" % self.game.score,
                              "KILLS  %d" % self.game.kills], top=360)

    # ------------------------------------------------------------------
    # Drawing: the game world
    # ------------------------------------------------------------------
    def draw_shooter_world(self, g, extra=None):
        scr = self.screen
        scr.blit(self.space_bg(), (0, 0))
        for sx, sy, sp in g.stars:
            c = int(70 + sp * 0.5)
            size = 2 if sp > 100 else 1
            pygame.draw.rect(scr, (c, c, c), (int(sx), int(sy), size, size))

        for e in g.enemies:                      # curse auras under everything
            if e["k"] == "curse":
                self.draw_aura(e["x"], e["y"], sh.CURSE_R, CURSE_COLOR, 45)
                pygame.draw.circle(scr, (110, 50, 150), (int(e["x"]), int(e["y"])),
                                   sh.CURSE_R, 2)
        if g.ups.get("halo") and not g.game_over:
            self.draw_aura(g.x, sh.PLAYER_Y, sh.HALO_R, (255, 200, 60), 34)
            pygame.draw.circle(scr, (255, 220, 110), (int(g.x), sh.PLAYER_Y), sh.HALO_R, 1)

        for o in g.boxes:
            self.draw_upgrade_box(g, o)
        if g.boxes:
            self.draw_reroll_cube(g)
        if g.boss:
            self.draw_boss(g.boss)
        for e in g.enemies:
            code = sh.ENEMY_CODE[e["k"]]
            self.draw_enemy(code, e["x"], e["y"], not e["native"], e)
            if e["max"] > 1 and e["hp"] < e["max"] and e["k"] != "rock":
                w = ENEMY_SIZE[code][0]
                frac = max(0.0, e["hp"] / float(e["max"]))
                pygame.draw.rect(scr, (60, 0, 0), (e["x"] - w / 2, e["y"] - 36, w, 5))
                pygame.draw.rect(scr, GREEN, (e["x"] - w / 2, e["y"] - 36, w * frac, 5))
        for b in g.bullets:
            self.draw_player_bullet(b)
        for q in g.ebullets:
            self.draw_laser_bolt(q["x"], q["y"], (80, 255, 110), 16, 5)
        for c in g.coin_drops:
            self.draw_coin(c["x"], c["y"], sh.COIN_R, spin=c["t"])

        if not g.game_over:
            self.draw_beam(g)
            if g.ups.get("wingman"):
                self.draw_wingman(g.wing_x, sh.PLAYER_Y + 14)
        if not g.game_over and not (g.invuln > 0 and int(g.invuln * 12) % 2 == 0):
            self.draw_player_ship(g.x, sh.PLAYER_Y, g)
            if g.shield > 0:
                pygame.draw.circle(scr, (110, 170, 255), (int(g.x), int(sh.PLAYER_Y)),
                                   34, 2 + g.shield)

        for x, y, age, max_age, color in g.effects:
            if age < 0:
                continue
            r = int(6 + 28 * age / max_age)
            pygame.draw.circle(scr, color, (int(x), int(y)), r, 3)
        if g.cursed and not g.game_over:
            self.text("CURSED - CAN'T SHOOT", self.font_small, (200, 120, 255),
                      (int(g.x), sh.PLAYER_Y - 62), "center")

        self.draw_shooter_hud(g, extra)

    def draw_shooter_hud(self, g, extra):
        scr = self.screen
        self.text("SCORE %d" % g.score, self.font_small, WHITE, (16, 12))
        if g.boss:
            self.text("WAVE %d - BOSS" % g.boss_wave, self.font_small, RED,
                      (W // 2, 12), "midtop")
            # boss health bar
            frac = max(0.0, g.boss["hp"] / float(g.boss["max"]))
            bar = pygame.Rect(0, 0, 360, 12)
            bar.midtop = (W // 2, 96)
            pygame.draw.rect(scr, (60, 0, 0), bar, border_radius=4)
            pygame.draw.rect(scr, RED, (bar.x, bar.y, int(bar.w * frac), bar.h),
                             border_radius=4)
            pygame.draw.rect(scr, WHITE, bar, 1, border_radius=4)
        else:
            self.text("WAVE %d" % g.wave, self.font_small, GREY, (W // 2, 12), "midtop")
        for i in range(max(0, g.lives)):                 # lives as small ships
            x = W - 28 - i * 32
            pygame.draw.polygon(scr, (90, 220, 255),
                                [(x, 12), (x - 12, 34), (x, 28), (x + 12, 34)])
        # progress bar to the next upgrade choice
        frac = g.upgrade_progress
        pygame.draw.rect(scr, (40, 40, 60), (16, 44, 160, 8))
        pygame.draw.rect(scr, GOLD if frac >= 1 else (120, 255, 160),
                         (16, 44, 160 * frac, 8))
        # coins, right next to the bar
        self.draw_coin(196, 48, 8)
        self.text("%d" % g.coins, self.font_small, GOLD, (210, 48), "midleft")
        # upgrade levels taken this run
        x, y = 16, 60
        for k in sh.UPGRADE_KINDS:
            lvl = g.ups.get(k, 0)
            if k == "life" or not lvl:
                continue
            rare = sh.UPGRADES[k].get("rare")
            label = UPGRADE_SHORT[k] if rare else "%s%d" % (UPGRADE_SHORT[k], lvl)
            color = UPGRADE_COLORS[k]
            if k == "phoenix" and g.phoenix_used:
                color = (90, 90, 110)
            lw = self.font_tiny.size(label)[0]
            if x + lw > W - 16:                      # next line
                x, y = 16, y + 16
            if rare:
                pygame.draw.rect(scr, (60, 45, 10), (x - 3, y - 1, lw + 6, 15),
                                 border_radius=3)
            self.text(label, self.font_tiny, color, (x, y))
            x += lw + 10
        if g.choosing and g.picks_total > 1:
            self.text("BOSS REWARD  -  PICK %d OF %d"
                      % (g.picks_total - g.picks_left + 1, g.picks_total),
                      self.font_med, (255, 120, 120),
                      (W // 2, sh.BOX_Y - sh.BOX_H // 2 - 50), "midtop")
        if g.choosing:
            if g.pick_lock > 0:                      # can't shoot yet
                self.text("WAVE CLEAR!  GET READY %d" % math.ceil(g.pick_lock),
                          self.font_med, GREY,
                          (W // 2, sh.BOX_Y + sh.BOX_H // 2 + 40), "midtop")
            else:
                self.text("SHOOT A BOX TO UPGRADE", self.font_med, GOLD,
                          (W // 2, sh.BOX_Y + sh.BOX_H // 2 + 40), "midtop")
        if g.banner:
            self.text(g.banner[0], self.font_big, (120, 255, 160),
                      (W // 2, 400), "center")
        if extra:
            self.text("%s %s" % extra, self.font_small, WHITE, (W - 16, 44), "topright")
        if g.incoming:
            self.text("INCOMING %d" % len(g.incoming), self.font_small, RED,
                      (W - 16, 70), "topright")

    def draw_aura(self, x, y, r, color, alpha):
        """See-through filled circle (cached, so it stays fast on the Pi)."""
        cache = self.__dict__.setdefault("_aura_cache", {})
        key = (r, color, alpha)
        surf = cache.get(key)
        if surf is None:
            surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, color + (alpha,), (r, r), r)
            cache[key] = surf
        self.screen.blit(surf, (int(x) - r, int(y) - r))

    def draw_player_ship(self, x, y, g=None):
        """The ship. Every upgrade adds something you can see:
        more bullets = more gun holes, damage = red stripes, fire rate = more
        engines, speed = wider wings and fins, pierce = green spike, homing =
        antennas, big bullets = a fat nose cannon, shield = blue panels, and
        each rare upgrade has its own part (laser orb, halo, bomb pods...)."""
        scr = self.screen
        ups = g.ups if g else {}

        def u(k):
            return ups.get(k, 0)

        t = time.monotonic()
        x, y = int(x), int(y)
        span = 24 + 3 * u("speed")
        hull = (150, 90, 200) if (g and g.cursed) else (90, 220, 255)
        # engines (more with fire rate)
        engines = 1 + (u("rate") + 1) // 2
        flame = 12 + 2 * u("rate") + (8 if int(t * 20) % 2 else 0)
        for i in range(engines):
            ex = x + (i - (engines - 1) / 2.0) * 9
            pygame.draw.polygon(scr, (90, 160, 255),
                                [(ex - 5, y + 16), (ex + 5, y + 16), (ex, y + 16 + flame)])
            pygame.draw.polygon(scr, (230, 245, 255),
                                [(ex - 2, y + 16), (ex + 2, y + 16), (ex, y + 10 + flame // 2)])
        # phoenix: burning wings until it has been used
        if u("phoenix") and g and not g.phoenix_used:
            lick = 5 * math.sin(t * 12)
            for side in (-1, 1):
                pygame.draw.polygon(scr, (255, 120, 40),
                                    [(x + side * 8, y + 4), (x + side * (span + 16), y - 8 + lick),
                                     (x + side * (span - 2), y + 24)])
                pygame.draw.polygon(scr, (255, 220, 90),
                                    [(x + side * 8, y + 6), (x + side * (span + 6), y - 2 + lick),
                                     (x + side * (span - 4), y + 20)])
        # speed: swept-back fins
        for i in range(u("speed")):
            for side in (-1, 1):
                fx = x + side * (span - 6 - i * 5)
                pygame.draw.line(scr, (90, 220, 255), (fx, y + 18), (fx + side * 6, y + 30), 2)
        # phase: ghostly copy of the hull
        pts = [(x, y - 22), (x - span, y + 20), (x, y + 10), (x + span, y + 20)]
        if u("phase"):
            off = 3 * math.sin(t * 5)
            ghost = [(px + off, py - 3) for px, py in pts]
            pygame.draw.polygon(scr, (190, 140, 255), ghost, 2)
        self.draw_starfighter(x, y, span, cursed=bool(g and g.cursed))
        # damage: red chevrons on the body
        for i in range(min(4, u("damage"))):
            yy = y + 6 - i * 6
            pygame.draw.lines(scr, (255, 80, 80), False,
                              [(x - 5, yy + 4), (x, yy), (x + 5, yy + 4)], 2)
        # shield: blue panels on the wings
        for i in range(u("shield")):
            for side in (-1, 1):
                pygame.draw.rect(scr, (110, 170, 255),
                                 (x + side * (11 + i * 5) - 2, y + 12 - i, 4, 5))
        # homing: antennas on the wing tips
        for i in range(u("homing")):
            for side in (-1, 1):
                ax = x + side * (span - 3 - i * 5)
                pygame.draw.line(scr, (255, 130, 220), (ax, y + 18), (ax, y + 4 - i * 2), 2)
                pygame.draw.circle(scr, (255, 200, 240), (ax, y + 3 - i * 2), 2)
        # boom shots: bomb pods under the wings
        if u("boom"):
            for side in (-1, 1):
                pygame.draw.circle(scr, (255, 140, 40), (x + side * 15, y + 22), 5)
                pygame.draw.circle(scr, (90, 40, 10), (x + side * 15, y + 22), 5, 1)
        # slow time: a little clock
        if u("slow"):
            pygame.draw.circle(scr, (230, 240, 255), (x, y + 2), 6)
            pygame.draw.circle(scr, (90, 130, 230), (x, y + 2), 6, 1)
            ang = t * 2
            pygame.draw.line(scr, (40, 60, 120), (x, y + 2),
                             (x + 4 * math.cos(ang), y + 2 + 4 * math.sin(ang)), 1)
        # more bullets: a gun rack with one hole per bullet
        n = 1 + u("bullets")
        if n > 1:
            bw = 6 + 7 * n
            pygame.draw.rect(scr, (40, 50, 70), (x - bw // 2, y - 2, bw, 7), border_radius=3)
            for i in range(n):
                hx = x + int((i - (n - 1) / 2.0) * 7)
                pygame.draw.circle(scr, (255, 235, 90), (hx, y + 1), 2)
        # big bullets: fat nose cannon
        if u("size"):
            cw = 4 + 3 * u("size")
            pygame.draw.rect(scr, (200, 150, 255), (x - cw // 2, y - 30, cw, 12), border_radius=2)
        # pierce: green spike on the nose
        if u("pierce"):
            tip = y - 26 - 4 * u("pierce")
            pygame.draw.polygon(scr, (120, 255, 200), [(x - 3, y - 18), (x + 3, y - 18), (x, tip)])
        # mega laser: glowing orb in the nose
        if u("laser"):
            charge = 0.0
            if g:
                charge = 1.0 if g.beam_active() else g.beam_charge / g.beam_charge_time()
            r = 4 + int(5 * charge) + int(1.5 * math.sin(t * 15))
            pygame.draw.circle(scr, (255, 60, 60), (x, y - 10), max(3, r))
            pygame.draw.circle(scr, WHITE, (x, y - 10), max(1, r // 2))
        # holy halo above the ship
        if u("halo"):
            pygame.draw.ellipse(scr, (255, 230, 120), (x - 15, y - 42, 30, 9), 3)
        # cursed: a cross over the guns
        if g and g.cursed:
            pygame.draw.line(scr, (220, 60, 255), (x - 8, y - 18), (x + 8, y - 2), 3)
            pygame.draw.line(scr, (220, 60, 255), (x + 8, y - 18), (x - 8, y - 2), 3)

    def draw_starfighter(self, x, y, span=24, cursed=False, scale=1.0):
        """The player's starfighter (nose up): swept wings with a red stripe and
        cannons on the tips, a long nose and a blue canopy."""
        scr = self.screen
        s = scale
        metal = (170, 150, 210) if cursed else (205, 210, 222)
        dark = (95, 100, 118)
        stripe = (200, 60, 210) if cursed else (225, 60, 50)
        sp = span * s
        for side in (-1, 1):
            wing = [(x + side * 5 * s, y - 2 * s), (x + side * sp, y + 12 * s),
                    (x + side * sp, y + 21 * s), (x + side * 6 * s, y + 15 * s)]
            pygame.draw.polygon(scr, metal, wing)
            pygame.draw.polygon(scr, dark, wing, 1)
            pygame.draw.line(scr, stripe, (x + side * 9 * s, y + 6 * s),
                             (x + side * (sp - 3 * s), y + 15 * s), max(1, int(3 * s)))
            gx = x + side * (sp - 1 * s)                           # wingtip cannon
            pygame.draw.line(scr, dark, (gx, y + 18 * s), (gx, y - 8 * s), max(1, int(3 * s)))
            pygame.draw.line(scr, (255, 120, 100), (gx, y - 8 * s), (gx, y - 10 * s), max(1, int(2 * s)))
        nose = [(x, y - 28 * s), (x - 6 * s, y - 8 * s), (x - 7 * s, y + 18 * s),
                (x + 7 * s, y + 18 * s), (x + 6 * s, y - 8 * s)]
        pygame.draw.polygon(scr, metal, nose)
        pygame.draw.polygon(scr, dark, nose, 1)
        pygame.draw.line(scr, stripe, (x, y - 26 * s), (x, y - 16 * s), max(1, int(2 * s)))
        canopy = pygame.Rect(0, 0, max(3, int(8 * s)), max(4, int(13 * s)))
        canopy.center = (int(x), int(y - 4 * s))
        pygame.draw.ellipse(scr, (60, 140, 230), canopy)
        pygame.draw.ellipse(scr, (190, 230, 255), canopy.inflate(-int(4 * s), -int(7 * s)))

    def draw_laser_bolt(self, x, y, color, length=16, width=4):
        """A glowing laser bolt (vertical): coloured glow, white-hot core."""
        r = pygame.Rect(0, 0, width + 4, length + 4)
        r.center = (int(x), int(y))
        pygame.draw.rect(self.screen, _dim(color), r, border_radius=(width + 4) // 2)
        r = pygame.Rect(0, 0, width, length)
        r.center = (int(x), int(y))
        pygame.draw.rect(self.screen, color, r, border_radius=width // 2)
        core = pygame.Rect(0, 0, max(1, width // 2), max(2, length - 4))
        core.center = (int(x), int(y))
        pygame.draw.rect(self.screen, (255, 245, 240), core, border_radius=1)

    def draw_wingman(self, x, y):
        x, y = int(x), int(y)
        flame = 4 if int(time.monotonic() * 20) % 2 else 0
        pygame.draw.polygon(self.screen, (90, 160, 255),
                            [(x - 3, y + 10), (x + 3, y + 10), (x, y + 16 + flame)])
        self.draw_starfighter(x, y, 15, scale=0.55)

    def draw_beam(self, g):
        """Mega laser: the beam itself (charging glow is on the ship)."""
        if not g.ups.get("laser") or not g.beam_active():
            return
        w = int(g.beam_width())
        flick = int(3 * math.sin(time.monotonic() * 40))
        top, bottom = 0, sh.PLAYER_Y - 18
        x = int(g.x)
        outer = pygame.Rect(x - w // 2 - flick, top, w + flick * 2, bottom - top)
        pygame.draw.rect(self.screen, (200, 30, 40), outer)
        inner = pygame.Rect(x - w // 4, top, max(4, w // 2), bottom - top)
        pygame.draw.rect(self.screen, (255, 120, 120), inner)
        core = pygame.Rect(x - max(2, w // 10), top, max(4, w // 5), bottom - top)
        pygame.draw.rect(self.screen, WHITE, core)

    def draw_enemy(self, code, x, y, sent, e=None):
        scr = self.screen
        color = ENEMY_COLORS[code]
        if code >= 3:
            self.draw_special_enemy(code, x, y, sent, e)
            return
        x, y = int(x), int(y)
        hull = (58, 62, 74)
        edge = (125, 130, 145)
        glow = int(4 * math.sin(time.monotonic() * 8))
        if code == 0:                                       # interceptor: arrowhead
            pts = [(x - 19, y - 17), (x + 19, y - 17), (x, y + 17)]
        elif code == 1:                                     # fighter: wide wedge
            pts = [(x, y + 20), (x - 23, y - 6), (x - 14, y - 20),
                   (x + 14, y - 20), (x + 23, y - 6)]
        else:                                               # gunship: armoured block
            pts = [(x - 35, y - 12), (x - 22, y - 28), (x + 22, y - 28),
                   (x + 35, y - 12), (x + 35, y + 12), (x + 22, y + 28),
                   (x - 22, y + 28), (x - 35, y + 12)]
        pygame.draw.polygon(scr, hull, pts)
        # engines at the back (the top: they fly down at you)
        for ex in ((x,) if code == 0 else (x - 8, x + 8) if code == 1 else (x - 16, 0, x + 16)):
            if ex:
                pygame.draw.circle(scr, (255, 140, 60), (ex, y - 19 if code < 2 else y - 27), 3 + (glow > 0))
        if code == 2:
            for k in (-1, 1):                               # panel lines and gun barrels
                pygame.draw.line(scr, edge, (x - 30, y + k * 8), (x + 30, y + k * 8), 1)
                pygame.draw.rect(scr, (30, 32, 40), (x + k * 20 - 3, y + 18, 6, 16))
            pygame.draw.rect(scr, color, (x - 18, y - 4, 36, 8), border_radius=3)
        else:                                               # a coloured accent stripe
            pygame.draw.line(scr, color, (x - 10, y - 12), (x + 10, y - 12), 3)
        pygame.draw.circle(scr, (255, 40, 40), (x, y + (4 if code < 2 else 0)), 5 + (glow > 1))
        pygame.draw.circle(scr, (255, 200, 190), (x, y + (4 if code < 2 else 0)), 2)
        pygame.draw.polygon(scr, SENT_COLOR if sent else edge, pts, 4 if sent else 2)

    def draw_special_enemy(self, code, x, y, sent, e):
        scr = self.screen
        color = ENEMY_COLORS[code]
        t = time.monotonic()
        x, y = int(x), int(y)
        edge = SENT_COLOR if sent else _light(color)
        if code == 3:                              # splitter: cracked diamond
            pts = [(x, y - 21), (x + 23, y), (x, y + 21), (x - 23, y)]
            pygame.draw.polygon(scr, color, pts)
            pygame.draw.lines(scr, (30, 80, 40), False,
                              [(x, y - 21), (x - 4, y - 6), (x + 4, y + 6), (x, y + 21)], 3)
            pygame.draw.polygon(scr, edge, pts, 4 if sent else 2)
        elif code == 4:                            # mini
            pts = [(x - 12, y - 11), (x + 12, y - 11), (x, y + 11)]
            pygame.draw.polygon(scr, color, pts)
            pygame.draw.polygon(scr, edge, pts, 2)
        elif code == 5:                            # diver: arrow, blinks while aiming
            mode = e.get("mode") if e else "down"
            c = color
            if mode == "aim" and int(t * 14) % 2:
                c = WHITE
            if mode == "dash" and e:
                sp = math.hypot(e["vx"], e["vy"]) or 1.0
                for i in range(1, 4):
                    pygame.draw.circle(scr, (255, 160, 90),
                                       (int(x - e["vx"] / sp * 14 * i),
                                        int(y - e["vy"] / sp * 14 * i)), 6 - i)
            pts = [(x, y + 23), (x - 20, y - 10), (x - 8, y - 4), (x - 8, y - 23),
                   (x + 8, y - 23), (x + 8, y - 4), (x + 20, y - 10)]
            pygame.draw.polygon(scr, c, pts)
            pygame.draw.polygon(scr, edge, pts, 4 if sent else 2)
        elif code == 6:                            # rock: lumpy, spinning, unbreakable
            ph = e["phase"] if e else 0.0
            spin = (e["t"] if e else 0.0) * 0.8 + ph
            pts = []
            for i in range(9):
                a = spin + i * math.tau / 9
                r = 27 + 5 * math.sin(i * 2.3 + ph * 3)
                pts.append((x + math.cos(a) * r, y + math.sin(a) * r))
            pygame.draw.polygon(scr, color, pts)
            pygame.draw.polygon(scr, (70, 65, 60), pts, 3)
            for i, (dx, dy, cr) in enumerate(((-8, -6, 6), (9, 5, 5), (-3, 11, 4))):
                a = spin
                cx = x + dx * math.cos(a) - dy * math.sin(a)
                cy = y + dx * math.sin(a) + dy * math.cos(a)
                pygame.draw.circle(scr, (95, 90, 85), (int(cx), int(cy)), cr)
            if sent:
                pygame.draw.polygon(scr, SENT_COLOR, pts, 2)
        elif code == 7:                            # curse eye
            pulse = 2 * math.sin(t * 5)
            pygame.draw.circle(scr, (60, 20, 90), (x, y), int(26 + pulse))
            pygame.draw.circle(scr, color, (x, y), 22)
            pygame.draw.ellipse(scr, (240, 230, 255), (x - 14, y - 8, 28, 16))
            pygame.draw.circle(scr, (120, 0, 40), (x, y), 6)
            pygame.draw.circle(scr, (10, 0, 10), (x, y), 3)
            pygame.draw.circle(scr, edge, (x, y), 22, 4 if sent else 2)

    def draw_player_bullet(self, b):
        w, h = b["w"], b["h"]
        color = (255, 130, 220) if b["homing"] else (255, 80, 60)
        if b["pierce"]:
            color = (120, 255, 200)
        if b.get("boom"):
            color = (255, 150, 50)
        if b.get("phase"):
            color = (200, 160, 255)
        self.draw_laser_bolt(b["x"], b["y"], color, max(10, int(h) + 6), max(3, int(w)))

    def draw_boss(self, b):
        """Big mothership. Colour changes with every boss; flashes when hit."""
        scr = self.screen
        x, y = int(b["x"]), int(b["y"])
        hw, hh = sh.BOSS_W // 2, sh.BOSS_H // 2
        colors = [(220, 60, 60), (90, 140, 255), (80, 220, 140), (255, 170, 50)]
        accent = colors[(b["n"] - 1) % len(colors)]
        color = WHITE if b["flash"] > 0 else (66, 70, 84)
        hull = [(x - hw, y - 10), (x - hw + 40, y - hh), (x + hw - 40, y - hh),
                (x + hw, y - 10), (x + hw - 25, y + hh - 20), (x + 30, y + hh),
                (x - 30, y + hh), (x - hw + 25, y + hh - 20)]
        pygame.draw.polygon(scr, color, hull)
        for k in range(-2, 3):                                # armour plating lines
            pygame.draw.line(scr, (95, 100, 115), (x - hw + 30, y + k * 12), (x + hw - 30, y + k * 12), 1)
        for k in range(-3, 4):                                # rows of lit windows
            pygame.draw.rect(scr, accent, (x + k * 22 - 3, y - hh + 12, 6, 3))
        pygame.draw.polygon(scr, (140, 145, 160), hull, 3)
        for side in (-1, 1):                     # wings with guns
            wing = [(x + side * hw, y - 10), (x + side * (hw + 18), y + 20),
                    (x + side * (hw - 25), y + hh - 20)]
            pygame.draw.polygon(scr, _light(color, 20), wing)
            pygame.draw.rect(scr, (40, 42, 52), (x + side * 55 - 6, y + hh - 18, 12, 24))
        pulse = 4 * math.sin(time.monotonic() * 6)
        pygame.draw.circle(scr, (20, 20, 28), (x, y), 26)
        pygame.draw.circle(scr, accent, (x, y), int(16 + pulse))
        pygame.draw.circle(scr, WHITE, (x, y), int(6 + pulse / 2))

    def draw_coin(self, x, y, r, spin=None):
        """A gold coin. With spin (seconds) it flips while it flies."""
        w = r if spin is None else max(2, int(r * abs(math.cos(spin * 9))))
        rect = pygame.Rect(0, 0, w * 2, r * 2)
        rect.center = (int(x), int(y))
        pygame.draw.ellipse(self.screen, GOLD, rect)
        pygame.draw.ellipse(self.screen, (255, 245, 170), rect.inflate(-w, -r), 0)
        pygame.draw.ellipse(self.screen, (170, 120, 20), rect, 2)

    def draw_reroll_cube(self, g):
        """The little reroll cube at the far left while choosing."""
        ready = g.can_reroll() and g.pick_lock <= 0
        size = sh.REROLL_SIZE
        bob = int(3 * math.sin(time.monotonic() * 4)) if ready else 0
        rect = pygame.Rect(0, 0, size, size)
        rect.center = (sh.REROLL_X, sh.REROLL_Y + bob)
        color = GOLD if ready else (80, 80, 100)
        pygame.draw.rect(self.screen, (18, 18, 38), rect, border_radius=8)
        pygame.draw.rect(self.screen, color, rect, 4 if ready else 2, border_radius=8)
        # circular arrow = "roll again"
        cx, cy, rr = rect.centerx, rect.centery - 4, 13
        arc = pygame.Rect(cx - rr, cy - rr, rr * 2, rr * 2)
        pygame.draw.arc(self.screen, color, arc, math.radians(40), math.radians(330), 3)
        tip = (cx + rr * math.cos(math.radians(40)), cy - rr * math.sin(math.radians(40)))
        pygame.draw.polygon(self.screen, color, [(tip[0] - 7, tip[1] - 4),
                                                 (tip[0] + 6, tip[1] - 6),
                                                 (tip[0] + 2, tip[1] + 7)])
        self.text("%d" % sh.REROLL_COST, self.font_tiny, color,
                  (rect.centerx + 5, rect.bottom - 10), "center")
        self.draw_coin(rect.centerx - 6, rect.bottom - 10, 5)
        self.text("REROLL", self.font_tiny, color, (rect.centerx, rect.bottom + 4), "midtop")

    def draw_upgrade_box(self, g, o):
        k = o["k"]
        color = UPGRADE_COLORS[k]
        rare = sh.UPGRADES[k].get("rare")
        t = time.monotonic()
        ready = o["y"] >= sh.BOX_Y and o["arm"] <= 0 and g.pick_lock <= 0
        bob = int(4 * math.sin(t * 3 + o["x"])) if ready else 0
        rect = pygame.Rect(0, 0, sh.BOX_W, sh.BOX_H)
        rect.center = (int(o["x"]), int(o["y"]) + bob)
        pygame.draw.rect(self.screen, (44, 34, 12) if rare else (18, 18, 38), rect,
                         border_radius=14)
        pulse = 5 if ready and int(t * 5) % 2 else 3
        if rare:                                   # gold frame + sparkles
            frame = GOLD if int(t * 4) % 2 else color
            pygame.draw.rect(self.screen, frame, rect.inflate(8, 8), 3, border_radius=17)
            pygame.draw.rect(self.screen, color, rect, pulse, border_radius=14)
            for i in range(4):
                a = t * 1.6 + i * math.tau / 4
                sx = rect.centerx + math.cos(a) * (rect.w / 2 + 6)
                sy = rect.centery + math.sin(a) * (rect.h / 2 + 6)
                pygame.draw.circle(self.screen, WHITE, (int(sx), int(sy)), 3)
            tag = pygame.Rect(0, 0, 64, 20)
            tag.center = (rect.centerx, rect.top)
            pygame.draw.rect(self.screen, GOLD, tag, border_radius=6)
            self.text("RARE", self.font_tiny, (40, 25, 0), tag.center, "center")
        else:
            pygame.draw.rect(self.screen, color if ready else GREY, rect, pulse,
                             border_radius=14)
        top, bottom = sh.UPGRADES[k]["name"]
        if bottom:
            self.text(top, self.font_med, color, (rect.centerx, rect.centery - 32), "center")
            self.text(bottom, self.font_med, color, (rect.centerx, rect.centery), "center")
        else:
            self.text(top, self.font_med, color, (rect.centerx, rect.centery - 16), "center")
        if rare:
            lvl_text = "ONE OF A KIND"
        elif k == "life":
            lvl_text = "LIVES %d" % g.lives
        else:
            lvl_text = "LV %d > %d" % (g.ups[k], g.ups[k] + 1)
        self.text(lvl_text, self.font_tiny, WHITE, (rect.centerx, rect.bottom - 26), "center")

    # ------------------------------------------------------------------
    # Drawing: the host's spectator view of one player's screen
    # ------------------------------------------------------------------
    def draw_shooter_snapshot(self, snap, x, y, s):
        scr = self.screen
        rect = pygame.Rect(x, y, int(sh.SW * s), int(sh.SH * s))
        pygame.draw.rect(scr, SPACE_BG, rect)
        if not isinstance(snap, dict):
            return
        scr.set_clip(rect)
        try:
            for ox, oy, kind in snap.get("o", []):
                bw, bh = max(6, int(sh.BOX_W * s)), max(6, int(sh.BOX_H * s))
                color = UPGRADE_COLORS[sh.UPGRADE_KINDS[kind]]
                pygame.draw.rect(scr, color, (x + ox * s - bw / 2, y + oy * s - bh / 2,
                                              bw, bh), 2)
            z = snap.get("z")
            if z:                                  # boss
                zx, zy, pct = z
                bw, bh = max(10, int(sh.BOSS_W * s)), max(8, int(sh.BOSS_H * s))
                r = pygame.Rect(0, 0, bw, bh)
                r.center = (int(x + zx * s), int(y + zy * s))
                pygame.draw.rect(scr, (200, 60, 90), r)
                pygame.draw.rect(scr, RED, (rect.x + 4, rect.y + 4,
                                            int((rect.w - 8) * pct / 100.0), 4))
            lz = snap.get("lz", 0)
            if lz:                                 # mega laser beam
                bw = max(2, int(lz * s))
                pygame.draw.rect(scr, (230, 50, 60), (x + snap["x"] * s - bw / 2, y,
                                                      bw, sh.PLAYER_Y * s))
            for code, ex, ey, sent in snap.get("e", []):
                w, h = ENEMY_SIZE[code]
                w, h = max(4, int(w * s)), max(4, int(h * s))
                r = pygame.Rect(0, 0, w, h)
                r.center = (int(x + ex * s), int(y + ey * s))
                pygame.draw.rect(scr, ENEMY_COLORS[code], r)
                if sent:
                    pygame.draw.rect(scr, SENT_COLOR, r, 2)
            for bx, by, big in snap.get("b", []):
                bw, bh = (max(3, int(9 * s)), max(6, int(70 * s))) if big else \
                         (max(2, int(5 * s)), max(3, int(16 * s)))
                pygame.draw.rect(scr, (255, 235, 90), (x + bx * s - bw / 2,
                                                       y + by * s - bh / 2, bw, bh))
            for qx, qy in snap.get("q", []):
                pygame.draw.rect(scr, RED, (x + qx * s - 2, y + qy * s - 2, 4, 4))
            if snap.get("l", 1) > 0:
                px, py = x + snap["x"] * s, y + sh.PLAYER_Y * s
                k = max(8, int(26 * s))
                pygame.draw.polygon(scr, (90, 220, 255),
                                    [(px, py - k), (px - k, py + k * 0.8),
                                     (px, py + k * 0.4), (px + k, py + k * 0.8)])
        except (TypeError, ValueError, IndexError, KeyError, AttributeError):
            pass
        finally:
            scr.set_clip(None)
