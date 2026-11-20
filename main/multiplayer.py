"""
LAN multiplayer for Pi Tetris.

How it works
------------
* The HOST Pi is a spectator: it never plays. It broadcasts a small UDP
  "beacon" once per second so other Pis can find it, and it accepts TCP
  connections from the PLAYER Pis.
* Players send their board to the host ~10 times per second, so the host can
  show everybody's screen. When a player clears lines they tell the host, and
  the host picks a random OTHER living player (never the host, never the
  clearer) and sends them a garbage line with one hole at a random spot.
* Sky Hopper (platformer): everybody climbs the same world. The host sends
  every player's position to all players ~15 times per second ("ghosts"), so
  each Pi can show the others as ghosts and pull its screen up to the leader.
* Saber Brawl (fighter): exactly two players. The HOST runs the fight itself
  (fighter.Versus): the players send their buttons ("in") the moment they
  change, the host sends a snapshot of the fight ("fs") every frame and the
  players just show it. With PLAY WITHOUT HOST one of the two Pis is the host.
* Glowbug (light race): the same way, with up to 4 players in one maze.
* Pulsar (paddle game): the same way, 2 players, first to 7 points.
* Game modes: the host picks one in its lobby (set_mode). It is in the
  roster ("gm") so the players see it before the start, and in the start
  message, so every Pi builds its round in that mode.
* Messages are JSON, one per line, over TCP.
"""
import json
import queue
import random
import socket
import threading
import time
import uuid

DISCOVERY_PORT = 47800
GAME_ID = "pi-tetris"
PROTOCOL = 1
MAX_PLAYERS = 8
COUNTDOWN = 3.0
SILENCE_TIMEOUT = 10.0
COLS, ROWS = 10, 20
BOARD_LEN = COLS * ROWS
GAME_KINDS = ("tetris", "shooter", "platformer", "fighter", "glowbug", "pulsar")
SIM_GAMES = ("fighter", "glowbug", "pulsar")      # games the host runs itself
FIGHT_ACTIONS = ("up", "down", "left", "right", "button2")
GHOST_RATE = 1 / 15.0             # platformer: seconds between position updates
ENEMY_KINDS = ("drone", "fighter", "tank")


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def clean_name(name):
    name = "".join(ch for ch in str(name) if 32 <= ord(ch) < 127).strip()
    return (name or "PLAYER")[:12]


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ----------------------------------------------------------------------------
# One TCP connection with a reader thread (JSON lines)
# ----------------------------------------------------------------------------
class _Conn:
    def __init__(self, sock, on_msg, on_close, autostart=True):
        self.sock = sock
        self.on_msg = on_msg
        self.on_close = on_close
        self.send_lock = threading.Lock()
        self.closed = False
        self.last_seen = time.monotonic()
        sock.settimeout(2.0)
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        if autostart:
            self.start()

    def start(self):
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        buf = b""
        try:
            while not self.closed:
                try:
                    chunk = self.sock.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buf += chunk
                if len(buf) > 262144:
                    break
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except ValueError:
                        continue
                    if isinstance(msg, dict):
                        self.last_seen = time.monotonic()
                        self.on_msg(msg)
        except OSError:
            pass
        finally:
            self.close()

    def send(self, obj):
        if self.closed:
            return False
        data = (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            with self.send_lock:
                self.sock.sendall(data)
            return True
        except OSError:
            self.close()
            return False

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
        self.on_close()


# ----------------------------------------------------------------------------
# Discovery: beacon (host) and finder (players)
# ----------------------------------------------------------------------------
class Beacon(threading.Thread):
    def __init__(self, info_fn):
        super().__init__(daemon=True)
        self.info_fn = info_fn
        self.stop_event = threading.Event()

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            while not self.stop_event.is_set():
                info = dict(self.info_fn())
                info["game"] = GAME_ID
                info["proto"] = PROTOCOL
                data = json.dumps(info).encode("utf-8")
                targets = ["255.255.255.255"]
                ip = local_ip()
                if ip.count(".") == 3 and not ip.startswith("127."):
                    targets.append(ip.rsplit(".", 1)[0] + ".255")
                for target in targets:
                    try:
                        sock.sendto(data, (target, DISCOVERY_PORT))
                    except OSError:
                        pass
                self.stop_event.wait(1.0)
        finally:
            sock.close()


class Finder(threading.Thread):
    """Listens for host beacons and keeps a list of games found."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.hosts = {}
        self.error = None

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            sock.bind(("", DISCOVERY_PORT))
            sock.settimeout(0.5)
        except OSError as exc:
            self.error = str(exc)
            sock.close()
            return
        try:
            while not self.stop_event.is_set():
                try:
                    data, addr = sock.recvfrom(2048)
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    info = json.loads(data.decode("utf-8"))
                    if info.get("game") != GAME_ID or info.get("proto") != PROTOCOL:
                        continue
                    entry = {
                        "id": str(info["id"]),
                        "name": clean_name(info.get("name", "HOST")),
                        "ip": addr[0],
                        "port": int(info["port"]),
                        "players": _int(info.get("players")),
                        "phase": str(info.get("phase", "lobby")),
                        "mode": str(info.get("mode", "tetris")),
                        "seen": time.monotonic(),
                    }
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
                with self.lock:
                    self.hosts[entry["id"]] = entry
        finally:
            sock.close()

    def get_hosts(self):
        now = time.monotonic()
        with self.lock:
            for key in [k for k, h in self.hosts.items() if now - h["seen"] > 4.0]:
                del self.hosts[key]
            return sorted((dict(h) for h in self.hosts.values()),
                          key=lambda h: h["name"].lower())

    def stop(self):
        self.stop_event.set()


# ----------------------------------------------------------------------------
# Host session (spectator + referee)
# ----------------------------------------------------------------------------
class HostSession:
    def __init__(self, name, game="tetris"):
        self.game = game if game in GAME_KINDS else "tetris"
        self.name = clean_name(name)
        self.id = uuid.uuid4().hex[:8]
        self.events = queue.Queue()
        self.players = {}          # cid -> dict
        self.conns = {}            # cid -> _Conn
        self.phase = "lobby"       # lobby | playing | results
        self.ranking = []
        self.death_order = []
        self.started_with = 0
        self.level = 1
        self.t_go = 0.0
        self._next_cid = 1
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._last_roster = 0.0
        self._last_ghosts = 0.0
        self.seed = 1
        self.max_players = {"fighter": 2, "glowbug": 4, "pulsar": 2}.get(self.game, MAX_PLAYERS)
        self.fight = None          # the game this host runs (fighter.Versus / glowbug.GlowRace)
        self.fight_cids = []       # the players in it, in order
        self._last_tick = 0.0
        self.game_mode = "CLASSIC"     # picked by the host in the lobby

        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("", 0))
        self.srv.listen(MAX_PLAYERS)
        self.srv.settimeout(0.5)
        self.port = self.srv.getsockname()[1]
        self.ip = local_ip()

        threading.Thread(target=self._accept_loop, daemon=True).start()
        self.beacon = Beacon(self._beacon_info)
        self.beacon.start()

    # -- background threads
    def _beacon_info(self):
        return {"id": self.id, "name": self.name, "port": self.port,
                "players": len(self.players), "phase": self.phase,
                "mode": self.game, "gm": self.game_mode}

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                sock, _addr = self.srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                cid = self._next_cid
                self._next_cid += 1
                full = len(self.conns) >= self.max_players or self.phase == "playing"
            if full:
                try:
                    sock.sendall(b'{"t":"full"}\n')
                except OSError:
                    pass
                sock.close()
                continue
            conn = _Conn(sock,
                         lambda m, c=cid: self.events.put(("msg", c, m)),
                         lambda c=cid: self.events.put(("close", c)),
                         autostart=False)
            with self._lock:
                self.conns[cid] = conn
            conn.start()

    # -- helpers
    def _unique_name(self, base):
        taken = {p["name"] for p in self.players.values()}
        name, i = base, 2
        while name in taken:
            name = "%s %d" % (base[:10], i)
            i += 1
        return name

    def _new_player(self, name):
        return {"name": self._unique_name(name), "alive": True, "gone": False,
                "score": 0, "lines": 0, "level": 1, "board": None,
                "hit": 0.0, "sent": 0.0, "last_target": None, "bag": [],
                "held": set(), "presses": []}

    def _broadcast(self, obj):
        for conn in list(self.conns.values()):
            conn.send(obj)

    def _send_roster(self):
        self._broadcast({
            "t": "roster", "phase": self.phase, "gm": self.game_mode,
            "players": [{"cid": c, "name": p["name"], "alive": p["alive"],
                         "score": p["score"]} for c, p in self.players.items()],
        })

    def _update_stats(self, p, msg):
        board = msg.get("b")
        if self.game == "tetris":
            if isinstance(board, str) and len(board) == BOARD_LEN:
                p["board"] = board
        elif isinstance(board, dict):
            p["board"] = board
        p["score"] = _int(msg.get("s"), p["score"])
        p["lines"] = _int(msg.get("l"), p["lines"])
        p["level"] = _int(msg.get("v"), p["level"])

    def _pick_target(self, sender):
        """A random living player that is not the sender (and not the host).

        Targets are dealt from a shuffled "bag": everybody gets hit once, in a
        random order, before anybody is hit a second time. So it is random,
        but one unlucky player can never be the victim over and over."""
        eligible = [c for c, p in self.players.items()
                    if p["alive"] and c != sender and c in self.conns]
        if not eligible:
            return None
        me = self.players[sender]
        bag = [c for c in me.get("bag", []) if c in eligible]
        if not bag:
            bag = eligible[:]
            random.shuffle(bag)
        target = bag.pop(0)
        me["bag"] = bag
        me["last_target"] = target
        return target

    def _send_garbage(self, sender, now):
        target = self._pick_target(sender)
        if target is None:
            return
        hole = random.randrange(COLS)
        self.conns[target].send({"t": "garbage", "hole": hole,
                                 "from": self.players[sender]["name"]})
        self.players[target]["hit"] = now
        self.players[sender]["sent"] = now

    def _send_enemy(self, sender, kind, fx, now):
        """Shooter: an enemy killed by `sender` appears for another player."""
        target = self._pick_target(sender)
        if target is None:
            return
        self.conns[target].send({"t": "enemy", "k": kind, "fx": fx,
                                 "from": self.players[sender]["name"]})
        self.players[target]["hit"] = now
        self.players[sender]["sent"] = now

    # -- events (call every frame from the main thread)
    def poll(self):
        now = time.monotonic()
        changed = False
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                break
            if ev[0] == "close":
                changed |= self._on_close(ev[1])
            else:
                changed |= self._on_msg(ev[1], ev[2], now)
        for conn in list(self.conns.values()):
            if now - conn.last_seen > SILENCE_TIMEOUT:
                conn.close()
        if changed or now - self._last_roster > 1.0:
            self._send_roster()
            self._last_roster = now
        if (self.game == "platformer" and self.phase == "playing"
                and now - self._last_ghosts >= GHOST_RATE):
            self._last_ghosts = now
            self._send_ghosts()
        if self.game in SIM_GAMES and self.phase == "playing" and self.fight:
            self._tick_fight(now)

    def _tick_fight(self, now):
        """Fighter / glowbug: run the game one frame with the players' buttons
        and send everybody a snapshot of it."""
        dt = max(0.0, min(0.05, now - self._last_tick))
        self._last_tick = now
        inputs = []
        for cid in self.fight_cids:
            p = self.players.get(cid)
            if p is None or not p["alive"] or cid not in self.conns:
                inputs.append(((), ()))
                continue
            inputs.append((set(p["held"]), p["presses"]))
            p["presses"] = []
        f = self.fight
        if self.game == "glowbug":
            f.update(dt * 1000.0, inputs)
            points = [b.total for b in f.racers]
        elif self.game == "pulsar":
            f.update(dt * 1000.0, inputs[0], inputs[1])
            points = (f.points, f.cpu_points)
        else:
            f.update(dt * 1000.0, inputs[0], inputs[1])
            points = (f.p_rounds, f.c_rounds)
        snap = f.snapshot()
        snap["t"] = "fs"
        self._broadcast(snap)
        for cid, pts in zip(self.fight_cids, points):
            if cid in self.players:
                self.players[cid]["score"] = pts
        if f.game_over and self.game == "glowbug":
            self.finish()                     # ranked by pickups
        elif f.game_over:
            w = f.match_winner()
            if w is not None:                 # the loser is out, the round ends
                loser = self.fight_cids[1 - w]
                if self.players.get(loser, {}).get("alive"):
                    self.players[loser]["alive"] = False
                    self.death_order.append(loser)
            self.finish()

    def _send_ghosts(self):
        """Platformer: everybody's position, to everybody."""
        ghosts = [{"cid": c, "name": p["name"], "alive": p["alive"], "b": p["board"]}
                  for c, p in self.players.items()
                  if isinstance(p["board"], dict) and not p["gone"]]
        if ghosts:
            self._broadcast({"t": "ghosts", "p": ghosts})

    def _on_msg(self, cid, msg, now):
        t = msg.get("t")
        if t == "hello":
            if cid in self.players or cid not in self.conns:
                return False
            self.players[cid] = self._new_player(clean_name(msg.get("name")))
            self.conns[cid].send({"t": "welcome", "cid": cid, "host": self.name})
            return True
        p = self.players.get(cid)
        if p is None or self.phase != "playing" or not p["alive"]:
            return False
        if t == "in" and self.game in SIM_GAMES:
            held = msg.get("h")
            if isinstance(held, list):
                p["held"] = {a for a in held[:6] if a in FIGHT_ACTIONS}
            presses = msg.get("p")
            if isinstance(presses, list) and len(p["presses"]) < 20:
                p["presses"].extend(a for a in presses[:6] if a in FIGHT_ACTIONS)
        elif t == "state":
            self._update_stats(p, msg)
        elif t == "clear" and self.game == "tetris":
            for _ in range(max(0, min(4, _int(msg.get("n"))))):
                self._send_garbage(cid, now)
        elif t == "kill" and self.game == "shooter":
            kind = msg.get("k")
            if kind in ENEMY_KINDS:
                try:
                    fx = max(0.0, min(1.0, float(msg.get("fx", 0.5))))
                except (TypeError, ValueError):
                    fx = 0.5
                self._send_enemy(cid, kind, fx, now)
        elif t == "dead":
            self._update_stats(p, msg)
            p["alive"] = False
            self.death_order.append(cid)
            self._check_end()
            return True
        return False

    def _on_close(self, cid):
        self.conns.pop(cid, None)
        p = self.players.get(cid)
        if p is None:
            return False
        if self.phase == "playing":
            p["gone"] = True
            if p["alive"]:
                p["alive"] = False
                self.death_order.append(cid)
                self._check_end()
        else:
            del self.players[cid]
        return True

    def _check_end(self):
        if self.phase != "playing":
            return
        alive = [c for c, p in self.players.items() if p["alive"]]
        if len(alive) == 0 or (self.started_with >= 2 and len(alive) <= 1):
            self.finish()

    # -- round control (called by the host UI)
    def set_mode(self, mode):
        """The host picked a game mode in the lobby: tell the players."""
        self.game_mode = str(mode)
        self._send_roster()

    def start_game(self, level=1):
        if self.phase == "playing":
            return False
        for cid in [c for c in self.players if c not in self.conns]:
            del self.players[cid]
        if not self.players or (self.game in ("fighter", "pulsar") and len(self.players) != 2):
            return False
        self.phase = "playing"
        self.level = level
        self.death_order = []
        self.ranking = []
        self.started_with = len(self.players)
        for p in self.players.values():
            p.update(alive=True, gone=False, score=0, lines=0, level=level,
                     board=None, hit=0.0, sent=0.0)
        self.t_go = time.monotonic() + COUNTDOWN
        self.seed = random.randrange(1, 2 ** 31)
        start = {"t": "start", "seed": self.seed, "level": level,
                 "countdown": COUNTDOWN, "game": self.game, "gm": self.game_mode}
        if self.game in SIM_GAMES:
            self.fight_cids = sorted(self.players)[:self.max_players]
            names = [self.players[c]["name"] for c in self.fight_cids]
            for p in self.players.values():
                p.update(held=set(), presses=[])
            gm = self.game_mode
            if self.game == "fighter":
                import fighter                # picade/fighter (main.py puts it on the path)
                self.fight = fighter.Versus(self.seed, names, mode=gm)
            elif self.game == "pulsar":
                import pulsar                 # picade/pulsar
                self.fight = pulsar.PulsarVersus(self.seed, names, mode=gm)
            else:
                import glowbug                # picade/glowbug
                self.fight = glowbug.GlowRace(self.seed, names, mode=gm)
            self._last_tick = time.monotonic()
            self.t_go = time.monotonic()      # the fight shows its own VS screen
            start.update(countdown=0, sides=self.fight_cids, names=names)
        self._broadcast(start)
        self._send_roster()
        return True

    def finish(self):
        """End the round and send the final ranking to everybody."""
        if self.phase != "playing":
            return
        alive = sorted((c for c, p in self.players.items() if p["alive"]),
                       key=lambda c: -self.players[c]["score"])
        dead = [c for c in reversed(self.death_order) if c in self.players]
        self.ranking = [
            {"cid": c, "name": self.players[c]["name"],
             "score": self.players[c]["score"], "place": i + 1}
            for i, c in enumerate(alive + dead)
        ]
        self.phase = "results"
        self._broadcast({"t": "over", "ranking": self.ranking})
        self._send_roster()

    def back_to_lobby(self):
        self.phase = "lobby"
        for cid in [c for c in self.players if c not in self.conns]:
            del self.players[cid]
        for p in self.players.values():
            p.update(alive=True, gone=False)
        self._send_roster()

    def close(self):
        self._stop.set()
        self.beacon.stop_event.set()
        try:
            self.srv.close()
        except OSError:
            pass
        for conn in list(self.conns.values()):
            conn.close()


# ----------------------------------------------------------------------------
# Client session (a playing Pi)
# ----------------------------------------------------------------------------
class ClientSession:
    def __init__(self, ip, port, name):
        self.ip = ip
        self.port = port
        self.name = clean_name(name)
        self.events = queue.Queue()
        self.conn = None
        self.cid = None
        self.host_name = ""
        self.phase = "lobby"
        self.roster = []
        self.game_mode = "CLASSIC"     # what the host picked
        self.closed = False
        self.last_host_msg = time.monotonic()
        self.last_ping = 0.0
        threading.Thread(target=self._connect, daemon=True).start()

    def _connect(self):
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=4.0)
        except OSError as exc:
            self.events.put(("failed", {"error": str(exc)}))
            return
        if self.closed:
            sock.close()
            return
        self.conn = _Conn(sock,
                          lambda m: self.events.put(("msg", m)),
                          self._on_close)
        self.last_host_msg = time.monotonic()
        self.conn.send({"t": "hello", "name": self.name, "proto": PROTOCOL})
        self.events.put(("connected", {}))

    def _on_close(self):
        if not self.closed:
            self.events.put(("closed", {}))

    def poll(self):
        """Return a list of (kind, data) events for the UI."""
        out = []
        now = time.monotonic()
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                break
            kind, data = ev
            if kind == "msg":
                self.last_host_msg = now
                t = data.get("t")
                if t == "welcome":
                    self.cid = data.get("cid")
                    self.host_name = clean_name(data.get("host", "HOST"))
                elif t == "roster":
                    self.phase = str(data.get("phase", "lobby"))
                    self.game_mode = str(data.get("gm", "CLASSIC"))[:16]
                    self.roster = [p for p in data.get("players", [])
                                   if isinstance(p, dict)]
                elif t in ("start", "garbage", "enemy", "over", "full", "ghosts", "fs"):
                    out.append((t, data))
            else:
                out.append((kind, data))
        if self.conn is not None and not self.closed:
            if now - self.last_ping > 2.0:
                self.conn.send({"t": "ping"})
                self.last_ping = now
            if now - self.last_host_msg > SILENCE_TIMEOUT:
                out.append(("closed", {}))
                self.close()
        return out

    def send_state(self, board, score, lines, level):
        if self.conn:
            self.conn.send({"t": "state", "b": board, "s": score,
                            "l": lines, "v": level})

    def send_clear(self, n):
        if self.conn:
            self.conn.send({"t": "clear", "n": n})

    def send_input(self, held, presses):
        """Fighter: our buttons (held now + newly pressed)."""
        if self.conn:
            self.conn.send({"t": "in", "h": sorted(held), "p": list(presses)})

    def send_kill(self, kind, fx):
        if self.conn:
            self.conn.send({"t": "kill", "k": kind, "fx": round(fx, 3)})

    def send_dead(self, board, score, lines, level):
        if self.conn:
            self.conn.send({"t": "dead", "b": board, "s": score,
                            "l": lines, "v": level})

    def close(self):
        self.closed = True
        if self.conn:
            self.conn.close()
