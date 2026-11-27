#!/usr/bin/env python3
"""
Checks the games in more_games/: do they follow the rules (game_rules.py),
do they load, and do they run for a few seconds without crashing?
GitHub runs this on every pull request. Run it yourself before you send yours in:

    python more_games/check_games.py            check all games
    python more_games/check_games.py space_cat  check just that one
"""
import os
import random
import sys
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")      # no window needed
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "main"))

import pygame                                           # noqa: E402

import more_games_ui                                    # noqa: E402

sys.path.insert(0, HERE)
import game_rules                                       # noqa: E402

BUTTONS = ("up", "down", "left", "right", "button2")


def check(entry, screen):
    folder = os.path.dirname(entry["path"])
    problems = game_rules.check_folder(folder)
    src = open(entry["path"], encoding="utf-8").read()
    for name in ("TITLE", "AUTHOR"):
        if name + " =" not in src and name + "=" not in src:
            problems.append("no %s = \"...\" line at the top" % name)
    if problems:                                    # never run code that breaks the rules
        return problems
    try:
        game = more_games_ui.MoreGamesUI.sg_load(None, entry)
    except Exception:
        return problems + ["does not load:\n" + traceback.format_exc()]
    for need in ("update", "draw"):
        if not callable(getattr(game, need, None)):
            problems.append("Game has no %s() method" % need)
    if problems:
        return problems
    rnd = random.Random(1)
    held = set()
    try:
        for frame in range(600):                        # 10 seconds of random buttons
            pressed = set()
            if frame % 10 == 0:
                b = rnd.choice(BUTTONS)
                pressed.add(b)
                held = {b}
            game.update(1 / 60.0, pressed, held)
            game.draw(screen)
            int(getattr(game, "score", 0))
            if getattr(game, "game_over", False):
                break
    except Exception:
        problems.append("crashed while playing:\n" + traceback.format_exc())
    return problems


def main():
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_mode((1, 1))
    screen = pygame.Surface((540, 960)).convert()
    games = more_games_ui.find_more_games()
    only = sys.argv[1:]
    if only:
        games = [g for g in games if g["folder"] in only]
        if not games:
            sys.exit("No game folder called %s (with a game.py in it)" % ", ".join(only))
    failed = 0
    for g in games:
        problems = check(g, screen)
        if problems:
            failed += 1
            print("FAIL  %s (%s)" % (g["folder"], g["title"]))
            for p in problems:
                print("      - " + p.replace("\n", "\n        "))
        else:
            print("OK    %s (%s)" % (g["folder"], g["title"]))
    print("\n%d game(s) checked, %d problem(s)" % (len(games), failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
