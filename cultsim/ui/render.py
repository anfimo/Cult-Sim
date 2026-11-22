"""Isometrischer Pseudo-3D-Renderer (drehbar in 90°-Schritten, ganzzahliger Pixel-Zoom)."""
from __future__ import annotations

import math

import pygame

from ..config import *
from ..data import DATA

SKIN = [(255, 226, 200), (242, 204, 166), (224, 174, 130), (192, 138, 98), (152, 104, 72), (112, 76, 54)]
HAIR = [(46, 36, 30), (96, 64, 38), (156, 106, 54), (216, 186, 106), (204, 204, 204), (130, 48, 34), (66, 66, 78), (242, 242, 236)]
CIV = [(204, 86, 76), (76, 126, 196), (96, 166, 106), (214, 194, 96), (156, 116, 176), (126, 126, 138), (234, 146, 66), (86, 176, 186)]
ROOM_COL = {"Tempel": (236, 190, 80), "Schlafsaal": (110, 150, 230), "Kammer": (110, 150, 230), "Küche": (236, 130, 70),
            "Speisesaal": (220, 160, 90), "Ziegengehege": (160, 220, 120), "Garten": (120, 200, 90), "Hof": (150, 190, 150),
            "Gemach des Gurus": (200, 110, 220), "Schreibstube": (120, 200, 210), "Druckerei": (120, 200, 210)}
DIR_NAMES = {(1, 0): "se", (0, 1): "sw", (-1, 0): "nw", (0, -1): "ne"}
N4 = ((1, 0), (0, 1), (-1, 0), (0, -1))
BACK_SKIP = ("acc_guard", "acc_press", "acc_inspector", "acc_sign")


def rot_vec(dx, dy, r):
    if r == 0:
        return dx, dy
    if r == 1:
        return dy, -dx
    if r == 2:
        return -dx, -dy
    return -dy, dx


class IsoView:
    def __init__(self, assets, size):
        self.a = assets
        self.S = size
        self.cx = self.cy = size / 2.0
        self.zoom = 2
        self.rot = 0
        self.low_walls = False
        self.show_rooms = False
        self._ground: dict[int, tuple] = {}
        self._pawn_cache: dict = {}
        self._fence_cache: dict = {}
        self._buf = None
        self.vw = self.vh = 0
        self.ox = self.oy = 0
        self.fence_dirs = [[DIR_NAMES[rot_vec(dx, dy, r)] for dx, dy in N4] for r in range(4)]

    # ------------------------------------------------------------ Koordinaten
    def rxy(self, x, y):
        S1 = self.S - 1
        r = self.rot
        if r == 0:
            return x, y
        if r == 1:
            return y, S1 - x
        if r == 2:
            return S1 - x, S1 - y
        return S1 - y, x

    def unrot(self, rx, ry):
        S1 = self.S - 1
        r = self.rot
        if r == 0:
            return rx, ry
        if r == 1:
            return S1 - ry, rx
        if r == 2:
            return S1 - rx, S1 - ry
        return ry, S1 - rx

    def set_view(self, w, h):
        self.vw, self.vh = w // self.zoom + 1, h // self.zoom + 1
        rx, ry = self.rxy(self.cx, self.cy)
        self.ox = self.vw // 2 - int((rx - ry) * 16)
        self.oy = self.vh // 2 - int((rx + ry) * 8)

    def to_view(self, x, y):
        rx, ry = self.rxy(x, y)
        return int((rx - ry) * 16) + self.ox, int((rx + ry) * 8) + self.oy

    def to_window(self, x, y):
        sx, sy = self.to_view(x, y)
        return sx * self.zoom, sy * self.zoom

    def tile_at(self, px, py):
        a = (px / self.zoom - self.ox) / 16.0
        b = (py / self.zoom - self.oy) / 8.0
        x, y = self.unrot((a + b) / 2, (b - a) / 2)
        return int(math.floor(x + 0.5)), int(math.floor(y + 0.5))

    def rotate(self, d):
        self.rot = (self.rot + d) % 4

    def pan_screen(self, dx, dy):
        """Verschiebt die Kamera um Bildschirm-Pixel."""
        a, b = dx / self.zoom / 16.0, dy / self.zoom / 8.0
        drx, dry = (a + b) / 2, (b - a) / 2
        r = self.rot
        ddx, ddy = (drx, dry) if r == 0 else (-dry, drx) if r == 1 else (-drx, -dry) if r == 2 else (dry, -drx)
        self.cx = max(0.0, min(self.S - 1.0, self.cx + ddx))
        self.cy = max(0.0, min(self.S - 1.0, self.cy + ddy))

    # ------------------------------------------------------------ Bodencache
    def ground(self, w):
        g = self._ground.get(self.rot)
        if g is not None and g[0] == w.ground_rev:
            return g[1]
        S, a = self.S, self.a
        surf = g[1] if g is not None else pygame.Surface((2 * S * 16, 2 * S * 8 + 16)).convert()
        surf.fill((14, 17, 24))
        terr = [a.frames(s)[0] for s in TERRAIN_SPRITES]
        soil = a.get("floor_soil")[0]
        floors = {k: a.get(d["sprite"])[0] for k, d in DATA.buildables.items() if d["kind"] == "floor"}
        zt = {z: a.tinted("tile_mask", 0, c[1], 70) for z, c in ZONES.items()}
        blits = []
        ox, oy = S * 16 - 16, 0
        for d in range(2 * S - 1):                    # von hinten nach vorn (Kacheln überlappen um 2 px)
            for rx in range(max(0, d - S + 1), min(S, d + 1)):
                ry = d - rx
                x, y = self.unrot(rx, ry)
                i = x + y * S
                pos = ((rx - ry) * 16 + ox, d * 8 + oy)
                fr = terr[w.terrain[i]]
                blits.append((fr[w.variant[i] % len(fr)], pos))
                f = w.floor[i]
                if f:
                    blits.append((floors[f], pos))
                z = w.zone[i]
                if z == Z_FIELD:
                    blits.append((soil, pos))
                elif z:
                    blits.append((zt[z], pos))
        surf.blits(blits)
        self._ground[self.rot] = (w.ground_rev, surf)
        return surf

    # ------------------------------------------------------------ Figuren
    def pawn_sprite(self, w, p, tick):
        k = p.kind
        frx, fry = rot_vec(p.face[0], p.face[1], self.rot)
        sdx, sdy = frx - fry, frx + fry
        front = sdy >= 0
        flip = sdx < 0
        frame = (1 + (tick // 5 + p.id) % 2) if p.moving else 0
        if k == "goat":
            key = ("goat", frame, sdx < 0)
            s = self._pawn_cache.get(key)
            if s is None:
                s = self.a.get("goat", frame % 2)[0]
                if sdx < 0:
                    s = pygame.transform.flip(s, True, False)
                self._pawn_cache[key] = s
            return s, 8, 12
        acc = None
        if k == "guru":
            body, col, acc = "pawn_robe", (250, 240, 205), "acc_guru"
        elif k == "member":
            body, col = "pawn_robe", tuple(DATA.doctrine["ranks"][p.rank]["robe"])
            acc = "acc_hood" if p.rank >= 3 else "acc_guard" if p.role == "guard" else None
        else:
            body = "pawn_civ"
            col = {"police": (52, 70, 130), "soldier": (92, 108, 62), "inspector": (120, 120, 128)}.get(k, CIV[p.look[2]])
            acc = {"police": "acc_police", "soldier": "acc_soldier", "inspector": "acc_inspector",
                   "journalist": "acc_press", "relative": "acc_sign"}.get(k)
        if not front and acc in BACK_SKIP:
            acc = None
        key = (body, col, p.look[0], p.look[1], acc, front, frame, flip, p.asleep)
        s = self._pawn_cache.get(key)
        if s is None:
            sfx = "_front" if front else "_back"
            a = self.a
            s = a.tinted("pawn_skin" + sfx, frame, SKIN[p.look[0]]).copy()
            s.blit(a.tinted(body + sfx, frame, col), (0, 0))
            if acc != "acc_hood":
                s.blit(a.tinted("pawn_hair" + sfx, frame, HAIR[p.look[1]]), (0, 0))
            if acc:
                s.blit(a.get(acc)[0], (0, 0))
            if flip:
                s = pygame.transform.flip(s, True, False)
            if p.asleep:
                s = pygame.transform.rotate(s, 90)
            if len(self._pawn_cache) > 4000:
                self._pawn_cache.clear()
            self._pawn_cache[key] = s
        return (s, 9, 9) if p.asleep else (s, 6, 16)

    def fence_sprite(self, th, ghost):
        dirs = self.fence_dirs[self.rot]
        names = tuple(sorted(dirs[b] for b in range(4) if th.conn >> b & 1))
        gate = th.defn["kind"] == "gate"
        key = (gate, names, ghost)
        s = self._fence_cache.get(key)
        if s is None:
            a = self.a
            s = pygame.Surface(a.get("fence_post")[0].get_size(), pygame.SRCALPHA)
            for n in ("ne", "nw"):
                if n in names:
                    s.blit(a.get("fence_rail_" + n)[0], (0, 0))
            s.blit(a.get("gate_post" if gate else "fence_post")[0], (0, 0))
            for n in ("se", "sw"):
                if n in names:
                    s.blit(a.get("fence_rail_" + n)[0], (0, 0))
            if ghost:
                s.fill((150, 200, 255, 255), special_flags=pygame.BLEND_RGBA_MULT)
                s.set_alpha(150)
            self._fence_cache[key] = s
        return s

    # ------------------------------------------------------------ Zeichnen
    def draw(self, target, w, st, alpha=0.0):
        """st: dict mit hover, sel_pawn, sel_thing, sel_tile, preview [(x, y, sprite|zone, ok)], tick (Animationszeit)."""
        W, H = target.get_size()
        self.set_view(W, H)
        vw, vh = self.vw, self.vh
        if self._buf is None or self._buf.get_size() != (vw, vh):
            self._buf = pygame.Surface((vw, vh)).convert()
        buf = self._buf
        buf.fill((14, 17, 24))
        S, a = self.S, self.a
        ox, oy = self.ox, self.oy
        buf.blit(self.ground(w), (ox - S * 16 + 16 - 16, oy - 8))
        rxy = self.rxy
        tick = st.get("tick", 0)
        flat = []
        # Raum-Overlay
        if self.show_rooms:
            for r in w.rooms:
                col = ROOM_COL.get(r.role, (170, 170, 190))
                t = a.tinted("tile_mask", 0, col, 90)
                for i in r.tiles:
                    rx, ry = rxy(i % S, i // S)
                    flat.append((t, ((rx - ry) * 16 + ox - 16, (rx + ry) * 8 + oy - 8)))
        cur = a.get("cursor")[0]
        for x, y, what, ok in st.get("preview", ()):
            rx, ry = rxy(x, y)
            pos = ((rx - ry) * 16 + ox - 16, (rx + ry) * 8 + oy - 8)
            if isinstance(what, int):
                col = ZONES[what][1] if what in ZONES else (255, 90, 90)
                flat.append((a.tinted("tile_mask", 0, col, 130), pos))
            elif what is None:
                flat.append((a.tinted("tile_mask", 0, (255, 80, 80), 120), pos))
            elif DATA.buildables[what]["kind"] == "floor":
                flat.append((a.ghost(DATA.buildables[what]["sprite"], 0, ok), pos))
        for key, col in (("sel_tile", (255, 255, 255)), ("hover", (255, 240, 170))):
            t = st.get(key)
            if t and w.inb(*t):
                rx, ry = rxy(*t)
                flat.append((a.tinted("cursor", 0, col), ((rx - ry) * 16 + ox - 16, (rx + ry) * 8 + oy - 8)))
        sp = st.get("sel_pawn")
        if sp is not None and not sp.away:
            rx, ry = rxy(sp.x, sp.y)
            flat.append((a.tinted("cursor", 0, (120, 255, 140)), (int((rx - ry) * 16) + ox - 16, int((rx + ry) * 8) + oy - 8)))
        buf.blits(flat)

        items = []
        add = items.append
        low = self.low_walls
        has_low = {k: a.has(k + "_low") for k in ("wall_wood", "wall_stone", "door_wood")}
        sel_thing = st.get("sel_thing")
        for th in w.thing_list:
            rx, ry = rxy(th.x, th.y)
            sx, sy = (rx - ry) * 16 + ox, (rx + ry) * 8 + oy
            if sx < -24 or sx > vw + 24 or sy < -12 or sy > vh + 64:
                continue
            d = th.defn
            k = d["kind"]
            if k in ("fence", "gate"):
                s = self.fence_sprite(th, not th.built)
                ax, ay = a.frames("fence_post")[1:]
            else:
                sid = d["sprite"]
                if low and has_low.get(sid):
                    sid += "_low"
                fr, ax, ay = a.frames(sid)
                n = len(fr)
                f = 0 if n == 1 else (th.x * 7 + th.y * 13) % n if k == "nature" else (tick // 8 + th.id) % n
                s = fr[f] if th.built else a.ghost(sid, f)
            add((rx + ry, 1, s, (sx - ax, sy - ay)))
            if th is sel_thing:
                add((rx + ry + 0.01, 0, cur, (sx - 16, sy - 8)))
        if w.crops:
            cf, cax, cay = a.frames("crop")
            for i, g in w.crops.items():
                rx, ry = rxy(i % S, i // S)
                sx, sy = (rx - ry) * 16 + ox, (rx + ry) * 8 + oy
                if -24 < sx < vw + 24 and -12 < sy < vh + 30:
                    add((rx + ry - 0.05, 0, cf[min(3, int(g * 3.01))], (sx - cax, sy - cay)))
        for x, y, what, ok in st.get("preview", ()):
            if isinstance(what, str) and DATA.buildables[what]["kind"] != "floor":
                d = DATA.buildables[what]
                rx, ry = rxy(x, y)
                sx, sy = (rx - ry) * 16 + ox, (rx + ry) * 8 + oy
                sid = {"fence": "fence_post", "gate": "gate_post", "animal": "goat"}.get(d["kind"], d["sprite"])
                fr, ax, ay = a.frames(sid)
                add((rx + ry + 0.02, 2, a.ghost(sid, 0, ok), (sx - ax, sy - ay)))
        now = w.tick_n
        for p in w.pawns:
            if p.away:
                continue
            px, py = p.x, p.y
            j = p.job
            if alpha and p.moving and j is not None and j.path:
                nx, ny = j.path[0]
                dx, dy = nx - px, ny - py
                dd = math.hypot(dx, dy)
                if dd > 1e-6:
                    m = min(dd, p.speed * alpha) / dd
                    px += dx * m
                    py += dy * m
            rx, ry = rxy(px, py)
            sx, sy = int((rx - ry) * 16) + ox, int((rx + ry) * 8) + oy
            if sx < -20 or sx > vw + 20 or sy < -10 or sy > vh + 30:
                continue
            s, ax, ay = self.pawn_sprite(w, p, tick)
            dep = rx + ry + 0.06
            add((dep, 3, s, (sx - ax, sy - ay)))
            b = p.bubble
            if b is not None and b[1] > now:
                fs, fax, fay = a.get(b[0])
                add((dep, 4, fs, (sx - fax, sy - fay - 19)))
            elif p.fleeing:
                fs, fax, fay = a.get("fx_exclaim")
                add((dep, 4, fs, (sx - fax, sy - fay - 19)))
        items.sort(key=lambda t: (t[0], t[1]))
        buf.blits([(t[2], t[3]) for t in items])
        # Tageszeit
        h = w.hour
        night = 0.0
        if h < 5 or h >= 22:
            night = 1.0
        elif h < 7:
            night = (7 - h) / 2
        elif h >= 20:
            night = (h - 20) / 2
        if night > 0:
            c = (int(255 - 150 * night), int(255 - 128 * night), int(255 - 62 * night))
            buf.fill(c, special_flags=pygame.BLEND_RGB_MULT)
        if self.zoom == 1:
            target.blit(buf, (0, 0))
        else:
            target.blit(pygame.transform.scale(buf, (vw * self.zoom, vh * self.zoom)), (0, 0))
