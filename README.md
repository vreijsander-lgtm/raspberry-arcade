# The Nova Arcade 🕹️

A home-made arcade for the **Raspberry Pi**: seven games in one menu, made for a tall
(portrait) screen and a simple controller with **a stick and two buttons**. It has
high-score tables, game modes, and LAN multiplayer between several Pis.

Everything is written in Python with [pygame](https://www.pygame.org/), and runs on a
Raspberry Pi 4 or 5 with Raspberry Pi OS (64-bit). It also runs on a normal PC with
Python and pygame, which is handy for testing.

---

## The games

| Game | What it is | Multiplayer |
|------|------------|-------------|
| **Tetris** | Stack the falling blocks and clear lines. | ✅ battle: your lines go to the others as garbage |
| **Space Shooter** | Waves of enemy ships and bosses, with upgrades to pick between waves. | ✅ survival: the ships you shoot down go to the others |
| **Sky Hopper** | Jump from platform to platform, as high as you can, as a little scout droid. | ✅ race to the top |
| **Saber Brawl** | One-on-one fights with laser swords: a ladder of 6 opponents. | ✅ 1 vs 1 |
| **Glowbug** | A maze game: eat every light while spider droids hunt you. | ✅ light race, 2–4 players |
| **Pulsar** | A paddle game: the longer nobody scores, the faster the ball. | ✅ 1 vs 1 |
| **Star Toss** | Hold to spin, let go to throw, and helpers on the walls throw you higher. | single player |

The start menu also has a **RANDOM GAME** button.

### Student games

Other students can add their own games: put a folder with a `game.py` in
[`student_games/`](student_games/) and it shows up under **STUDENT GAMES** on the start
screen of every arcade, with its own top 10. The Pis pick it up the next time they start.
See [student_games/README.md](student_games/README.md) for how to make one.

### Game modes

Most games have extra **modes**, picked with `MODE < … >` in the game's menu. Every mode has
its own top 10. In multiplayer, the host picks the mode in the lobby.

| Game | Mode | What it does | Multiplayer |
|------|------|--------------|-------------|
| **Tetris** | CLASSIC | The normal game | ✅ |
| | CHAOS | Every block is a random new shape | ✅ |
| **Space Shooter** | CLASSIC | The normal game | ✅ |
| | BOSS RUSH | A boss fight every wave | ✅ |
| | ONE LIFE | No extra lives | ✅ |
| **Sky Hopper** | CLASSIC | The normal game | ✅ |
| | TURBO | Everything runs 1.75× faster, and the screen rises fast right away | ✅ |
| **Saber Brawl** | CLASSIC | The normal game: a ladder of 6 opponents | ✅ |
| | GLASS JAW | Every hit does triple damage | ✅ |
| **Glowbug** | CLASSIC | The normal game | ✅ |
| | FRENZY | Everything runs 1.75× faster, and all the spiders come out at once | ✅ |
| **Pulsar** | CLASSIC | The longer nobody scores, the faster the ball | ✅ |
| | POWER | Hit the ball through power-up orbs | ✅ |
| | MULTIBALL | An extra ball for every 5 points (up to 3) | ✅ |
| | SHRINK | Your paddle shrinks with every point | ✅ |
| | BRICKS | A brick breaker: a smash plows straight through | ❌ single player only |
| **Star Toss** | *(one mode)* | Hold to spin, let go to throw | ❌ single player only |

---

## Controls

All games use the same six buttons:

| Button | Keyboard | Usually does |
|--------|----------|--------------|
| **Up / Down / Left / Right** | arrow keys | move / choose in menus |
| **Button 1** | `Esc` or `Tab` | menu / back |
| **Button 2** | `Space`, `Enter`, `Z` or `X` | action / OK |

You can use the keyboard, a **USB arcade stick** (zero-delay encoder) or **buttons wired to
the Pi's GPIO pins**, all at the same time. `Alt+F4` quits.

---

## What you need

- A **Raspberry Pi 4 or 5** with **Raspberry Pi OS (64-bit, with desktop)**
- A screen. A monitor turned on its side works best; the game can also rotate itself.
- A controller: a keyboard, a USB arcade stick, or 6 buttons on the GPIO pins
- For multiplayer: two or more Pis on the **same network**

---

## Installation

### 1. Get the arcade onto the Pi

Open a **Terminal** on the Pi (`Ctrl+Alt+T`) and download it into a folder called `picade`
in your home folder:

```bash
git clone https://github.com/vreijsander-lgtm/raspberry-arcade.git ~/picade
```

> No `git`? Run `sudo apt install git` first, or download the ZIP from GitHub
> (**Code → Download ZIP**) and unpack it to `~/picade`.

### 2. Install what it needs (once, needs internet)

```bash
cd ~/picade/main
bash install.sh
```

This installs `python3-pygame`, `python3-gpiozero` and `python3-lgpio`. It may ask for your
password; nothing shows while you type it, which is normal.

### 3. Play

```bash
cd ~/picade/main
bash run.sh
```

The arcade starts **fullscreen**. Run it from the Pi's desktop, not over plain SSH, because
it needs a screen.

### 4. Start automatically when the Pi boots (optional)

```bash
cd ~/picade/main
bash enable_autostart.sh
```

Then turn on auto-login: `sudo raspi-config` → **System Options** → **Boot / Auto Login** →
**Desktop Autologin**. To undo it: `bash disable_autostart.sh`.

---

## Settings

The first time the arcade runs it uses sensible defaults. Settings live in
`main/config.json`, which every Pi keeps for itself; it is never uploaded or overwritten by
updates. The most useful ones:

| Setting | What it does |
|---------|--------------|
| `"rotate"` | `0` if the monitor is already vertical; `90` or `270` to let the game turn its picture |
| `"fullscreen"` | `true` / `false` |
| `"player_name"` | the name other players see in multiplayer (empty = the Pi's network name) |
| `"gpio_enabled"`, `"gpio_pins"` | buttons wired to the GPIO pins (BCM numbers, each button to GND) |
| `"joy_buttons"` | which USB-stick buttons are Button 1 / Button 2 (`python3 stick_test.py` in `~/picade/main` shows the numbers) |
| `"shared_scores"`, `"score_group"` | share the high-score tables between all arcade Pis on your network |
| `"auto_update"` | `false` = don't download the newest version from GitHub at start (default: on) |

The full guide (wiring the buttons, screens, multiplayer, every game) is in
**[main/TUTORIAL.md](main/TUTORIAL.md)**.

---

## Multiplayer

Every Pi needs the arcade installed and has to be on the same network. Open a game →
**MULTIPLAYER**, then:

- **PLAY WITHOUT HOST**: this Pi hosts the game and plays too. This is the easiest with two Pis.
- **JOIN A GAME**: the other Pis join it.
- **HOST (SPECTATE)**: a third Pi shows everybody's game on its screen (live view).

The host picks the **mode** with LEFT / RIGHT in the lobby and starts with Button 2.

> **Every Pi must run the same version** of the arcade, so update them all together (see
> below).

---

## Updating your Pis

**Automatically, every time the arcade starts.** If a Pi was installed with `git clone`
(as above), `run.sh` first checks GitHub for a newer version and downloads it, then starts
the games. Without internet it waits at most 15 seconds and starts the version it has.
Scores and settings are never touched. What happened is written to `main/update.log`. To
switch it off on one Pi, put `"auto_update": false` in its `main/config.json`.

> A Pi that still has an **older** `run.sh` (from before this feature) needs one update by
> hand first (`git pull` below, or the PC tool). From then on it updates itself.

**Option A: from your PC, in one click.** Put your arcade Pis in [`update/pis.txt`](update/pis.txt)
and double-click [`update/update_pis.bat`](update/update_pis.bat). Only the Pis in that list are
updated, and each one keeps its own settings and high scores. Setup (switch on SSH, one-time
key) is explained in section 10 of the [tutorial](main/TUTORIAL.md).

**Option B: on the Pi itself** (if you installed it with `git clone`):

```bash
cd ~/picade
git pull
```

Restart the arcade (or the Pi) afterwards.

---

## Folder layout

```
picade/
├── main/          the arcade: start menu, menus, scoreboards, multiplayer, settings
│   ├── run.sh, install.sh, enable_autostart.sh   ← the scripts you run on the Pi
│   └── TUTORIAL.md                               ← the full guide
├── tetris/        Tetris
├── spaceshooter/  Space Shooter
├── platformer/    Sky Hopper
├── fighter/       Saber Brawl
├── glowbug/       Glowbug
├── pulsar/        Pulsar
├── startoss/      Star Toss
├── cabinet/       3D-printable cabinet (STL files + make_cabinet.py that makes them)
├── update/        the tool that updates your Pis from your PC (runs on the PC)
└── pi-tetris/     the old first version (Tetris only), not used by the arcade
```

Each game is two files: the rules (no pygame, easy to test) and the drawing and menus
(`*_ui.py`), which plug into the arcade in `main/main.py`.

---

## Troubleshooting

| Problem | Try this |
|---------|----------|
| `No module named pygame` | run `bash install.sh` again (in `~/picade/main`) |
| Black screen or wrong way round | change `"rotate"` in `main/config.json` |
| Buttons do nothing | check the wiring and `"gpio_pins"`; for a USB stick run `python3 stick_test.py` in `~/picade/main` |
| Multiplayer: no games found | all Pis on the same network (not guest Wi-Fi), same arcade version, the host in its lobby |
| Something crashed at start-up | read `main/game.log`; it keeps the output of the last run |

More in the **Troubleshooting** section of the [tutorial](main/TUTORIAL.md).
