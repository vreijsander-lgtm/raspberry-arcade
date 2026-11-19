# Pi Tetris - Setup Tutorial (Raspberry Pi 4, 64-bit Raspberry Pi OS)

A vertical (portrait) fullscreen Tetris with a top-10 scoreboard and a LAN
multiplayer mode, made for a 6-button controller.

---

## 1. Get the zip onto your Raspberry Pi

Pick ONE of these:

**A. Download straight on the Pi** - open the browser on the Pi, go to the chat
where you got `pi-tetris.zip`, and download it. It lands in `~/Downloads`.

**B. USB stick** - download the zip on your PC, copy it to a USB stick, plug it
into the Pi and copy it to the Downloads folder (use the file manager).

**C. Over the network (from your PC)** - in a terminal / PowerShell in the folder
with the zip:

    scp pi-tetris.zip YOURUSER@raspberrypi.local:~/

(SSH must be enabled on the Pi: `sudo raspi-config` > Interface Options > SSH.
With this option the zip ends up in the Pi's home folder.)

---

## 2. Unzip it

Open the **Terminal** on the Pi (black icon in the top bar, or Ctrl+Alt+T):

    cd ~/Downloads
    unzip pi-tetris.zip -d ~
    cd ~/pi-tetris

(If `unzip` is missing: `sudo apt install unzip`. For option C use `cd ~`.)

---

## 3. Install the requirements (once, needs internet)

    bash install.sh

This runs `sudo apt install python3-pygame python3-gpiozero python3-lgpio`.
It may ask for your password (typing shows nothing - that is normal).

---

## 4. Play

Run from the Pi's desktop (not plain SSH, the game needs a screen):

    bash run.sh

The game starts **fullscreen and vertical (portrait)**.

| Action            | Keyboard                         | GPIO name |
|-------------------|----------------------------------|-----------|
| Menu up           | Up arrow                         | up        |
| Menu down / speed up falling | Down arrow            | down      |
| Move left / menu value - | Left arrow                | left      |
| Move right / menu value + | Right arrow              | right     |
| Open menu / go back  | Esc or Tab                    | button1   |
| Rotate / OK (Space Shooter: **shoot**) | Space, Enter, Z or X | button2   |
| (keyboard only) toggle fullscreen | F11              |           |

**Games menu:** the Pi starts on a list of games (TETRIS, SPACE SHOOTER) and EXIT TO DESKTOP.
Pick a game with Up/Down + B2. B1 inside a game's main menu brings you back to this list.

**Tetris main menu:** SINGLE PLAYER, LEVEL (Left/Right), MULTIPLAYER, SCOREBOARD,
FULLSCREEN (Left/Right or B2 toggles it, and remembers it), BACK (to the games list).

**Scoreboard:** when you game over with a top-10 score you can enter a 3-letter
name: Up/Down changes the letter, Left/Right moves the cursor, B2 saves.
Scores are stored in `highscores.json`.

**Scoring:** 1 / 2 / 3 / 4 lines = 100 / 300 / 500 / 800 x level. Soft drop = 1 point
per row. A new level every 10 lines.

---

## 5. Space Shooter

Pick **SPACE SHOOTER** in the games menu. Its menu works like Tetris:
SINGLE PLAYER, MULTIPLAYER, SCOREBOARD, FULLSCREEN, BACK.

| Button | In the game |
|--------|-------------|
| Left / Right | fly left / right |
| **Button 2** | **shoot** (hold it to keep firing) |
| **Button 1** | **menu** (pause, restart, scoreboard, main menu) |

* You have 3 lives. Enemies that touch you or their bullets take a life
  (you blink and can't be hit for 2 seconds). Waves get harder the longer you survive.
* Enemies: **drone** (zig-zags, 10 pts), **fighter** (aims at you, 25 pts, 2 hits),
  **tank** (slow, 3-way shots, 60 pts, 7 hits).
* **Upgrades**: every few kills (the green bar under your score) enemies stop coming and
  **three big boxes** fly in. **Shoot one** to pick it - the other two disappear. Upgrades last
  for the whole run and stack (losing a life does not take them away). The first choice comes
  after 8 kills, each next one needs 3 more kills than the last. Enemies slowly get tougher.

| Box | What it does (per level) |
|-----|--------------------------|
| **More bullets** | +1 bullet per shot (side by side, then a wider fan) |
| **More damage** | +1 damage per bullet |
| **Fire rate** | shoot about 18% faster |
| **Pierce** | bullets go through 1 more enemy |
| **Homing** | bullets steer towards enemies (stronger each level) |
| **Big bullets** | bigger shots, easier to hit with |
| **Ship speed** | fly 15% faster |
| **Shield** | blocks one hit; recharges after 15 s (more levels = more charges) |
| **Extra life** | +1 life right away |

* The top 10 is kept in `highscores_shooter.json` (kills are shown next to the score).

### Space Shooter multiplayer
Same as Tetris multiplayer (section 6): the host Pi spectates and shows every player's screen,
the others play. **Every enemy you kill is sent to another random player**: the same type of
enemy appears at the top of their screen (at the same spot where you shot it, with a pink outline
so you can see it came from a rival). Enemies that were sent to you are not passed on again.
The last player alive wins. In the round, Button 1 opens a small menu; the game keeps running.

---

## 6. Multiplayer

You need **2 or more Raspberry Pis** with the game installed, all on the **same
network** (same router / same Wi-Fi). One Pi is the **host**, the others **play**. It works for **both games**: choose
MULTIPLAYER inside Tetris or inside Space Shooter. A Pi only sees hosts of the game it picked.

### The rules
* The **host does not play**. Its screen shows **everybody's board live** so people can watch.
* **Tetris:** whenever a player clears a line, **one new line is added at the bottom of the board of
  one random other player**. It is never the person who cleared the line and never the host.
  (Clear 3 lines = 3 garbage lines, each one to a random player.)
* **Shooter:** every enemy you kill is sent to a random other player (see section 5).
* **How the random player is picked:** it is random, but fair. Everybody still alive gets
  hit once, in a random order, before anybody is hit a second time, so it never keeps
  hitting the same person. (With only 2 players there is just one other player, so it is always them.)
* Each garbage line is grey and has **one hole at a random spot**, so it can be cleared.
* The line arrives after the victim's current piece lands. A red bar beside the board
  shows how many lines are on their way.
* Everybody gets the same pieces in the same order. Someone who tops out is OUT.
  The **last player alive wins**. Up to 8 players.
* On the host screen a board flashes **red** when it gets a line and **green** when it sends one.

### Step by step
1. **On the host Pi:** Games > TETRIS (or SPACE SHOOTER) > MULTIPLAYER > **HOST (SPECTATE)**.
   It shows its name and IP address and waits for players.
2. **On every player Pi:** the same game > MULTIPLAYER > **JOIN A GAME**.
   The Pi searches the network automatically; the host appears in the list
   (e.g. `tetris-host [1 IN]`). Select it and press B2.
3. When all players are listed on the host screen, the host presses **B2 = START GAME**
   (in Tetris the host can first choose the start level with Left/Right). A 3-2-1 countdown starts on all screens.
4. During a round the in-game menu (B1, in both games) does **not** pause the game - it keeps running.
5. After the round everybody sees the ranking. Press B1/B2 to go back to the lobby;
   the host can start the next round.

Nobody can join while a round is running.

### Give every Pi a different name
Players are shown by their Pi's hostname. If two Pis are both called `raspberrypi`
the game adds a number, but it is nicer to give them real names. Either:

    sudo hostnamectl set-hostname tetris-1

(then reboot), or put a name in `config.json`:

    "player_name": "ALICE"

### Network notes
* Pis find each other with a UDP broadcast on port **47800**, and then connect over TCP.
  Normal home networks need no setup (Raspberry Pi OS has no firewall by default).
* Some networks block Pis from seeing each other (guest Wi-Fi, "client isolation",
  school/office networks). If the host never shows up in the join list, use a normal
  network or connect the Pis to a small switch/router together.
* Wi-Fi works, but a wired connection gives the smoothest game.

---

## 7. Vertical screen & fullscreen

The game is drawn as a **portrait** picture (9:16). Pick whichever fits your monitor:

**A. The monitor is physically turned vertical:** rotate the desktop in Raspberry Pi OS:
Raspberry Pi menu > Preferences > **Screen Configuration** > right-click your screen >
**Orientation** > Left or Right > Apply. Leave `"rotate": 0` in `config.json`.

**B. Let the game rotate itself:** open `config.json` and set `"rotate": 90`
(or `270` if the picture is upside down). No changes to the Pi's settings needed.

Fullscreen is **on by default**. Turn it off in the Tetris main menu (FULLSCREEN),
with F11 on a keyboard, or by setting `"fullscreen": false` in `config.json`.
The picture scales to any screen size and the mouse cursor is hidden.

---

## 8. Wire the 6 buttons (GPIO)

Every button has 2 legs: one goes to a GPIO pin, the other to any GND pin.
No resistors needed (the Pi's internal pull-ups are used).

| Button  | BCM GPIO | Physical pin |
|---------|----------|--------------|
| UP      | 5        | 29           |
| DOWN    | 6        | 31           |
| LEFT    | 13       | 33           |
| RIGHT   | 19       | 35           |
| BUTTON1 | 26       | 37           |
| BUTTON2 | 21       | 40           |
| GND (shared by all buttons) | - | 39 (or 30, 34) |

Power the Pi off before wiring. Different pins? Edit `config.json` (BCM numbers).
No buttons connected? Set `"gpio_enabled": false` (the keyboard always works).

---

## 9. Start the games menu automatically when the Pi boots

Do this once, from inside the game folder:

    cd ~/pi-tetris
    bash enable_autostart.sh

Then make the Pi log in to the desktop by itself (otherwise it waits at the login screen):

    sudo raspi-config

> System Options > Boot / Auto Login > **Desktop Autologin** > Finish > reboot.

Now whenever you power on the Pi it boots to the desktop and the **games menu
starts fullscreen by itself**. (Booting takes a little while, wait until the desktop has loaded.)

* The script sets up the autostart for every desktop type Raspberry Pi OS uses. If more than one
  entry is found the game still only starts once.
* Pick **EXIT TO DESKTOP** in the games menu if you want to get out of the game.
  It starts again at the next boot.
* **Turn it off again:** `bash disable_autostart.sh`
* **Did not start?** Open the file `game.log` in the game folder: it holds the messages of the
  last run. Also check that Desktop Autologin is on, and that `bash run.sh` works by hand.

---

## Troubleshooting

* **`pygame` not found:** run `bash install.sh` again and start with `bash run.sh`.
* **"GPIO not available" message:** harmless, keyboard still works. For buttons run
  `sudo apt install python3-gpiozero python3-lgpio`.
* **A button does nothing:** check the pin table and that the other leg goes to GND.
  Test: `python3 -c "from gpiozero import Button; b=Button(5); b.wait_for_press(); print('ok')"`
* **A button triggers twice:** raise `gpio_debounce_ms` in `config.json` (try 50).
* **Picture is sideways:** change `"rotate"` to 90 or 270 (or use the Screen Configuration, see section 7).
* **Black screen / no window over SSH:** run it on the Pi's own desktop, or `DISPLAY=:0 bash run.sh`.
* **Host not found when joining:** same network? Host must be in its lobby (not mid-round).
  Pis on guest Wi-Fi often cannot see each other.
* **Game slow on the Pi:** close other programs; wired network helps multiplayer.
* **Reset the scoreboard:** quit the game and run `rm highscores.json`.
