# Student Games 🎮

Made a game? Put it here and it shows up on every arcade automatically, under
**STUDENT GAMES** on the start screen. You don't need to change anything in the arcade itself.

## How to add your game

1. **Copy** the `example_dodge` folder and give it your own name, e.g. `student_games/space_cat/`.
   Use letters, numbers and `_` only.
2. **Edit `game.py`** in your folder and make your game (see the rules below).
3. **Test it** on your own PC (you need Python and pygame):
   ```
   python student_games/check_games.py space_cat
   python main/main.py
   ```
   The first command checks that your game loads and runs. The second starts the
   arcade so you can play it (keyboard: arrows, Space = B2, Esc = B1).
4. **Push it to GitHub.** Make a branch, commit your folder, and open a pull request.
   GitHub checks your game automatically. Once the pull request is merged, every arcade
   gets your game the next time it starts.

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

**Don't:**
- Call `pygame.init()`, `pygame.display.set_mode()`, `pygame.display.flip()` or
  `pygame.event.get()`. The arcade does all of that for you.
- Write your own `while True:` game loop. The arcade calls `update` and `draw` for you.
- Touch files outside your folder.

If your game crashes, the arcade doesn't stop. It shows an **OOPS!** screen with the
error and goes back to the list. The full error is in `main/game.log`.
