"""
STUDENT GAMES: games made by other students, found automatically.

Every folder in picade/student_games/ that has a game.py in it shows up in the
STUDENT GAMES list on the start screen (see student_games/README.md for how to
make one). Nothing has to be changed in the arcade itself: push the folder to
GitHub, and the Pis pick it up the next time they start.

A student game can never crash the whole arcade: if it breaks (while loading,
playing or drawing) the arcade shows what went wrong and goes back to the list.

This is a mixin like the other *_ui files: main.py's App inherits from it.
"""
import importlib.util
import os
import random
import re
import sys
import time
import traceback

import pygame

from common import W, H, WHITE, GOLD, RED

STUDENT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "student_games")
LIST_ROWS = 7                       # how many games the list shows at once
BUTTONS = ("up", "down", "left", "right", "button1", "button2")


def _clean(text, n):
    """Upper case, printable, at most n characters (for titles and names)."""
    text = " ".join(str(text).split()).upper()
    return text[:n]


def find_student_games():
    """[{folder, key, title, author, about, path}] of every student_games/*/game.py.
    Only reads the files - nothing is run yet (that happens when it's picked)."""
    found = []
    if not os.path.isdir(STUDENT_DIR):
        return found
    for folder in sorted(os.listdir(STUDENT_DIR), key=str.lower):
        path = os.path.join(STUDENT_DIR, folder, "game.py")
        if folder.startswith((".", "_")) or not os.path.isfile(path):
            continue
        info = {"TITLE": folder.replace("_", " "), "AUTHOR": "", "DESCRIPTION": "",
                "SCORE_NAME": "POINTS"}
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    # TITLE = "..." lines at the top of game.py
                    m = re.match(r'\s*(TITLE|AUTHOR|DESCRIPTION|SCORE_NAME)\s*=\s*["\'](.*)["\']\s*$',
                                 line)
                    if m:
                        info[m.group(1)] = m.group(2)
        except (OSError, UnicodeDecodeError):
            continue
        slug = re.sub(r"[^a-z0-9]", "", folder.lower()) or "game"
        while "sg-" + slug in [g["key"] for g in found]:      # two folders, same name
            slug += "x"
        found.append({"folder": folder, "key": "sg-" + slug, "path": path,
                      "title": _clean(info["TITLE"], 18) or "NO NAME",
                      "author": _clean(info["AUTHOR"], 24),
                      "about": _clean(info["DESCRIPTION"], 44),
                      "score_name": _clean(info["SCORE_NAME"], 8) or "POINTS"})
    return found


class StudentUI:
    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def init_students(self, scores_cls, base_dir):
        """Called once by App.__init__: find the games, give each a scoreboard."""
        self.sg_games = find_student_games()
        self.sg_sel = 0
        self.sg_top = 0
        self.sg_cur = None              # the entry of the game being played
        self.sg_obj = None              # the student's Game object
        self.sg_error = None            # (title, last lines of the error)
        for g in self.sg_games:
            self.mode_boards[g["key"]] = scores_cls(
                os.path.join(base_dir, "highscores_%s.json" % g["key"]))
        print("Student games found:", len(self.sg_games))

    def sg_fail(self, where):
        """Something in a student game broke: show it, never crash."""
        tb = traceback.format_exc()
        print("Student game '%s' broke while %s:\n%s" % (
            self.sg_cur["folder"] if self.sg_cur else "?", where, tb))
        lines = [ln for ln in tb.strip().splitlines() if ln.strip(" ~^")][-4:]
        self.sg_error = ("BROKE WHILE " + where.upper(), lines)
        self.sg_obj = None
        self.set_state("sg_error")

    def sg_load(self, entry):
        """Run the student's game.py (fresh every time) and make its Game."""
        folder = os.path.dirname(entry["path"])
        name = "student_game_" + re.sub(r"\W", "_", entry["folder"])
        sys.path.insert(0, folder)              # so it can import its own helper files
        try:
            spec = importlib.util.spec_from_file_location(name, entry["path"])
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.Game()
        finally:
            if folder in sys.path:
                sys.path.remove(folder)

    def start_student(self, entry=None):
        if entry is None:
            entry = self.sg_games[self.sg_sel]
        self.sg_cur = entry
        try:
            self.sg_obj = self.sg_load(entry)
        except Exception:
            self.sg_fail("loading")
            return
        self.set_state("sg_play")

    def start_random_student(self):
        """RANDOM on the start screen landed on STUDENT GAMES."""
        if not self.sg_games:
            return
        self.sg_sel = random.randrange(len(self.sg_games))
        self.start_student()

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def handle_sg_list(self, presses):
        n = len(self.sg_games) + 1              # + BACK
        for a in presses:
            if a == "up":
                self.sg_sel = (self.sg_sel - 1) % n
            elif a == "down":
                self.sg_sel = (self.sg_sel + 1) % n
            elif a == "button1":
                self.set_state("games", reset=False)
                return
            elif a == "button2":
                if self.sg_sel == len(self.sg_games):
                    self.set_state("games", reset=False)
                else:
                    self.start_student()
                return
            elif a in ("left", "right") and self.sg_sel < len(self.sg_games):
                self.show_scores("sg_list", game=self.sg_games[self.sg_sel]["key"])
                return
        # keep the selected game in view
        if self.sg_sel < self.sg_top:
            self.sg_top = self.sg_sel
        elif self.sg_sel >= self.sg_top + LIST_ROWS:
            self.sg_top = self.sg_sel - LIST_ROWS + 1

    def handle_sg_play(self, presses):
        if "button1" in presses:                # BUTTON1 = menu (like the other games)
            self.set_state("sg_pause")
            return
        self.sg_presses = presses

    def handle_sg_pause(self, presses):
        r = self.menus["sg_pause"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "back" or (kind == "ok" and idx == 0):
            self.set_state("sg_play")
        elif kind == "ok" and idx == 1:
            self.start_student(self.sg_cur)
        elif kind == "ok" and idx == 2:
            self.show_scores("sg_pause", game=self.sg_cur["key"])
        elif kind == "ok" and idx == 3:
            self.set_state("sg_list")

    def handle_sg_over(self, presses):
        r = self.menus["sg_over"].handle(presses)
        if not r:
            return
        kind, idx = r
        if kind == "ok" and idx == 0:
            self.start_student(self.sg_cur)
        elif kind == "ok" and idx == 1:
            self.show_scores("sg_over", game=self.sg_cur["key"])
        elif kind == "back" or (kind == "ok" and idx == 2):
            self.set_state("sg_list")

    def handle_sg_error(self, presses):
        if "button1" in presses or "button2" in presses:
            self.set_state("sg_list")

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update_sg_play(self, dt):
        g = self.sg_obj
        pressed = set(a for a in getattr(self, "sg_presses", ()) if a != "button1")
        self.sg_presses = []
        held = set(self.input.held) - {"button1"}
        try:
            g.update(dt / 1000.0, pressed, held)
            over = bool(getattr(g, "game_over", False))
            score = int(getattr(g, "score", 0))
        except Exception:
            self.sg_fail("playing")
            return
        if over:
            scores = self.board(self.sg_cur["key"])
            if score > 0 and scores.qualifies(score):
                self.entry_ctx = {"scores": scores, "score": score, "lines": score,
                                  "level": 1, "ret": "sg_over", "game": self.sg_cur["key"]}
                self.cursor = 0
                self.set_state("entry")
            else:
                self.set_state("sg_over")

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def sg_draw_game(self):
        """Let the student's game draw itself (black screen if that breaks)."""
        self.screen.fill((0, 0, 0))
        if self.sg_obj is None:
            return
        try:
            self.sg_obj.draw(self.screen)
        except Exception:
            self.sg_fail("drawing")
            self.screen.fill((0, 0, 0))

    def draw_sg_play(self):
        self.sg_draw_game()
        self.text("B1: MENU", self.font_tiny, (150, 150, 180), (W - 8, H - 8), "bottomright")

    def draw_sg_pause(self):
        self.sg_draw_game()
        self.screen.blit(self.overlay, (0, 0))
        self.draw_menu(self.menus["sg_pause"], "PAUSED",
                       lines=[self.sg_cur["title"]], top=300)

    def draw_sg_over(self):
        self.sg_draw_game()
        self.screen.blit(self.overlay, (0, 0))
        try:
            score = int(getattr(self.sg_obj, "score", 0))
        except Exception:
            score = 0
        self.draw_menu(self.menus["sg_over"], "GAME OVER",
                       lines=["%s  %d" % (self.sg_cur["score_name"], score),
                              self.sg_cur["title"]], top=340)

    def draw_sg_error(self):
        cx = W // 2
        img = self.neon_title("OOPS!", (255, 60, 90))
        self.screen.blit(img, img.get_rect(center=(cx, 105)))
        title = self.sg_cur["title"] if self.sg_cur else "THIS GAME"
        what, lines = self.sg_error or ("", [])
        self.text(title, self.font_med, GOLD, (cx, 190), "center")
        self.text(what, self.font_small, RED, (cx, 230), "center")
        self.draw_glass(pygame.Rect(20, 270, W - 40, 330))
        y = 285
        for line in lines:
            line = line.strip()
            while line and y < 580:             # wrap long lines
                part, line = line[:52], line[52:]
                self.text(part, self.font_tiny, WHITE, (34, y))
                y += 22
            y += 8
        self.text("THE MAKER CAN SEE THE FULL ERROR", self.font_small, (190, 180, 230),
                  (cx, 640), "center")
        self.text("IN main/game.log", self.font_small, (190, 180, 230), (cx, 670), "center")
        self.text("B1 / B2 : BACK", self.font_tiny, (200, 190, 240), (cx, H - 22), "center")

    def draw_sg_list(self):
        cx = W // 2
        t = time.monotonic()
        img = self.neon_title("STUDENT GAMES", size=64)
        self.screen.blit(img, img.get_rect(center=(cx, 80)))
        self.text("MADE BY OTHER STUDENTS", self.font_small, (190, 180, 230),
                  (cx, 135), "center")
        if not self.sg_games:
            self.draw_glass(pygame.Rect(40, 300, W - 80, 120))
            self.text("NO GAMES YET!", self.font_med, WHITE, (cx, 335), "center")
            self.text("ADD ONE IN student_games/", self.font_small, GOLD, (cx, 380), "center")
        rows = self.sg_games[self.sg_top:self.sg_top + LIST_ROWS]
        for i, g in enumerate(rows):
            idx = self.sg_top + i
            sel = idx == self.sg_sel
            rect = pygame.Rect(30, 170 + i * 88, W - 60, 78)
            self.draw_glass(rect, 14, None if sel else (55, 45, 100))
            if sel:
                self.draw_neon_frame(rect, 3, 14)
            self.text(g["title"], self.font_med, WHITE if sel else (195, 190, 225),
                      (rect.x + 18, rect.y + 10))
            sub = ("BY " + g["author"]) if g["author"] else ""
            self.text(sub, self.font_tiny, (150, 140, 200), (rect.right - 16, rect.y + 16),
                      "topright")
            best = self.board(g["key"]).best()
            line = g["about"] or ("TOP %d" % best if best else "")
            self.text(line, self.font_tiny, GOLD if sel else (150, 130, 80),
                      (rect.x + 18, rect.y + 48))
        if self.sg_top > 0:
            self.text("^  MORE  ^", self.font_tiny, GOLD, (cx, 158), "center")
        if self.sg_top + LIST_ROWS < len(self.sg_games):
            self.text("v  MORE  v", self.font_tiny, GOLD, (cx, 170 + LIST_ROWS * 88), "center")
        # BACK button
        m = self._menu_assets()
        self.draw_menu_button("BACK", self.sg_sel == len(self.sg_games), 830, t, m)
        self.text("B2 : PLAY    LEFT/RIGHT : SCORES    B1 : BACK", self.font_tiny,
                  (200, 190, 240), (cx, H - 22), "center")

    def draw_student_icon(self, box, t):
        """Card icon on the start screen: a little joystick with sparkles."""
        scr = self.screen
        cx, cy = box.centerx, box.centery
        pygame.draw.rect(scr, (60, 70, 140), (cx - 34, cy + 10, 68, 26), border_radius=8)
        lean = int(6 * (1 if int(t * 2) % 2 else -1)) if t else 0
        pygame.draw.line(scr, (200, 200, 220), (cx, cy + 14), (cx + lean, cy - 18), 6)
        pygame.draw.circle(scr, (255, 70, 120), (cx + lean, cy - 22), 12)
        pygame.draw.circle(scr, GOLD, (cx + 20, cy + 22), 6)
        for i, (sx, sy) in enumerate(((cx - 32, cy - 30), (cx + 30, cy - 34), (cx - 20, cy - 6))):
            if not t or int(t * 3 + i) % 2:
                pygame.draw.line(scr, GOLD, (sx - 5, sy), (sx + 5, sy), 2)
                pygame.draw.line(scr, GOLD, (sx, sy - 5), (sx, sy + 5), 2)
