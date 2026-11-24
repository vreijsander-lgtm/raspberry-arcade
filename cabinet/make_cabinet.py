"""
Picade mini arcade cabinet - makes the STL files to 3D print.

    python make_cabinet.py          (needs only plain Python 3, no extra packages)

Writes (all sizes in mm):
    arcade_body.stl          the cabinet: sides, base, front, control deck, screen
                             face with window, roof, screen holders, Pi standoffs
    arcade_back_panel.stl    the back: slides UP out of the rails to open it
    arcade_screen_clamp.stl  2 straps that hold the screen (print 2x, M3 screws)

Inside: a Raspberry Pi 4B on the base and the Elecrow 7" 1024x600 HDMI touch
screen (RC070, 164 x 124 x 14.4 mm, picture 155 x 88.5 mm) mounted sideways
(landscape - the long side across). On the control deck: a joystick hole
made to match joystick.stl (22 mm hole + two 3.5 mm screw holes 33.5 mm apart,
2 mm thick deck) and two standard 30 mm arcade button holes.

PRINT the body lying on its side (a side wall flat on the bed): then nothing
but the screen window and the round holes needs support. The side profile is
about 170 x 201 mm and the body is 182 mm wide, so it fits a 220 x 220 mm bed
(Ender 3, Prusa, Bambu Lab, ...). The back panel and the
clamps print flat.

All the sizes are at the top: CHECK THE SCREEN AGAINST YOUR OWN SCREEN before
printing (Elecrow doesn't publish where the picture sits on the board).
"""
import math
import os
import struct

# ----------------------------------------------------------------------------
# Sizes you may want to change
# ----------------------------------------------------------------------------
WALL = 3.0                 # wall thickness
WIDTH = 182.0              # outside width of the cabinet (x)
DEPTH = 170.0              # outside depth (y, front = 0)
FRONT_H = 40.0             # height of the front edge of the control deck
DECK_BACK = (80.0, 52.0)   # (y, z) where the deck meets the screen face
FACE_TILT = 12.0           # screen face leans back this many degrees
FACE_LEN = 152.0           # length of the screen face (bottom to top)

# screen (landscape: the 164 mm side runs across, the 124 mm side up the face)
SCREEN_W, SCREEN_L, SCREEN_T = 164.0, 124.0, 14.4
VIEW_W, VIEW_L = 155.0, 88.5               # visible picture area (across, up)
VIEW_OFFSET_X = 0.0        # picture centre left(-)/right(+) of the board centre - MEASURE
VIEW_OFFSET_L = 0.0        # picture centre down(-)/up(+) from the board centre - MEASURE
SCREEN_BOTTOM = 10.0       # gap from the bottom of the face to the screen board
CLEAR = 0.5                # play around the screen

# control deck
DECK_T = 2.0               # deck plate (2 mm like joystick.stl) ...
DOUBLER_T = 2.0            # ... with a second plate under it (cut out around the controls)
JOY_X = -45.0              # joystick centre (x) ...
JOY_HOLE = 22.0
JOY_SCREW, JOY_SCREW_DX = 3.5, 16.75
BUTTON_X = (16.0, 56.0)    # the two buttons (40 mm apart)
BUTTON_HOLE = 30.0         # standard 30 mm arcade button (use 24.0 for 24 mm buttons)
CONTROL_S = 0.5            # controls sit this far along the deck (0 = front, 1 = back)

# Raspberry Pi 4B: 85 x 56 board, holes 58 x 49 apart, 3.5 mm in from the edges
PI_X0 = -80.0              # left edge of the board (x)
PI_STANDOFF_H, PI_STANDOFF_D, PI_SCREW = 6.0, 6.0, 2.5

# back panel
PANEL_T = 3.0
SLOT = PANEL_T + 0.4       # the rail slot it slides in

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
        for i in sorted(range(len(poly)), key=lambda i: (poly[i][0] - mp[0]) ** 2 + (poly[i][1] - mp[1]) ** 2):
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
    while len(idx) > 3 and guard < 100000:
        guard += 1
        n = len(idx)
        for k in range(n):
            ia, ib, ic = idx[k - 1], idx[k], idx[(k + 1) % n]
            a, b, c = poly[ia], poly[ib], poly[ic]
            if _cross(a, b, c) <= 1e-12:
                continue
            ear = True
            for j in idx:
                p = poly[j]
                if p == a or p == b or p == c:
                    continue
                if _cross(a, b, p) >= -1e-12 and _cross(b, c, p) >= -1e-12 and _cross(c, a, p) >= -1e-12:
                    ear = False
                    break
            if ear:
                tris.append((ia, ib, ic))
                idx.pop(k)
                break
        else:
            raise RuntimeError("ear clipping got stuck")
    tris.append(tuple(idx))
    return tris


class Mesh:
    def __init__(self):
        self.tris = []          # ((x,y,z) x 3)
        self.shells = []        # (start, end) per closed piece

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
X_IN = WIDTH / 2 - WALL                     # inner side wall faces at +-X_IN
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


def body():
    m = Mesh()
    X, Y, Z = (1.0, 0, 0), (0, 1.0, 0), (0, 0, 1.0)
    # side walls (the whole side profile)
    for x0 in (-WIDTH / 2, X_IN):
        m.plate(PROFILE, [], x0, x0 + WALL, (0, 0, 0), Y, Z)          # N = Y x Z = +x
    # base
    m.box(-X_IN - 0.5, 0, 0, X_IN + 0.5, DEPTH, WALL)
    # front wall
    m.box(-X_IN - 0.5, 0, 0, X_IN + 0.5, WALL, FRONT_H)

    # control deck: (u across = x, s along the deck from the front edge), top = deck surface
    def deck_plate(holes, w0, w1):
        m.plate(rect(-X_IN - 0.5, 0, X_IN + 0.5, DECK_LEN + 1.0), holes, w0, w1,
                (0, 0, FRONT_H), X, DECK_DIR)                         # N = X x DECK_DIR (up)
    s = CONTROL_S * DECK_LEN
    holes = [circle(JOY_X, s, JOY_HOLE, 72), circle(JOY_X - JOY_SCREW_DX, s, JOY_SCREW, 24),
             circle(JOY_X + JOY_SCREW_DX, s, JOY_SCREW, 24)]
    holes += [circle(bx, s, BUTTON_HOLE) for bx in BUTTON_X]
    deck_plate(holes, -DECK_T, 0.0)
    # the doubler plate under it: open around the joystick (its plate is 50 x 50) and the button nuts
    d_holes = [rect(JOY_X - 27, s - 27, JOY_X + 27, s + 27)] + [circle(bx, s, BUTTON_HOLE + 6) for bx in BUTTON_X]
    deck_plate(d_holes, -DECK_T - DOUBLER_T, -DECK_T + 0.01)

    # screen face with the window
    u0, s0, u1, s1 = _screen_box()
    vc_u = VIEW_OFFSET_X
    vc_s = (s0 + s1) / 2 + VIEW_OFFSET_L
    window = rect(vc_u - VIEW_W / 2 - 0.5, vc_s - VIEW_L / 2 - 0.5, vc_u + VIEW_W / 2 + 0.5, vc_s + VIEW_L / 2 + 0.5)
    face_o = (0, DECK_BACK[0], DECK_BACK[1])
    m.plate(rect(-X_IN - 0.5, -DECK_T - DOUBLER_T, X_IN + 0.5, FACE_LEN), [window], -WALL, 0.0,
            face_o, X, FACE_DIR)                                      # N points out of the front
    # screen holders on the inside: 4 corner guides + 4 screw bosses for the clamps
    g, leg = 2.0, 16.0
    w0, w1 = -WALL - SCREEN_T, -WALL + 0.01
    for cu, cs, du, ds in ((u0, s0, -1, -1), (u1, s0, 1, -1), (u0, s1, -1, 1), (u1, s1, 1, 1)):
        a_u, b_u = sorted((cu, cu + du * g))
        a_s, b_s = sorted((cs, cs + ds * g))
        L_u = sorted((cu + du * g, cu - du * leg))
        L_s = sorted((cs + ds * g, cs - ds * leg))
        m.plate(rect(L_u[0], a_s, L_u[1], b_s), [], w0, w1, face_o, X, FACE_DIR)   # along the edge
        m.plate(rect(a_u, L_s[0], b_u, L_s[1]), [], w0, w1, face_o, X, FACE_DIR)   # up the side
    for bu, bs in boss_points():
        m.plate(circle(bu, bs, 7.0, 40), [circle(bu, bs, 2.6, 24)], w0, w1, face_o, X, FACE_DIR)

    # roof (stops in front of the back panel slot, so the panel slides up and out)
    m.box(-X_IN - 0.5, FACE_TOP[0], HEIGHT - WALL, X_IN + 0.5, SLOT_Y0, HEIGHT)
    # back panel rails on both walls, and a lip on the base
    for side in (-1, 1):
        xa, xb = sorted((side * X_IN, side * (X_IN - RAIL)))
        xa, xb = (xa - 0.5, xb) if side < 0 else (xa, xb + 0.5)
        m.box(xa, SLOT_Y0 - 2.0, WALL - 0.01, xb, SLOT_Y0, HEIGHT - WALL + 0.01)    # in front of the panel
        m.box(xa, SLOT_Y1, WALL - 0.01, xb, DEPTH, HEIGHT)                          # behind it
    m.box(-X_IN - 0.5, SLOT_Y0 - 2.0, WALL - 0.01, X_IN + 0.5, SLOT_Y0, WALL + 3.0)

    # Raspberry Pi standoffs (USB / Ethernet end towards the back panel)
    py1 = SLOT_Y0 - 2.0 - 3.0                       # board's back edge (ports stick out ~2 mm)
    py0 = py1 - 85.0
    for hx in (PI_X0 + 3.5, PI_X0 + 52.5):
        for hy in (py0 + 3.5, py0 + 61.5):
            m.plate(circle(hx, hy, PI_STANDOFF_D, 40), [circle(hx, hy, PI_SCREW, 24)],
                    WALL - 0.01, WALL + PI_STANDOFF_H, (0, 0, 0), X, Y)
    m.check("body")
    return m


def boss_points():
    u0, s0, u1, s1 = _screen_box()
    bu = SCREEN_W / 2 - 32.0                        # (clear of the corner guides)
    return [(su * bu, s) for su in (-1, 1) for s in (s0 - 4.0, s1 + 4.0)]     # below / above the screen


def back_panel():
    """Flat on the bed: u = x across, v = height. Slides down into the rails."""
    m = Mesh()
    half = X_IN - 0.2
    top = HEIGHT - WALL - 0.3
    outline = [(-half, 0), (half, 0), (half, top), (-half, top)]
    holes = []
    # the Pi's USB / Ethernet ports
    holes.append(rect(PI_X0 - 1.0, PI_STANDOFF_H, PI_X0 + 57.0, PI_STANDOFF_H + 22.0))
    # a notch for the power cable next to them
    holes.append(rect(PI_X0 + 62.0, 4.0, PI_X0 + 74.0, 12.0))
    # air vents
    for row in range(6):
        v = 60.0 + row * 18.0
        for k in range(3):
            u = -45.0 + k * 45.0
            holes.append(rect(u - 18.0, v, u + 18.0, v + 5.0))
    # finger hole to pull it up
    holes.append(rect(-20.0, top - 22.0, 20.0, top - 10.0))
    m.plate(outline, holes, 0.0, PANEL_T, (0, 0, 0), (1, 0, 0), (0, 1, 0))
    m.check("back panel")
    return m


def screen_clamp():
    """A strap from the boss below the screen to the one above it, across its back (print 2)."""
    m = Mesh()
    pts = boss_points()
    bu = (pts[1][1] - pts[0][1]) / 2                # half the distance between the screws
    half = bu + 6.0
    m.plate(rect(-half, -6.0, half, 6.0), [circle(-bu, 0, 3.4, 32), circle(bu, 0, 3.4, 32)],
            0.0, 3.0, (0, 0, 0), (1, 0, 0), (0, 1, 0))
    m.check("clamp")
    return m


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    for name, fn in (("arcade_body.stl", body), ("arcade_back_panel.stl", back_panel),
                     ("arcade_screen_clamp.stl", screen_clamp)):
        m = fn()
        m.save(os.path.join(here, name))
        b = m.bounds()
        print("%-26s %6d triangles  %5.1f x %5.1f x %5.1f mm" % (name, len(m.tris), *(hi - lo for lo, hi in b)))


if __name__ == "__main__":
    main()
