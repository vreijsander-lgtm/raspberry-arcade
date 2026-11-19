"""
Saber Brawl - game logic (no pygame in here, so it can be tested anywhere).

A one-on-one fighting game against the computer, made for the tall screen.
Fight your way up a ladder of six opponents (best of three rounds each).
After the last one the ladder starts again, and everybody fights harder.
Lose a match and the run is over.

Controls (see main.py) - the same six buttons as the other games:
    LEFT / RIGHT      walk. Holding AWAY from the enemy BLOCKS attacks.
    UP                jump
    DOWN              crouch (crouching ducks under normal blasts).
                      DOWN + away = low block (needed against sweeps)
    BUTTON2           punch - press again for punch, punch, kick
      DOWN + B2       low sweep (knocks down; block it crouching)
      UP + B2         rising uppercut (beats jump-ins)
      B2 in the air   dive kick (block it standing)
      HOLD B2, let go NOVA BLAST, an energy ball. When the POWER bar is
                      full it becomes a SUPER BLAST (can't be ducked)
    BUTTON1           menu

Score: damage you deal, a bonus for every round you win (health and time
left, extra for a PERFECT round) and a bonus for every opponent beaten.

Multiplayer (Versus): two players on two Pis, best of three rounds. The host
Pi runs the fight (Versus.update with both players' buttons) and sends a
snapshot of it every frame; the players' Pis only show it (Versus.apply).
"""
import math
import random

SW, SH = 540, 960                # playfield size (same as the screen)
FLOOR_Y = 800                    # where the fighters' feet are
WALL_L, WALL_R = 52, SW - 52     # the fighters' x (their middle) stays inside these

BODY_W = 54                      # hurt box
SPACE_W = 72                     # the fighters' middles never get closer than this
STAND_H = 180
CROUCH_H = 135
WALK_FWD = 235.0                 # px/s
WALK_BACK = 185.0
JUMP_V = 1020.0
JUMP_VX = 240.0
GRAVITY = 3000.0
PREJUMP = 0.07                   # tiny squat before a jump (UP + B2 in it = uppercut)
DIVE_VX, DIVE_VY = 470.0, 900.0
LIE_TIME = 0.65                  # lying on the floor after a knockdown
GETUP_TIME = 0.35

MAX_HP = 100
ROUND_TIME = 60
ROUNDS_TO_WIN = 2
MAX_ROUNDS = 5                   # draws replay the round; after this many you lose
CHARGE_TIME = 0.45               # hold B2 this long, then let go = blast
METER_MAX = 100.0
THREAT_RANGE = 230               # holding away shows the guard when an attack is this close

# projectiles: centre height above the floor and radius. A normal blast flies
# over a crouching fighter (CROUCH_H), a super blast does not.
BLAST_Y, BLAST_R, BLAST_V, BLAST_DMG = 160, 22, 560.0, 9
SUPER_Y, SUPER_R, SUPER_V, SUPER_DMG = 150, 36, 500.0, 24

# The moves. s / a / r = startup, active and recovery time (s). box = the
# hit box: x0..x1 in front of the fighter, y0..y1 above the feet. stun = how
# long the one who is hit can't act, kb = push back (px/s), kind = mid / low
# (block crouching) / over (block standing), down = knocks down,
# chain = the move B2 turns this one into (a combo).
MOVES = {
    "jab":   dict(s=0.06, a=0.07, r=0.13, dmg=5, box=(24, 112, 120, 172), stun=0.30, kb=140,
                  kind="mid", down=False, chain="jab2"),
    "jab2":  dict(s=0.06, a=0.07, r=0.15, dmg=6, box=(24, 114, 112, 168), stun=0.32, kb=160,
                  kind="mid", down=False, chain="kick"),
    "kick":  dict(s=0.10, a=0.09, r=0.28, dmg=10, box=(30, 104, 70, 132), stun=0.42, kb=430,
                  kind="mid", down=False, chain=None),
    "sweep": dict(s=0.12, a=0.10, r=0.34, dmg=9, box=(20, 108, 0, 36), stun=0.40, kb=160,
                  kind="low", down=True, chain=None),
    "upper": dict(s=0.05, a=0.16, r=0.40, dmg=12, box=(4, 72, 110, 250), stun=0.50, kb=180,
                  kind="mid", down=True, lift=820, chain=None),
    "dive":  dict(s=0.04, a=9.0, r=0.0, dmg=9, box=(8, 64, -12, 46), stun=0.40, kb=220,
                  kind="over", down=False, chain=None),
    "land":  dict(s=0.0, a=0.0, r=0.20, dmg=0, box=None, chain=None),
    "blast": dict(s=0.16, a=0.0, r=0.30, dmg=0, box=None, chain=None),
}
BLAST_MOVE = dict(dmg=BLAST_DMG, stun=0.45, kb=260, kind="mid", down=False)
SUPER_MOVE = dict(dmg=SUPER_DMG, stun=0.60, kb=380, kind="mid", down=True, lift=700)

# Looks: suit = trousers, top = tunic, robe = the long robe over it, skin,
# glove, band = belt, blade = laser sword colour, hair colour and style
# (spikes, mohawk, bun, long, bald, hood)
PLAYER = dict(name="BLAZE", suit=(120, 85, 55), top=(225, 205, 165), robe=(105, 72, 45),
              skin=(236, 184, 140), glove=(70, 50, 35), band=(60, 40, 25), blade=(80, 160, 255),
              hair=(70, 45, 30), style="spikes")

# The computer opponents, in order. d = how good it is (0..1), speed and
# power multiply walking speed and damage, hp = health.
LADDER = [
    dict(name="VOLT", suit=(70, 72, 84), top=(170, 175, 190), robe=None, skin=(225, 170, 125),
         glove=(40, 40, 50), band=(255, 215, 40), blade=(255, 215, 40), hair=(250, 240, 120),
         style="mohawk",
         d=0.10, speed=0.95, power=0.85, hp=95, sky=((10, 6, 40), (110, 40, 150))),
    dict(name="KAIJA", suit=(40, 90, 80), top=(200, 215, 200), robe=(30, 70, 62),
         skin=(190, 135, 95), glove=(30, 40, 40), band=(150, 120, 60), blade=(90, 255, 120),
         hair=(20, 15, 20), style="bun",
         d=0.25, speed=1.05, power=0.9, hp=100, sky=((4, 20, 40), (30, 120, 130))),
    dict(name="RONIN-X", suit=(45, 45, 60), top=(130, 30, 45), robe=(55, 50, 70),
         skin=(215, 160, 120), glove=(30, 30, 40), band=(200, 170, 80), blade=(255, 140, 40),
         hair=(15, 15, 25), style="long",
         d=0.40, speed=1.0, power=1.0, hp=100, sky=((30, 6, 20), (170, 50, 60))),
    dict(name="MAMBA", suit=(90, 60, 140), top=(235, 225, 200), robe=(70, 45, 110),
         skin=(140, 95, 65), glove=(40, 30, 50), band=(220, 190, 90), blade=(190, 90, 255),
         hair=(30, 20, 20), style="spikes",
         d=0.55, speed=1.18, power=0.95, hp=95, sky=((8, 4, 30), (70, 30, 140))),
    dict(name="GRANITE", suit=(95, 85, 75), top=(150, 140, 125), robe=(80, 70, 60),
         skin=(205, 150, 110), glove=(60, 50, 40), band=(40, 35, 30), blade=(240, 240, 255),
         hair=(90, 80, 70), style="bald",
         d=0.65, speed=0.85, power=1.3, hp=120, sky=((20, 12, 8), (150, 80, 40))),
    dict(name="NOVA QUEEN", suit=(30, 30, 38), top=(45, 45, 55), robe=(20, 20, 26),
         skin=(240, 195, 160), glove=(20, 20, 26), band=(200, 40, 50), blade=(255, 40, 50),
         hair=(20, 20, 26), style="hood",
         d=0.85, speed=1.12, power=1.1, hp=115, sky=((5, 3, 22), (255, 70, 160))),
]


def _overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


class Fighter:
    def __init__(self, info, x, face):
        self.info = info
        self.name = info["name"]
        self.max_hp = info.get("hp", MAX_HP)
        self.speed = info.get("speed", 1.0)
        self.power = info.get("power", 1.0)
        self.meter = 0.0
        self.reset(x, face)

    def reset(self, x, face):
        self.x, self.y = float(x), float(FLOOR_Y)
        self.vx = self.vy = 0.0
        self.face = face
        self.hp = float(self.max_hp)
        self.state = "idle"
        self.st = 0.0                   # time in this state
        self.move = None
        self.move_hit = False
        self.fired = False
        self.queued = None
        self.charge = 0.0
        self.blast_req = 0.0
        self.stun = 0.0
        self.combo = 0                  # hits taken in a row (damage gets less)
        self.invuln = 0.0
        self.flash = 0.0
        self.crouch = False
        self.back_held = False
        self.walk_t = 0.0
        self.dove = False
        self.jump_dir = 0

    # -- helpers
    @property
    def ground(self):
        return self.y >= FLOOR_Y - 0.5

    def to(self, state):
        if self.state != state:
            self.state = state
            self.st = 0.0

    def free(self):
        return self.state in ("idle", "walk", "crouch", "guard")

    def start_move(self, name):
        self.state = "attack"
        self.st = 0.0
        self.move = name
        self.move_hit = False
        self.fired = False
        self.queued = None
        if name == "upper":
            self.invuln = max(self.invuln, 0.14)
            self.vx = 0.0
        elif name == "dive":
            self.vx = self.face * DIVE_VX
            self.vy = DIVE_VY
            self.dove = True
        elif name in ("jab", "jab2", "kick", "sweep", "blast"):
            self.vx = 0.0

    def is_crouching(self):
        if self.state in ("crouch", "prejump"):
            return True
        if self.state in ("guard", "block"):
            return self.crouch
        return self.state == "attack" and self.move in ("sweep", "land")

    def hurtbox(self):
        if self.state in ("down", "lying", "getup", "ko"):
            return None
        h = CROUCH_H if self.is_crouching() else STAND_H
        return (self.x - BODY_W / 2, self.y - h, BODY_W, h)

    def hitbox(self):
        if self.state != "attack" or self.move_hit:
            return None
        m = MOVES[self.move]
        if not m.get("box") or not m["s"] <= self.st < m["s"] + m["a"]:
            return None
        x0, x1, y0, y1 = m["box"]
        if self.face > 0:
            left, right = self.x + x0, self.x + x1
        else:
            left, right = self.x - x1, self.x - x0
        return (left, self.y - y1, right - left, y1 - y0)

    # -- input (only while the round is on)
    def control(self, held, presses, threat, dt, can_blast):
        fwd = "right" if self.face > 0 else "left"
        back = "left" if self.face > 0 else "right"
        if "button2" in held:
            self.charge += dt
        else:
            if self.charge >= CHARGE_TIME:
                self.blast_req = 0.3        # fires as soon as we're free
            self.charge = 0.0
        self.blast_req = max(0.0, self.blast_req - dt)

        for a in presses:
            if a == "up" and self.ground and self.free():
                self.to("prejump")
                self.jump_dir = 1 if fwd in held and back not in held else (
                    -1 if back in held and fwd not in held else 0)
            elif a == "button2":
                if self.state == "prejump" or (self.free() and self.ground and "up" in held):
                    self.start_move("upper")
                elif self.state == "jump" and not self.dove and self.y < FLOOR_Y - 40:
                    self.start_move("dive")
                elif self.free() and self.ground:
                    self.start_move("sweep" if "down" in held else "jab")
                elif self.state == "attack" and MOVES[self.move].get("chain"):
                    self.queued = MOVES[self.move]["chain"]

        self.back_held = back in held and fwd not in held
        if self.free() and self.ground:
            if self.blast_req > 0 and can_blast:
                self.blast_req = 0.0
                self.start_move("blast")
                return
            self.crouch = "down" in held
            if self.crouch:
                self.to("guard" if self.back_held and threat else "crouch")
                self.vx = 0.0
            elif self.back_held and threat:
                self.to("guard")
                self.vx = 0.0
            elif fwd in held and back not in held:
                self.to("walk")
                self.vx = self.face * WALK_FWD * self.speed
            elif self.back_held:
                self.to("walk")
                self.vx = -self.face * WALK_BACK * self.speed
            else:
                self.to("idle")
                self.vx = 0.0

    def no_input(self):
        """Between rounds: stand still (and let go of everything)."""
        self.charge = 0.0
        self.blast_req = 0.0
        self.back_held = False
        if self.free():
            self.to("idle")
            self.vx = 0.0

    # -- the body moving by itself (every frame)
    def update(self, dt, opp):
        self.st += dt
        self.invuln = max(0.0, self.invuln - dt)
        self.flash = max(0.0, self.flash - dt)
        s = self.state
        if s == "walk":
            self.walk_t += dt * abs(self.vx) / 40.0
        if self.ground and self.state in ("idle", "walk", "crouch", "guard"):
            self.face = 1 if opp.x >= self.x else -1

        if s == "prejump" and self.st >= PREJUMP:
            self.to("jump")
            self.vy = -JUMP_V
            self.vx = self.jump_dir * self.face * JUMP_VX * self.speed
            self.dove = False
        elif s == "attack":
            m = MOVES[self.move]
            if self.move == "dive":
                if self.ground and self.vy >= 0:       # (safety: a dive always ends on the floor)
                    self.y = FLOOR_Y
                    self.vy = 0.0
                    self.land()
            elif self.queued and self.st >= m["s"] + m["a"]:
                self.start_move(self.queued)
            elif self.st >= m["s"] + m["a"] + m["r"]:
                self.move = None
                self.to("crouch" if s == "attack" and m is MOVES["sweep"] else "idle")
                if not self.ground:
                    self.to("jump")
        elif s in ("hit", "block"):
            self.stun -= dt
            if self.stun <= 0 and self.ground:
                self.to("idle")
                self.combo = 0
        elif s == "lying" and self.st >= LIE_TIME:
            self.to("getup")
            self.invuln = GETUP_TIME + 0.15
        elif s == "getup" and self.st >= GETUP_TIME:
            self.to("idle")
            self.combo = 0

        # physics
        airborne = self.y < FLOOR_Y or self.vy < 0
        if airborne:
            if not (self.state == "attack" and self.move == "dive"):
                self.vy += GRAVITY * dt
            self.y += self.vy * dt
            if self.y >= FLOOR_Y:
                self.y = FLOOR_Y
                self.vy = 0.0
                self.land()
        if self.state not in ("walk", "jump", "prejump") and not (
                self.state == "attack" and self.move == "dive") and self.ground:
            self.vx *= math.exp(-9.0 * dt)
        self.x += self.vx * dt
        self.x = max(WALL_L, min(WALL_R, self.x))

    def land(self):
        s = self.state
        if s == "jump":
            self.to("idle")
            self.vx = 0.0
        elif s == "attack" and self.move == "dive":
            self.start_move("land")
            self.vx *= 0.3
        elif s == "attack":
            self.move = None
            self.to("idle")
        elif s == "down":
            self.to("lying")
        elif s == "hit":
            self.to("lying")              # hit in the air = knocked down


class Brain:
    """The computer player: looks at the fight and 'presses buttons'.
    d (0..1.25) = skill: how quick it reacts, how often it blocks, ..."""

    def __init__(self, d, rng):
        self.d = d
        self.rng = rng
        self.react = max(0.07, 0.36 - 0.26 * d)     # seconds before it reacts
        self.block_chance = min(0.92, 0.18 + 0.65 * d)
        self.anti_air = min(0.9, 0.12 + 0.7 * d)
        self.script = None
        self.t = 0.0
        self.issued = 0
        self.think_in = 0.8
        self.threat_t = None
        self.threat_go = False

    def run(self, steps, dur, interrupt=True):
        self.script = (steps, dur, interrupt)
        self.t = 0.0
        self.issued = 0

    def inputs(self, game, me, opp, dt):
        rng = self.rng
        d = self.d
        # react to danger: attacks, blasts and jump-ins
        threat = game.threat_kind(me)
        if threat and (self.script is None or self.script[2]):
            if self.threat_t is None:
                self.threat_t = 0.0
                chance = self.anti_air if threat == "air" else self.block_chance
                self.threat_go = rng.random() < chance
            self.threat_t += dt
            if self.threat_go and self.threat_t >= self.react:
                self.threat_go = False
                if threat == "air":
                    if abs(opp.x - me.x) < 170:
                        self.run([(0, (), ("up", "button2"))], 0.7, False)
                    else:
                        self.run([(0, ("back",), ())], 0.45, False)
                elif threat == "blast":
                    r = rng.random()
                    if r < 0.4:
                        self.run([(0, ("down",), ())], 0.5, False)       # duck it
                    elif r < 0.55 + 0.2 * d:
                        self.run([(0, ("fwd",), ("up",)), (0.35, ("fwd",), ("button2",))],
                                 0.9, False)                              # jump over it
                    else:
                        self.run([(0, ("back",), ())], 0.5, False)
                elif threat == "low":
                    self.run([(0, ("back", "down"), ())], 0.45, False)
                else:
                    self.run([(0, ("back",), ())], 0.4, False)
        elif not threat:
            self.threat_t = None

        if self.script is None:
            self.think_in -= dt
            if self.think_in <= 0:
                self.think(game, me, opp)
        held, presses = set(), []
        if self.script:
            steps, dur, _ = self.script
            self.t += dt
            hold = ()
            for i, (t, h, p) in enumerate(steps):
                if t <= self.t:
                    hold = h
                    if i >= self.issued:
                        presses.extend(p)
                        self.issued = i + 1
            held.update(hold)
            if self.t >= dur:
                self.script = None
                self.think_in = rng.uniform(0.05, 0.35) * (1.4 - d)
        fwd = "right" if me.face > 0 else "left"
        back = "left" if me.face > 0 else "right"
        swap = {"fwd": fwd, "back": back}
        held = {swap.get(a, a) for a in held}
        presses = [swap.get(a, a) for a in presses]
        return held, presses

    def think(self, game, me, opp):
        rng = self.rng
        d = self.d
        dist = abs(opp.x - me.x)
        can_blast = game.can_blast(me)
        r = rng.random()
        blast = [(0, ("button2",), ()), (0.5, (), ())]
        jump_in = [(0, ("fwd",), ("up",)),
                   (0.34, ("fwd",), ("button2",) if rng.random() < 0.45 + 0.4 * d else ())]
        if dist > 290:
            if can_blast and r < 0.22 + 0.3 * d:
                self.run(blast, 0.85)
            elif r < 0.7:
                self.run([(0, ("fwd",), ())], rng.uniform(0.3, 0.7))
            elif r < 0.82:
                self.run(jump_in, 0.9, False)
            else:
                self.run([(0, (), ())], rng.uniform(0.2, 0.5))
        elif dist > 125:
            if r < 0.45:
                self.run([(0, ("fwd",), ())], rng.uniform(0.15, 0.4))
            elif r < 0.6:
                self.run(jump_in, 0.9, False)
            elif r < 0.7 and can_blast:
                self.run(blast, 0.85)
            elif r < 0.8:
                self.run([(0, ("back",), ())], rng.uniform(0.2, 0.4))
            else:
                self.run([(0, ("back",), ())], 0.35)            # wait, ready to block
        else:
            if r < 0.34 + 0.24 * d:
                n = 3 if rng.random() < 0.3 + 0.6 * d else rng.choice((1, 2))
                steps = [(0.155 * i, (), ("button2",)) for i in range(n)]
                self.run(steps, 0.35 + 0.17 * n, False)
            elif r < 0.52:
                self.run([(0, ("down",), ()), (0.03, ("down",), ("button2",))], 0.65, False)
            elif r < 0.6:
                self.run([(0, (), ("up", "button2"))], 0.75, False)
            elif r < 0.78:
                self.run([(0, ("back",), ())], rng.uniform(0.2, 0.4))
            else:
                self.run([(0, ("back",), ())], 0.4)


MODES = ("CLASSIC", "SURVIVAL", "GLASS JAW")
SURVIVAL_HEAL = 0.35             # SURVIVAL: health back between opponents (part of max)
GLASS_POWER = 3.0                # GLASS JAW: every hit does this much more damage


class Brawl:
    """One run: the ladder of opponents, until you lose a match.
    SURVIVAL: one round per opponent and your health carries over.
    GLASS JAW: every hit does triple damage (for everybody)."""
    versus = False
    me = 0                               # which fighter is "you" (0 = left)
    mode = "CLASSIC"
    rounds_to_win = ROUNDS_TO_WIN
    carry_hp = None                      # SURVIVAL: health carried into the next opponent

    def __init__(self, seed=None, mode="CLASSIC"):
        self.rng = random.Random(seed)
        self.mode = mode if mode in MODES else "CLASSIC"
        self.rounds_to_win = 1 if self.mode == "SURVIVAL" else ROUNDS_TO_WIN
        self.carry_hp = None
        self.player = Fighter(PLAYER, 150, 1)
        if self.mode == "GLASS JAW":
            self.player.power *= GLASS_POWER
        self.score = 0
        self.wins = 0                    # opponents beaten
        self.stage = 1
        self.game_over = False
        self.effects = []                # [x, y, age, max_age, kind]
        self.popups = []                 # [text, age]
        self.shake = 0.0
        self.hitstop = 0.0
        self.pending = []                # presses during the hit stop
        self.bonus = []                  # (label, points) after a round
        self.player_combo = 0
        self.start_match()

    # -- flow
    def start_match(self):
        info = LADDER[(self.stage - 1) % len(LADDER)]
        self.loop = (self.stage - 1) // len(LADDER)
        d = min(1.25, info["d"] + 0.3 * self.loop)
        self.cpu = Fighter(info, 390, -1)
        self.cpu.power *= 1 + 0.1 * self.loop
        if self.mode == "GLASS JAW":
            self.cpu.power *= GLASS_POWER
        self.carry_hp = None
        if self.mode == "SURVIVAL" and self.stage > 1:
            p = self.player
            self.carry_hp = min(float(p.max_hp), p.hp + SURVIVAL_HEAL * p.max_hp)
        self.stage_info = info
        self.brain = Brain(d, self.rng)
        self.p_rounds = self.c_rounds = 0
        self.round_no = 0
        self.player.meter = 0.0
        self.start_round()
        self.phase = "versus"
        self.phase_t = 0.0

    def start_round(self):
        self.round_no += 1
        self.player.reset(150, 1)
        self.cpu.reset(390, -1)
        if self.carry_hp:
            self.player.hp = self.carry_hp
        if self.brain:
            self.brain.script = None
            self.brain.think_in = 0.6
        self.projs = []
        self.timer = float(ROUND_TIME)
        self.phase = "intro"
        self.phase_t = 0.0
        self.result = None
        self.bonus = []

    @property
    def final_round(self):
        return (self.rounds_to_win > 1 and self.p_rounds == self.rounds_to_win - 1
                and self.c_rounds == self.rounds_to_win - 1)

    def banner(self):
        """(big text, small text) to show in the middle, or None."""
        p, t = self.phase, self.phase_t
        if p == "intro":
            if t < 1.05:
                return ("FINAL ROUND" if self.final_round else "ROUND %d" % self.round_no, None)
            return ("FIGHT!", None)
        if p == "fight" and t < 0.45:
            return ("FIGHT!", None)
        if p == "ko":
            if self.result == "draw":
                return ("DRAW", "TIME UP" if self.ko_kind == "TIME" else None)
            big = "K.O.!" if self.ko_kind == "KO" else "TIME!"
            if t < 1.1:
                return (big, None)
            if self.result == "p":
                return ("PERFECT!" if any(b[0] == "PERFECT" for b in self.bonus)
                        else "YOU WIN", None)
            return ("%s WINS" % self.cpu.name, None)
        if p == "matchwin":
            if self.stage % len(LADDER) == 0:
                return ("CHAMPION!", "THE LADDER STARTS AGAIN - HARDER!")
            return ("VICTORY!", "NEXT: %s" % LADDER[self.stage % len(LADDER)]["name"])
        if p == "lost":
            return ("DEFEATED", None)
        return None

    # -- what the brain and the guard pose look at
    def opponent(self, f):
        return self.cpu if f is self.player else self.player

    def can_blast(self, f):
        return not any(pr["owner"] is f for pr in self.projs)

    def threat_kind(self, f):
        """What's coming at f: 'blast', 'air', 'low', 'mid' or None."""
        o = self.opponent(f)
        for pr in self.projs:
            if pr["owner"] is o and (pr["x"] - f.x) * pr["vx"] < 0 and abs(pr["x"] - f.x) < 330:
                return "blast"
        dist = abs(o.x - f.x)
        if o.state in ("jump",) or (o.state == "attack" and o.move == "dive"):
            if dist < 260 and (o.x - f.x) * o.vx <= 10 or dist < 150:
                return "air"
        if o.state == "attack" and o.move not in ("land", "blast") and dist < THREAT_RANGE:
            return "low" if o.move == "sweep" else "mid"
        return None

    # -- the frame
    def update(self, dt_ms, held=(), presses=()):
        dt = min(dt_ms, 50) / 1000.0
        self.shake = max(0.0, self.shake - dt * 30)
        for e in self.effects:
            e[2] += dt
        self.effects = [e for e in self.effects if e[2] < e[3]]
        for pp in self.popups:
            pp[1] += dt
        self.popups = [pp for pp in self.popups if pp[1] < 1.2]
        if self.hitstop > 0:
            self.hitstop -= dt
            self.pending.extend(presses)
            return
        presses = self.pending + list(presses)
        self.pending = []
        self.phase_t += dt
        p, c = self.player, self.cpu
        ph = self.phase

        if ph == "versus":
            if self.phase_t >= 2.4:
                self.phase, self.phase_t = "intro", 0.0
            return
        if ph == "intro":
            p.no_input()
            c.no_input()
            if self.phase_t >= 1.6:
                self.phase, self.phase_t = "fight", 0.0
        elif ph == "fight":
            self.timer = max(0.0, self.timer - dt)
            p.control(set(held), presses, self.threat_kind(p) is not None, dt, self.can_blast(p))
            ch, cp = self.cpu_inputs(dt)
            c.control(ch, cp, self.threat_kind(c) is not None, dt, self.can_blast(c))
        else:
            p.no_input()
            c.no_input()
            if ph == "ko" and self.phase_t < 0.9:
                dt *= 0.35                                    # slow motion K.O.

        p.update(dt, c)
        c.update(dt, p)
        self.push_apart()
        for f in (p, c):
            if f.state == "attack" and f.move == "blast" and not f.fired and f.st >= MOVES["blast"]["s"]:
                f.fired = True
                self.fire(f)
        if ph == "fight":
            self.check_hits()
        self.move_projectiles(dt, ph == "fight")
        if ph == "fight":
            self.check_end()
        elif ph == "ko":
            if self.phase_t >= 1.1 and self.result in ("p", "c"):
                winner = p if self.result == "p" else c
                if winner.free() and winner.ground:
                    winner.to("win")
            if self.phase_t >= 3.0:
                self.finish_round()
        elif ph == "matchover":                               # versus only
            if self.phase_t >= 3.0:
                self.game_over = True
                self.phase_t = -999.0
        elif ph in ("matchwin", "lost"):
            if self.phase_t >= 3.0:
                if ph == "lost":
                    self.game_over = True
                    self.phase_t = -999.0
                else:
                    self.stage += 1
                    self.wins += 1
                    self.start_match()

    def cpu_inputs(self, dt):
        return self.brain.inputs(self, self.cpu, self.player, dt)

    def push_apart(self):
        p, c = self.player, self.cpu
        dx = c.x - p.x
        gap = SPACE_W - abs(dx)
        if gap > 0:
            s = 1 if dx >= 0 else -1
            if dx == 0:
                s = 1 if p.x < SW / 2 else -1
            p.x -= s * gap / 2
            c.x += s * gap / 2
            for f in (p, c):
                f.x = max(WALL_L, min(WALL_R, f.x))
            if abs(c.x - p.x) < SPACE_W - 1:               # one is at the wall
                if p.x <= WALL_L + 1 or p.x >= WALL_R - 1:
                    c.x = p.x + s * SPACE_W
                else:
                    p.x = c.x - s * SPACE_W

    def check_hits(self):
        p, c = self.player, self.cpu
        hits = []
        for att, dfn in ((p, c), (c, p)):
            box = att.hitbox()
            hurt = dfn.hurtbox()
            if box and hurt and dfn.invuln <= 0 and _overlap(box, hurt):
                hits.append((att, dfn, box, hurt, MOVES[att.move]))
        for att, dfn, box, hurt, m in hits:         # both at once = a trade
            att.move_hit = True
            cx = (max(box[0], hurt[0]) + min(box[0] + box[2], hurt[0] + hurt[2])) / 2
            cy = (max(box[1], hurt[1]) + min(box[1] + box[3], hurt[1] + hurt[3])) / 2
            self.resolve(att, dfn, m, att.x, cx, cy)

    def resolve(self, att, dfn, m, src_x, cx, cy, proj=False):
        dirn = 1 if dfn.x > src_x else -1 if dfn.x < src_x else -dfn.face
        kind = m["kind"]
        blocking = (dfn.ground and dfn.back_held and dfn.face == -dirn
                    and dfn.state in ("idle", "walk", "crouch", "guard", "block")
                    and not (kind == "low" and not dfn.crouch)
                    and not (kind == "over" and dfn.crouch))
        dmg = m["dmg"] * att.power
        if blocking:
            if proj:
                dfn.hp = max(1.0, dfn.hp - dmg * 0.15)       # chip damage
            dfn.to("block")
            dfn.st = 0.0
            dfn.stun = m["stun"] * 0.65
            dfn.vx = dirn * m["kb"] * 0.8
            att.meter = min(METER_MAX, att.meter + 4)
            dfn.meter = min(METER_MAX, dfn.meter + 6)
            if not proj and (dfn.x <= WALL_L + 2 or dfn.x >= WALL_R - 2):
                att.vx = -dirn * m["kb"] * 0.6
            self.effects.append([cx, cy, 0.0, 0.25, "block"])
            self.hitstop = 0.04
            return
        dmg *= max(0.4, 1.0 - 0.12 * dfn.combo)
        dfn.hp -= dmg
        dfn.combo += 1
        dfn.flash = 0.12
        dfn.move = None
        dfn.queued = None
        att.meter = min(METER_MAX, att.meter + 8)
        dfn.meter = min(METER_MAX, dfn.meter + 5)
        heavy = m.get("down") or m["dmg"] >= 10
        if att is self.player and not self.versus:
            self.score += int(round(dmg * 10))
        if att is self.player or self.versus:
            if dfn.combo >= 2:
                self.popups = [pp for pp in self.popups if not pp[0].endswith("COMBO!")]
                self.popups.append(["%d HIT COMBO!" % dfn.combo, 0.0])
        if dfn.hp <= 0:
            dfn.hp = 0.0
            dfn.to("ko")
            dfn.vy = -640.0
            dfn.vx = dirn * 320.0
            heavy = True
        elif m.get("down") or not dfn.ground:
            dfn.to("down")
            dfn.vy = -m.get("lift", 520)
            dfn.vx = dirn * max(m["kb"], 220)
        else:
            dfn.to("hit")
            dfn.st = 0.0
            dfn.stun = m["stun"]
            dfn.vx = dirn * m["kb"]
            if not proj and (dfn.x <= WALL_L + 2 or dfn.x >= WALL_R - 2):
                att.vx = -dirn * m["kb"] * 0.6          # pushed off the wall instead
        self.effects.append([cx, cy, 0.0, 0.32 if heavy else 0.22, "heavy" if heavy else "hit"])
        self.hitstop = 0.1 if heavy else 0.06
        self.shake = max(self.shake, 9.0 if heavy else 4.0)

    def fire(self, f):
        sup = f.meter >= METER_MAX
        if sup:
            f.meter = 0.0
        self.projs.append({"x": f.x + f.face * 62, "y": f.y - (SUPER_Y if sup else BLAST_Y),
                           "vx": f.face * (SUPER_V if sup else BLAST_V), "owner": f,
                           "super": sup, "r": SUPER_R if sup else BLAST_R, "age": 0.0})

    def move_projectiles(self, dt, live):
        keep = []
        for pr in self.projs:
            pr["age"] += dt
            pr["x"] += pr["vx"] * dt
            if pr["x"] < -60 or pr["x"] > SW + 60:
                continue
            if not live:
                keep.append(pr)
                continue
            dfn = self.opponent(pr["owner"])
            hurt = dfn.hurtbox()
            r = pr["r"]
            box = (pr["x"] - r, pr["y"] - r * 0.8, r * 2, r * 1.6)
            if hurt and dfn.invuln <= 0 and _overlap(box, hurt):
                m = SUPER_MOVE if pr["super"] else BLAST_MOVE
                self.resolve(pr["owner"], dfn, m, pr["x"] - pr["vx"], pr["x"], pr["y"], proj=True)
                continue
            keep.append(pr)
        # two blasts meeting cancel out (a super blast eats a normal one)
        if live and len(keep) >= 2:
            a, b = keep[0], keep[1]
            if a["owner"] is not b["owner"] and abs(a["x"] - b["x"]) < a["r"] + b["r"]:
                self.effects.append([(a["x"] + b["x"]) / 2, (a["y"] + b["y"]) / 2, 0.0, 0.3, "heavy"])
                if a["super"] != b["super"]:
                    keep = [a if a["super"] else b]
                else:
                    keep = []
        self.projs = keep

    def check_end(self):
        p, c = self.player, self.cpu
        if p.hp > 0 and c.hp > 0 and self.timer > 0:
            return
        if p.hp <= 0 and c.hp <= 0:
            self.result = "draw"
        elif c.hp <= 0:
            self.result = "p"
        elif p.hp <= 0:
            self.result = "c"
        else:
            fp, fc = p.hp / p.max_hp, c.hp / c.max_hp
            self.result = "p" if fp > fc + 1e-6 else "c" if fc > fp + 1e-6 else "draw"
        self.ko_kind = "KO" if (p.hp <= 0 or c.hp <= 0) else "TIME"
        self.phase, self.phase_t = "ko", 0.0
        self.projs = []
        self.bonus = []
        if self.result == "p" and not self.versus:
            self.bonus.append(("ROUND", 1000))
            self.bonus.append(("HEALTH", int(p.hp) * 20))
            self.bonus.append(("TIME", int(self.timer) * 10))
            if p.hp >= p.max_hp:
                self.bonus.append(("PERFECT", 5000))
            self.score += sum(b[1] for b in self.bonus)
        if self.ko_kind == "KO":
            self.shake = 14.0
            self.hitstop = 0.25

    def finish_round(self):
        if self.result == "p":
            self.p_rounds += 1
        elif self.result == "c":
            self.c_rounds += 1
        if self.p_rounds >= self.rounds_to_win:
            self.phase, self.phase_t = "matchwin", 0.0
            self.bonus = [("OPPONENT BEATEN", 2000 * self.stage)]
            self.score += 2000 * self.stage
            self.player.to("win")
        elif self.c_rounds >= self.rounds_to_win or self.round_no >= MAX_ROUNDS:
            self.phase, self.phase_t = "lost", 0.0
            self.bonus = []
        else:
            self.start_round()


# ----------------------------------------------------------------------------
# Multiplayer: two players, best of three
# ----------------------------------------------------------------------------
P2_LOOK = dict(LADDER[3], speed=1.0, power=1.0, hp=MAX_HP)
ACTIONS = ("up", "down", "left", "right", "button2")
STATES = ("idle", "walk", "crouch", "guard", "prejump", "jump", "attack", "hit", "block",
          "down", "lying", "getup", "ko", "win")
EFFECTS = ("hit", "heavy", "block")


class Versus(Brawl):
    """Player 1 (left, self.player) against player 2 (right, self.cpu).
    me = 0 / 1 = which one is on this screen, None = the host watching."""
    versus = True

    def __init__(self, seed=None, names=("P1", "P2"), me=None, mode="CLASSIC"):
        self.rng = random.Random(seed)
        self.me = me
        # SURVIVAL online = one round decides it; GLASS JAW = triple damage
        self.mode = mode if mode in MODES else "CLASSIC"
        self.rounds_to_win = 1 if self.mode == "SURVIVAL" else ROUNDS_TO_WIN
        self.player = Fighter(dict(PLAYER, name=str(names[0])[:12]), 150, 1)
        self.cpu = Fighter(dict(P2_LOOK, name=str(names[1])[:12]), 390, -1)
        if self.mode == "GLASS JAW":
            self.player.power *= GLASS_POWER
            self.cpu.power *= GLASS_POWER
        self.brain = None
        self.stage_info = LADDER[(seed or 0) % len(LADDER)]
        self.score = 0
        self.wins = 0
        self.stage = 1
        self.loop = 0
        self.game_over = False
        self.effects = []
        self.popups = []
        self.shake = 0.0
        self.hitstop = 0.0
        self.pending = []
        self.pending2 = []
        self.held2 = set()
        self.bonus = []
        self.ko_kind = None
        self.p_rounds = self.c_rounds = 0
        self.round_no = 0
        self.start_round()
        self.phase = "versus"
        self.phase_t = 0.0

    # -- host side
    def update(self, dt_ms, in1=((), ()), in2=((), ())):
        """in1 / in2 = (held buttons, new presses) of player 1 / player 2."""
        if self.phase != "fight":
            self.pending2 = []
        self.held2 = set(in2[0])
        self.pending2.extend(in2[1])
        Brawl.update(self, dt_ms, in1[0], in1[1])

    def cpu_inputs(self, dt):
        presses, self.pending2 = self.pending2, []
        return self.held2, presses

    def finish_round(self):
        if self.result == "p":
            self.p_rounds += 1
        elif self.result == "c":
            self.c_rounds += 1
        if (self.p_rounds >= self.rounds_to_win or self.c_rounds >= self.rounds_to_win
                or self.round_no >= MAX_ROUNDS):
            self.phase, self.phase_t = "matchover", 0.0
            if self.p_rounds != self.c_rounds:
                winner = self.player if self.p_rounds > self.c_rounds else self.cpu
                winner.to("win")
        else:
            self.start_round()

    def match_winner(self):
        """0 = player 1, 1 = player 2, None = draw."""
        if self.p_rounds == self.c_rounds:
            return None
        return 0 if self.p_rounds > self.c_rounds else 1

    # -- text in the middle of the screen
    def win_text(self, side):
        if self.me is None:
            return "%s WINS" % (self.player if side == 0 else self.cpu).name
        return "YOU WIN" if side == self.me else "YOU LOSE"

    def banner(self):
        if self.phase == "ko" and self.result in ("p", "c") and self.phase_t >= 1.1:
            return (self.win_text(0 if self.result == "p" else 1), None)
        if self.phase == "matchover":
            w = self.match_winner()
            if w is None:
                return ("DRAW", "MATCH OVER")
            return (self.win_text(w), "MATCH OVER  %d - %d" % (self.p_rounds, self.c_rounds))
        return Brawl.banner(self)

    # -- network: the host sends snapshot(), the players apply() it
    def snapshot(self):
        def fs(f):
            return [round(f.x, 1), round(f.y, 1), f.face, round(f.hp, 1), f.state,
                    round(f.st, 3), f.move, round(f.meter, 1), round(f.flash, 2),
                    f.crouch, round(f.walk_t, 2), round(f.charge, 2)]
        return {
            "ph": self.phase, "pt": round(self.phase_t, 3), "tm": round(self.timer, 2),
            "rn": self.round_no, "r": [self.p_rounds, self.c_rounds],
            "res": self.result, "ko": self.ko_kind,
            "f": [fs(self.player), fs(self.cpu)],
            "pr": [[round(p["x"], 1), round(p["y"], 1), p["vx"], p["super"],
                    0 if p["owner"] is self.player else 1, round(p["age"], 2)]
                   for p in self.projs],
            "fx": [[round(e[0]), round(e[1]), round(e[2], 3), e[3], e[4]] for e in self.effects],
            "pop": [[t, round(a, 2)] for t, a in self.popups],
            "sh": round(self.shake, 1),
        }

    def apply(self, snap):
        """Show the host's fight (ignores anything broken)."""
        try:
            fighters = []
            for f, d in zip((self.player, self.cpu), snap["f"]):
                state = str(d[4]) if d[4] in STATES else "idle"
                move = d[6] if d[6] in MOVES else None
                if state == "attack" and move is None:
                    state = "idle"
                fighters.append((f, float(d[0]), float(d[1]), 1 if d[2] >= 0 else -1,
                                 max(0.0, float(d[3])), state, float(d[5]), move,
                                 float(d[7]), float(d[8]), bool(d[9]), float(d[10]), float(d[11])))
            projs = []
            for x, y, vx, sup, owner, age in snap.get("pr", [])[:4]:
                sup = bool(sup)
                projs.append({"x": float(x), "y": float(y), "vx": float(vx), "super": sup,
                              "owner": self.player if owner == 0 else self.cpu,
                              "r": SUPER_R if sup else BLAST_R, "age": float(age)})
            effects = [[float(x), float(y), float(a), float(m), k]
                       for x, y, a, m, k in snap.get("fx", [])[:12] if k in EFFECTS]
            popups = [[str(t)[:24], float(a)] for t, a in snap.get("pop", [])[:3]]
            phase = str(snap["ph"])
            phase_t, timer = float(snap["pt"]), float(snap["tm"])
            rn = int(snap["rn"])
            pr, cr = int(snap["r"][0]), int(snap["r"][1])
            shake = float(snap.get("sh", 0))
        except (KeyError, TypeError, ValueError, IndexError):
            return
        for (f, x, y, face, hp, state, st, move, meter, flash, crouch, walk_t, charge) in fighters:
            f.x, f.y, f.face, f.hp, f.state, f.st, f.move = x, y, face, hp, state, st, move
            f.meter, f.flash, f.crouch, f.walk_t, f.charge = meter, flash, crouch, walk_t, charge
        self.projs, self.effects, self.popups = projs, effects, popups
        self.phase, self.phase_t, self.timer = phase, phase_t, timer
        self.round_no, self.p_rounds, self.c_rounds = rn, pr, cr
        self.result = snap.get("res") if snap.get("res") in ("p", "c", "draw") else None
        self.ko_kind = snap.get("ko") if snap.get("ko") in ("KO", "TIME") else None
        self.shake = shake
