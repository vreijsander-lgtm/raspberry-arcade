"""
Shared scoreboard: every arcade Pi on the same network sends its high scores
to the others, so all Pis show the same (combined) top 10.

How it works: every few seconds, and right after a new high score, each Pi
broadcasts its two score lists (a small UDP message). Every Pi that hears it
adds the scores it didn't have yet. A Pi that was switched off catches up
within seconds after it starts again.

Only Pis with the same "score_group" (config.json) share scores, so another
arcade on the same school network won't mix in. If the network blocks
broadcasts, put the other Pis' IP addresses in "score_peers".
"""
import json
import queue
import socket
import threading
import uuid

from multiplayer import local_ip

PORT = 47810
APP_ID = "nova-scores"
VERSION = 1


class ScoreSync:
    def __init__(self, group, peers=(), listen=True):
        self.group = str(group)
        self.peers = [str(p) for p in peers]
        self.me = uuid.uuid4().hex            # to ignore our own broadcasts
        self.inbox = queue.Queue()
        self.stop_event = threading.Event()
        self.error = None
        self.out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.out.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        if listen:
            threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", PORT))
            sock.settimeout(0.5)
        except OSError as exc:
            self.error = str(exc)
            print("Shared scores: can't listen on port %d: %s" % (PORT, exc))
            sock.close()
            return
        try:
            while not self.stop_event.is_set():
                try:
                    data, _addr = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    msg = json.loads(data.decode("utf-8"))
                    if (msg.get("app") != APP_ID or msg.get("v") != VERSION
                            or msg.get("group") != self.group or msg.get("from") == self.me):
                        continue
                    boards = msg["boards"]
                    if isinstance(boards, dict):
                        self.inbox.put(boards)
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
        finally:
            sock.close()

    def send(self, boards):
        """boards: {"tetris": [entries], "shooter": [entries]}"""
        data = json.dumps({"app": APP_ID, "v": VERSION, "group": self.group,
                           "from": self.me, "boards": boards},
                          separators=(",", ":")).encode("utf-8")
        targets = ["255.255.255.255"]
        ip = local_ip()
        if ip.count(".") == 3 and not ip.startswith("127."):
            targets.append(ip.rsplit(".", 1)[0] + ".255")
        for target in targets + self.peers:
            try:
                self.out.sendto(data, (target, PORT))
            except OSError:
                pass

    def poll(self):
        """Score lists received since the last call."""
        got = []
        while True:
            try:
                got.append(self.inbox.get_nowait())
            except queue.Empty:
                return got

    def stop(self):
        self.stop_event.set()
        try:
            self.out.close()
        except OSError:
            pass
