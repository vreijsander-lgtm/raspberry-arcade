"""
Screens, menus and drawing for Saber Brawl (the fighting game).
This is a mixin like platformer_ui: main.py's App inherits from it, so
everything here can use App's helpers (self.text, self.draw_menu, ...).

The fighters are drawn from a little skeleton: every pose is a set of
angles (degrees) for the body parts, see POSES below.
"""
import math
import random
import time

import pygame

import fighter as fg
from common import W, H, WHITE, GOLD, RED

try:
    from title_ui import _draw_planet
except ImportError:                          # (only for testing without main/)
    def _draw_planet(surf, cx, cy, r, light, dark, ring=None, bands=True):
        pygame.draw.circle(surf, light, (cx, cy), r)

try:
    from multiplayer import clean_name as mp_name
except ImportError:                          # only needed for multiplayer
    def mp_name(name):
        return str(name)[:12] or "PLAYER"

# body part lengths (px at scale 1)
THIGH, SHIN, TORSO, UPPER, FORE, HEAD_R, NECK = 46, 46, 62, 34, 34, 17, 7
OUTLINE = (12, 6, 26)
BLADE_LEN = 78                         # laser sword length (px at scale 1)
HORIZON_FG = 742                       # top of the neon floor grid

# Angles: arms and legs 0 = pointing down, 90 = pointing forward, 180 = up,
# negative = backwards. tor = the body: 0 = upright, + = leaning forward.
# ft/fs = front thigh / shin, bt/bs = back leg, fu/ff = front upper arm /
# forearm, bu/bf = back arm. hip = fixed hip height (else: feet on the floor),
# rise = whole body lifted (px).
STANCE = dict(ft=28, fs=2, bt=-24, bs=-8)
GUARD_ARMS = dict(fu=55, ff=150, bu=30, bf=140)
POSES = {
    "idle": dict(tor=8, **GUARD_ARMS, **STANCE),
    "crouch": dict(tor=48, fu=70, ff=150, bu=45, bf=150, ft=75, fs=-5, bt=20, bs=-70),
    "prejump": dict(tor=18, ft=62, fs=-10, bt=14, bs=-48, **GUARD_ARMS),
    "jump": dict(tor=10, ft=78, fs=-22, bt=42, bs=-62, fu=60, ff=160, bu=40, bf=150),
    "guard": dict(tor=-6, fu=30, ff=168, bu=58, bf=172, **STANCE),
    "guard_low": dict(tor=40, fu=45, ff=165, bu=70, bf=170, ft=75, fs=-5, bt=20, bs=-70),
    "hit": dict(tor=-28, fu=10, ff=-20, bu=-25, bf=-45, ft=20, fs=0, bt=-15, bs=-5),
    "down": dict(tor=-65, fu=-60, ff=-95, bu=-40, bf=-75, ft=62, fs=40, bt=50, bs=28),
    "lying": dict(tor=-93, fu=-100, ff=-100, bu=-80, bf=-95, ft=95, fs=92, bt=86, bs=92, hip=14),
    "win": dict(tor=0, fu=172, ff=178, bu=-30, bf=40, ft=12, fs=0, bt=-12, bs=0),
    # attacks: (wind-up pose, hitting pose)
    "jab": (dict(tor=10, fu=70, ff=120, bu=30, bf=140, **STANCE),
            dict(tor=16, fu=92, ff=90, bu=28, bf=145, **STANCE)),
    "jab2": (dict(tor=16, fu=50, ff=130, bu=55, bf=120, **STANCE),
             dict(tor=24, fu=50, ff=140, bu=94, bf=91, ft=32, fs=4, bt=-30, bs=-12)),
    "kick": (dict(tor=-4, fu=45, ff=140, bu=25, bf=130, ft=70, fs=-20, bt=-6, bs=-6),
             dict(tor=-14, fu=40, ff=130, bu=20, bf=120, ft=98, fs=92, bt=-6, bs=-6)),
    "sweep": (dict(tor=42, fu=30, ff=20, bu=60, bf=140, ft=70, fs=-5, bt=30, bs=-80, hip=34),
              dict(tor=40, fu=10, ff=5, bu=60, bf=140, ft=80, fs=95, bt=60, bs=-80, hip=30)),
    "upper": (dict(tor=34, fu=60, ff=25, bu=40, bf=140, ft=70, fs=-5, bt=20, bs=-65),
              dict(tor=-8, fu=165, ff=178, bu=30, bf=100, ft=30, fs=10, bt=-15, bs=-25, rise=34)),
    "dive": (dict(tor=-10, fu=60, ff=150, bu=40, bf=150, ft=70, fs=10, bt=70, bs=-40),
             dict(tor=-25, fu=60, ff=120, bu=30, bf=140, ft=45, fs=40, bt=80, bs=-50)),
    "land": (dict(tor=24, ft=62, fs=-10, bt=14, bs=-48, **GUARD_ARMS),) * 2,
    "blast": (dict(tor=-12, fu=-40, ff=-15, bu=-50, bf=-25, ft=38, fs=18, bt=-36, bs=-18),
              dict(tor=16, fu=84, ff=86, bu=78, bf=82, ft=38, fs=18, bt=-36, bs=-18)),
}
KEYS = ("tor", "fu", "ff", "bu", "bf", "ft", "fs", "bt", "bs")


def _mix(a, b, f):
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


def _shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def _hip_height(p):
    if "hip" in p:
        return p["hip"]
    legs = []
    for t, s in (("ft", "fs"), ("bt", "bs")):
        legs.append(math.cos(math.radians(p[t])) * THIGH + math.cos(math.radians(p[s])) * SHIN)
    return max(legs)


def target_pose(f, t):
    """The pose fighter f should be in right now (a dict of angles)."""
    s = f.state
    if s == "attack":
        m = fg.MOVES[f.move]
        wind, hit = POSES[f.move]
        if f.move == "dive":
            return hit if f.st >= m["s"] else wind
        return wind if f.st < m["s"] else hit
    if s == "walk":
        k = f.walk_t
        sw = 24 * math.sin(k)
        pose = dict(POSES["idle"])
        pose.update(ft=10 + sw, fs=10 + sw - 22 * max(0.0, math.cos(k)),
                    bt=-6 - sw, bs=-6 - sw - 22 * max(0.0, -math.cos(k)))
        return pose
    if s in ("guard", "block"):
        return POSES["guard_low" if f.crouch else "guard"]
    if s == "crouch" or s == "getup":
        return POSES["crouch"]
    if s in ("ko",):
        return POSES["lying"] if f.ground and f.st > 0.15 else POSES["down"]
    if s in POSES and not isinstance(POSES[s], tuple):
        pose = POSES[s]
        if s == "idle":                                  # breathing
            pose = dict(pose)
            b = math.sin(t * 3.2 + f.x * 0.01)
            pose["tor"] += 2 * b
            pose["fu"] += 3 * b
            pose["ft"] += 2 * b
        return pose
    return POSES["idle"]


class FighterUI:
    # ------------------------------------------------------------------
    # Single player flow
    # ------------------------------------------------------------------
    def start_fighter(self):
        self.game = fg.Brawl(mode=self.mode_of("fighter"))
        self.__dict__["_fg_view"] = {}
        self.set_state("fg_play")

    def handle_fg_main(self, presses):
        r = self.menus["fg_main"].handle(presses)
        if not r:
            return
        kind, idx = r
        if self.mode_menu_input("fg_main", kind, idx):
            return
        if idx > 1:
            idx -= 1                      # (item 1 is MODE)
        if kind == "back":
            self.set_state("games", reset=False)
        elif kind == "ok":
            if idx == 0:
                self.start_fighter()
            elif idx == 1:
                self.mp_game = "fighter"
                self.set_state("mp")
            elif idx == 2:
                self.set_state("fg_help")
            elif idx == 3:
                self.show_scores("fg_main", game=self.board_key("fighter", self.mode_of("fighter")))
            elif idx == 4:
                self.set_state("games", reset=False)

    def handle_fg_help(self, presses):
        if any(a in ("button1", "button2") for a in presses):
            self.set_state("fg_main", reset=False)

    def handle_fg_play(self, presses):
        if "button1" in presses:                  # BUTTON1 = menu (like the others)
            self.set_state("fg_pause")
            return
        self.__dict__["_fg_presses"] = presses

    def handle_fg_pause(self, presses):
        r = self.menus["fg_pause"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "back" or (kind == "ok" and idx == 0):
            self.set_state("fg_play")
        elif kind == "ok":
            if idx == 1:
                self.start_fighter()
            elif idx == 2:
                self.set_state("fg_help_pause")
            elif idx == 3:
                self.set_state("fg_main")

    def handle_fg_help_pause(self, presses):
        if any(a in ("button1", "button2") for a in presses):
            self.set_state("fg_pause", reset=False)

    def handle_fg_over(self, presses):
        r = self.menus["fg_over"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "ok":
            if idx == 0:
                self.start_fighter()
            elif idx == 1:
                self.show_scores("fg_over", game=self.board_key("fighter", self.game.mode))
            elif idx == 2:
                self.set_state("fg_main")

    def update_fg_play(self, dt):
        g = self.game
        presses = self.__dict__.pop("_fg_presses", [])
        g.update(dt, self.input.held, presses)
        self.fg_animate(dt)
        if g.game_over:
            self.finish_run("fighter", g, g.wins, g.stage, "fg_over")

    # ------------------------------------------------------------------
    # Multiplayer (the host runs the fight, see multiplayer.py)
    # ------------------------------------------------------------------
    def fg_begin_versus(self, msg, seed):
        names = msg.get("names")
        sides = msg.get("sides")
        if not (isinstance(names, list) and len(names) == 2):
            names = ["P1", "P2"]
        me = None
        if isinstance(sides, list) and self.client and self.client.cid in sides:
            me = sides.index(self.client.cid)
        self.__dict__["_fg_view"] = {}
        self.__dict__["_fg_sent"] = (None, 0.0)
        return fg.Versus(seed, [mp_name(n) for n in names], me, mode=str(msg.get("gm", "CLASSIC")))

    def handle_fighter_mp(self, presses):
        if "button1" in presses:
            self.mp_menu_open = True
            self.menus["mp_pause"].sel = 0
            return
        self.__dict__.setdefault("_fg_presses", []).extend(presses)

    def update_fighter_mp(self, dt):
        self.send_mp_buttons()
        self.fg_animate(dt)

    def send_mp_buttons(self):
        """Games the host runs (fighter, glowbug): send our buttons to the
        host whenever they change (and now and then anyway)."""
        c = self.client
        presses = self.__dict__.pop("_fg_presses", [])
        if c is None:
            return
        held = set() if self.mp_menu_open else (self.input.held & set(fg.ACTIONS))
        presses = [] if self.mp_menu_open else [a for a in presses if a in fg.ACTIONS]
        last, when = self.__dict__.get("_fg_sent", (None, 0.0))
        now = time.monotonic()
        if presses or held != last or now - when > 0.25:
            c.send_input(held, presses)
            self.__dict__["_fg_sent"] = (held, now)

    def draw_fg_host_watch(self):
        h = self.host
        if h.fight is None:
            return
        self.draw_fighter_world(h.fight)
        self.text("LIVE VIEW", self.font_small, GOLD, (W // 2, 150), "center")
        if self.host_menu_open:
            self.screen.blit(self.overlay, (0, 0))
            self.draw_menu(self.menus["host_pause"], "HOST MENU", top=330)

    def fg_animate(self, dt, g=None):
        """Ease the drawn poses towards the fighters' real poses (smooth moves)
        and let the health bars' red 'damage' part catch up slowly."""
        g = g or self.game
        view = self.__dict__.setdefault("_fg_view", {})
        t = time.monotonic()
        for key, f in (("p", g.player), ("c", g.cpu)):
            v = view.get(key)
            if v is None or v["f"] is not f:
                v = view[key] = {"f": f, "pose": None, "lag": f.hp}
            target = target_pose(f, t)
            snap = f.state == "attack" and f.move != "land"
            k = 1 - math.exp(-(46.0 if snap else 24.0) * dt / 1000.0)
            pose = v["pose"]
            if pose is None:
                pose = v["pose"] = {kk: float(target[kk]) for kk in KEYS}
                pose["hip"] = _hip_height(target)
                pose["rise"] = 0.0
            for kk in KEYS:
                pose[kk] += (target[kk] - pose[kk]) * k
            pose["hip"] += (_hip_height(target) - pose["hip"]) * k
            pose["rise"] += (target.get("rise", 0) - pose["rise"]) * k
            if v["lag"] > f.hp:
                v["lag"] = max(f.hp, v["lag"] - f.max_hp * 0.5 * dt / 1000.0)
            else:
                v["lag"] = f.hp

    # ------------------------------------------------------------------
    # Drawing: screens
    # ------------------------------------------------------------------
    def draw_fg_main(self):
        self.draw_game_menu("fg_main", self.menus["fg_main"], top=300)

    def draw_fg_play(self):
        self.draw_fighter_world(self.game)

    def draw_fg_pause(self):
        self.draw_fighter_world(self.game)
        self.screen.blit(self.overlay, (0, 0))
        self.draw_menu(self.menus["fg_pause"], "PAUSED", top=290)

    def draw_fg_over(self):
        self.draw_fighter_world(self.game)
        self.screen.blit(self.overlay, (0, 0))
        g = self.game
        self.draw_menu(self.menus["fg_over"], "GAME OVER",
                       lines=["SCORE  %d" % g.score,
                              "OPPONENTS BEATEN  %d" % g.wins], top=360)

    def draw_fg_help(self):
        self.draw_fighter_help("B1 / B2 : BACK")

    def draw_fg_help_pause(self):
        self.draw_fighter_world(self.game)
        self.screen.blit(self.overlay, (0, 0))
        self.draw_fighter_help("B1 / B2 : BACK TO THE MENU")

    def draw_fighter_help(self, footer):
        cx = W // 2
        img = self.neon_title("HOW TO FIGHT", (255, 80, 80), 74)
        self.screen.blit(img, img.get_rect(center=(cx, 80)))
        rows = [
            ("LEFT / RIGHT", "WALK"),
            ("HOLD AWAY", "BLOCK"),
            ("UP", "JUMP"),
            ("DOWN", "CROUCH  (DUCKS BLASTS)"),
            ("DOWN + AWAY", "LOW BLOCK"),
            ("B2", "SABER STRIKE"),
            ("B2  B2  B2", "STRIKE, STRIKE, KICK"),
            ("DOWN + B2", "SWEEP  (BLOCK LOW!)"),
            ("UP + B2", "UPPERCUT  (VS JUMPS)"),
            ("B2 IN THE AIR", "DIVE KICK"),
            ("HOLD B2, LET GO", "NOVA BLAST (ENERGY BALL)"),
            ("POWER BAR FULL", "BLAST = SUPER BLAST"),
            ("B1", "MENU"),
        ]
        box = pygame.Rect(22, 140, W - 44, 46 * len(rows) + 22)
        self.draw_glass(box, 16)
        for i, (keys, what) in enumerate(rows):
            y = box.y + 34 + i * 46
            self.text(keys, self.font_small, GOLD, (box.x + 22, y), "midleft")
            self.text(what, self.font_small, WHITE, (box.x + 218, y), "midleft")
        self.text("BEAT 6 FIGHTERS. BEST OF 3 ROUNDS EACH.", self.font_tiny, (200, 190, 240),
                  (cx, box.bottom + 22), "center")
        self.text(footer, self.font_tiny, (200, 190, 240), (cx, H - 22), "center")

    # ------------------------------------------------------------------
    # Drawing: the fight
    # ------------------------------------------------------------------
    def _fg_stage(self, info):
        """Background for one opponent's stage (cached): sky, sun, city."""
        cache = self.__dict__.setdefault("_fg_stages", {})
        bg = cache.get(info["name"])
        if bg is not None:
            return bg
        top, bottom = info.get("sky", ((5, 3, 22), (40, 8, 62)))
        bg = pygame.Surface((W, H)).convert()
        for y in range(HORIZON_FG):
            pygame.draw.line(bg, _mix(top, bottom, y / float(HORIZON_FG)), (0, y), (W, y))
        rng = random.Random(info["name"])
        for _ in range(70):                                       # stars
            b = rng.randint(90, 230)
            bg.set_at((rng.randrange(W), rng.randrange(0, 420)), (b, b, min(255, b + 30)))
        # a big ringed planet and a small moon in the sky
        light = _mix(info.get("blade", (150, 180, 240)), (255, 255, 255), 0.3)
        _draw_planet(bg, W // 2 + rng.randint(-70, 70), 430, 125, light, _shade(top, 0.8),
                     ring=_mix(light, (255, 255, 255), 0.2))
        _draw_planet(bg, rng.choice((70, W - 70)), 250, 26, (215, 210, 200), (50, 45, 55), bands=False)
        # city: two rows of buildings with windows
        for row, (shade, base, hmin, hmax) in enumerate((((0.45), 742, 120, 260),
                                                         ((0.2), 742, 70, 190))):
            x = -rng.randint(0, 30)
            dark = _shade(top, 0.6 + shade)
            while x < W:
                bw = rng.randint(38, 80)
                bh = rng.randint(hmin, hmax)
                rect = pygame.Rect(x, base - bh, bw, bh)
                pygame.draw.rect(bg, dark, rect)
                pygame.draw.line(bg, _mix(dark, info["band"], 0.35), rect.topleft,
                                 rect.topright, 2)
                for wy in range(rect.y + 10, rect.bottom - 8, 16):
                    for wx in range(rect.x + 6, rect.right - 8, 12):
                        if rng.random() < 0.28:
                            lit = _mix(dark, (255, 220, 140) if rng.random() < 0.6
                                       else info["band"], 0.55 - 0.25 * row)
                            pygame.draw.rect(bg, lit, (wx, wy, 5, 7))
                x += bw + rng.randint(0, 8)
        pygame.draw.rect(bg, (16, 3, 30), (0, HORIZON_FG, W, H - HORIZON_FG))
        cache[info["name"]] = bg
        return bg

    def draw_fighter_world(self, g):
        scr = self.screen
        t = time.monotonic()
        view = self.__dict__.get("_fg_view", {})
        if view.get("p", {}).get("f") is not g.player or view.get("c", {}).get("f") is not g.cpu:
            self.fg_animate(0, g)
        view = self.__dict__["_fg_view"]
        ox = oy = 0
        if g.shake > 0:
            ox = int(random.uniform(-g.shake, g.shake))
            oy = int(random.uniform(-g.shake, g.shake) * 0.6)
        scr.blit(self._fg_stage(g.stage_info), (ox, oy))
        self.draw_neon_grid(t, HORIZON_FG + oy)

        if g.phase == "versus":
            self.draw_fg_versus(g, t)
            return

        # shadows, fighters (the one attacking in front), blasts, sparks
        for f in (g.player, g.cpu):
            w = max(30, 80 - (fg.FLOOR_Y - f.y) * 0.15)
            shadow = pygame.Rect(0, 0, int(w), 12)
            shadow.center = (int(f.x) + ox, fg.FLOOR_Y + 2 + oy)
            pygame.draw.ellipse(scr, (8, 2, 18), shadow)
        order = [("c", g.cpu), ("p", g.player)]
        if g.cpu.state == "attack" and g.player.state != "attack":
            order.reverse()
        for key, f in order:
            self.draw_fighter(f.info, view[key]["pose"], f.x + ox, f.y + oy, f.face,
                              flash=f.flash > 0, glow=f.charge >= fg.CHARGE_TIME,
                              saber=f.state not in ("ko", "lying", "down"))
        for pr in g.projs:
            self.draw_blast(pr, ox, oy, t)
        for x, y, age, max_age, kind in g.effects:
            self.draw_spark(x + ox, y + oy, age / max_age, kind)

        self.draw_fighter_hud(g, t)
        self.draw_fg_banner(g, t)

    def draw_fighter(self, info, pose, x, feet_y, face, scale=1.0, flash=False, glow=False,
                     saber=True):
        scr = self.screen
        s = scale
        hip_h = pose["hip"] * s
        hip = (x, feet_y - hip_h - pose.get("rise", 0) * s)

        def limb(start, ang, length):
            a = math.radians(ang)
            return (start[0] + math.sin(a) * length * s * face, start[1] + math.cos(a) * length * s)

        tor = math.radians(pose["tor"])
        shoulder = (hip[0] + math.sin(tor) * TORSO * s * face, hip[1] - math.cos(tor) * TORSO * s)
        head = (shoulder[0] + math.sin(tor) * (NECK + HEAD_R) * s * face,
                shoulder[1] - math.cos(tor) * (NECK + HEAD_R) * s)
        fk = limb(hip, pose["ft"], THIGH)
        ffoot = limb(fk, pose["fs"], SHIN)
        bk = limb(hip, pose["bt"], THIGH)
        bfoot = limb(bk, pose["bs"], SHIN)
        fe = limb(shoulder, pose["fu"], UPPER)
        fh = limb(fe, pose["ff"], FORE)
        be = limb(shoulder, pose["bu"], UPPER)
        bh = limb(be, pose["bf"], FORE)

        white = (255, 255, 255)
        suit = white if flash else info["suit"]
        top = white if flash else info["top"]
        skin = white if flash else info["skin"]
        glove = white if flash else info["glove"]

        def seg(a, b, col, width):
            wd = max(2, int(width * s))
            pygame.draw.line(scr, OUTLINE, a, b, wd + 4)
            pygame.draw.circle(scr, OUTLINE, (int(b[0]), int(b[1])), (wd + 4) // 2)
            pygame.draw.line(scr, col, a, b, wd)
            pygame.draw.circle(scr, col, (int(a[0]), int(a[1])), wd // 2)
            pygame.draw.circle(scr, col, (int(b[0]), int(b[1])), wd // 2)

        def foot(ankle, knee, col):
            dx = ankle[0] - knee[0]
            toe = (ankle[0] + face * 13 * s + dx * 0.1, ankle[1] + 2 * s)
            seg(ankle, toe, col, 9)

        def arm(sh, el, hand, dark):
            seg(sh, el, _shade(top, dark), 13)
            seg(el, hand, _shade(skin, dark), 11)
            pygame.draw.circle(scr, OUTLINE, (int(hand[0]), int(hand[1])), int(10 * s))
            pygame.draw.circle(scr, _shade(glove, dark), (int(hand[0]), int(hand[1])), int(8 * s))

        if glow:                                     # charging a blast
            r = int(36 * s)
            self.draw_aura(int(x), int(hip[1] - 40 * s), r * 2, (120, 220, 255), 40)
        # back leg and arm (darker), body, front leg, head, front arm
        seg(hip, bk, _shade(suit, 0.7), 18)
        seg(bk, bfoot, _shade(suit, 0.7), 15)
        foot(bfoot, bk, _shade(OUTLINE, 1.0) if not flash else white)
        arm(shoulder, be, bh, 0.72)
        # body: a wedge from hips to shoulders
        perp = (math.cos(tor) * face, math.sin(tor))
        pts = [(hip[0] - perp[0] * 13 * s, hip[1] - perp[1] * 13 * s),
               (hip[0] + perp[0] * 13 * s, hip[1] + perp[1] * 13 * s),
               (shoulder[0] + perp[0] * 17 * s, shoulder[1] + perp[1] * 17 * s),
               (shoulder[0] - perp[0] * 17 * s, shoulder[1] - perp[1] * 17 * s)]
        pygame.draw.polygon(scr, OUTLINE, pts, max(1, int(5 * s)))
        pygame.draw.polygon(scr, top, pts)
        belt_a = (hip[0] - perp[0] * 14 * s + math.sin(tor) * 6 * s * face, hip[1] - perp[1] * 14 * s - math.cos(tor) * 6 * s)
        belt_b = (hip[0] + perp[0] * 14 * s + math.sin(tor) * 6 * s * face, hip[1] + perp[1] * 14 * s - math.cos(tor) * 6 * s)
        pygame.draw.line(scr, white if flash else info["band"], belt_a, belt_b, max(2, int(6 * s)))
        seg(hip, fk, suit, 18)
        seg(fk, ffoot, suit, 15)
        foot(ffoot, fk, OUTLINE if not flash else white)
        # head
        hx, hy = int(head[0]), int(head[1])
        r = int(HEAD_R * s)
        pygame.draw.line(scr, OUTLINE, shoulder, head, max(2, int(10 * s)))
        pygame.draw.circle(scr, OUTLINE, (hx, hy), r + 2)
        pygame.draw.circle(scr, skin, (hx, hy), r)
        self.draw_hair(info, hx, hy, r, face, tor, flash)
        # eye
        ex = hx + face * int(r * 0.45)
        pygame.draw.rect(scr, OUTLINE, (ex - int(3 * s), hy - int(2 * s), int(7 * s), max(2, int(4 * s))))
        pygame.draw.rect(scr, WHITE, (ex - int(2 * s) + (face > 0), hy - int(1 * s), int(4 * s), max(1, int(2 * s))))
        if saber:                                    # the laser sword, along the forearm
            a = math.atan2(fh[1] - fe[1], fh[0] - fe[0])
            dx, dy = math.cos(a), math.sin(a)
            hilt = (fh[0] + dx * 12 * s, fh[1] + dy * 12 * s)
            tip = (fh[0] + dx * (12 + BLADE_LEN) * s, fh[1] + dy * (12 + BLADE_LEN) * s)
            blade = info.get("blade", (80, 160, 255))
            pygame.draw.line(scr, _shade(blade, 0.45), hilt, tip, max(3, int(11 * s)))
            pygame.draw.line(scr, blade, hilt, tip, max(2, int(7 * s)))
            pygame.draw.line(scr, (255, 255, 255), hilt, tip, max(1, int(3 * s)))
            pygame.draw.line(scr, (150, 150, 160), (fh[0] - dx * 4 * s, fh[1] - dy * 4 * s), hilt,
                             max(2, int(6 * s)))
        arm(shoulder, fe, fh, 1.0)

    def draw_hair(self, info, hx, hy, r, face, tor, flash):
        scr = self.screen
        col = (255, 255, 255) if flash else info["hair"]
        style = info.get("style")
        if style == "hood":                          # a deep hood, face in shadow
            hood = (255, 255, 255) if flash else info.get("robe") or col
            pygame.draw.circle(scr, hood, (hx - face * 3, hy - 2), r + 4)
            pygame.draw.circle(scr, (10, 8, 14), (hx + face * 4, hy + 2), r - 5)
            pygame.draw.circle(scr, (255, 60, 60), (hx + face * 7, hy), 2)
            return
        if style == "bald":
            pygame.draw.circle(scr, _mix(info["skin"], (255, 255, 255), 0.4) if not flash else col,
                               (hx - face * r // 3, hy - r // 2), max(2, r // 4))
            return
        # a cap of hair over the top of the head
        pygame.draw.circle(scr, col, (hx - face * 2, hy - r // 3), r - 1,
                           draw_top_right=True, draw_top_left=True)
        if style == "spikes":
            for i in range(4):
                bx = hx - face * (r - 4 - i * 7)
                pygame.draw.polygon(scr, col, [(bx - 5, hy - r // 2), (bx + 5, hy - r // 2),
                                               (bx - face * 10, hy - r - 10 + i * 2)])
        elif style == "mohawk":
            pygame.draw.polygon(scr, col, [(hx - face * (r + 4), hy - r // 2), (hx - face * 2, hy - r - 14),
                                           (hx + face * 8, hy - r + 2)])
        elif style == "bun":
            pygame.draw.circle(scr, OUTLINE, (hx - face * (r - 3), hy - r + 1), r // 2 + 2)
            pygame.draw.circle(scr, col, (hx - face * (r - 3), hy - r + 1), r // 2)
        elif style == "long":
            pts = [(hx - face * 2, hy - r), (hx - face * (r + 4), hy - r // 3),
                   (hx - face * (r + 10), hy + r + 14), (hx - face * (r - 6), hy + r // 2)]
            pygame.draw.polygon(scr, col, pts)

    def draw_blast(self, pr, ox, oy, t):
        x, y = int(pr["x"]) + ox, int(pr["y"]) + oy
        r = pr["r"]
        sup = pr["super"]
        core = (255, 240, 255) if sup else (220, 250, 255)
        glow = (255, 80, 200) if sup else (80, 200, 255)
        d = -1 if pr["vx"] > 0 else 1
        for i in range(5, 0, -1):                             # trail
            self.draw_aura(x + d * i * r * 0.55, y, max(4, int(r * (1 - i * 0.14))), glow, 34)
        wob = 1 + 0.12 * math.sin(t * 30)
        self.draw_aura(x, y, int(r * 1.5 * wob), glow, 70)
        pygame.draw.circle(self.screen, glow, (x, y), int(r * wob))
        pygame.draw.circle(self.screen, core, (x, y), int(r * 0.62))
        for k in range(4 if sup else 3):
            a = t * 9 + k * math.tau / (4 if sup else 3)
            pygame.draw.circle(self.screen, WHITE, (int(x + math.cos(a) * r * 0.9),
                                                    int(y + math.sin(a) * r * 0.9)), 3)

    def draw_spark(self, x, y, f, kind):
        scr = self.screen
        x, y = int(x), int(y)
        if kind == "block":
            r = int(10 + 26 * f)
            pygame.draw.circle(scr, (120, 210, 255), (x, y), r, max(1, int(5 * (1 - f))))
            return
        big = kind == "heavy"
        n = 10 if big else 7
        length = (54 if big else 34) * (0.4 + f)
        col = _mix((255, 255, 220), (255, 120, 60) if big else (255, 220, 80), f)
        for i in range(n):
            a = i * math.tau / n + (0.3 if big else 0)
            r0 = length * 0.35
            pygame.draw.line(scr, col, (x + math.cos(a) * r0, y + math.sin(a) * r0),
                             (x + math.cos(a) * length, y + math.sin(a) * length), 4 if big else 3)
        if f < 0.4:
            pygame.draw.circle(scr, WHITE, (x, y), int((18 if big else 11) * (1 - f)))

    def draw_fighter_hud(self, g, t):
        scr = self.screen
        view = self.__dict__["_fg_view"]
        self.draw_glass(pygame.Rect(8, 6, W - 16, 132), 14)
        bar_w, bar_h, by = 196, 24, 42
        for side, (key, f) in enumerate((("p", g.player), ("c", g.cpu))):
            left = side == 0
            x = 20 if left else W - 20 - bar_w
            self.text(f.name, self.font_small, WHITE, (x if left else x + bar_w, 16),
                      "topleft" if left else "topright")
            frame = pygame.Rect(x, by, bar_w, bar_h)
            pygame.draw.rect(scr, (40, 10, 30), frame, border_radius=6)
            lag = view[key]["lag"] / f.max_hp
            frac = f.hp / f.max_hp
            for amount, col in ((lag, (230, 50, 60)), (frac, None)):
                w = int(bar_w * max(0.0, amount))
                if w <= 0:
                    continue
                if col is None:
                    col = _mix((255, 70, 70), (255, 220, 60), min(1.0, frac * 1.6))
                    if frac > 0.5:
                        col = _mix((255, 220, 60), (90, 240, 120), (frac - 0.5) * 2)
                r = pygame.Rect(x if left else x + bar_w - w, by, w, bar_h)
                pygame.draw.rect(scr, col, r, border_radius=6)
            pygame.draw.rect(scr, (230, 230, 255), frame, 2, border_radius=6)
            # round wins
            won = g.p_rounds if left else g.c_rounds
            for i in range(g.rounds_to_win):
                px = (x + 12 + i * 26) if left else (x + bar_w - 12 - i * 26)
                pygame.draw.circle(scr, GOLD if i < won else (60, 50, 90), (px, by + bar_h + 16), 8)
                pygame.draw.circle(scr, WHITE, (px, by + bar_h + 16), 8, 2)
            # power bar
            mf = f.meter / fg.METER_MAX
            pw = 120
            mx = x + bar_w - pw if left else x
            mrect = pygame.Rect(mx, by + bar_h + 10, pw, 12)
            pygame.draw.rect(scr, (20, 20, 50), mrect, border_radius=4)
            full = mf >= 1.0
            mcol = _mix((80, 200, 255), (255, 80, 200), 0.5 + 0.5 * math.sin(t * 10)) if full \
                else (80, 200, 255)
            fill = pygame.Rect(mx if left else mx + pw - int(pw * mf), mrect.y, int(pw * mf), 12)
            if fill.w > 0:
                pygame.draw.rect(scr, mcol, fill, border_radius=4)
            pygame.draw.rect(scr, (150, 150, 210), mrect, 1, border_radius=4)
            if full:
                self.text("SUPER!", self.font_tiny, (30, 10, 40), mrect.center, "center")
        # timer
        cx = W // 2
        sec = int(math.ceil(g.timer))
        pygame.draw.circle(scr, (14, 10, 40), (cx, 56), 32)
        pygame.draw.circle(scr, RED if sec <= 10 and g.phase == "fight" else (120, 100, 200),
                           (cx, 56), 32, 3)
        self.text(str(sec), self.font_big, WHITE if sec > 10 else (255, 120, 120), (cx, 58), "center")
        if g.versus:
            if g.me == 0:
                self.text("YOU", self.font_small, GOLD, (20, 112), "midleft")
            elif g.me == 1:
                self.text("YOU", self.font_small, GOLD, (W - 20, 112), "midright")
        else:
            self.text("SCORE  %d" % g.score, self.font_small, GOLD, (20, 112), "midleft")
            self.text("STAGE %d" % g.stage, self.font_small, (190, 180, 230), (W - 20, 112),
                      "midright")
        # combo text
        for text, age in g.popups:
            a = min(1.0, (1.2 - age) * 3)
            img = self.font_med.render(text, True, _mix((60, 20, 60), GOLD, a))
            scr.blit(img, img.get_rect(center=(cx, 180 - int(age * 10))))
        # first round of a run: show the most important buttons
        if g.stage == 1 and g.round_no == 1 and g.phase in ("intro", "fight") and \
                (g.phase == "intro" or g.phase_t < 12):
            self.draw_glass(pygame.Rect(20, 842, W - 40, 72), 12)
            self.text("B2 : STRIKE      HOLD AWAY : BLOCK", self.font_small, WHITE, (cx, 864), "center")
            self.text("HOLD B2 + LET GO : BLAST     UP+B2 : UPPERCUT", self.font_tiny,
                      (200, 190, 240), (cx, 892), "center")

    def draw_fg_banner(self, g, t):
        b = g.banner()
        if not b:
            return
        big, small = b
        cache = self.__dict__.setdefault("_fg_banners", {})
        img = cache.get(big)
        if img is None:
            glow = (255, 70, 70) if big in ("K.O.!", "DEFEATED", "YOU LOSE") else (
                (255, 170, 40) if big in ("VICTORY!", "CHAMPION!", "PERFECT!", "YOU WIN") else (255, 70, 190))
            img = cache[big] = self.neon_title(big, glow, 104 if len(big) <= 8 else 80)
        pop = 1.0
        if g.phase in ("intro", "ko", "fight"):
            pop = min(1.0, 0.6 + (g.phase_t % 1.05) * 4) if g.phase == "intro" else 1.0
        if pop < 1.0:
            sized = pygame.transform.smoothscale(img, (int(img.get_width() * pop), int(img.get_height() * pop)))
        else:
            sized = img
        self.screen.blit(sized, sized.get_rect(center=(W // 2, 330)))
        y = 400
        if small:
            self.text(small, self.font_small, WHITE, (W // 2, y), "center")
            y += 40
        if g.bonus and (g.phase == "matchwin" or (g.phase == "ko" and g.phase_t >= 1.1)):
            box = pygame.Rect(70, y, W - 140, 20 + 34 * len(g.bonus))
            self.draw_glass(box, 12)
            for i, (label, pts) in enumerate(g.bonus):
                ry = box.y + 27 + i * 34
                self.text(label, self.font_small, WHITE, (box.x + 18, ry), "midleft")
                self.text("+%d" % pts, self.font_small, GOLD, (box.right - 18, ry), "midright")

    def draw_fg_versus(self, g, t):
        """Before every match: you vs the next opponent."""
        self.screen.blit(self.overlay, (0, 0))
        cx = W // 2
        img = self.neon_title("BEST OF 3" if g.versus else "STAGE %d" % g.stage,
                              (255, 170, 40), 70, (255, 240, 200))
        self.screen.blit(img, img.get_rect(center=(cx, 110)))
        slide = min(1.0, g.phase_t * 3.0)
        for f, x, face in ((g.player, 140 - (1 - slide) * 200, 1), (g.cpu, W - 140 + (1 - slide) * 200, -1)):
            pose = POSES["win"] if f is g.player and g.stage > 1 else POSES["idle"]
            full = {k: float(pose[k]) for k in KEYS}
            full["hip"] = _hip_height(pose)
            full["rise"] = 0.0
            self.draw_fighter(f.info, full, x, 640, face, scale=1.45)
            self.text(f.name, self.font_big if len(f.name) <= 7 else self.font_med, WHITE,
                      (int(x), 700), "center")
            if g.versus and g.me is not None and (f is g.player) == (g.me == 0):
                self.text("YOU", self.font_small, GOLD, (int(x), 740), "center")
        vs = self.__dict__.get("_fg_vs")
        if vs is None:
            vs = self.__dict__["_fg_vs"] = self.neon_title("VS", (255, 70, 70), 120, GOLD)
        bob = 1 + 0.06 * math.sin(t * 6)
        img = pygame.transform.smoothscale(vs, (int(vs.get_width() * bob), int(vs.get_height() * bob)))
        self.screen.blit(img, img.get_rect(center=(cx, 470)))
        if g.loop:
            self.text("ROUND TRIP %d - THEY HIT HARDER!" % (g.loop + 1), self.font_small, RED,
                      (cx, 780), "center")

    # ------------------------------------------------------------------
    # The start screen card icon and the menu background
    # ------------------------------------------------------------------
    def _demo_pose(self, name, phase=1):
        p = POSES[name]
        if isinstance(p, tuple):
            p = p[phase]
        full = {k: float(p[k]) for k in KEYS}
        full["hip"] = _hip_height(p)
        full["rise"] = float(p.get("rise", 0))
        return full

    def draw_fighter_icon(self, box, t):
        punch = t and (t * 1.6) % 1.0 < 0.35
        floor = box.bottom - 10
        pygame.draw.line(self.screen, (255, 70, 190), (box.x, floor + 2), (box.right, floor + 2), 2)
        self.draw_fighter(fg.LADDER[0], self._demo_pose("guard" if punch else "idle"),
                          box.x + 70, floor, -1, scale=0.4)
        self.draw_fighter(fg.PLAYER, self._demo_pose("jab" if punch else "idle"),
                          box.x + 32, floor, 1, scale=0.4)

    def draw_brawl_scene(self, t):
        """Fighter menu: two fighters sparring on a neon floor near the bottom."""
        cycle = (t * 0.7) % 4.0
        seg = int(cycle)
        ph = cycle - seg
        moves = [("jab", "guard"), ("kick", "guard"), ("guard", "jab2"), ("idle", "idle")]
        a, b = moves[seg]
        pa = self._demo_pose(a, 1 if 0.2 < ph < 0.55 else 0) if a not in ("guard", "idle") \
            else self._demo_pose(a)
        pb = self._demo_pose(b, 1 if 0.2 < ph < 0.55 else 0) if b not in ("guard", "idle") \
            else self._demo_pose(b)
        self.draw_fighter(fg.LADDER[5], pb, W // 2 + 58, 832, -1, scale=0.72)
        self.draw_fighter(fg.PLAYER, pa, W // 2 - 58, 832, 1, scale=0.72)
