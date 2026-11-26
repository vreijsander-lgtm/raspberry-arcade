"""
Picade mini arcade cabinet - makes the STL files to 3D print.

    python make_cabinet.py            make all the STL files
    python make_cabinet.py --check    ... and check that no parts are in each other's way

(needs only plain Python 3, no extra packages). All sizes in mm.

The cabinet is a kit of flat panels, each printed lying flat (no supports) and
small enough for a 256 x 256 mm bed (BED below). It CLICKS together, no glue or
screws: the panels have springy arrow clips on both side edges that snap into
slots in the side walls. The clips click into pockets hidden inside the 6 mm side
walls, and the walls' lip wraps round the panel edges, so the outside stays clean. Put the panels into one side wall (they rest
on its ledges), then press the other side wall on until every clip clicks. It is
meant to stay together: the back clicks on just like every other panel.
    cabinet_side_left.stl / cabinet_side_right.stl
                             the two sides: slots for the clips and ledges the
                             panels rest on
    cabinet_base.stl         the bottom, with the Raspberry Pi standoffs
    cabinet_front.stl        the front below the controls
    cabinet_deck.stl         the control deck: joystick + 2 button holes (prints top down)
    cabinet_screen_face.stl  the front with the screen window and its screw holes
                             (prints front down)
    cabinet_roof.stl         the top
    cabinet_back_panel.stl   the back: clicks in like the others (Pi ports stay inside)

Test prints, to check the sizes first (quick, small):
    test_click.stl           one clip + a bit of side wall with its slot and hidden
                             pocket: it should click in and hold (too tight / loose?)
    test_controls.stl        joystick holes + one button hole, in a strip of deck
    test_screen.stl          a frame with the screen-sized opening and the 4 screw holes:
                             the screen should drop into the opening with its own screw
                             holes right under the holes in the frame (arrow = up)
    test_pi_standoffs.stl    the four Pi standoffs: the Pi should sit on them

Inside: a Raspberry Pi 4B on the base and the Elecrow 7" 1024x600 HDMI touch
screen (RC070, 164 x 124 x 14.4 mm, picture 155 x 88.5 mm) mounted sideways
(landscape). It sits against the inside of the face and screws onto 4 posts
(7 mm high, like the Pi standoffs) through its own mounting holes, from behind,
so the front of the face stays smooth.
The joystick hole matches joystick.stl (22 mm hole + two 3.5 mm screw holes
33.5 mm apart, 2 mm thick deck); the buttons are standard 30 mm arcade buttons.
"""
import math
import os
import struct

# ----------------------------------------------------------------------------
# Sizes you may want to change
# ----------------------------------------------------------------------------
WALL = 3.0                 # wall thickness
WIDTH = 250.0              # outside width of the cabinet (x)
DEPTH = 170.0              # outside depth (y, front = 0)
FRONT_H = 40.0             # height of the front edge of the control deck
DECK_BACK = (80.0, 52.0)   # (y, z) where the deck meets the screen face
FACE_TILT = 12.0           # screen face leans back this many degrees
FACE_LEN = 152.0           # length of the screen face (bottom to top)

# screen (landscape: the 164 mm side runs across, the 124 mm side up the face)
SCREEN_W, SCREEN_L, SCREEN_T = 165.0, 103.0, 14.4   # the opening (inner frame): 165 x 103
# (the opening in the face is the whole board, so the whole screen fits in it)
SCREEN_BOTTOM = 20.0       # gap from the bottom of the face to the screen board (= screen in the middle)
# the screen's own mounting holes, from the centre of the board seen from the front
# (x right, y up) - measured: 3 mm in from the left / right edge, 8 mm past the top / bottom edge
_HX, _HY = 157.0 / 2, 115.0 / 2   # screw hole centres on the corners of a 157 x 115 rectangle
SCREEN_HOLES = [(-_HX, -_HY), (_HX, -_HY), (-_HX, _HY), (_HX, _HY)]
SCREEN_SCREW = 2.7         # screw holes in the screen posts (M2.5, like the Pi)
SCREEN_POST_H = 7.0        # the posts: from the face to the screen's screw holes ...
SCREEN_POST_D = 6.0        # ... this thick (the front of the face stays closed)
CLEAR = 0.0                # the opening is exactly SCREEN_W x SCREEN_L

# control deck
DECK_T = 2.0               # deck plate (2 mm like joystick.stl) ...
DOUBLER_T = 2.0            # ... with a second plate under it (flat, only the holes go through)
JOY_X = -45.0              # joystick centre (x) ...
JOY_HOLE = 22.0
JOY_SCREW, JOY_SCREW_DX = 3.5, 16.75
JOY_HEAD, JOY_HEAD_DEPTH = 5.2, 1.0   # recess for the joystick screw heads (5 mm, 1 mm high) - flush
BUTTON_X = (16.0, 56.0)    # the two buttons (40 mm apart)
BUTTON_DS = (-10.0, 10.0)  # ... left one 10 mm lower (towards you), right one 10 mm higher (away)
BUTTON_HOLE = 30.0         # standard 30 mm arcade button (use 24.0 for 24 mm buttons)
CONTROL_S = 0.5            # controls sit this far along the deck (0 = front, 1 = back)

# Raspberry Pi 4B: 85 x 56 board, holes 58 x 49 apart, 3.5 mm in from the edges
PI_X0 = -28.0              # left edge of the board (x): the Pi sits in the middle
PI_PLUG_ROOM = 40.0        # free space between the Pi's USB end and the back (plugs + cables stay inside)
PI_STANDOFF_H, PI_STANDOFF_D, PI_SCREW = 6.0, 6.0, 2.7   # (2.7: M2.5 screws, not too tight)

# screw holes in the posts (screen + Pi): a wider lead-in at the top, and the hole goes
# on down into the plate, so screws find the hole and can go in deeper
SCREW_LEAD = 1.2           # the top this many mm of every post hole is wider ...
SCREW_LEAD_D = 3.6         # ... this wide
SCREW_SKIN = 1.0           # under the posts only this much plate stays closed (front / bottom stays clean)

# room for a battery (power bank) at the back on the right (no frame, just free space);
# the charging hole in the back panel sits next to it. Size (x, y) of that spot.
BATTERY = (72.0, 28.0)
BATTERY_WALL, BATTERY_H = 2.0, 18.0
CABLE_TIES = [(-70.0, 55.0), (70.0, 55.0), (0.0, 25.0), (-45.0, 150.0)]   # pairs of slots for cable ties

# back panel
PANEL_T = 3.0
SLOT = PANEL_T + 0.4       # the rail slot it slides in

BED = 256.0                # print bed size: every piece must fit on it
SEG = 96                   # segments in a circle


# ----------------------------------------------------------------------------
# A tiny mesh builder: flat shapes (with holes) extruded into plates
# ----------------------------------------------------------------------------
def _area(poly):
    return 0.5 * sum(poly[i - 1][0] * poly[i][1] - poly[i][0] * poly[i - 1][1] for i in range(len(poly)))


def _ccw(poly):
    return poly if _area(poly) > 0 else poly[::-1]


def circle(cx, cy, d, n=SEG):
    r = d / 2.0
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def rect(u0, v0, u1, v1):
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segs_cross(p1, p2, q1, q2):
    """Proper crossing of two segments (touching at end points doesn't count)."""
    d1, d2 = _cross(q1, q2, p1), _cross(q1, q2, p2)
    d3, d4 = _cross(p1, p2, q1), _cross(p1, p2, q2)
    return ((d1 > 1e-9 and d2 < -1e-9) or (d1 < -1e-9 and d2 > 1e-9)) and \
           ((d3 > 1e-9 and d4 < -1e-9) or (d3 < -1e-9 and d4 > 1e-9))


def _on_segment(q, a, b):
    if abs(_cross(a, b, q)) > 1e-7 * max(1.0, math.dist(a, b)):
        return False
    return min(a[0], b[0]) - 1e-9 <= q[0] <= max(a[0], b[0]) + 1e-9 and \
        min(a[1], b[1]) - 1e-9 <= q[1] <= max(a[1], b[1]) + 1e-9


def _inside(pt, poly):
    x, y = pt
    c = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i - 1], poly[i]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def _bridge(outer, holes):
    """Join the holes into the outline with zero-width cuts so it can be ear-clipped."""
    poly = list(outer)
    holes = [h[::-1] if _area(h) > 0 else list(h) for h in holes]      # holes clockwise
    holes.sort(key=lambda h: -max(p[0] for p in h))
    for k, hole in enumerate(holes):
        m = max(range(len(hole)), key=lambda i: hole[i][0])
        mp = hole[m]
        others = holes[k + 1:]
        best = None
        used = {q for q in poly if poly.count(q) > 1}         # corners that already carry a bridge
        order = sorted(range(len(poly)), key=lambda i: (poly[i][0] < mp[0], poly[i] in used,
                                                          (poly[i][0] - mp[0]) ** 2 + (poly[i][1] - mp[1]) ** 2))
        for i in order:
            vp = poly[i]
            ok = True
            for j in range(len(poly)):
                if _segs_cross(mp, vp, poly[j - 1], poly[j]):
                    ok = False
                    break
            if ok:
                for h in [hole] + others:
                    for j in range(len(h)):
                        if _segs_cross(mp, vp, h[j - 1], h[j]):
                            ok = False
                            break
                    if not ok:
                        break
            if ok:                                 # (and it mustn't run through another corner)
                for q in poly + [p for h in [hole] + others for p in h]:
                    if q != mp and q != vp and _on_segment(q, mp, vp):
                        ok = False
                        break
            if ok:
                mid = ((mp[0] + vp[0]) / 2, (mp[1] + vp[1]) / 2)
                if _inside(mid, outer) and not any(_inside(mid, h) for h in holes):
                    best = i
                    break
        assert best is not None, "no bridge found"
        ring = hole[m:] + hole[:m + 1]
        poly = poly[:best + 1] + ring + [poly[best]] + poly[best + 1:]
    return poly


def _earclip(poly):
    idx = list(range(len(poly)))
    tris = []
    guard = 0
    eps = -1e-12
    while len(idx) > 3 and guard < 100000:
        guard += 1
        n = len(idx)
        for k in list(range(n)) + ([] if eps > 0 else [None]):
            if k is None:                           # stuck: let points right on an edge pass, try again
                eps = 1e-9
                break
            ia, ib, ic = idx[k - 1], idx[k], idx[(k + 1) % n]
            a, b, c = poly[ia], poly[ib], poly[ic]
            if _cross(a, b, c) <= 1e-12:
                continue
            ear = True
            for j in idx:
                p = poly[j]
                if p == a or p == b or p == c:
                    continue
                if _cross(a, b, p) >= eps and _cross(b, c, p) >= eps and _cross(c, a, p) >= eps:
                    ear = False
                    break
            if ear:
                tris.append((ia, ib, ic))
                idx.pop(k)
                eps = -1e-12
                break
        else:
            raise RuntimeError("ear clipping got stuck")
    tris.append(tuple(idx))
    return tris


class Mesh:
    def __init__(self):
        self.tris = []          # ((x,y,z) x 3)
        self.shells = []        # (start, end) per closed piece
        self.plates = []        # what each piece was made of (for the collision check)

    def plate(self, outline, holes, w0, w1, origin, U, V):
        """Extrude a flat shape (u, v) from w0 to w1 along N = U x V; place it at origin."""
        N = (U[1] * V[2] - U[2] * V[1], U[2] * V[0] - U[0] * V[2], U[0] * V[1] - U[1] * V[0])

        def P(u, v, w):
            return tuple(origin[i] + u * U[i] + v * V[i] + w * N[i] for i in range(3))

        start = len(self.tris)
        outline = _ccw(outline)
        # nudge every hole by a different tiny amount (< 0.01 mm), so no corners of
        # different holes line up exactly - that would confuse the triangulation
        holes = [[(u + (k + 1) * 1.3e-4, v + (k + 1) * 1.7e-4) for u, v in h] for k, h in enumerate(holes)]
        self.plates.append((outline, holes, w0, w1, origin, U, V, N))
        poly = _bridge(outline, holes) if holes else outline
        for a, b, c in _earclip(poly):
            pa, pb, pc = poly[a], poly[b], poly[c]
            self.tris.append((P(*pa, w1), P(*pb, w1), P(*pc, w1)))       # top (+N)
            self.tris.append((P(*pa, w0), P(*pc, w0), P(*pb, w0)))       # bottom (-N)
        rings = [outline] + [h[::-1] if _area(h) > 0 else list(h) for h in holes]
        for ring in rings:
            for i in range(len(ring)):
                a, b = ring[i - 1], ring[i]
                self.tris.append((P(*a, w0), P(*b, w0), P(*b, w1)))
                self.tris.append((P(*a, w0), P(*b, w1), P(*a, w1)))
        self.shells.append((start, len(self.tris)))

    def box(self, x0, y0, z0, x1, y1, z1):
        self.plate(rect(x0, y0, x1, y1), [], z0, z1, (0, 0, 0), (1, 0, 0), (0, 1, 0))

    def check(self, name):
        """Every piece must be closed with all faces pointing out."""
        for s, e in self.shells:
            edges = {}
            vol = 0.0
            for t in self.tris[s:e]:
                for i in range(3):
                    k = (t[i], t[(i + 1) % 3])
                    edges[k] = edges.get(k, 0) + 1
                a, b, c = t
                vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
                        + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
            bad = [k for k, n in edges.items() if n != 1 or edges.get((k[1], k[0]), 0) != 1]
            assert not bad, "%s: open / flipped piece (%d bad edges)" % (name, len(bad))
            assert vol > 0, "%s: inside-out piece" % name

    def save(self, path):
        with open(path, "wb") as f:
            f.write(b"Picade arcade cabinet".ljust(80, b" "))
            f.write(struct.pack("<I", len(self.tris)))
            for a, b, c in self.tris:
                ux, uy, uz = (b[i] - a[i] for i in range(3))
                vx, vy, vz = (c[i] - a[i] for i in range(3))
                n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
                ln = math.sqrt(sum(x * x for x in n)) or 1.0
                f.write(struct.pack("<12fH", *(x / ln for x in n), *a, *b, *c, 0))

    def bounds(self):
        pts = [p for t in self.tris for p in t]
        return [(min(p[i] for p in pts), max(p[i] for p in pts)) for i in range(3)]


# ----------------------------------------------------------------------------
# The cabinet
# ----------------------------------------------------------------------------
SIDE_T = 7.0                                # side walls: thick enough to hide the clips inside
SIDE_SKIN = 1.2                             # the closed outside skin over the clip pockets
POCKET_TOP = 3.8                            # the clip pockets go from the skin up to here
X_IN = WIDTH / 2 - SIDE_T                   # inner side wall faces at +-X_IN
TILT = math.radians(FACE_TILT)
FACE_DIR = (0.0, math.sin(TILT), math.cos(TILT))                   # up the screen face
FACE_TOP = (DECK_BACK[0] + FACE_LEN * FACE_DIR[1], DECK_BACK[1] + FACE_LEN * FACE_DIR[2])
HEIGHT = FACE_TOP[1]
SLOT_Y0 = DEPTH - 1.3 - SLOT                # the back panel slot: y from SLOT_Y0 ...
SLOT_Y1 = DEPTH - 1.3                       # ... to SLOT_Y1
RAIL = 3.0                                  # how far the rails stick out of the walls

deck_dy, deck_dz = DECK_BACK[0], DECK_BACK[1] - FRONT_H
DECK_LEN = math.hypot(deck_dy, deck_dz)
DECK_DIR = (0.0, deck_dy / DECK_LEN, deck_dz / DECK_LEN)

PROFILE = [(0.0, 0.0), (DEPTH, 0.0), (DEPTH, HEIGHT), FACE_TOP, DECK_BACK, (0.0, FRONT_H)]


def _screen_box():
    """The screen board on the face, in face coordinates (u across, s up the face)."""
    s0 = SCREEN_BOTTOM + WALL                       # (clear of the deck)
    return (-SCREEN_W / 2 - CLEAR, s0, SCREEN_W / 2 + CLEAR, s0 + SCREEN_L + 2 * CLEAR)


def screen_holes():
    """The screen's own mounting holes, seen from the front (x right, s up the face)."""
    u0, s0, u1, s1 = _screen_box()
    sc = (s0 + s1) / 2
    return [(hx, sc + hy) for hx, hy in SCREEN_HOLES]


# Every piece is built lying flat the way it prints (w = up from the bed) and has a
# placement (origin, U, V) that puts it where it goes in the cabinet.
X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
NX = (-1.0, 0.0, 0.0)
HALF_IN = X_IN - 0.1                        # panels between the side walls (0.1 mm play each side)
DECK_TOTAL = DECK_T + DOUBLER_T
FACE_START = 1.5                            # the face starts this far up, resting on the deck


# ---- click system: every panel has springy arrow clips on both side edges that snap
# through slots in the side walls (prongs squeeze together going in, the barbs click
# out behind the wall). The clips lie flat in the panel, so they print flat too.
SIDE_LIP = 6.0             # the side walls wrap this far round the front of the panels
CLIP_W = 4.8               # clip width (two 1.6 mm prongs with a 1.6 mm gap between them)
CLIP_GAP = 1.6
CLIP_BARB = 0.45           # how far each barb sticks out (what holds it)
CLIP_RAMP = 1.2            # length of the lead-in slope at the tip
CLIP_DEPTH = SIDE_LIP - 0.5   # the prongs are cut this far into the panel (hidden under the lip)
CLIP_RELIEF = 0.8          # width of the cuts beside the prongs
CLIP_OUT = X_IN - HALF_IN + (SIDE_T - POCKET_TOP) + 0.2   # from the panel edge to the barbs (in the pocket)
POCKET_EXTRA = CLIP_BARB + 0.3              # the pocket is this much wider than the slot each side
SLOT_PLAY = 0.15           # play around the clip in the wall slot (each side)


def _fork(e, c):
    """Outline points of one clip on a panel edge at u = e, centred at v = c (going up in v)."""
    W, g, r, D, b = CLIP_W, CLIP_GAP, CLIP_RELIEF, CLIP_DEPTH, CLIP_BARB
    o, tip = e + CLIP_OUT, e + CLIP_OUT + CLIP_RAMP
    return [(e, c - W / 2 - r), (e - D, c - W / 2 - r), (e - D, c - W / 2), (o, c - W / 2),
            (o, c - W / 2 - b), (tip, c - W / 2 + 0.3), (tip, c - g / 2), (e - D + 1.0, c - g / 2),
            (e - D + 1.0, c + g / 2), (tip, c + g / 2), (tip, c + W / 2 - 0.3), (o, c + W / 2 + b),
            (o, c + W / 2), (e - D, c + W / 2), (e - D, c + W / 2 + r), (e, c + W / 2 + r)]


def clip_outline(v0, v1, tabs, half=None):
    """A panel outline from v0 to v1, as wide as the inside of the cabinet, with clips
    on both side edges at the heights in tabs."""
    e = HALF_IN if half is None else half
    pts = [(-e, v0), (e, v0)]
    for c in sorted(tabs):
        pts += _fork(e, c)
    pts += [(e, v1), (-e, v1)]
    for c in sorted(tabs, reverse=True):
        pts += [(-u, v) for u, v in reversed(_fork(e, c))]
    return pts


# where the panels go, and where their clips are (v along the panel)
FRONT_TOP = FRONT_H - DECK_TOTAL / DECK_DIR[1] - 0.3          # the deck rests on the front
ROOF_V0 = FACE_TOP[0] + 3.2
CLIPPED = {   # name: (placement, thickness, clip positions)
    "base": (((0, 0, 0), X, Y), WALL, (30.0, 105.0, 150.0)),
    "front": (((0, WALL, 0), X, Z), WALL, ((WALL + FRONT_TOP) / 2,)),
    "deck": (((0, 0, FRONT_H), NX, DECK_DIR), DECK_TOTAL, (15.0, DECK_LEN - 15.0)),
    "face": (((0, DECK_BACK[0], DECK_BACK[1]), NX, FACE_DIR), WALL, (8.0, FACE_LEN - 6.0)),
    "roof": (((0, 0, HEIGHT - WALL), X, Y), WALL, (ROOF_V0 + 10.0, DEPTH - 15.0)),
    "back": (((0, DEPTH, 0), X, Z), PANEL_T, (30.0, HEIGHT / 2, HEIGHT - 30.0)),
}


def wall_slots(extra=0.0):
    """The slots in the side walls where the clips go through, in side profile (y, z)."""
    slots = []
    for (o, U, V), t, tabs in CLIPPED.values():
        N = (U[1] * V[2] - U[2] * V[1], U[2] * V[0] - U[0] * V[2], U[0] * V[1] - U[1] * V[0])
        a = CLIP_W / 2 + SLOT_PLAY + extra
        b = t / 2 + SLOT_PLAY
        for c in tabs:
            cy = o[1] + c * V[1] + t / 2 * N[1]
            cz = o[2] + c * V[2] + t / 2 * N[2]
            slots.append([(cy + sa * a * V[1] + sb * b * N[1], cz + sa * a * V[2] + sb * b * N[2])
                          for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    return slots


SIDE_RIM = 3.0             # the side walls stick out this far past the panels (front, top, bottom)


def _grow(poly, offsets):
    """Move each edge of an anticlockwise outline outwards by its offset."""
    lines = []
    for i in range(len(poly)):
        (ay, az), (by, bz) = poly[i], poly[(i + 1) % len(poly)]
        ln = math.hypot(by - ay, bz - az)
        n = ((bz - az) / ln, -(by - ay) / ln)              # outward (right of the direction)
        o = offsets[i]
        lines.append(((ay + n[0] * o, az + n[1] * o), (by - ay, bz - az)))
    pts = []
    for i in range(len(lines)):
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
        pts.append((p1[0] + d1[0] * t, p1[1] + d1[1] * t))
    return pts


# the side wall outline: the profile grown by the rim, except at the back (back panel)
SIDE_OUTLINE = _grow(PROFILE, [SIDE_RIM] * 6)
# extra corners on the back edge, level with the back clips (gives each back slot its
# own short bridge in the triangulation)
SIDE_OUTLINE[2:2] = [(SIDE_OUTLINE[1][0], (WALL + c) * 1.0 + 0.37) for c in sorted(CLIPPED["back"][2])]


def _cleat(p, q, t, trim_a, trim_b):
    """A ledge along the profile edge p -> q, t mm in from the edge (where the panel ends)."""
    dy, dz = q[0] - p[0], q[1] - p[1]
    ln = math.hypot(dy, dz)
    d = (dy / ln, dz / ln)
    n = (-d[1], d[0])                       # (the profile goes round anticlockwise: left = inside)
    a = (p[0] + d[0] * trim_a, p[1] + d[1] * trim_a)
    b = (q[0] - d[0] * trim_b, q[1] - d[1] * trim_b)
    t += 0.1                                # (a little play for the panel)
    return [(a[0] + n[0] * t, a[1] + n[1] * t), (b[0] + n[0] * t, b[1] + n[1] * t),
            (b[0] + n[0] * (t + RAIL), b[1] + n[1] * (t + RAIL)), (a[0] + n[0] * (t + RAIL), a[1] + n[1] * (t + RAIL))]


def side(right):
    """A side wall: the whole side profile, with a lip that wraps round the edges of the
    other panels, ledges they rest on, slots + hidden pockets for their click clips,
    and the two rails the back panel slides in. Prints inside face up."""
    m = Mesh()
    back0, back1 = (DEPTH, 0.0), (DEPTH, HEIGHT)
    front0 = (0.0, 0.0)
    shapes = [PROFILE]
    w_shapes = [
        _cleat(front0, back0, WALL, WALL + 0.3, WALL + 0.3),                                # on the base
        _cleat(back0, back1, PANEL_T, 2 * WALL + 0.3, 2 * WALL + 0.3),                       # behind the back
        _cleat(back1, FACE_TOP, WALL, WALL + 0.3, 5.0),                                      # under the roof
        _cleat(FACE_TOP, DECK_BACK, WALL, 8.0, 8.0),                                         # behind the screen face
        _cleat(DECK_BACK, (0.0, FRONT_H), DECK_TOTAL, 6.0, 6.0),                             # under the deck
        _cleat((0.0, FRONT_H), front0, WALL, 8.0, 2 * WALL + 0.3),                           # behind the front
    ]
    sw = (lambda poly: [(v, u) for u, v in poly]) if right else (lambda poly: poly)
    # three layers: a closed outside skin, the clip pockets, and the slots on the inside
    m.plate(sw(SIDE_OUTLINE), [], 0.0, SIDE_SKIN, (0, 0, 0), X, Y)
    m.plate(sw(SIDE_OUTLINE), [sw(sl) for sl in wall_slots(POCKET_EXTRA)], SIDE_SKIN - 0.01, POCKET_TOP, (0, 0, 0), X, Y)
    m.plate(sw(SIDE_OUTLINE), [sw(sl) for sl in wall_slots()], POCKET_TOP - 0.01, SIDE_T, (0, 0, 0), X, Y)
    for sh in w_shapes:
        m.plate(sw(sh), [], SIDE_T - 0.01, SIDE_T + RAIL, (0, 0, 0), X, Y)
    # the lip round the front of the panels (hides their edges and the clips)
    # (a ring all the way round, the back too)
    inner = _grow(PROFILE, [0.1] * 6)
    m.plate(sw(SIDE_OUTLINE), [sw(inner)], SIDE_T - 0.01, SIDE_T + SIDE_LIP, (0, 0, 0), X, Y)
    m.check("side")
    place = ((WIDTH / 2, 0, 0), Z, Y) if right else ((-WIDTH / 2, 0, 0), Y, Z)
    return m, place


def post(m, x, y, w0, h, d, screw):
    """A screw post standing on w0, h high: lead-in at the top."""
    m.plate(circle(x, y, d, 40), [circle(x, y, screw, 24)], w0 - 0.01, w0 + h - SCREW_LEAD, (0, 0, 0), X, Y)
    m.plate(circle(x, y, d, 40), [circle(x, y, SCREW_LEAD_D, 24)], w0 + h - SCREW_LEAD - 0.01, w0 + h, (0, 0, 0), X, Y)


def battery_box():
    """(x0, y0, x1, y1) inside of the battery frame on the base."""
    x1 = X_IN - RAIL - 1.0 - BATTERY_WALL
    y1 = DEPTH - PANEL_T - 1.0 - BATTERY_WALL
    return x1 - BATTERY[0], y1 - BATTERY[1], x1, y1


def base():
    m = Mesh()
    outline = clip_outline(0, DEPTH, CLIPPED["base"][2])
    py1 = DEPTH - PANEL_T - PI_PLUG_ROOM            # room behind the Pi for the USB plugs (inside)
    py0 = py1 - 85.0
    pcx, pcy = PI_X0 + 28.0, py0 + 32.5             # middle of the hole pattern (same spot as before)
    # Pi turned 90 degrees: the 58 mm hole spacing now runs left-right (x), the 49 mm front-back (y)
    pi_holes = [(hx, hy) for hx in (pcx - 29.0, pcx + 29.0) for hy in (pcy - 24.5, pcy + 24.5)]
    ties = []
    for cx, cy in CABLE_TIES:                       # two little slots: thread a cable tie through
        ties += [rect(cx - 4.0, cy - 3.5, cx + 4.0, cy - 1.5), rect(cx - 4.0, cy + 1.5, cx + 4.0, cy + 3.5)]
    m.plate(outline, ties, 0.0, SCREW_SKIN, (0, 0, 0), X, Y)
    m.plate(outline, ties + [circle(hx, hy, PI_SCREW, 24) for hx, hy in pi_holes], SCREW_SKIN - 0.01, WALL, (0, 0, 0), X, Y)
    for hx, hy in pi_holes:                         # Raspberry Pi standoffs (board turned 90 degrees)
        post(m, hx, hy, WALL, PI_STANDOFF_H, PI_STANDOFF_D, PI_SCREW)
    m.check("base")
    return m, CLIPPED["base"][0]


def front():
    m = Mesh()
    m.plate(clip_outline(WALL, FRONT_TOP, CLIPPED["front"][2]), [], 0.0, WALL, (0, 0, 0), X, Y)
    m.check("front")
    return m, CLIPPED["front"][0]                             # N = X x Z = -y


def deck():
    """The control deck, printed top side down (u is mirrored: u = -x)."""
    m = Mesh()
    s = CONTROL_S * DECK_LEN
    out = clip_outline(0, DECK_LEN + 3.5, CLIPPED["deck"][2])
    holes = [circle(-JOY_X, s, JOY_HOLE, 72)] + [circle(-bx, s + ds, BUTTON_HOLE) for bx, ds in zip(BUTTON_X, BUTTON_DS)]
    screws = [circle(-JOY_X - JOY_SCREW_DX, s, JOY_SCREW, 24), circle(-JOY_X + JOY_SCREW_DX, s, JOY_SCREW, 24)]
    heads = [circle(-JOY_X - JOY_SCREW_DX, s, JOY_HEAD, 40), circle(-JOY_X + JOY_SCREW_DX, s, JOY_HEAD, 40)]
    # top layer (on the bed): wide recesses so the joystick screw heads sit flush
    m.plate(out, holes + heads, 0.0, JOY_HEAD_DEPTH, (0, 0, 0), X, Y)
    m.plate(out, holes + screws, JOY_HEAD_DEPTH - 0.01, DECK_T, (0, 0, 0), X, Y)
    # the doubler under it: flat, with only the same holes going through
    m.plate(out, holes + screws, DECK_T - 0.01, DECK_TOTAL, (0, 0, 0), X, Y)
    m.check("deck")
    return m, CLIPPED["deck"][0]                              # N = -x X deck = down into the cabinet


def face():
    """The screen face, printed front side down (u = -x), with 4 posts on the inside: the
    screen screws onto them from behind (the front stays closed)."""
    m = Mesh()
    u0, s0, u1, s1 = _screen_box()
    window = rect(u0, s0, u1, s1)                   # the whole board (+ play): the screen fits in it
    outline = clip_outline(FACE_START, FACE_LEN, CLIPPED["face"][2])
    m.plate(outline, [window], 0.0, SCREW_SKIN, (0, 0, 0), X, Y)
    m.plate(outline, [window] + [circle(-hx, hs, SCREEN_SCREW, 24) for hx, hs in screen_holes()],
            SCREW_SKIN - 0.01, WALL, (0, 0, 0), X, Y)
    for hx, hs in screen_holes():
        post(m, -hx, hs, WALL, SCREEN_POST_H, SCREEN_POST_D, SCREEN_SCREW)
    m.check("face")
    return m, CLIPPED["face"][0]                              # N = -x X face = into the cabinet


def roof():
    m = Mesh()
    m.plate(clip_outline(ROOF_V0, DEPTH, CLIPPED["roof"][2]), [], 0.0, WALL, (0, 0, 0), X, Y)
    m.check("roof")
    return m, CLIPPED["roof"][0]


# engraved text on the back: a little built-in pixel font (5 x 7), so no font files are needed
SIGN_TEXT = "MADE BY SANDER"
SIGN_PIXEL = 1.3           # size of one font pixel (mm): letters are 9 mm high
SIGN_DEPTH = 0.8           # how deep it is engraved
SIGN_V = 50.0              # top of the text, up from the bottom of the back panel
FONT = {
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    " ": ["00000"] * 7,
}


def _sign_rows():
    """The text as rows of 0 / 1 (one font pixel each), with a 1 pixel border."""
    rows = []
    for r in range(7):
        line = "0".join(FONT[c][r] for c in SIGN_TEXT)
        rows.append("0" + line + "0")
    blank = "0" * len(rows[0])
    return [blank] + rows + [blank]


def back_panel():
    """The back: clicks in between the side walls like the other panels (sits on the
    base, under the roof). Only a small hole for the power cable. "MADE BY SANDER" is engraved in the outside (it prints on the bed, mirrored, so it
    reads the right way round from behind the cabinet)."""
    m = Mesh()
    top = HEIGHT - WALL
    outline = clip_outline(WALL, top, CLIPPED["back"][2])
    holes = []
    bx0 = battery_box()[0] - BATTERY_WALL
    holes.append(rect(bx0 - 17.0, WALL + 4.0, bx0 - 4.0, WALL + 12.0))                   # power / charge cable hole
    for row in range(6):                                                                  # air vents
        v = 60.0 + row * 18.0
        for k in range(3):
            u = -45.0 + k * 45.0
            holes.append(rect(u - 18.0, v, u + 18.0, v + 5.0))
    # the engraving: the outside layer is open where the text is (built row by row)
    rows = _sign_rows()
    px = SIGN_PIXEL
    width = len(rows[0]) * px
    x0 = -width / 2                                 # left edge of the text, seen from behind
    v_top = SIGN_V + px
    box = rect(-width / 2, v_top - len(rows) * px, width / 2, v_top)
    m.plate(outline, holes + [box], 0.0, SIGN_DEPTH, (0, 0, 0), X, Y)
    for r, line in enumerate(rows):
        v1 = v_top - r * px
        c = 0
        while c < len(line):                        # each run of plain (not engraved) pixels
            if line[c] == "1":
                c += 1
                continue
            c1 = c
            while c1 < len(line) and line[c1] == "0":
                c1 += 1
            xa, xb = x0 + c * px, x0 + c1 * px      # seen from behind: u = -x (mirrored)
            m.plate(rect(-xb, v1 - px, -xa, v1), [], 0.0, SIGN_DEPTH + 0.01, (0, 0, 0), X, Y)
            c = c1
    m.plate(outline, holes, SIGN_DEPTH, PANEL_T, (0, 0, 0), X, Y)
    m.check("back panel")
    return m, CLIPPED["back"][0]                              # N = -y: outside on the bed


DECK_BACK_3 = (0.0, DECK_BACK[0], DECK_BACK[1])
FACE_N = (0.0, -math.cos(TILT), math.sin(TILT))    # out of the front of the screen face

PIECES = [                                          # (file, how many to print, maker)
    ("cabinet_side_left.stl", 1, lambda: side(False)),
    ("cabinet_side_right.stl", 1, lambda: side(True)),
    ("cabinet_base.stl", 1, base),
    ("cabinet_front.stl", 1, front),
    ("cabinet_deck.stl", 1, deck),
    ("cabinet_screen_face.stl", 1, face),
    ("cabinet_roof.stl", 1, roof),
    ("cabinet_back_panel.stl", 1, back_panel),
]


def placed(mesh, place):
    """The piece moved to where it goes in the cabinet (a list of triangles)."""
    o, U, V = place
    N = (U[1] * V[2] - U[2] * V[1], U[2] * V[0] - U[0] * V[2], U[0] * V[1] - U[1] * V[0])
    return [tuple(tuple(o[i] + p[0] * U[i] + p[1] * V[i] + p[2] * N[i] for i in range(3)) for p in t)
            for t in mesh.tris]


def assembly():
    """[(name, mesh, placement)] for every part in the cabinet."""
    parts = []
    for name, count, fn in PIECES:
        m, pl = fn()
        parts.append((name, m, pl))
    return parts


# ----------------------------------------------------------------------------
# Check that no two parts are in each other's way once put together
# ----------------------------------------------------------------------------
def _frames(mesh, place):
    """World frames of all the plates of a placed piece."""
    o, U, V = place
    N = (U[1] * V[2] - U[2] * V[1], U[2] * V[0] - U[0] * V[2], U[0] * V[1] - U[1] * V[0])

    def to_world(p):
        return tuple(o[i] + p[0] * U[i] + p[1] * V[i] + p[2] * N[i] for i in range(3))

    def vec(v):
        return tuple(v[0] * U[i] + v[1] * V[i] + v[2] * N[i] for i in range(3))

    res = []
    for outline, holes, w0, w1, po, pU, pV, pN in mesh.plates:
        res.append((outline, holes, w0, w1, to_world(po), vec(pU), vec(pV), vec(pN)))
    return res


def _dist_to_edges(pt, poly):
    best = 1e9
    for i in range(len(poly)):
        (ax, ay), (bx, by) = poly[i - 1], poly[i]
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy or 1e-12
        t = max(0.0, min(1.0, ((pt[0] - ax) * dx + (pt[1] - ay) * dy) / L))
        best = min(best, math.hypot(pt[0] - ax - t * dx, pt[1] - ay - t * dy))
    return best


def _solid_at(fr, p, margin=0.06):
    outline, holes, w0, w1, o, U, V, N = fr
    d = (p[0] - o[0], p[1] - o[1], p[2] - o[2])
    w = d[0] * N[0] + d[1] * N[1] + d[2] * N[2]
    if not (w0 + margin < w < w1 - margin):
        return False
    u = d[0] * U[0] + d[1] * U[1] + d[2] * U[2]
    v = d[0] * V[0] + d[1] * V[1] + d[2] * V[2]
    if not _inside((u, v), outline) or _dist_to_edges((u, v), outline) < margin:
        return False
    for h in holes:
        if _inside((u, v), h) or _dist_to_edges((u, v), h) < margin:
            return False
    return True


def _samples(fr, step=2.0):
    outline, holes, w0, w1, o, U, V, N = fr
    us = [p[0] for p in outline]
    vs = [p[1] for p in outline]
    pts = []
    u = min(us) + 0.3
    while u < max(us):
        v = min(vs) + 0.3
        while v < max(vs):
            if _inside((u, v), outline) and not any(_inside((u, v), h) for h in holes):
                for w in (w0 + 0.2, (w0 + w1) / 2, w1 - 0.2):
                    pts.append(tuple(o[i] + u * U[i] + v * V[i] + w * N[i] for i in range(3)))
            v += step
        u += step
    return pts


def check_fit(parts):
    """Sample each part and make sure no point is inside another part."""
    frames = [(name, _frames(m, pl)) for name, m, pl in parts]
    boxes = []
    for name, m, pl in parts:
        pts = [p for t in placed(m, pl) for p in t]
        boxes.append([(min(p[i] for p in pts), max(p[i] for p in pts)) for i in range(3)])
    problems = []
    for a, (na, fa) in enumerate(frames):
        pts = [p for fr in fa for p in _samples(fr)]
        for b, (nb, fb) in enumerate(frames):
            if a == b:
                continue
            bb = boxes[b]
            near = [p for p in pts if all(bb[i][0] - 0.1 <= p[i] <= bb[i][1] + 0.1 for i in range(3))]
            hits = [p for p in near if any(_solid_at(fr, p) for fr in fb)]
            if hits:
                problems.append((na, nb, len(hits), hits[0]))
    return problems


# ----------------------------------------------------------------------------
# Test prints: small and quick, to check the sizes before printing the cabinet
# ----------------------------------------------------------------------------
def test_controls():
    """A strip of deck (same thickness) with the joystick holes and one button hole."""
    m = Mesh()
    holes = [circle(-25.0, 0, JOY_HOLE, 72), circle(35.0, 0, BUTTON_HOLE)]
    screws = [circle(-25.0 - JOY_SCREW_DX, 0, JOY_SCREW, 24), circle(-25.0 + JOY_SCREW_DX, 0, JOY_SCREW, 24)]
    heads = [circle(-25.0 - JOY_SCREW_DX, 0, JOY_HEAD, 40), circle(-25.0 + JOY_SCREW_DX, 0, JOY_HEAD, 40)]
    strip = rect(-55.0, -22.0, 60.0, 22.0)
    # (the screw head recesses on top, like the top of the deck)
    m.plate(strip, holes + screws, 0.0, DECK_T - JOY_HEAD_DEPTH, (0, 0, 0), X, Y)
    m.plate(strip, holes + heads, DECK_T - JOY_HEAD_DEPTH - 0.01, DECK_T, (0, 0, 0), X, Y)
    m.check("test controls")
    return m


def test_screen():
    """A thin frame with the screen-sized opening and the 4 screw holes: the screen should
    drop into the opening, with its own screw holes right under the holes in the frame."""
    m = Mesh()
    w, l = SCREEN_W / 2 + CLEAR, SCREEN_L / 2 + CLEAR
    hy = max(abs(y) for _, y in SCREEN_HOLES)
    for sy in (-1, 1):                              # top and bottom strips with the screw holes
        y0, y1 = sorted((sy * l, sy * (hy + 5.0)))
        m.plate(rect(-w - 4.0, y0, w + 4.0, y1),
                [circle(hx, y, SCREEN_SCREW, 24) for hx, y in SCREEN_HOLES if y * sy > 0], 0.0, 1.2, (0, 0, 0), X, Y)
    for sx in (-1, 1):                              # left and right bars
        x0, x1 = sorted((sx * w, sx * (w + 4.0)))
        m.plate(rect(x0, -l - 0.5, x1, l + 0.5), [], 0.0, 1.2, (0, 0, 0), X, Y)
    # a little arrow pointing up (which way round it goes) on the top edge
    m.plate([(-6.0, hy + 5.0), (6.0, hy + 5.0), (0.0, hy + 12.0)], [], 0.0, 1.2, (0, 0, 0), X, Y)
    m.check("test screen")
    return m


def test_pi():
    """The four Pi standoffs on a thin plate: the Pi should sit on them, holes lined up."""
    m = Mesh()
    m.plate(rect(-6.0, -6.0, 64.0, 55.0), [rect(10.0, 8.0, 48.0, 41.0)], 0.0, 1.6, (0, 0, 0), X, Y)
    for hx in (0.0, 58.0):
        for hy in (0.0, 49.0):
            post(m, hx, hy, 1.6, PI_STANDOFF_H, PI_STANDOFF_D, PI_SCREW)
    m.check("test pi")
    return m


def test_click():
    """One clip on a strip of panel and a bit of side wall with its slot: push the clip
    into the slot - it should click into the hidden pocket and hold."""
    m = Mesh()
    e = 0.0
    pts = [(-25.0, -10.0), (e, -10.0)] + _fork(e, 0.0) + [(e, 10.0), (-25.0, 10.0)]
    m.plate(pts, [], 0.0, WALL, (0, 0, 0), X, Y)
    a, b = CLIP_W / 2 + SLOT_PLAY, WALL / 2 + SLOT_PLAY
    wall = rect(12.0, -12.0, 32.0, 12.0)                     # (a bit of side wall, inside face up)
    m.plate(wall, [], 0.0, SIDE_SKIN, (0, 0, 0), X, Y)
    m.plate(wall, [rect(22.0 - b, -a - POCKET_EXTRA, 22.0 + b, a + POCKET_EXTRA)], SIDE_SKIN - 0.01, POCKET_TOP,
            (0, 0, 0), X, Y)
    m.plate(wall, [rect(22.0 - b, -a, 22.0 + b, a)], POCKET_TOP - 0.01, SIDE_T, (0, 0, 0), X, Y)
    m.check("test click")
    return m


TESTS = [("test_click.stl", test_click), ("test_controls.stl", test_controls), ("test_screen.stl", test_screen),
         ("test_pi_standoffs.stl", test_pi)]


# ----------------------------------------------------------------------------
# One Bambu Studio project with every part already laid out on its plates
# ----------------------------------------------------------------------------
PLATES = [                                          # what goes on each plate (front to back)
    ["cabinet_side_left.stl"],
    ["cabinet_side_right.stl", "cabinet_roof.stl"],
    ["cabinet_base.stl", "cabinet_front.stl"],
    ["cabinet_deck.stl", "cabinet_screen_face.stl"],
    ["cabinet_back_panel.stl"],
]
PLATE_GAP = 8.0            # space between parts on one plate


def _plate_origin(i, count):
    """Where Bambu Studio puts plate i (plates in rows, 20 % apart, rows going -y)."""
    v = math.sqrt(count)
    cols = int(round(v)) + (1 if v > round(v) else 0)
    stride = BED * 1.2
    return (i % cols) * stride, -(i // cols) * stride


def write_3mf(path, meshes):
    """meshes: {file name: Mesh}. Writes a Bambu Studio project with one plate per PLATES entry."""
    import zipfile
    from xml.sax.saxutils import escape
    objects, items, config = [], [], []
    plates_xml = []
    oid = 0
    for pi, names in enumerate(PLATES):
        ox, oy = _plate_origin(pi, len(PLATES))
        sizes = []
        for n in names:
            b = meshes[n].bounds()
            sizes.append((b, b[0][1] - b[0][0], b[1][1] - b[1][0]))
        total = sum(sz[2] for sz in sizes) + PLATE_GAP * (len(sizes) - 1)
        assert total <= BED and all(sz[1] <= BED for sz in sizes), "plate %d too full" % (pi + 1)
        y = BED / 2 + total / 2                    # stack the parts from the back to the front
        insts = []
        for n, (b, w, d) in zip(names, sizes):
            oid += 1
            cx, cy = BED / 2, y - d / 2
            y -= d + PLATE_GAP
            # the mesh, centred on its own middle (x, y) with its bottom at z = 0
            mx, my, mz = (b[0][0] + b[0][1]) / 2, (b[1][0] + b[1][1]) / 2, b[2][0]
            index, verts, tris = {}, [], []
            for t in meshes[n].tris:
                ids = []
                for p in t:
                    q = (round(p[0] - mx, 4), round(p[1] - my, 4), round(p[2] - mz, 4))
                    if q not in index:
                        index[q] = len(verts)
                        verts.append(q)
                    ids.append(index[q])
                if len(set(ids)) == 3:
                    tris.append(ids)
            vx = "".join('<vertex x="%g" y="%g" z="%g"/>' % v for v in verts)
            tx = "".join('<triangle v1="%d" v2="%d" v3="%d"/>' % tuple(t) for t in tris)
            objects.append('<object id="%d" name="%s" type="model"><mesh><vertices>%s</vertices>'
                           '<triangles>%s</triangles></mesh></object>' % (oid, escape(n[:-4]), vx, tx))
            items.append('<item objectid="%d" transform="1 0 0 0 1 0 0 0 1 %g %g 0" printable="1"/>'
                         % (oid, ox + cx, oy + cy))
            config.append('<object id="%d"><metadata key="name" value="%s"/><metadata key="extruder" value="1"/>'
                          '<part id="1" subtype="normal_part"><metadata key="name" value="%s"/></part></object>'
                          % (oid, escape(n[:-4]), escape(n[:-4])))
            insts.append('<model_instance><metadata key="object_id" value="%d"/><metadata key="instance_id" '
                         'value="0"/><metadata key="identify_id" value="%d"/></model_instance>' % (oid, 100 + oid))
        plates_xml.append('<plate><metadata key="plater_id" value="%d"/><metadata key="plater_name" value="%s"/>'
                          '<metadata key="locked" value="false"/>%s</plate>'
                          % (pi + 1, escape(" + ".join(n[8:-4] for n in names)), "".join(insts)))
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             '<metadata name="Application">BambuStudio-01.10.00.00</metadata>'
             '<metadata name="BambuStudio:3mfVersion">1</metadata>'
             '<metadata name="Title">Picade arcade cabinet</metadata>'
             '<resources>%s</resources><build>%s</build></model>' % ("".join(objects), "".join(items)))
    settings = ('<?xml version="1.0" encoding="UTF-8"?>\n<config>%s%s</config>'
                % ("".join(config), "".join(plates_xml)))
    types = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
             '<Default Extension="config" ContentType="text/xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel-1" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)
        z.writestr("Metadata/model_settings.config", settings)


def main():
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    for old in ("arcade_body.stl", "arcade_back_panel.stl", "arcade_screen_clamp.stl", "cabinet_screen_clamp.stl", "test_back_slot.stl"):
        if os.path.exists(os.path.join(here, old)):
            os.remove(os.path.join(here, old))
    made = {}
    for name, count, fn in PIECES:
        m, _ = fn()
        made[name] = m
        m.save(os.path.join(here, name))
        b = m.bounds()
        size = [hi - lo for lo, hi in b]
        fits = max(size[0], size[1]) <= BED and min(size[0], size[1]) <= BED and size[2] <= BED
        print("%-28s print %dx  %5.1f x %5.1f x %5.1f mm  %s" % (name, count, *size, "" if fits else "TOO BIG FOR THE BED"))
    write_3mf(os.path.join(here, "cabinet_all_plates.3mf"), made)
    print("%-28s Bambu Studio project: %d plates" % ("cabinet_all_plates.3mf", len(PLATES)))
    for name, fn in TESTS:
        m = fn()
        m.save(os.path.join(here, name))
        b = m.bounds()
        print("%-28s test     %5.1f x %5.1f x %5.1f mm" % (name, *(hi - lo for lo, hi in b)))
    if "--check" in sys.argv:
        problems = check_fit(assembly())
        for na, nb, n, p in problems:
            print("CLASH: %s goes into %s (%d points, e.g. at %.1f %.1f %.1f)" % (na, nb, n, *p))
        print("fit check:", "OK - nothing in the way" if not problems else "%d clashes" % len(problems))


if __name__ == "__main__":
    main()
