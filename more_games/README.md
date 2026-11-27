# More Games 🎮

Made a game? Put it here and it shows up on every arcade automatically, under
**MORE GAMES** on the start screen. You don't need to change anything in the arcade itself.

## How to add your game

1. **Copy** the `example_dodge` folder and give it your own name, e.g. `more_games/space_cat/`.
   Use letters, numbers and `_` only.
2. **Edit `game.py`** in your folder and make your game (see the rules below).
3. **Test it** on your own PC (you need Python and pygame):
   ```
   python more_games/check_games.py space_cat
   python main/main.py
   ```
   The first command checks that your game loads and runs. The second starts the
   arcade so you can play it (keyboard: arrows, Space = B2, Esc = B1).
4. **Send it in** with a pull request. You don't need to be added to the project:
   1. On the arcade's GitHub page, click **Fork** (top right). You now have your own copy.
   2. Put your game folder in `more_games/` in **your** copy (upload it on the GitHub
      website with **Add file → Upload files**, or push it with git).
   3. Click **Contribute → Open pull request**.

   GitHub then tests your game by itself. **If it follows the rules below, it is merged
   automatically** and every arcade gets your game the next time it starts. If something
   is wrong, a comment on your pull request says what to fix. Fix it in your copy and the
   test runs again.

   One game per pull request, and you can only change your own game folder. To update
   your game later, send a new pull request that only changes your own folder.

## The rules for `game.py`

Your `game.py` needs these 4 lines at the top. The arcade shows them in its list:

```python
TITLE = "SPACE CAT"
AUTHOR = "YOUR NAME"
DESCRIPTION = "ONE SHORT LINE ABOUT YOUR GAME"
SCORE_NAME = "POINTS"
```

It also needs a class called `Game` with three parts:

```python
class Game:
    def __init__(self):
        self.score = 0           # your score: the arcade saves the top 10
        self.game_over = False   # set it to True when the round ends

    def update(self, dt, pressed, held):
        # runs 60 times a second. dt = seconds since the last time
        # pressed = buttons pressed just now, held = buttons held down
        ...

    def draw(self, screen):
        # draw your game on screen (540 wide, 960 high)
        ...
```

**Buttons:** `"up"`, `"down"`, `"left"`, `"right"`, `"button2"`.
The arcade keeps `button1` for itself: it opens the pause menu.

**The screen** is tall: **540 × 960** pixels.

**Do:**
- Keep everything in your own folder. Load pictures and sounds like this:
  ```python
  import os
  HERE = os.path.dirname(os.path.abspath(__file__))
  img = pygame.image.load(os.path.join(HERE, "cat.png"))
  ```
- Keep files small (pictures under 1 MB).
- Split your code over more `.py` files in your folder if you like (`import helpers`).

**Don't:**
- Call `pygame.init()`, `pygame.display.set_mode()`, `pygame.display.flip()` or
  `pygame.event.get()`. The arcade does all of that for you.
- Write your own `while True:` game loop. The arcade calls `update` and `draw` for you.
- Touch files outside your folder.

## The safety rules (checked automatically)

Games are added without anyone reading the code first, so they have to stay inside their
own folder. The test refuses a game that breaks one of these rules:

- **Imports:** only `pygame`, `math`, `random`, `time`, `os.path`, `json`, `collections`,
  `dataclasses`, `itertools`, `functools`, `enum`, `typing`, `copy`, `colorsys`, `string`,
  `re`, `statistics`, `fractions`, `decimal`, `heapq`, `bisect`, `array`, and your own
  `.py` files.
- **`os`** only as `os.path` (to find your own files).
- **Files:** `open()` may only read, not write.
- **Not allowed:** `eval`, `exec`, `getattr`, `setattr`, `globals`, `input`, `__import__`,
  and names with double underscores (`__init__`, `__name__` and `__file__` are fine).
- **File types:** `.py`, `.png`, `.jpg`, `.gif`, `.bmp`, `.wav`, `.ogg`, `.mp3`, `.ttf`,
  `.otf`, `.txt`, `.md`, `.json`. Max **5 MB** per file, **20 MB** per game.
- **Folder name:** letters, numbers and `_`, not starting with `_`.

`check_games.py` checks all of this on your own PC too, so run it before you send your
game in. The full list is in [game_rules.py](game_rules.py).

If your game crashes, the arcade doesn't stop. It shows an **OOPS!** screen with the
error and goes back to the list. The full error is in `main/game.log`.
