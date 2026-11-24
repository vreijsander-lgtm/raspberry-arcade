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

A USB arcade stick works too (see section 8).

| Action            | Keyboard                         | GPIO name |
|-------------------|----------------------------------|-----------|
| Menu up           | Up arrow                         | up        |
| Menu down / speed up falling | Down arrow            | down      |
| Move left / menu value - | Left arrow                | left      |
| Move right / menu value + | Right arrow              | right     |
| Open menu / go back  | Esc or Tab                    | button1   |
| Rotate / OK (Space Shooter: **shoot**) | Space, Enter, Z or X | button2   |

**Start screen - THE NOVA ARCADE:** the Pi starts on an animated title screen with a card
for each game (TETRIS, SPACE SHOOTER) showing its top score. Up/Down picks a game, B2 starts it.
The Tetris and Space Shooter main menus use the same neon style: their own glowing logo,
neon buttons, and a little animation (falling blocks / a ship shooting an alien). The pause,
game-over, scoreboard, name-entry and multiplayer screens use the same sky and neon buttons.
All of these screens are drawn in `title_ui.py`.
Pick a game with Up/Down + B2. B1 inside a game's main menu brings you back to this list.

**Tetris main menu:** SINGLE PLAYER, LEVEL (Left/Right), MULTIPLAYER, SCOREBOARD,
BACK (to the games list).

**Scoreboard:** when you game over with a top-10 score you can enter a name of up to
**10 characters** (letters, digits and spaces): Up/Down changes the letter (Down from A is a
space), Left/Right moves the cursor, B2 saves. Scores are stored in `highscores.json`.

**Name filter:** slurs and other nasty words are refused ("THAT NAME IS NOT ALLOWED"),
also when written with digits (N1GG3R), spaces or repeated letters. The list (English and
Dutch) is in `name_filter.py`. To ban more words, make a file `banned_names.txt` next to it
with one word per line, then restart the game.

**Shared scoreboard:** all arcade Pis on the same network share their high scores, so a
score set on one Pi shows up on every other Pi within about 5 seconds. A Pi that was off
catches up when it starts. Settings in `config.json`:
* `"shared_scores": false` turns it off.
* `"score_group"`: only Pis with the same group share (change it if another school's arcade
  is on the same network).
* `"score_peers": ["192.168.1.21", "192.168.1.22"]`: only needed if the network blocks
  broadcasts (school Wi-Fi sometimes does). Put the other Pis' IP addresses there.

The Pis send to each other on UDP port 47810.

**Scoring:** 1 / 2 / 3 / 4 lines = 100 / 300 / 500 / 800 x level. Soft drop = 1 point
per row. A new level every 10 lines.

---

## 5. Space Shooter

Pick **SPACE SHOOTER** in the games menu. Its menu works like Tetris:
SINGLE PLAYER, MULTIPLAYER, SCOREBOARD, BACK.

| Button | In the game |
|--------|-------------|
| Left / Right | fly left / right |
| **Button 2** | **shoot** (hold it to keep firing) |
| **Button 1** | **menu** (pause, restart, scoreboard, main menu) |

* You have 3 lives. Enemies that touch you or their bullets take a life
  (you blink and can't be hit for 2 seconds). Waves get harder the longer you survive.
* Enemies: **drone** (zig-zags, 10 pts), **fighter** (aims at you, 25 pts, 2 hits),
  **tank** (slow, 3-way shots, 60 pts, 7 hits).
* Special enemies (they start showing up in later waves):
  * **Splitter** (green cracked diamond, from wave 3): breaks into two fast **minis** when killed.
  * **Diver** (orange arrow, from wave 4): stops, **blinks while it aims at you**, then dashes
    straight at where you were - move away while it blinks!
  * **Rock** (grey asteroid, from wave 6): **can't be destroyed** and blocks your bullets.
    Just dodge it.
  * **Curse eye** (purple eye, from wave 7): has a big purple **aura** and slowly follows you.
    While you are inside the aura you **can't shoot** ("CURSED"). Shoot it before it gets
    close, or fly out of the circle. Only one at a time.
* **Upgrades**: at the end of every wave (the green bar under your score shows how far the
  wave is) all enemies and shots vanish and **three big boxes** fly in. You can't shoot for
  2 seconds (so holding the button can't pick by accident), then you fire **one bullet** at a
  time - your extra bullets come back after you choose. **Shoot one** box to pick it - the other
  two disappear. Upgrades last for the whole run and stack (losing a life does not take them
  away).
* **Tougher every wave**: enemies get a bit more HP every wave - hardly at the start
  (wave 2 is the same as wave 1), more later on, so your upgrades stay useful but never make
  the game trivial. Example HP (drone / fighter / tank): wave 1: 1/2/7, wave 10: 3/7/23,
  wave 20: 10/20/71.
* **Bosses**: every **5th wave** (5, 10, 15, ...) is a boss wave: right after you pick your
  upgrade at the start of the wave, a boss flies in instead of normal enemies. Its health bar is at the top. It shoots aimed fans, rings of bullets (with a
  gap to slip through) and, from boss 2 on, quick bursts. Each next boss is tougher. Beat it
  for **3 coins** and **two free upgrade picks** in a row.
* **Coins**: every enemy you kill has a 10% chance to drop a gold coin. It flies to your ship by
  itself (the number next to the green bar is how many you have). On the upgrade screen, shoot the
  **little reroll cube** at the far left (under the left box) to pay 1 coin and get three new
  upgrades. The cube is grey when you have no coins or there is nothing else to roll.

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

**Rare upgrades** - sometimes a box has a gold frame and a **RARE** tag (about 1 in 8 upgrade
choices, and most boss rewards). Each rare one can only be taken once per run:

| Rare box | What it does |
|----------|--------------|
| **Mega laser** | Replaces your bullets: hold the button to charge (the orb on your nose grows), then a big beam fires that hits **everything** in a line. More bullets / damage / fire rate / big bullets make the beam stronger, wider and charge faster. |
| **Wingman** | A small helper ship flies next to you and shoots with you. |
| **Phase shots** | Your bullets go through every enemy - and through rocks. |
| **Boom shots** | Bullets explode when they hit, hurting enemies close by. |
| **Holy halo** | Enemies close to you slowly burn, and curse auras don't work on you. |
| **Phoenix** | The first time you would die, you come back with 1 life and the screen is cleared. |
| **Slow time** | All enemies move slower and their bullets are a lot slower. |

**Your ship shows your upgrades**: more bullets = a gun rack with one hole per bullet, damage =
red stripes, fire rate = more engines, ship speed = wider wings with fins, pierce = a green
spike on the nose, homing = antennas, big bullets = a fat nose cannon, shield = blue panels.
Rare upgrades add their own parts: a glowing laser orb, a halo, bomb pods, a little clock,
burning phoenix wings (until used) and a ghost outline for phase shots.

* The top 10 is kept in `highscores_shooter.json` (kills are shown next to the score).

### Space Shooter multiplayer
Same as Tetris multiplayer (section 6): the host Pi spectates and shows every player's screen,
the others play. **Every enemy you kill is sent to another random player**: the same type of
enemy appears at the top of their screen (at the same spot where you shot it, with a pink outline
so you can see it came from a rival). Enemies that were sent to you are not passed on again.
The last player alive wins. In the round, Button 1 opens a small menu; the game keeps running.

---

## 5b. Sky Hopper (platformer)

Pick **SKY HOPPER** in the games menu: SINGLE PLAYER, SCOREBOARD, BACK.
Climb as high as you can by jumping from platform to platform.

| Button | In the game |
|--------|-------------|
| Left / Right | run left / right |
| **Button 2** or **Up** | **jump** (hold it to jump higher) |
| Down | drop down through the platform you stand on |
| **Button 1** | **menu** (pause, restart, scoreboard, main menu) |

* The screen follows you up, and after the first few metres it **keeps rising by itself**
  (the red glow at the bottom). Fall off the bottom and the run is over.
* **Green** platforms are normal, **pink** ones move, **orange** ones crumble shortly after
  you land on them. Land on a **spring** for a huge jump: until you land again you glow
  green and **smash every enemy you bump into** instead of getting hurt.
* **Walkers** (purple spiky blobs) and **flyers** (red bats, higher up): jump on their head
  to squash them (+50, and you bounce), touching them from the side costs a heart. You have 3.
* Points: 5 per metre, 50 per squashed enemy, plus a bonus for every new
  **zone** (every 150 m). Each zone gets harder and the sky changes colour.
* The top 10 is kept in `highscores_platformer.json` (metres are shown next to the score)
  and is shared with the other Pis like the other scoreboards.

### Sky Hopper multiplayer

Works like the other games' multiplayer (HOST, PLAY WITHOUT HOST, JOIN A GAME), but it is a
**race to the top**:

* Everybody climbs the **same** world.
* The other players are shown as **see-through ghosts** with their name above them, and the
  little list at the top right shows everybody's height (you are gold, an X = out).
* **Everybody's screen follows the highest player.** If you are too slow you drop off the
  bottom of your screen and you are out (YOU FELL BEHIND!). You can keep watching the others.
* Getting hit too often (3 hearts) also puts you out. The last player still climbing wins.
* The host's LIVE VIEW shows one big screen that follows the leader, with every player in
  their own colour.

## 5c. Saber Brawl (fighting game)

Pick **SABER BRAWL** in the games menu: SINGLE PLAYER, HOW TO PLAY, SCOREBOARD, BACK.
Fight your way up a ladder of 6 computer opponents, one-on-one, best of 3 rounds each.
After the 6th the ladder starts again and everybody hits harder. Lose a match and the run is over.

| Button | In the game |
|--------|-------------|
| Left / Right | walk. **Holding away from the enemy blocks** |
| Up | jump |
| Down | crouch (ducks normal blasts). Down + away = low block |
| **Button 2** | saber strike. Press it 3 times for strike, strike, kick |
| Down + Button 2 | sweep (knocks down, has to be blocked crouching) |
| Up + Button 2 | uppercut (beats enemies jumping at you) |
| Button 2 in the air | dive kick (has to be blocked standing) |
| Hold Button 2, let go | **Nova Blast** (energy ball). With a full POWER bar: SUPER BLAST |
| **Button 1** | **menu** (pause, restart, how to play, main menu) |

* Points: 10 per point of damage, plus a bonus for every round you win (health and time left,
  +5000 for a PERFECT round without getting hit) and for every opponent you beat.
* The top 10 is kept in `highscores_fighter.json` (opponents beaten are shown next to the
  score) and is shared with the other Pis like the other scoreboards.

### Saber Brawl multiplayer (1 vs 1)

SABER BRAWL > MULTIPLAYER works like the other games' multiplayer, but it is always
**exactly 2 players**, best of 3 rounds:

* **PLAY WITHOUT HOST** on one Pi, **JOIN A GAME** on the other, then B2 on the first Pi starts
  the fight. With only two Pis this is the way to go.
* Or use a third Pi as **HOST (SPECTATE)**: it shows the fight big on its screen (LIVE VIEW)
  while the two players fight from their own Pis. It starts when both players are in.
* The host Pi runs the fight; the players' Pis send their buttons to it and show what it sends
  back. A wired network (or good Wi-Fi) feels best.
* Button 1 opens a small menu (the fight keeps going). If a player leaves, the other one wins.
* Multiplayer fights don't go on the scoreboard; the results screen shows the rounds won.

## 5d. Glowbug (maze game)

Pick **GLOWBUG** in the games menu: SINGLE PLAYER, HOW TO PLAY, SCOREBOARD, BACK.
You are a glowbug in a neon maze: eat every light while four spiders hunt you.

| Button | In the game |
|--------|-------------|
| Stick | move. Press a turn a bit early: it is remembered until the next crossing |
| **Button 2** | **FLASH**: stuns the spiders close to you for a moment |
| **Button 1** | **menu** (pause, restart, scoreboard, main menu) |

* Eat a big **spark** and the spiders get scared for a few seconds: catch them for 200, 400, 800
  and 1600 points. Caught spiders roll back to their nest as a web ball.
* You get a **FLASH** charge for every 60 lights you eat (max 3). Stunned spiders can't hurt you.
* **Gems** appear twice per level under the nest: grab them for bonus points.
* Each spider hunts differently: VIOLA comes straight at you, EMBER cuts you off, TEAL guards
  the sparks near you and AMBER follows your trail.
* 3 lives, an extra one every 10000 points. Each level is faster and the scare time is shorter.
* The top 10 is kept in `highscores_glowbug.json` (the level reached is shown next to the
  score) and is shared with the other Pis like the other scoreboards.

### Glowbug multiplayer (light race)

GLOWBUG > MULTIPLAYER works like the other games' multiplayer (HOST, PLAY WITHOUT HOST,
JOIN A GAME). **2 to 4 players**, all in the **same maze**, **5 rounds**:

* Collect the most **pickups**: light = 1, spark = 2, caught spider = 3, gem = 5.
  Whoever has the most pickups after round 5 wins.
* A round ends when every light is gone or after 75 seconds. Each round has the other maze
  and the spiders get a bit faster.
* Caught by a spider? You're out for a moment, then you come back at your start corner.
* Your **FLASH** (B2) stuns the spiders near you *and* dazzles the other bugs near you for a
  moment. Everybody starts every round with 1 flash and gets one more per 30 lights.
* Every bug has its own colour and name; yours says YOU. The bar at the top shows everybody's
  total (+ this round). Between rounds you see the standings.
* With only two Pis: PLAY WITHOUT HOST on one, JOIN A GAME on the other. A third Pi on
  HOST (SPECTATE) shows the race big on its screen (LIVE VIEW).
* Multiplayer races don't go on the scoreboard. If players leave and only one is left, that
  player wins.

## 5d2. Pulsar (paddle game)

Pick **PULSAR** in the games menu. Your energy paddle is at the bottom, the computer's at the
top. Get the plasma ball past the computer to score a point. **The longer nobody scores, the
faster the ball goes** (the SPEED bar at the top fills up); after every point it starts slow
again. If the ball gets past you, you lose one of your 3 lives.

| Button | In the game |
|--------|-------------|
| Left / Right | move your paddle |
| **Button 2** | **SMASH**: press it just as the ball reaches you and it flies back extra fast |
| **Button 1** | **menu** (pause, restart, scoreboard, main menu) |

* Where the ball hits your paddle decides the angle: the edges send it off steeply. Steep and
  smashed balls are the hardest for the computer to reach.
* Points: 10 for every return, 100 for every point you score (more after every 5 points).
* The top 10 is kept in `highscores_pulsar.json` (your points are shown next to the score).

### Pulsar BRICKS power-ups

Broken bricks sometimes drop a capsule; catch it with your paddle:

| Capsule | What it does |
|---------|--------------|
| **x3** | every ball splits into three (up to 6 balls) |
| **WIDE** | a much wider paddle for 15 seconds |
| **FIRE** | your balls burn straight through bricks for 8 seconds |
| **SHIELD** | a barrier under your paddle bounces one lost ball back |
| **1UP** | an extra life (rare) |
| **MINI** (red) | BAD: a smaller paddle for 10 seconds - dodge it! |

With more than one ball you only lose a life when the last ball is gone.

### Pulsar multiplayer (1 vs 1)

PULSAR > MULTIPLAYER works like Saber Brawl's: exactly **2 players**, **first to 7 points**.
PLAY WITHOUT HOST on one Pi, JOIN A GAME on the other (or a third Pi as HOST (SPECTATE)).
**Both players see their own (blue) paddle at the bottom** - the other player is red at the
top. SMASH works for both. Multiplayer games don't go on the scoreboard.

## 5d3. Star Toss (throwing game)

Pick **STAR TOSS** in the games menu. At the bottom of a tall space shaft a launcher droid on a
bobbing hover pad holds your astronaut on its arm.

| Button | In the game |
|--------|-------------|
| **Button 2 (press)** | **spin**: the droid starts swinging you round - faster and faster |
| **Button 2 (press again)** | **throw**: you fly off the way you were moving (no aiming arrow - judge it by eye) |
| **Button 1** | **menu** (pause, restart, scoreboard, main menu) |

* Wait too long (3.4 seconds) and the droid gets **DIZZY** and drops you - a wasted throw.
  The pad bobs and tilts, which shifts the angle a little every time. Once thrown, you can't steer.
* **Helper droids** sit in the walls, left and right, every 64 m (a few metres up or down).
  Touch one and it bounces you up and across straight away. How hard depends on:
  * **angle** - steep is good, a flat sideways hit is a **FLAT HIT**;
  * **spot** - rising, hit the front of its arms (behind them is an **UNDER-CLIP**);
    falling, land on top of it like a springboard;
  * **speed** - rising fast carries on into the bounce.
  A perfect hit is a **SUPER BOUNCE**. Every bounce is a bit weaker, and after 4 the helpers
  send you up the middle, so every throw comes down in the end.
* **Power-up capsules** drift down on parachutes - fly through one (it works on that astronaut;
  all five turn up early in every throw):

  | Capsule | What it does |
  |---------|--------------|
  | **M** MULTI | that astronaut splits into three (up to 9) - the highest one counts |
  | **R** ROCKET | a burst of rocket thrust |
  | **G** GIANT | bigger: easier to hit helpers, but heavier and slower |
  | **T** TINY | smaller: lighter and faster, but easy to miss helpers |
  | **?** MYSTERY | SPLIT + ROCKET, MEGA ROCKET... or an ANVIL / TINY ANVIL (heavy for a moment; it breaks off at a helper) |

* Every time an astronaut reaches a new highest point the picture freezes for a moment: a
  **SNAPSHOT** of the peak.
* A throw is over when the **last astronaut is back down**.
* A game is **5 throws**. The score is the heights of all 5 added up (in metres); a throw lower
  than 12 m counts as 0. The top 10 is kept in `highscores_toss.json`. Single player only for now.

## 5e. Game modes

Every game's menu has **MODE < ... >**: select it and press LEFT / RIGHT (or B2) to switch.
The line at the bottom of the menu says what the mode does. SINGLE PLAYER, RESTART and the
RANDOM GAME button on the start screen all use the mode that is picked. Every mode has its
**own top 10** (`highscores_tetris_chaos.json` and so on), shared with the other Pis.
**Multiplayer:** the host picks the mode in its lobby with **LEFT / RIGHT** (for Tetris,
UP / DOWN sets the start level); everybody who joined sees the mode before the start, and the
whole round is played in it. Every mode works online except Pulsar BRICKS.

| Game | Mode | What changes |
|------|------|--------------|
| Tetris | CHAOS | every block is a brand new random shape (3 to 6 squares) |
| Space Shooter | BOSS RUSH | a boss every wave (a bit weaker); you start with 3 free upgrades |
| Space Shooter | ONE LIFE | 1 life and no extra lives |
| Sky Hopper | TURBO | the whole game runs 1.75x faster, and the screen starts rising almost right away, and fast |
| Saber Brawl | GLASS JAW | every hit does triple damage, for everybody |
| Glowbug | FRENZY | the whole game runs 1.75x faster, the spiders are faster still, and they all come out at once |
| Pulsar | MULTIBALL | an extra ball for every 5 points you have (up to 3 at once) |
| Pulsar | SHRINK | your paddle gets a bit smaller with every point |
| Pulsar | POWER | power-up orbs float across the middle: hit the ball through one and it's yours (WIDE paddle, MINI for the other side, x3 balls, SHIELD, FREEZE the other paddle, auto-SMASH); the computer collects them too |
| Pulsar | BRICKS | no computer: break walls of bricks (metal ones need 2 hits) at one steady ball speed; a SMASH plows straight through bricks; bricks drop power-ups (below); single player only |

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

### Play without a host (no spectator Pi)
Don't have a spare Pi for the spectator screen? One of the players chooses
MULTIPLAYER > **PLAY WITHOUT HOST**. That Pi runs the game in the background *and* plays
along. The others choose **JOIN A GAME** and pick it from the list (it has that Pi's name).

On the Pi that made the game, the lobby shows **YOUR GAME** with all players. When at least one
other player has joined, press **B2 = START GAME** (in Tetris first pick the start level with
Left/Right). After a round, B1/B2 goes back to the lobby for the next round. If that Pi leaves
(B1), the game ends for everybody.

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

Fullscreen is **on by default**. There is no button or key to leave it (so players can't get
to the desktop). To test in a window, set `"fullscreen": false` in `config.json`.
The picture scales to any screen size and the mouse cursor is hidden.

**C. A normal wide monitor (not turned):** the tall game sits in the middle. Instead of black
bars, both sides show the starry neon sky. This only happens in fullscreen. Want plain black bars?
Add `"fill_sides": false` to `config.json`.

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

### USB arcade stick (zero-delay board) instead of GPIO

Just plug it in, even while the game runs. The stick (left analog stick or d-pad) gives the
4 directions. Which buttons are BUTTON1 / BUTTON2 is set in `config.json`:

```json
"joy_buttons": { "button1": [1, 3], "button2": [0, 2] }
```

To find your button numbers, stop the game and run `python3 stick_test.py`. Press each button
and it shows its number and what it does. Put the numbers in the lists (more numbers per action
are fine), then restart the game. If the stick feels too sensitive or too slow to react, change
`"joy_deadzone"` (0.5 = halfway; with a real arcade stick this hardly matters).

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
* The game has **no exit button**. To get out, plug in a keyboard and press **Alt+F4**.
  It starts again at the next boot.
* **Turn it off again:** `bash disable_autostart.sh`
* **Did not start?** Open the file `game.log` in the game folder: it holds the messages of the
  last run. Also check that Desktop Autologin is on, and that `bash run.sh` works by hand.

---

## 9b. Automatic updates from GitHub (when the arcade starts)

If the arcade was installed with
`git clone https://github.com/vreijsander-lgtm/raspberry-arcade.git ~/picade`, then every
time it starts (`run.sh`, also at boot) it first checks GitHub for a newer version, downloads
it and then starts the games.

* No internet or GitHub too slow: after at most 15 seconds it starts the version it has.
* Scores (`highscores*.json`) and settings (`config.json`) are never changed by an update.
* The Pi always follows GitHub exactly: changes made to the game code **on the Pi itself**
  are replaced by the GitHub version.
* `main/update.log` shows what the last start did ("Updated to ...", "Already the newest
  version", "No connection ...").
* Switch it off for one Pi: add `"auto_update": false` to its `main/config.json`.
* A Pi with an older `run.sh` (from before this existed) needs one manual update first:
  `cd ~/picade && git pull` (or the PC tool in section 10).

## 10. Update all arcade Pis from your PC (one click)

The `update` folder (next to `main`) has a tool that sends the newest version of the arcade
to your arcade Pis over your home network. **Only the Pis you list are updated** - other Pis
on your network are never touched.

**Once, on every arcade Pi:** switch SSH on: `sudo raspi-config` > Interface Options > SSH >
Yes. Write down the Pi's network name (`hostname` in a terminal, e.g. `arcade1`; on your
network it is `arcade1.local`) or its IP address (`hostname -I`).

**Once, on your PC:**

1. Open `update\pis.txt` and put your arcade Pis in it, one per line:
   `arcade1.local`  (add the user if it isn't `pi`, and the folder if the arcade isn't in
   `~/picade` - e.g. `arcade2.local  gamer  pi-tetris`).
2. So you don't have to type passwords every time, open a terminal in the `update` folder
   and run `py update_pis.py --setup-keys` - it asks every Pi's password one last time.

**Every time you want to update:** double-click `update\update_pis.bat`. Each Pi in the list
gets the new version; it starts the next time the arcade starts (reboot the Pi, or run
`py update_pis.py --restart` to reboot them for you).

* Every Pi **keeps its own** `config.json` (controls, name) and **its scoreboards** - they are
  never sent or overwritten.
* The new version **replaces** the old code (removed games really disappear); the previous
  version stays as a backup folder `picade.old` until the next update.
* A Pi that's switched off or can't be reached is skipped and listed as *Failed* - just run it
  again later.
* `py update_pis.py --dry-run` shows what would be sent where without changing anything;
  `--only arcade1.local` updates just one Pi.

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
* **Reset the scoreboard:** quit the game and run `rm highscores.json`. With the shared
  scoreboard the other Pis would send the old scores back, so do it **on all Pis** while the
  games are closed (or give them all a new `"score_group"`).
