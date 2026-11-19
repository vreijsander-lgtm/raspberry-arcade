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
ENEMY_COLORS = {0: (230, 70, 70), 1: (240, 150, 40), 2: (160, 80, 210)}
ENEMY_SIZE = {0: (38, 34), 1: (46, 40), 2: (70, 56)}
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
}
UPGRADE_SHORT = {"bullets": "BUL", "damage": "DMG", "rate": "RATE", "pierce": "PRC",
                 "homing": "HOM", "size": "BIG", "speed": "SPD", "shield": "SHD"}


def _light(c, amount=70):
    return tuple(min(255, v + amount) for v in c)


class ShooterUI:
    # ------------------------------------------------------------------
    # Single player flow
    # ------------------------------------------------------------------
    def start_shooter(self):
        self.game = sh.Shooter()
        self.set_state("sh_play")

    def handle_sh_main(self, presses):
        r = self.menus["sh_main"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "back":
            self.set_state("games", reset=False)
        elif kind == "ok":
            if idx == 0:
                self.start_shooter()
            elif idx == 1:
                self.mp_game = "shooter"
                self.set_state("mp")
            elif idx == 2:
                self.show_scores("sh_main", game="shooter")
            elif idx == 3:
                self.toggle_fullscreen()
            elif idx == 4:
                self.set_state("games", reset=False)
        elif kind in ("left", "right") and idx == 3:
            self.toggle_fullscreen()

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
                self.show_scores("sh_pause", game="shooter")
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
                self.show_scores("sh_over", game="shooter")
            elif idx == 2:
                self.set_state("sh_main")

    def update_sh_play(self, dt):
        g = self.game
        held = self.input.held
        g.update(dt, "left" in held, "right" in held, "button2" in held)
        if g.game_over:
            if self.scores_sh.qualifies(g.score):
                self.entry_ctx = {"scores": self.scores_sh, "score": g.score,
                                  "lines": g.kills, "level": g.wave,
                                  "ret": "sh_over", "game": "shooter"}
                self.cursor = 0
                self.set_state("entry")
            else:
                self.set_state("sh_over")

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
        cx = W // 2
        self.text("SPACE", self.font_huge, (90, 220, 255), (cx, 100), "center")
        self.text("SHOOTER", self.font_huge, GOLD, (cx, 190), "center")
        self.draw_menu(self.menus["sh_main"], top=340)

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
        scr.fill(SPACE_BG)
        for sx, sy, sp in g.stars:
            c = int(70 + sp * 0.5)
            size = 2 if sp > 100 else 1
            pygame.draw.rect(scr, (c, c, c), (int(sx), int(sy), size, size))

        for o in g.boxes:
            self.draw_upgrade_box(g, o)
        for e in g.enemies:
            code = sh.ENEMY_CODE[e["k"]]
            self.draw_enemy(code, e["x"], e["y"], not e["native"])
            if e["max"] > 1 and e["hp"] < e["max"]:
                w = ENEMY_SIZE[code][0]
                frac = max(0.0, e["hp"] / float(e["max"]))
                pygame.draw.rect(scr, (60, 0, 0), (e["x"] - w / 2, e["y"] - 36, w, 5))
                pygame.draw.rect(scr, GREEN, (e["x"] - w / 2, e["y"] - 36, w * frac, 5))
        for b in g.bullets:
            self.draw_player_bullet(b)
        for q in g.ebullets:
            pygame.draw.circle(scr, RED, (int(q["x"]), int(q["y"])), 6)
            pygame.draw.circle(scr, (255, 190, 190), (int(q["x"]), int(q["y"])), 3)

        if not g.game_over and not (g.invuln > 0 and int(g.invuln * 12) % 2 == 0):
            self.draw_player_ship(g.x, sh.PLAYER_Y)
            if g.shield > 0:
                pygame.draw.circle(scr, (110, 170, 255), (int(g.x), int(sh.PLAYER_Y)),
                                   34, 2 + g.shield)

        for x, y, age, max_age, color in g.effects:
            r = int(6 + 28 * age / max_age)
            pygame.draw.circle(scr, color, (int(x), int(y)), r, 3)

        self.draw_shooter_hud(g, extra)

    def draw_shooter_hud(self, g, extra):
        scr = self.screen
        self.text("SCORE %d" % g.score, self.font_small, WHITE, (16, 12))
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
        # upgrade levels taken this run
        x = 16
        for k in sh.UPGRADE_KINDS:
            lvl = g.ups.get(k, 0)
            if k == "life" or not lvl:
                continue
            label = "%s%d" % (UPGRADE_SHORT[k], lvl)
            self.text(label, self.font_tiny, UPGRADE_COLORS[k], (x, 60))
            x += self.font_tiny.size(label)[0] + 10
        if g.choosing:
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

    def draw_player_ship(self, x, y):
        scr = self.screen
        flame = 8 if int(time.monotonic() * 20) % 2 else 0
        pygame.draw.polygon(scr, (255, 150, 40),
                            [(x - 8, y + 14), (x + 8, y + 14), (x, y + 26 + flame)])
        pts = [(x, y - 22), (x - 24, y + 20), (x, y + 10), (x + 24, y + 20)]
        pygame.draw.polygon(scr, (90, 220, 255), pts)
        pygame.draw.polygon(scr, WHITE, pts, 2)

    def draw_enemy(self, code, x, y, sent):
        scr = self.screen
        color = ENEMY_COLORS[code]
        if code == 0:
            pts = [(x - 19, y - 17), (x + 19, y - 17), (x, y + 17)]
        elif code == 1:
            pts = [(x, y + 20), (x - 23, y - 6), (x - 14, y - 20),
                   (x + 14, y - 20), (x + 23, y - 6)]
        else:
            pts = [(x - 35, y - 12), (x - 22, y - 28), (x + 22, y - 28),
                   (x + 35, y - 12), (x + 35, y + 12), (x + 22, y + 28),
                   (x - 22, y + 28), (x - 35, y + 12)]
        pygame.draw.polygon(scr, color, pts)
        if code == 2:
            pygame.draw.rect(scr, (90, 40, 130), (x - 6, y + 6, 12, 26))
        pygame.draw.polygon(scr, SENT_COLOR if sent else _light(color), pts,
                            4 if sent else 2)

    def draw_player_bullet(self, b):
        w, h = b["w"], b["h"]
        color = (255, 130, 220) if b["homing"] else (255, 235, 90)
        if b["pierce"]:
            color = (120, 255, 200)
        r = pygame.Rect(0, 0, max(2, int(w)), max(4, int(h)))
        r.center = (int(b["x"]), int(b["y"]))
        pygame.draw.rect(self.screen, color, r, border_radius=int(w // 2))
        if w > 7:
            pygame.draw.rect(self.screen, WHITE, r.inflate(-int(w * 0.6), -4),
                             border_radius=2)

    def draw_upgrade_box(self, g, o):
        k = o["k"]
        color = UPGRADE_COLORS[k]
        ready = o["y"] >= sh.BOX_Y and o["arm"] <= 0
        bob = int(4 * math.sin(time.monotonic() * 3 + o["x"])) if ready else 0
        rect = pygame.Rect(0, 0, sh.BOX_W, sh.BOX_H)
        rect.center = (int(o["x"]), int(o["y"]) + bob)
        pygame.draw.rect(self.screen, (18, 18, 38), rect, border_radius=14)
        pulse = 5 if ready and int(time.monotonic() * 5) % 2 else 3
        pygame.draw.rect(self.screen, color if ready else GREY, rect, pulse,
                         border_radius=14)
        top, bottom = sh.UPGRADES[k]["name"]
        if bottom:
            self.text(top, self.font_med, color, (rect.centerx, rect.centery - 32), "center")
            self.text(bottom, self.font_med, color, (rect.centerx, rect.centery), "center")
        else:
            self.text(top, self.font_med, color, (rect.centerx, rect.centery - 16), "center")
        if k == "life":
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
