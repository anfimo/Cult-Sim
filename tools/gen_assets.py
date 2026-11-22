#!/usr/bin/env python3
"""Placeholder art + sound generator for Cult-Sim.

Procedurally draws every placeholder sprite, synthesises the sfx / music and
writes ``assets/manifest.json`` (the contract between art and game code).

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy uv run python tools/gen_assets.py
    ... tools/gen_assets.py --preview <dir>   # also writes contact sheets + iso test scene
    ... tools/gen_assets.py --skip-audio      # sprites + manifest only (faster)

Deterministic (fixed seeds) and re-runnable.  pygame + stdlib only.

Iso conventions (must match the renderer):
  * tile diamond 32x16, tile (rx, ry) centre at sx=(rx-ry)*16, sy=(rx+ry)*8
  * sprite is blitted at (sx-ax, sy-ay)
  * object space used below: u,v in 0..16 across one tile (+u = screen down-right,
    +v = screen down-left), z = pixels up.  Light comes from the upper left.
  * pawn layer order (bottom -> top): skin, robe|civ, hair, accessory
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import wave
import zlib
from array import array
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SEED = 1977
TW, TH = 32, 16
SR = 22050


# --------------------------------------------------------------------------
# colour helpers / palette
# --------------------------------------------------------------------------
def hx(s: str):
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)


def mul(c, f):
    return (min(255, int(c[0] * f)), min(255, int(c[1] * f)), min(255, int(c[2] * f)), c[3] if len(c) > 3 else 255)


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t), 255)


OUT = hx("231c2b")
GRASS, GRASS_D, GRASS_L = hx("5f8f3e"), hx("4f7c36"), hx("72a04a")
DIRT, DIRT_D, DIRT_L = hx("8c6b45"), hx("78593a"), hx("9e7c53")
SAND, SAND_D, SAND_L = hx("d4c084"), hx("c3ad70"), hx("e2d29c")
ROCK, ROCK_D, ROCK_L = hx("84847e"), hx("6a6a67"), hx("9e9e96")
WATER, WATER_D, WATER_L = hx("3f72aa"), hx("35629a"), hx("86b4de")
WOOD, WOOD_D, WOOD_L = hx("9c6e3e"), hx("75512e"), hx("bb8c54")
BARK, BARK_D, BARK_L = hx("6e5136"), hx("523b28"), hx("876646")
STONE, STONE_D, STONE_L = hx("9a9a92"), hx("77776f"), hx("b9b9af")
PURPLE, PURPLE_D, PURPLE_L = hx("7b4bb3"), hx("57327f"), hx("a07ad2")
GOLD, GOLD_D, GOLD_L = hx("e0b040"), hx("a87c28"), hx("f6dc78")
CREAM, CREAM_D, WHITE = hx("e6dcc0"), hx("c2b594"), hx("f4f0e6")
IRON, IRON_D, IRON_L = hx("5a5662"), hx("3e3a46"), hx("8e8c98")
RED, RED_D = hx("c8483a"), hx("8e2c2c")
FIRE1, FIRE2, FIRE3, FIRE4 = hx("d8502a"), hx("f08a28"), hx("fcd858"), hx("fff4c0")
LEAF, LEAF_D, LEAF_L = hx("4e8a3c"), hx("376c36"), hx("78ae4a")
PINE, PINE_D, PINE_L = hx("3b7a52"), hx("28583f"), hx("5a9a5e")
SKIN = hx("e8b890")
BLUE, BLUE_D = hx("3a5c9e"), hx("263f72")
OLIVE, OLIVE_D, OLIVE_L = hx("6a7a3e"), hx("4a5a2a"), hx("8a9a56")


# --------------------------------------------------------------------------
# drawing primitives
# --------------------------------------------------------------------------
def rng_for(name: str) -> random.Random:
    return random.Random(zlib.crc32(name.encode()) ^ SEED)


def new(w, h):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    s.fill((0, 0, 0, 0))
    return s


def put(s, x, y, c):
    if 0 <= x < s.get_width() and 0 <= y < s.get_height():
        s.set_at((x, y), c)


def solid(s, x, y):
    return 0 <= x < s.get_width() and 0 <= y < s.get_height() and s.get_at((x, y))[3] >= 128


def rect(s, x, y, w, h, c):
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            put(s, xx, yy, c)


def paste(dst, src, ox, oy):
    """Raw pixel copy (no blending)."""
    for y in range(src.get_height()):
        for x in range(src.get_width()):
            dst.set_at((ox + x, oy + y), src.get_at((x, y)))


def strip(frames):
    w, h = frames[0].get_size()
    s = new(w * len(frames), h)
    for i, f in enumerate(frames):
        assert f.get_size() == (w, h)
        paste(s, f, i * w, 0)
    return s


def outline(s, strength=0.62, col=OUT):
    """Inner outline: darken every solid pixel that touches transparency."""
    w, h = s.get_size()
    edge = []
    for y in range(h):
        for x in range(w):
            if s.get_at((x, y))[3] < 128:
                continue
            if not (solid(s, x - 1, y) and solid(s, x + 1, y) and solid(s, x, y - 1) and solid(s, x, y + 1)):
                edge.append((x, y))
    for x, y in edge:
        s.set_at((x, y), mix(s.get_at((x, y)), col, strength))
    return s


def outline_outer(s, col=OUT):
    """Outer outline: grow the shape by one dark pixel (4-neighbourhood)."""
    w, h = s.get_size()
    add = []
    for y in range(h):
        for x in range(w):
            if s.get_at((x, y))[3] >= 128:
                continue
            if solid(s, x - 1, y) or solid(s, x + 1, y) or solid(s, x, y - 1) or solid(s, x, y + 1):
                add.append((x, y))
    for x, y in add:
        s.set_at((x, y), col)
    return s


def grain(s, rng, amt=0.07, p=0.35):
    """A little brightness noise so flat faces don't look flat."""
    for y in range(s.get_height()):
        for x in range(s.get_width()):
            c = s.get_at((x, y))
            if c[3] < 255:
                continue
            if rng.random() < p:
                s.set_at((x, y), mul(c, 1 + rng.uniform(-amt, amt)))
    return s


def shadow(s, cx, cy, rx, ry, alpha=64):
    for y in range(cy - ry, cy + ry + 1):
        for x in range(cx - rx, cx + rx):
            if ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / (ry + 0.5)) ** 2 <= 1:
                put(s, x, y, (20, 16, 28, alpha))


def art(rows, pal):
    """ASCII pixel art -> surface.  '.' is transparent."""
    w = len(rows[0])
    s = new(w, len(rows))
    for y, row in enumerate(rows):
        assert len(row) == w, f"bad row width {len(row)} != {w}: {row!r}"
        for x, ch in enumerate(row):
            if ch != ".":
                s.set_at((x, y), pal[ch])
    return s


def layer(dst, fn, ol=0.62):
    """Draw with fn() on a temp surface, outline it, composite onto dst."""
    t = new(*dst.get_size())
    fn(t)
    if ol:
        outline(t, ol)
    dst.blit(t, (0, 0))


# ---- tile diamond ---------------------------------------------------------
def _diamond():
    pts = []
    for y in range(16):
        k = y if y < 8 else 15 - y
        for x in range(16 - 2 * (k + 1), 16 + 2 * (k + 1)):
            pts.append((x, y))
    return pts


DIAMOND = _diamond()
DSET = set(DIAMOND)


def uv(x, y, ax=16, ay=8):
    """Tile-local (u, v) in 0..16 of the pixel centre."""
    dx, dy = x + 0.5 - ax, y + 0.5 - ay
    u = 8 + (dx + 2 * dy) / 2
    v = 8 + (2 * dy - dx) / 2
    return min(15.99, max(0.0, u)), min(15.99, max(0.0, v))


def P(A, u, v, z=0.0):
    """Object space -> pixel inside a sprite whose anchor is A."""
    return (math.floor(A[0] + (u - v)), math.floor(A[1] + (u + v - 16) / 2 - z))


def box(s, A, foot, zz, tex, ol=0.62, shade=(1.12, 0.92, 0.70)):
    """Pixel-exact iso box.  foot=(u0,v0,u1,v1) in 0..16, zz=(z0,z1) px.

    A full-tile footprint reproduces the tile diamond exactly.  ``tex`` is a
    colour or ``tex(face, u, v, z) -> colour|None`` with face in top/left/right
    (left = sw-facing = medium, right = se-facing = darkest).
    """
    ax, ay = A
    u0, v0, u1, v1 = foot
    z0, z1 = zz
    a0, a1 = 2 * (u0 - 8) - 1, 2 * (u1 - 8) + 1
    b0, b1 = 2 * (v0 - 8) - 1, 2 * (v1 - 8) + 1
    fn = tex if callable(tex) else (lambda face, u, v, z: tex)
    xc = u1 - v1
    w, h = s.get_size()
    t = new(w, h)
    for py in range(h):
        dyy = py + 0.5 - ay
        for px in range(w):
            dx = px + 0.5 - ax
            a = dx + 2 * (dyy + z1)
            b = 2 * (dyy + z1) - dx
            if a0 <= a <= a1 and b0 <= b <= b1:
                face, u, v, z, f = "top", 8 + a / 2, 8 + b / 2, z1, shade[0]
            else:
                zlo = max(z0, (a0 - dx) / 2 - dyy, (b0 + dx) / 2 - dyy)
                zhi = min(z1, (a1 - dx) / 2 - dyy, (b1 + dx) / 2 - dyy)
                if zlo > zhi:
                    continue
                if dx < xc:
                    u, v = dx + v1, v1
                    face, z, f = "left", (u + v1 - 16) / 2 - dyy, shade[1]
                else:
                    u, v = u1, u1 - dx
                    face, z, f = "right", (u1 + v - 16) / 2 - dyy, shade[2]
            c = fn(face, u, v, z)
            if c is None:
                continue
            c = mul(c, f)
            if face != "top" and z1 - z0 >= 3 and z > z1 - 1.0:
                c = mul(c, 1.13)  # lit rim under the top edge
            t.set_at((px, py), c)
    if ol:
        outline(t, ol)
    s.blit(t, (0, 0))


def column(s, x, y_top, y_bot, w, cols, ol=0.62):
    """Vertical post in screen space, lit from the left."""
    def d(t):
        for y in range(y_top, y_bot + 1):
            for i in range(w):
                c = cols[0] if i == 0 else cols[2] if i == w - 1 and w > 2 else cols[1]
                put(t, x + i, y, c)
    layer(s, d, ol)


def flame(s, cx, base, h, w, phase, core=False):
    for t in range(h):
        f = t / (h - 1) if h > 1 else 0.0
        y = base - t
        half = w * math.sin(math.pi * (0.25 + 0.75 * f))
        sway = math.sin(f * 2.6 + phase) * f * w * 0.55
        for x in range(int(cx - 2 * w - 2), int(cx + 2 * w + 3)):
            d = abs(x + 0.5 - (cx + sway))
            if d <= half + 0.25:
                k = d / max(half, 0.4) + f * 0.65
                c = FIRE3 if k < 0.42 else FIRE2 if k < 0.85 else FIRE1
                if core and k < 0.18:
                    c = FIRE4
                put(s, x, y, c)


def blob(s, circles, tones, rng, speck=0.07):
    """Foliage: union of circles, each lit from the upper left, dithered."""
    li, mi, da = tones
    for y in range(s.get_height()):
        for x in range(s.get_width()):
            best = None
            for cx, cy, r in circles:
                d = math.hypot(x + 0.5 - cx, y + 0.5 - cy) / r
                if d <= 1 and (best is None or d < best[0]):
                    best = (d, cx, cy, r)
            if best is None:
                continue
            _, cx, cy, r = best
            lgt = -((x + 0.5 - cx) * 0.55 + (y + 0.5 - cy) * 0.8) / r
            if lgt > 0.38:
                c = li
            elif lgt > 0.28:
                c = li if (x + y) % 2 else mi
            elif lgt > -0.22:
                c = mi
            elif lgt > -0.34:
                c = mi if (x + y) % 2 else da
            else:
                c = da
            q = rng.random()
            if q < speck:
                c = mul(c, 0.86)
            elif q > 1 - speck:
                c = mul(c, 1.12)
            s.set_at((x, y), c)


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------
SPRITES: dict[str, tuple[pygame.Surface, tuple[int, int], int]] = {}


def reg(sid, surf_or_frames, anchor):
    if isinstance(surf_or_frames, (list, tuple)):
        n = len(surf_or_frames)
        surf = strip(surf_or_frames)
    else:
        n, surf = 1, surf_or_frames
    assert sid not in SPRITES, sid
    SPRITES[sid] = (surf, tuple(anchor), n)


# --------------------------------------------------------------------------
# ground tiles (32x16, anchor 16,8)
# --------------------------------------------------------------------------
def ground(name, fn):
    rng = rng_for(name)
    s = new(32, 16)
    for x, y in DIAMOND:
        u, v = uv(x, y)
        s.set_at((x, y), fn(rng, x, y, u, v))
    return s


def speckle(base, dark, light, pd=0.16, pl=0.14):
    def fn(rng, x, y, u, v):
        r = rng.random()
        return dark if r < pd else light if r > 1 - pl else base
    return fn


def interior_points(rng, n, margin=2):
    pts = [(x, y) for x, y in DIAMOND if all((x + dx, y + dy) in DSET for dx in (-margin * 2, margin * 2) for dy in (-margin, margin))]
    return [pts[rng.randrange(len(pts))] for _ in range(n)]


def make_ground():
    # grass
    frames = []
    for i in range(4):
        s = ground(f"grass{i}", speckle(GRASS, GRASS_D, GRASS_L))
        rng = rng_for(f"grassdeco{i}")
        for x, y in interior_points(rng, 5):  # tufts
            s.set_at((x, y), mul(GRASS_L, 1.08))
            s.set_at((x, y + 1), mul(GRASS_D, 0.9))
        if i == 2:
            for (x, y), c in zip(interior_points(rng, 3), (WHITE, GOLD_L, WHITE)):
                s.set_at((x, y), c)
        if i == 3:
            for (x, y), c in zip(interior_points(rng, 2), (PURPLE_L, GOLD_L)):
                s.set_at((x, y), c)
            x, y = interior_points(rng, 1)[0]
            s.set_at((x, y), ROCK_L)
            s.set_at((x + 1, y), ROCK)
        frames.append(s)
    reg("terrain_grass", frames, (16, 8))

    # dirt
    frames = []
    for i in range(2):
        s = ground(f"dirt{i}", speckle(DIRT, DIRT_D, DIRT_L, 0.18, 0.14))
        rng = rng_for(f"dirtdeco{i}")
        for x, y in interior_points(rng, 2 + i):
            s.set_at((x, y), ROCK_L)
            s.set_at((x + 1, y), ROCK)
            s.set_at((x, y + 1), mul(DIRT_D, 0.85))
        frames.append(s)
    reg("terrain_dirt", frames, (16, 8))

    # sand
    frames = []
    for i in range(2):
        s = ground(f"sand{i}", speckle(SAND, SAND_D, SAND_L, 0.10, 0.12))
        rng = rng_for(f"sanddeco{i}")
        for x, y in interior_points(rng, 3):  # little ripples
            for k in range(3):
                s.set_at((x + k, y), SAND_D)
        if i == 1:
            x, y = interior_points(rng, 1)[0]
            s.set_at((x, y), WHITE)
        frames.append(s)
    reg("terrain_sand", frames, (16, 8))

    # rock
    frames = []
    for i in range(2):
        s = ground(f"rock{i}", speckle(ROCK, ROCK_D, ROCK_L, 0.14, 0.16))
        rng = rng_for(f"rockdeco{i}")
        for x, y in interior_points(rng, 3):  # cracks
            sx = rng.choice((-1, 1))
            for k in range(4):
                p = (x + sx * k, y + k // 2)
                if p in DSET:
                    s.set_at(p, mul(ROCK_D, 0.78))
        for x, y in interior_points(rng, 3):  # lit facets
            s.set_at((x, y), mul(ROCK_L, 1.08))
            s.set_at((x + 1, y), mul(ROCK_L, 1.08))
        frames.append(s)
    reg("terrain_rock", frames, (16, 8))

    # road: cobbles laid out in tile space so they tessellate
    frames = []
    for i in range(2):
        tones = (hx("a89a80"), hx("9a8c74"), hx("b4a68c"), hx("a09684"))

        def road(rng, x, y, u, v, i=i, tones=tones):
            row = int(v // 4)
            uu = (u + 2 * (row % 2) + i * 1.0) % 16
            if (uu % 4) < 1.0 or (v % 4) < 1.0:
                return hx("756a58")
            cell = (int(uu // 4) * 7 + row * 13 + i * 5) % len(tones)
            c = tones[cell]
            return mul(c, 0.93) if rng.random() < 0.15 else c
        frames.append(ground(f"road{i}", road))
    reg("terrain_road", frames, (16, 8))

    # water (2 animation frames)
    frames = []
    rngd = rng_for("waterdashes")
    dashes = [(rngd.randrange(0, 32), rngd.randrange(1, 15), rngd.choice((2, 3, 3, 4))) for _ in range(9)]
    for i in range(2):
        s = ground(f"water{i}", speckle(WATER, WATER_D, mul(WATER, 1.07), 0.14, 0.12))
        for n, (x, y, ln) in enumerate(dashes):
            xx = (x + 3 * i) % 32
            yy = y + (i if n % 2 else 0)
            for k in range(ln):
                if (xx + k, yy) in DSET:
                    s.set_at((xx + k, yy), WATER_L if n % 3 else mul(WATER_L, 1.12))
                if (xx + k + 1, yy + 1) in DSET and n % 2 == 0:
                    s.set_at((xx + k + 1, yy + 1), mul(WATER_D, 0.92))
        frames.append(s)
    reg("terrain_water", frames, (16, 8))

    # floors
    def f_wood(rng, x, y, u, v):
        row = int(v // 4)
        if v % 4 < 1.0:
            return mul(WOOD_D, 0.9)
        if int(u) == (row * 5 + 3) % 16:
            return mul(WOOD_D, 0.95)
        c = WOOD_L if row % 2 else mix(WOOD_L, WOOD, 0.45)
        return mul(c, 0.93) if rng.random() < 0.14 else c
    reg("floor_wood", ground("floor_wood", f_wood), (16, 8))

    def f_stone(rng, x, y, u, v):
        row = int(v // 8)
        uu = (u + 4 * (row % 2)) % 16
        if uu % 8 < 1.0 or v % 8 < 1.0:
            return STONE_D
        c = (STONE, STONE_L, mix(STONE, STONE_L, 0.5), mul(STONE, 0.95))[(int(uu // 8) + row * 2) % 4]
        r = rng.random()
        return mul(c, 0.93) if r < 0.14 else mul(c, 1.05) if r > 0.9 else c
    reg("floor_stone", ground("floor_stone", f_stone), (16, 8))

    def f_carpet(rng, x, y, u, v):
        e = min(u, v, 16 - u, 16 - v)
        d = abs(u - 8) + abs(v - 8)
        if 1.2 <= e < 2.2:
            return GOLD
        if d < 2.6:
            return GOLD if d >= 1.3 else PURPLE_D
        c = PURPLE if (x + y) % 2 else mul(PURPLE, 0.93)
        if e < 1.2:
            c = mul(c, 0.86)
        return c
    reg("floor_carpet", ground("floor_carpet", f_carpet), (16, 8))

    def f_tile(rng, x, y, u, v):
        if u % 8 < 0.8 or v % 8 < 0.8:
            return hx("8f8a80")
        c = hx("d9d3c1") if (int(u // 8) + int(v // 8)) % 2 == 0 else hx("8fa6a2")
        return mul(c, 0.95) if rng.random() < 0.12 else c
    reg("floor_tile", ground("floor_tile", f_tile), (16, 8))

    def f_soil(rng, x, y, u, v):
        k = v % 4
        c = hx("58402c") if k < 1.2 else hx("7c5e3e") if k < 3 else hx("906f49")
        r = rng.random()
        return mul(c, 0.9) if r < 0.15 else mul(c, 1.08) if r > 0.9 else c
    reg("floor_soil", ground("floor_soil", f_soil), (16, 8))

    # mask + cursor
    m = new(32, 16)
    for p in DIAMOND:
        m.set_at(p, (255, 255, 255, 255))
    reg("tile_mask", m, (16, 8))
    c = new(32, 16)
    for x, y in DIAMOND:
        if not all(q in DSET for q in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))):
            c.set_at((x, y), (255, 255, 255, 255))
    reg("cursor", c, (16, 8))


# --------------------------------------------------------------------------
# nature
# --------------------------------------------------------------------------
def make_nature():
    # crop: 4 growth stages on a 32x24 canvas
    A = (16, 16)
    spots = sorted(((u, v) for u in (3, 8, 13) for v in (3, 8, 13)), key=lambda p: p[0] + p[1])
    frames = []
    for st in range(4):
        s = new(32, 24)
        rng = rng_for(f"crop{st}")
        for u, v in spots:
            x, y = P(A, u + rng.uniform(-0.6, 0.6), v + rng.uniform(-0.6, 0.6))
            if st == 0:
                put(s, x, y, LEAF_D)
                put(s, x, y - 1, LEAF_L)
                put(s, x + 1, y - 2, LEAF_L)
                put(s, x - 1, y - 2, LEAF)
            elif st == 1:
                for k in range(4):
                    put(s, x, y - k, LEAF if k else LEAF_D)
                put(s, x - 1, y - 2, LEAF_L)
                put(s, x + 1, y - 3, LEAF_L)
                put(s, x - 1, y - 4, LEAF_L)
                put(s, x + 1, y - 1, LEAF_D)
            elif st == 2:
                for k in range(7):
                    put(s, x, y - k, LEAF if k > 1 else LEAF_D)
                for k, sx in ((2, -1), (3, 1), (4, -1), (5, 1), (6, -1)):
                    put(s, x + sx, y - k, LEAF_L)
                put(s, x - 2, y - 3, LEAF)
                put(s, x + 2, y - 4, LEAF)
                put(s, x, y - 7, hx("b8c060"))
                put(s, x, y - 8, hx("b8c060"))
            else:
                for k in range(7):
                    put(s, x, y - k, hx("9a9a44") if k > 1 else hx("6e7a36"))
                put(s, x - 1, y - 2, hx("8aa24a"))
                put(s, x + 1, y - 3, hx("8aa24a"))
                put(s, x - 1, y - 5, hx("b0a850"))
                for k in range(7, 11):  # ripe golden ear
                    put(s, x, y - k, GOLD_L if k % 2 else GOLD)
                    put(s, x - 1, y - k, GOLD)
                    put(s, x + 1, y - k, GOLD_D)
                put(s, x, y - 11, GOLD_L)
        frames.append(s)
    reg("crop", frames, A)

    # trees 32x52, anchor (16,44)
    A = (16, 44)
    frames = []
    s = new(32, 52)
    rng = rng_for("tree0")
    shadow(s, 16, 44, 11, 4)

    def trunk(t):
        for y in range(24, 46):
            hw = 2 if y < 42 else 3 if y < 45 else 4
            for x in range(16 - hw, 16 + hw):
                c = BARK_L if x < 15 else BARK if x < 17 else BARK_D
                if (x * 3 + y) % 7 == 0:
                    c = mul(c, 0.85)
                put(t, x, y, c)
    layer(s, trunk)
    layer(s, lambda t: blob(t, [(16, 16, 11), (9, 21, 7), (23, 21, 7), (12, 10, 7), (20, 10, 7), (16, 25, 6)], (LEAF_L, LEAF, LEAF_D), rng))
    frames.append(s)

    s = new(32, 52)
    rng = rng_for("tree1")
    shadow(s, 16, 44, 9, 3)
    column(s, 14, 36, 45, 4, (BARK_L, BARK, BARK_D))
    for apex, base, hw in ((18, 39, 13), (9, 29, 10), (1, 19, 7)):
        def tier(t, apex=apex, base=base, hw=hw):
            for y in range(apex, base + 1):
                f = (y - apex + 1) / (base - apex + 1)
                half = max(1, int(round(hw * f)))
                if (y - apex) % 4 == 3:
                    half = max(1, half - 1)  # jagged boughs
                for x in range(16 - half, 16 + half):
                    lgt = (16 - (x + 0.5)) / max(half, 1) * 0.8 + (0.35 - f) * 0.6
                    if y >= base - 1:
                        c = PINE_D
                    elif lgt > 0.35:
                        c = PINE_L
                    elif lgt > 0.2:
                        c = PINE_L if (x + y) % 2 else PINE
                    elif lgt > -0.35:
                        c = PINE
                    elif lgt > -0.5:
                        c = PINE if (x + y) % 2 else PINE_D
                    else:
                        c = PINE_D
                    if rng.random() < 0.07:
                        c = mul(c, 0.88)
                    put(t, x, y, c)
        layer(s, tier)
    frames.append(s)
    reg("tree", frames, A)

    # bush 32x20, anchor (16,12)
    s = new(32, 20)
    rng = rng_for("bush")
    shadow(s, 16, 13, 11, 3)
    layer(s, lambda t: blob(t, [(11, 10, 6), (17, 8, 7), (22, 11, 5), (15, 12, 5)], (LEAF_L, LEAF, LEAF_D), rng))
    for x, y in ((10, 8), (16, 5), (20, 9), (14, 11), (22, 12)):
        put(s, x, y, hx("c0455a"))
        put(s, x, y + 1, hx("8a2c44"))
    reg("bush", s, (16, 12))

    # boulder 32x22, anchor (16,14)
    s = new(32, 22)
    rng = rng_for("boulder")
    shadow(s, 16, 15, 12, 4)

    def rock(t):
        pygame.draw.polygon(t, ROCK, [(6, 15), (8, 8), (14, 3), (22, 4), (27, 11), (25, 17), (16, 19), (8, 18)])
        pygame.draw.polygon(t, ROCK_L, [(8, 8), (14, 3), (22, 4), (19, 9), (11, 11)])
        pygame.draw.polygon(t, ROCK_D, [(22, 4), (27, 11), (25, 17), (20, 18), (19, 9)])
        for x, y in ((12, 13), (13, 14), (14, 14), (15, 15), (10, 12)):
            put(t, x, y, mul(ROCK_D, 0.85))
        for x, y in ((9, 9), (10, 8), (12, 6)):
            put(t, x, y, mul(ROCK_L, 1.1))
        for x, y in ((8, 15), (9, 16), (10, 16), (9, 15), (20, 6), (21, 6)):
            put(t, x, y, LEAF if (x + y) % 2 else LEAF_D)  # moss
    layer(s, rock)
    grain(s, rng)
    reg("boulder", s, (16, 14))


# --------------------------------------------------------------------------
# walls / doors / fences
# --------------------------------------------------------------------------
def wood_wall_tex(h):
    def tex(face, u, v, z):
        if face == "top":
            e = min(u, v, 16 - u, 16 - v)
            return WOOD_L if e > 1.5 else mix(WOOD_L, WOOD, 0.6)
        s_ = int(u if face == "left" else v)
        if s_ % 4 == 0:
            return mul(WOOD_D, 0.92)
        c = WOOD if (s_ // 4) % 2 == 0 else mix(WOOD, WOOD_L, 0.35)
        if z < 2 and (s_ + int(z)) % 2 == 0:
            c = mul(c, 0.86)  # dithered contact shadow
        if int(z) == (s_ // 4 * 5 + 6) % 13 and s_ % 4 == 2:
            c = WOOD_D  # knot
        return c
    return tex


def stone_wall_tex(h):
    def tex(face, u, v, z):
        if face == "top":
            e = min(u, v, 16 - u, 16 - v)
            return STONE_L if e > 1.5 else mix(STONE_L, STONE, 0.6)
        s_ = int(u if face == "left" else v)
        row = int(max(z, 0)) // 4
        if int(max(z, 0)) % 4 == 3 and z < h - 1.5:
            return STONE_D
        if (s_ + 4 * (row % 2)) % 8 == 0:
            return STONE_D
        cell = ((s_ + 4 * (row % 2)) // 8 + row * 3) % 4
        c = (STONE, mix(STONE, STONE_L, 0.4), mul(STONE, 0.94), mix(STONE, hx("a09a86"), 0.6))[cell]
        if z < 2 and (s_ + int(z)) % 2 == 0:
            c = mul(c, 0.88)
        return c
    return tex


DOOR, DOOR_FRAME = hx("d2a868"), hx("4e3220")


def door_tex(h):
    wall = wood_wall_tex(h)
    top = min(13, h)

    def tex(face, u, v, z):
        if face == "top":
            if h < 13:  # cut-away: show the door leaf / threshold from above
                e = min(u, v, 16 - u, 16 - v)
                if e < 1.5:
                    return mix(WOOD_L, WOOD, 0.6)
                if e < 3:
                    return DOOR_FRAME
                return DOOR if int(u + v) % 4 else mul(DOOR, 0.9)
            return wall(face, u, v, z)
        s_ = u if face == "left" else v
        if 3 <= s_ < 13 and z < top:
            if s_ < 4 or s_ >= 12 or (h >= 13 and z >= top - 1):
                return DOOR_FRAME
            if 10 <= s_ < 11 and 5 <= z < 7:
                return GOLD_L  # knob
            if int(s_) in (6, 8) or (h >= 13 and int(z) in (3, 9)):
                return mul(DOOR, 0.84)  # planks + cross battens
            return DOOR
        return wall(face, u, v, z)
    return tex


def make_blocks():
    for name, texf in (("wall_wood", wood_wall_tex), ("wall_stone", stone_wall_tex), ("door_wood", door_tex)):
        for suffix, h in (("", 16), ("_low", 5)):
            s = new(32, 16 + h)
            box(s, (16, 8 + h), (0, 0, 16, 16), (0, h), texf(h), ol=0.42)
            grain(s, rng_for(name + suffix), 0.05)
            reg(name + suffix, s, (16, 8 + h))

    # fences: canvas 32x28, anchor (16,20)
    A = (16, 20)
    s = new(32, 28)
    column(s, 14, 9, 20, 4, (WOOD_L, WOOD, WOOD_D))
    put(s, 15, 10, mul(WOOD_L, 1.12))
    put(s, 16, 10, WOOD_L)
    reg("fence_post", s, A)

    def rail(direction):
        s = new(32, 28)
        for x in (range(16, 24) if direction in ("se", "ne") else range(8, 16)):
            off = {"se": (x - 16) // 2, "sw": (15 - x) // 2,
                   "ne": -((x - 16) // 2) - 1, "nw": -((15 - x) // 2) - 1}[direction]
            lit = direction in ("sw", "ne")  # planks seen on their sw-facing side are lighter
            for z in (8, 4):
                y = 20 - z + off
                put(s, x, y, WOOD_L if lit else mix(WOOD_L, WOOD, 0.6))
                put(s, x, y + 1, WOOD if lit else WOOD_D)
                put(s, x, y + 2, mix(WOOD_D, OUT, 0.55))
        return s
    for d in ("ne", "nw", "se", "sw"):
        reg(f"fence_rail_{d}", rail(d), A)

    s = new(32, 28)
    column(s, 10, 5, 20, 4, (WOOD_L, WOOD, WOOD_D))
    column(s, 18, 5, 20, 4, (WOOD_L, WOOD, WOOD_D))

    def lintel(t):
        rect(t, 8, 2, 16, 1, WOOD_L)
        rect(t, 8, 3, 16, 2, WOOD)
        rect(t, 8, 5, 16, 1, WOOD_D)
    layer(s, lintel)

    def pennant(t):
        for i, wd in enumerate((4, 4, 4, 3, 2, 2, 1)):
            for k in range(wd):
                put(t, 14 + k + (4 - wd) // 2, 6 + i, PURPLE_L if k == 0 else PURPLE)
        put(t, 15, 8, GOLD)
        put(t, 16, 8, GOLD)
    layer(s, pennant)
    put(s, 15, 1, GOLD)
    put(s, 16, 1, GOLD_D)
    put(s, 15, 0, GOLD_L)
    reg("gate_post", s, A)


# --------------------------------------------------------------------------
# furniture
# --------------------------------------------------------------------------
def bowl(s, x, y, food):
    for i, c in enumerate((CREAM, food, food, CREAM_D)):
        put(s, x + i, y, c)
    put(s, x, y + 1, mix(CREAM_D, OUT, 0.4))
    put(s, x + 1, y + 1, CREAM_D)
    put(s, x + 2, y + 1, CREAM_D)
    put(s, x + 3, y + 1, mix(CREAM_D, OUT, 0.5))
    put(s, x + 1, y + 2, mix(WOOD, OUT, 0.45))
    put(s, x + 2, y + 2, mix(WOOD, OUT, 0.45))


def candle(s, x, y, h=3):
    """Candle whose base pixel is (x, y)."""
    for k in range(h):
        put(s, x, y - k, CREAM if k else CREAM_D)
    put(s, x, y - h, FIRE3)
    put(s, x, y - h - 1, FIRE2)


def make_furniture():
    A = (16, 24)

    # --- bed (simple cot) ---
    s = new(32, 32)
    box(s, A, (1, 4, 2.5, 12), (0, 9), WOOD_D)                      # headboard
    box(s, A, (2, 4, 15, 12), (0, 3), WOOD)                         # frame
    box(s, A, (2.5, 4.5, 14.5, 11.5), (3, 5), CREAM)                # mattress
    box(s, A, (3, 5.5, 6, 10.5), (5, 7), WHITE)                     # pillow

    def blanket(face, u, v, z):
        if face == "top" and u < 8:
            return hx("9aa878")
        return hx("7d8f62") if int(u + v) % 3 else hx("72845a")
    box(s, A, (7, 4.5, 14.5, 11.5), (3, 6), blanket)
    grain(s, rng_for("bed"), 0.05)
    reg("bed", s, A)

    # --- guru bed ---
    s = new(32, 32)

    def head(face, u, v, z):
        if face == "right" and 4 <= v < 12 and 6 <= z < 12:
            return PURPLE if not (7 <= v < 9 and 8 <= z < 10) else GOLD_L
        return GOLD
    box(s, A, (0.5, 2, 2.5, 14), (0, 14), head)
    box(s, A, (2, 2, 15.5, 14), (0, 4), lambda f, u, v, z: GOLD if z > 2.6 or f == "top" else WOOD_D)
    box(s, A, (2.5, 2.5, 15, 13.5), (4, 6), CREAM)
    box(s, A, (3, 3.5, 6, 7.5), (6, 8), lambda f, u, v, z: WHITE if f == "top" else GOLD_L)
    box(s, A, (3, 8.5, 6, 12.5), (6, 8), lambda f, u, v, z: WHITE if f == "top" else GOLD_L)

    def cover(face, u, v, z):
        if face == "top":
            if u < 8.2 or u > 13.6:
                return GOLD
            if abs(u - 11) + abs(v - 8) < 1.8:
                return GOLD_L
            return PURPLE if int(u + v) % 2 else PURPLE_L
        return GOLD if z < 5.2 else PURPLE
    box(s, A, (7, 2.5, 15, 13.5), (4, 7), cover)
    grain(s, rng_for("bed_guru"), 0.04)
    reg("bed_guru", s, A)

    # --- table ---
    s = new(32, 32)
    for u, v in ((2.5, 3.5), (12, 3.5), (2.5, 11), (12, 11)):
        box(s, A, (u, v, u + 1.5, v + 1.5), (0, 6), WOOD_D)

    def ttop(face, u, v, z):
        if face == "top":
            return WOOD_L if int(v) % 4 else WOOD
        return WOOD
    box(s, A, (1.5, 2.5, 14.5, 13.5), (6, 8), ttop)
    grain(s, rng_for("table"), 0.04)
    bowl(s, 8, 15, hx("c8642c"))
    bowl(s, 19, 14, hx("6f9a40"))
    bowl(s, 14, 19, hx("c8642c"))
    rect(s, 15, 12, 2, 3, hx("8fa8b4"))  # jug
    put(s, 15, 12, hx("d0dce0"))
    put(s, 16, 14, hx("6a8490"))
    reg("table", s, A)

    # --- stove ---
    s = new(32, 32)
    column(s, 15, 3, 14, 3, (IRON_L, IRON, IRON_D))                 # flue at the back

    def stove(face, u, v, z):
        if face == "top":
            d = math.hypot(u - 8, v - 8)
            return IRON_D if 2.6 < d < 3.6 else IRON_L
        s_ = u if face == "left" else v
        if 4.5 <= s_ < 11.5 and 1.5 <= z < 7.5:
            if 5.5 <= s_ < 10.5 and 2.5 <= z < 6.5:
                return FIRE3 if (int(s_) + int(z)) % 2 else FIRE2
            return IRON_D
        if z > 8.5:
            return IRON_L
        return IRON
    box(s, A, (2.5, 2.5, 13.5, 13.5), (0, 10), stove, shade=(1.12, 0.95, 0.74))

    def pot(face, u, v, z):
        if face == "top":
            return hx("c8783a") if math.hypot(u - 8, v - 8) < 2.0 else hx("b4b4bc")
        return hx("a4a4ae")
    box(s, A, (5.5, 5.5, 10.5, 10.5), (10, 14), pot)
    put(s, 10, 12, IRON_D)
    put(s, 21, 12, IRON_D)
    for x, y in ((15, 6), (16, 5), (15, 4), (17, 7)):
        put(s, x, y, (236, 236, 240, 200))                          # steam
    grain(s, rng_for("stove"), 0.05)
    reg("stove", s, A)

    # --- altar ---
    s = new(32, 32)
    box(s, A, (2, 4, 14, 12), (0, 2), STONE_D)

    def abody(face, u, v, z):
        if face == "left" and 5.5 <= u < 10.5:
            if z < 3.6:
                return GOLD if int(u * 2) % 2 else GOLD_D
            if 7 <= u < 9 and 5 <= z < 7:
                return GOLD_L
            return PURPLE
        if face == "right" and 6.5 <= v < 9.5 and 3.5 <= z < 6.5:
            return GOLD if not (7.5 <= v < 8.5 and 4.5 <= z < 5.5) else PURPLE_D
        return STONE
    box(s, A, (3, 5, 13, 11), (2, 8), abody)

    def slab(face, u, v, z):
        if 5.5 <= u < 10.5 and face in ("top", "left"):
            return PURPLE_L if face == "top" else PURPLE
        return STONE_L
    box(s, A, (2, 4, 14, 12), (8, 10), slab)
    # golden idol (eye-in-triangle) + two candles
    for x, y, c in ((16, 9, GOLD_L), (15, 10, GOLD_L), (16, 10, GOLD), (17, 10, GOLD_D), (14, 11, GOLD_L), (15, 11, GOLD),
                    (16, 11, PURPLE_D), (17, 11, GOLD), (18, 11, GOLD_D), (14, 12, GOLD_D), (15, 12, GOLD_D), (16, 12, GOLD_D),
                    (17, 12, GOLD_D), (18, 12, GOLD_D)):
        put(s, x, y, c)
    candle(s, 9, 10, 3)
    candle(s, 22, 15, 3)
    candle(s, 11, 14, 2)
    grain(s, rng_for("altar"), 0.05)
    reg("altar", s, A)

    # --- desk ---
    s = new(32, 32)

    def ped(face, u, v, z):
        if face == "left" and int(z) in (3,):
            return WOOD_D
        if face == "left" and int(z) in (5, 1) and int(u) % 4 == 0:
            return GOLD
        return WOOD
    box(s, A, (2, 4.5, 6, 11.5), (0, 7), ped)
    box(s, A, (10, 4.5, 14, 11.5), (0, 7), ped)
    box(s, A, (1.5, 4, 14.5, 12), (7, 9), lambda f, u, v, z: WOOD_L if f == "top" else WOOD)

    def paper(face, u, v, z):
        return WHITE if int(u * 1.5) % 2 else hx("c9c9cf")
    box(s, A, (9, 5.5, 13, 10.5), (9, 9), paper, ol=0.25)
    box(s, A, (7, 9, 9.5, 11.5), (9, 9), lambda f, u, v, z: WHITE, ol=0.25)

    def cash(face, u, v, z):
        if face == "top":
            return hx("7f9a78")
        if face == "left" and 4 <= u < 5.2 and 9.8 <= z < 11.2:
            return GOLD_L
        return hx("5e7a5a")
    box(s, A, (3, 6, 6.5, 9.5), (9, 12), cash)
    put(s, 19, 20, GOLD_L)
    put(s, 20, 20, GOLD)
    put(s, 17, 21, GOLD)
    grain(s, rng_for("desk"), 0.04)
    reg("desk", s, A)

    # --- printing press ---
    s = new(32, 32)
    box(s, A, (2, 2.5, 14, 10), (0, 6), lambda f, u, v, z: WOOD if f == "top" or z > 4.5 else WOOD_D)

    def pbed(face, u, v, z):                                         # type bed with a fresh sheet
        if face == "top" and 5 <= u < 11 and 4 <= v < 8.5:
            return WHITE if int(u) % 2 else hx("c9c9cf")
        return IRON
    box(s, A, (3.5, 3.5, 12.5, 9), (6, 7), pbed, ol=0.4)
    box(s, A, (2.5, 5.25, 4.5, 7.25), (6, 20), WOOD)                # back upright
    box(s, A, (5.5, 4.5, 10.5, 8), (10, 11.5), IRON_L)              # platen

    def screw(t):
        for y in range(5, 14):
            put(t, 15, y, IRON_L if y % 2 else hx("c4c2ce"))
            put(t, 16, y, IRON if y % 2 else IRON_L)
    layer(s, screw, 0)
    box(s, A, (11.5, 5.25, 13.5, 7.25), (6, 20), WOOD)              # front upright
    box(s, A, (2.5, 5.25, 13.5, 7.25), (18, 20.5), WOOD_L)          # head beam
    grain(s, rng_for("printer"), 0.04)
    for k in range(8):                                               # lever through the screw
        put(s, 12 + k, 8 + k // 3, GOLD if k < 6 else GOLD_L)
        put(s, 12 + k, 9 + k // 3, GOLD_D)

    def stack(face, u, v, z):
        if face == "top":
            if 6.5 <= u < 9.5 and 11.5 <= v < 12.6:
                return PURPLE
            if 6.5 <= u < 9.5 and (13 <= v < 13.6 or 14 <= v < 14.5):
                return hx("9a9aa2")
            return WHITE
        return WHITE if int(z * 1.5) % 2 else hx("a9a9b3")
    box(s, A, (5.5, 10.75, 10.5, 15.25), (0, 5), stack, ol=0.5, shade=(1.0, 0.95, 0.8))
    reg("printer", s, A)

    # --- crate ---
    s = new(32, 32)

    def crate(face, u, v, z):
        lo, hi = 3, 13
        if face == "top":
            e = min(u - lo, hi - u, v - lo, hi - v)
            if e < 1.5:
                return WOOD
            return hx("d0a468") if int(u) % 3 else WOOD_L
        s_ = (u if face == "left" else v) - lo
        if s_ < 1.6 or s_ > 8.4 or z < 1.6 or z > 8.4:
            return WOOD_D
        if abs(s_ - z) < 1.0:
            return WOOD_D
        return hx("d0a468") if int(s_) % 3 else WOOD_L
    box(s, A, (3, 3, 13, 13), (0, 10), crate)
    grain(s, rng_for("crate"), 0.05)
    reg("crate", s, A)

    # --- donation box ---
    s = new(32, 32)
    box(s, A, (5.5, 5.5, 10.5, 10.5), (0, 7), lambda f, u, v, z: WOOD_D if z < 1.5 else WOOD)

    def dbox(face, u, v, z):
        if face == "top":
            if abs(v - 8) < 0.8 and abs(u - 8) < 2.8:
                return OUT
            e = min(u - 4, 12 - u, v - 4, 12 - v)
            return GOLD if e < 1.2 else PURPLE_L
        s_ = u if face == "left" else v
        if z > 13 or z < 8.2:
            return GOLD
        d = math.hypot(s_ - 8, z - 10.6)
        if d < 1.9:
            return GOLD_L if d > 0.8 else GOLD_D
        return PURPLE
    box(s, A, (4, 4, 12, 12), (7, 15), dbox)
    grain(s, rng_for("donation_box"), 0.04)
    reg("donation_box", s, A)

    # --- merch stall ---
    s = new(32, 32)
    for u, v in ((2.5, 5), (13.5, 5)):                               # back posts
        x, y = P(A, u, v)
        column(s, x, y - 17, y, 1, (WOOD, WOOD, WOOD), ol=0)

    def counter(face, u, v, z):
        if face == "top":
            return PURPLE_L if int(u + v) % 2 else PURPLE
        s_ = u if face == "left" else v
        if z > 3.2:
            return PURPLE
        if z > 2.2 or (z > 1.2 and int(s_) % 2):
            return GOLD
        return WOOD_D
    box(s, A, (2, 5, 14, 12.5), (0, 7), counter)
    # goods on the counter: crystals, books
    for cx, cy, c1, c2 in ((9, 17, hx("7fe0e0"), hx("3a9aa8")), (13, 19, hx("f0a0d0"), hx("b05a98")), (17, 21, hx("b8f0a0"), hx("5aa860"))):
        put(s, cx, cy - 3, WHITE)
        put(s, cx, cy - 2, c1)
        put(s, cx + 1, cy - 2, c2)
        put(s, cx, cy - 1, c1)
        put(s, cx + 1, cy - 1, c2)
        put(s, cx - 1, cy - 1, c1)
        put(s, cx, cy, c2)
    box(s, A, (10.5, 6.5, 13, 9), (7, 9), lambda f, u, v, z: RED if f == "top" else (WHITE if z < 8.5 and f == "left" else RED_D), ol=0.4)
    box(s, A, (10.5, 9.5, 13, 12), (7, 8.5), lambda f, u, v, z: BLUE if f == "top" else WHITE, ol=0.4)
    for u, v in ((2.5, 12), (13.5, 12)):                             # front posts
        x, y = P(A, u, v)
        column(s, x, y - 17, y - 1, 1, (WOOD_L, WOOD_L, WOOD_L), ol=0)

    def awning(face, u, v, z):
        stripe = int(u // 2) % 2 if face != "right" else int(v // 2) % 2
        if face != "top" and z < 15.2 and int((u if face == "left" else v)) % 2 == 0:
            return None  # scalloped edge
        return PURPLE if stripe else GOLD
    box(s, A, (1.5, 4, 14.5, 9.5), (14, 17), awning, ol=0.45)
    grain(s, rng_for("merch"), 0.04)
    reg("merch", s, A)

    # --- lamp (brazier on a pole), 2 flicker frames ---
    frames = []
    for i in range(2):
        s = new(32, 32)
        box(s, A, (6, 6, 10, 10), (0, 2), IRON)
        column(s, 14, 12, 22, 3, (IRON_L, IRON, IRON_D))

        def bowl_(t):
            rect(t, 11, 9, 10, 1, GOLD_L)
            rect(t, 11, 10, 10, 1, GOLD)
            rect(t, 12, 11, 8, 1, GOLD_D)
            rect(t, 13, 12, 6, 1, GOLD_D)
            for x in range(11, 21):
                if x > 17:
                    t.set_at((x, 10), GOLD_D)
        flame(s, 16.0, 9, 8 + i, 3.2, i * math.pi)
        layer(s, bowl_)
        frames.append(s)
    reg("lamp", frames, A)

    # --- campfire, 2 frames ---
    frames = []
    for i in range(2):
        s = new(32, 32)
        rng = rng_for("campfire")
        shadow(s, 16, 24, 11, 4, 50)
        ring = [(8, 24), (10, 21), (14, 20), (19, 20), (23, 22), (24, 25), (21, 27), (16, 28), (11, 27)]
        for n, (x, y) in enumerate(ring[:5]):                       # back stones
            layer(s, lambda t, x=x, y=y, n=n: (rect(t, x - 1, y - 1, 3, 2, ROCK_L if n % 2 else ROCK), put(t, x + 1, y, ROCK_D)), 0.5)

        def logs(t):
            for k in range(13):
                put(t, 10 + k, 26 - k // 3, BARK_L)
                put(t, 10 + k, 27 - k // 3, BARK_D)
                put(t, 22 - k, 26 - k // 3, BARK)
                put(t, 22 - k, 27 - k // 3, BARK_D)
        layer(s, logs, 0.4)
        flame(s, 16.0, 24, 12 + i, 4.6, i * math.pi + 0.6, core=True)
        for n, (x, y) in enumerate(ring[5:]):                       # front stones
            layer(s, lambda t, x=x, y=y, n=n: (rect(t, x - 1, y - 1, 3, 2, ROCK if n % 2 else ROCK_L), put(t, x + 1, y, ROCK_D)), 0.5)
        for x, y in (((12, 9), (20, 13), (17, 7)) if i == 0 else ((13, 7), (19, 10), (15, 6))):
            put(s, x, y, FIRE2)                                      # sparks
        frames.append(s)
    reg("campfire", frames, A)

    # --- meditation mat (flat) ---
    s = new(32, 16)

    def mat(face, u, v, z):
        e = min(u - 2.5, 13.5 - u, v - 2.5, 13.5 - v)
        d = math.hypot(u - 8, v - 8)
        if 1.0 <= e < 2.0:
            return GOLD
        if 1.6 <= d < 2.7:
            return GOLD_L
        if d < 0.9:
            return GOLD
        return PURPLE if int(u + v) % 2 else PURPLE_L
    box(s, (16, 8), (2.5, 2.5, 13.5, 13.5), (0, 0), mat, shade=(1.0, 1, 1))
    reg("mat", s, (16, 8))

    # --- statue 32x48, anchor (16,40) ---
    A2 = (16, 40)
    s = new(32, 48)
    box(s, A2, (3, 3, 13, 13), (0, 3), STONE_D)

    def plinth(face, u, v, z):
        if face == "left" and 6.5 <= u < 9.5 and 5.5 <= z < 8.5:
            return GOLD
        if face == "right" and 6.5 <= v < 9.5 and 5.5 <= z < 8.5:
            return GOLD
        return STONE
    box(s, A2, (4.5, 4.5, 11.5, 11.5), (3, 10), plinth)
    box(s, A2, (4, 4, 12, 12), (10, 12), STONE_L)

    def guru(t):
        g = (255, 255, 255, 255)
        pygame.draw.polygon(t, g, [(13, 16), (18, 16), (21, 29), (10, 29)])     # robe
        pygame.draw.ellipse(t, g, (13, 9, 6, 7))                                 # head
        pygame.draw.line(t, g, (13, 17), (8, 10), 2)                             # arms raised
        pygame.draw.line(t, g, (18, 17), (23, 10), 2)
        rect(t, 7, 8, 3, 3, g)
        rect(t, 22, 8, 3, 3, g)
        pygame.draw.ellipse(t, g, (11, 4, 10, 4), 1)                             # halo
        for y in range(48):
            for x in range(32):
                if t.get_at((x, y))[3]:
                    k = (x - 15.5) / 6 + (y - 18) / 40
                    if k < -0.35:
                        c = GOLD_L
                    elif k < -0.2:
                        c = GOLD_L if (x + y) % 2 else GOLD
                    elif k < 0.3:
                        c = GOLD
                    elif k < 0.45:
                        c = GOLD if (x + y) % 2 else GOLD_D
                    else:
                        c = GOLD_D
                    t.set_at((x, y), c)
        t.set_at((15, 12), GOLD_D)
        t.set_at((17, 12), GOLD_D)
        for y in range(19, 28, 3):
            t.set_at((16, y), GOLD_D)
    t = new(32, 48)
    guru(t)
    outline(t, 0.6, hx("4a3010"))
    s.blit(t, (0, 0))
    grain(s, rng_for("statue"), 0.04)
    reg("statue", s, A2)

    # --- loudspeaker 32x48 ---
    s = new(32, 48)
    box(s, A2, (6, 6, 10, 10), (0, 2), STONE_D)
    column(s, 14, 12, 38, 3, (WOOD_L, WOOD, WOOD_D))
    rect(s, 14, 24, 3, 2, PURPLE)

    def horn(t, mx, body, c_body, c_rim):
        pygame.draw.polygon(t, c_body, body)
        pygame.draw.ellipse(t, c_rim, (mx - 4, 5, 9, 13))
        pygame.draw.ellipse(t, IRON_D, (mx - 2, 7, 5, 9))
        rect(t, mx - 1, 10, 3, 3, OUT)
        put(t, mx, 11, IRON_L)
    # two horns turned towards the viewer (down-left / down-right)
    layer(s, lambda t: horn(t, 25, [(25, 5), (16, 7), (16, 12), (25, 17)], IRON, hx("9a98a6")))
    layer(s, lambda t: horn(t, 7, [(7, 5), (15, 7), (15, 12), (7, 17)], IRON_L, hx("bcbac8")))
    layer(s, lambda t: (rect(t, 13, 6, 6, 7, IRON), rect(t, 14, 7, 2, 5, IRON_L)))
    put(s, 16, 5, RED)
    put(s, 15, 5, hx("f08070"))
    reg("loudspeaker", s, A2)

    # --- confession booth 32x44, anchor (16,36) ---
    A3 = (16, 36)
    s = new(32, 44)
    CW, CWD = hx("7a5636"), hx("5c3e28")

    def booth(face, u, v, z):
        if face == "top":
            return CWD
        s_ = u if face == "left" else v
        if 5 <= s_ < 11 and z < 15:
            if z > 13.6 and (s_ < 6 or s_ >= 10):
                return CWD
            if z > 12.8:
                return GOLD
            return PURPLE_L if int(s_) % 2 else PURPLE_D
        if 4 <= s_ < 12 and z < 16:
            return CWD
        if 6 <= s_ < 10 and 17.5 <= z < 20.5:
            return OUT if 7 <= s_ < 9 and 18.3 <= z < 19.7 else GOLD  # little grille
        if int(s_) % 3 == 0:
            return CWD
        return CW
    box(s, A3, (3, 3, 13, 13), (0, 23), booth)
    box(s, A3, (2, 2, 14, 14), (23, 25), lambda f, u, v, z: hx("8a6440") if f == "top" else CW)
    for x, y, c in ((16, 6, GOLD_L), (15, 7, GOLD_L), (16, 7, GOLD), (14, 8, GOLD_L), (15, 8, PURPLE_D), (16, 8, GOLD),
                    (17, 8, GOLD_D), (17, 7, GOLD_D), (13, 9, GOLD), (14, 9, GOLD), (15, 9, GOLD), (16, 9, GOLD_D),
                    (17, 9, GOLD_D), (18, 9, GOLD_D), (18, 8, GOLD_D)):
        put(s, x, y, c)
    grain(s, rng_for("confession"), 0.05)
    reg("confession", s, A3)

    # --- watchtower 32x60, anchor (16,52) ---
    A4 = (16, 52)
    s = new(32, 60)
    wcols = (WOOD_L, WOOD, WOOD_D)
    column(s, 15, 22, 47, 2, wcols)                                  # back leg
    column(s, 5, 27, 52, 2, wcols)                                   # left leg
    column(s, 25, 27, 52, 2, wcols)                                  # right leg

    def braces(t):
        for k in range(10):
            y = 30 + k * 2
            put(t, 6 + k, y + k // 2, WOOD)
            put(t, 6 + k, y + 1 + k // 2, WOOD)
            put(t, 15 - k, y + 5 - k // 2, WOOD_D)
            put(t, 15 - k, y + 4 - k // 2, WOOD_D)
            put(t, 25 - k, y + k // 2, WOOD_D)
            put(t, 25 - k, y + 1 + k // 2, WOOD_D)
            put(t, 16 + k, y + 5 - k // 2, mul(WOOD_D, 0.85))
            put(t, 16 + k, y + 4 - k // 2, mul(WOOD_D, 0.85))
    layer(s, braces, 0.3)
    column(s, 15, 32, 57, 2, wcols)                                  # front leg
    box(s, A4, (1.5, 1.5, 14.5, 14.5), (25, 27), WOOD)               # platform

    def parapet(face, u, v, z):
        if face == "top":
            e = min(u - 1.5, 14.5 - u, v - 1.5, 14.5 - v)
            return WOOD_L if e < 1.3 else mul(WOOD_D, 0.6)
        s_ = int(u if face == "left" else v)
        return WOOD_D if s_ % 3 == 0 else WOOD_L
    box(s, A4, (1.5, 1.5, 14.5, 14.5), (27, 32), parapet)
    for u, v in ((2, 2), (2, 14), (14, 2), (14, 14)):                # roof posts
        x, y = P(A4, u, v, 32)
        column(s, x - (1 if u < 14 or v < 14 else 0), y - 8, y, 1 if (u, v) != (14, 14) else 2, wcols, ol=0)

    def roof(t):
        pygame.draw.polygon(t, PURPLE, [(0, 13), (15, 20), (15, 2)])
        pygame.draw.polygon(t, PURPLE_D, [(16, 20), (31, 13), (16, 2)])
        for y in range(2, 21):
            for x in range(32):
                if t.get_at((x, y))[3] and (x + 2 * y) % 5 == 0:
                    t.set_at((x, y), mul(t.get_at((x, y)), 0.84))    # shingles
        for k in range(16):
            put(t, k, 13 + (k + 1) // 2, PURPLE_L)
    layer(s, roof)
    put(s, 15, 1, GOLD_L)
    put(s, 16, 1, GOLD)
    put(s, 15, 0, GOLD_L)
    put(s, 16, 0, GOLD_D)
    grain(s, rng_for("watchtower"), 0.05)
    reg("watchtower", s, A4)

    # --- banner 32x48 ---
    s = new(32, 48)
    box(s, A2, (6, 6, 10, 10), (0, 2), STONE_D)
    column(s, 14, 5, 38, 3, wcols)

    def bar(t):
        rect(t, 7, 7, 18, 1, WOOD_L)
        rect(t, 7, 8, 18, 1, WOOD_D)
        rect(t, 14, 2, 4, 4, GOLD)
        put(t, 15, 3, GOLD_L)
        put(t, 17, 5, GOLD_D)
        put(t, 17, 4, GOLD_D)
    layer(s, bar)

    def flag(t):
        for y in range(9, 31):
            for x in range(9, 23):
                if y >= 26 and abs(x + 0.5 - 16) < (y - 25) * 1.4:
                    continue                                         # swallowtail
                c = PURPLE_L if x < 12 else PURPLE if x < 19 else PURPLE_D
                if x in (11, 18) and y % 2:
                    c = PURPLE if x == 11 else PURPLE_D              # dithered folds
                if x in (10, 21) or y == 10:
                    c = GOLD if x < 19 else GOLD_D
                put(t, x, y, c)
        for r, y in enumerate(range(14, 19)):                        # eye-in-triangle
            put(t, 15 - r, y, GOLD_L)
            put(t, 16 + r, y, GOLD)
        for x in range(11, 21):
            put(t, x, 19, GOLD)
        put(t, 15, 17, GOLD_L)
        put(t, 16, 17, GOLD_L)
    layer(s, flag)
    reg("banner", s, A2)

    # --- holy goat 16x14, facing right, anchor (8,12) ---
    gp = {"o": OUT, "W": hx("f0ece0"), "L": hx("cfc8b8"), "G": hx("a8a090"), "g": GOLD_D, "y": GOLD_L,
          "e": OUT, "k": hx("3a3038"), "p": hx("e8a8a0")}
    body = [
        "................",
        ".........gg.g...",
        "..........ggg...",
        "..........oooo..",
        ".o.......oWWWWo.",
        "oWoooooooWWWeWWo",
        ".oWWWWWWWWWWWLpo",
        ".oWWWWWWWWWoooo.",
        ".oWWWWWWWLLoL...",
        "..oLLWWWLLLoL...",
    ]
    legs_a = [
        "..oLoooooLo.....",
        "..oLoGo.oLoGo...",
        "..okoko.okoko...",
        "................",
    ]
    legs_b = [
        "..oLoooooLo.....",
        ".oLoGo..oGoLo...",
        ".okoko..okooko..",
        "................",
    ]
    frames = []
    for legs in (legs_a, legs_b):
        s = new(16, 14)
        shadow(s, 7, 12, 6, 1, 50)
        s.blit(art(body + legs, gp), (0, 0))
        put(s, 10, 8, GOLD_L)                                        # little bell
        frames.append(s)
    reg("goat", frames, (8, 12))


# --------------------------------------------------------------------------
# pawns (greyscale tint layers, 3 frames of 12x18, anchor 6,16)
# --------------------------------------------------------------------------
def g(v):
    return (v, v, v, 255)


GP = {"o": (26, 20, 30, 255), "e": (34, 24, 38, 255), "W": g(255), "L": g(218), "G": g(178), "D": g(136), "K": g(100), "k": g(64)}
E12 = "............"

SKIN_HEAD_F = [E12, "...oooooo...", "..oWWWWWWo..", "..oWWWWWWo..", "..oWWWWWWo..", "..oWWeWeLo..", "..oLWWWWLo..", "...oooooo...", "....oLLo...."]
SKIN_HEAD_B = [E12, "...oooooo...", "..oWWWWWWo..", "..oWWWWWLo..", "..oWWWWWLo..", "..oWWWWLLo..", "..oLWWLLLo..", "...oooooo...", "....oLLo...."]

ROBE_F = ["..oWWWWWWo..", "..oWWWWWLo..", "..oLWWWWGo..", "..o.DDDD.o..", "..oWWWDWLo..", "..oWWWDWLo..", "..oWWWWWGo..", ".oWWWWWWLGo.", ".oooooooooo.", E12]
ROBE_B = ["..oWWWWWWo..", "..oWLLLLWo..", "..oLWLLWGo..", "..o.DDDD.o..", "..oWWWWWLo..", "..oWWWWWLo..", "..oWWWWWGo..", ".oWWWWWWLGo.", ".oooooooooo.", E12]
CIV_F = ["..oWWLLWWo..", "..oWWWWWLo..", "..oLWWWWGo..", "..o.WWWL.o..", "...oDDDDo...", "...oDDDKo...", "...oDDKKo...", "...oDDKKo...", "...okkkko...", E12]
CIV_B = ["..oWWWWWWo..", "..oWWWWWLo..", "..oLWWWWGo..", "..o.WWWL.o..", "...oDDDDo...", "...oDDDKo...", "...oDDKKo...", "...oDDKKo...", "...okkkko...", E12]
HAIR_F = [E12, "...oooooo...", "..oLWWWLGo..", "..oWLLGGGo..", "..oG........"]
HAIR_B = [E12, "...oooooo...", "..oLWWWLGo..", "..oWWLLLGo..", "..oLLLLGGo..", "..oLLLGGGo..", "..o.GGGGGo.."]

# hand rows (left hand x=3, right hand x=8) for stand / walk A / walk B
HANDS = ((11, 11), (10, 12), (12, 10))


def grid(rows, top=0):
    gr = [list(E12) for _ in range(18)]
    for i, r in enumerate(rows):
        assert len(r) == 12, r
        gr[top + i] = list(r)
    return gr


def pawn_frames(kind, rows, top):
    frames = []
    for f, (ly, ry) in enumerate(HANDS):
        gr = grid(rows, top)
        if kind == "skin":
            gr[ly][3], gr[ly][2], gr[ly + 1][3] = "W", "o", "o"
            gr[ry][8], gr[ry][9], gr[ry + 1][8] = "W", "o", "o"
        elif kind == "robe":
            for x, yy, fill in ((3, ly, ("L", "W", "W")), (8, ry, ("G", "L", "L"))):
                col = {10: (".", fill[1], fill[2]), 11: (fill[0], ".", fill[2]), 12: (fill[1], fill[0], ".")}[yy]
                gr[10][x], gr[11][x], gr[12][x] = col
            if f == 1:
                gr[15], gr[16] = list(".oWWWWWWLo.."), list(".ooooooooo..")
            elif f == 2:
                gr[15], gr[16] = list("..oWWWWWLGo."), list("..ooooooooo.")
        elif kind == "civ":
            for x, ox, yy, sl in ((3, 2, ly, "L"), (8, 9, ry, "G")):
                if yy == 10:
                    gr[10][x], gr[11][x], gr[11][ox] = ".", "o", "."
                elif yy == 12:
                    gr[10][x], gr[11][x], gr[12][x] = sl, sl, "."
            if f == 1:
                gr[15], gr[16] = list("...oDDkko..."), list("...okkoo....")
            elif f == 2:
                gr[15], gr[16] = list("...okkKKo..."), list("...oookko...")
        frames.append(art(["".join(r) for r in gr], GP))
    return frames


def make_pawns():
    A = (6, 16)
    reg("pawn_skin_front", pawn_frames("skin", SKIN_HEAD_F, 0), A)
    reg("pawn_skin_back", pawn_frames("skin", SKIN_HEAD_B, 0), A)
    reg("pawn_robe_front", pawn_frames("robe", ROBE_F, 8), A)
    reg("pawn_robe_back", pawn_frames("robe", ROBE_B, 8), A)
    reg("pawn_civ_front", pawn_frames("civ", CIV_F, 8), A)
    reg("pawn_civ_back", pawn_frames("civ", CIV_B, 8), A)
    reg("pawn_hair_front", pawn_frames("hair", HAIR_F, 0), A)
    reg("pawn_hair_back", pawn_frames("hair", HAIR_B, 0), A)

    def acc(rows_by_y, pal):
        gr = [E12] * 18
        for y, r in rows_by_y.items():
            gr[y] = r
        return art(gr, pal)

    reg("acc_guru", acc({0: "..Y..YY..Y..", 1: "..YY.YY.YY..", 2: "..YYGPPGYY..", 3: "..gggggggg..", 8: "....Y..Y....", 9: ".....YY....."},
                        {"Y": GOLD_L, "G": GOLD, "g": GOLD_D, "P": PURPLE}), A)
    reg("acc_hood", acc({0: "....oooo....", 1: "...oPPPPo...", 2: "..oPPPPPPo..", 3: "..oPPqqPPo..", 4: "..oPp...po..",
                         5: "..oP....Po..", 6: "..oP....Po..", 7: "..oPP..PPo.."},
                        {"o": OUT, "P": hx("4a2a6e"), "p": hx("38205a"), "q": hx("5e3a88")}), A)
    reg("acc_guard", acc({5: "...kkKkkk...", 9: "...Y........"}, {"k": hx("18141e"), "K": hx("5a5a70"), "Y": GOLD}), A)
    reg("acc_police", acc({0: "....BBBB....", 1: "...BBBBBB...", 2: "..BBBBYBBB..", 3: "..bbbbbbbbb.", 9: ".......Y...."},
                          {"B": BLUE, "b": BLUE_D, "Y": GOLD_L}), A)
    reg("acc_soldier", acc({0: "....lOOO....", 1: "...lOOOOO...", 2: "..lOOOOOOd..", 3: ".dddddddddd."},
                           {"O": OLIVE, "l": OLIVE_L, "d": OLIVE_D}), A)
    reg("acc_press", acc({0: "....FFFF....", 1: "...FFFFFf...", 2: "...kkkkkk...", 3: ".fFFFFFFFff.", 7: "..........y.", 8: ".........w..",
                          9: ".....kkkk...", 10: ".....kCkk..."},
                         {"F": hx("7a6a56"), "f": hx("5a4c3e"), "k": hx("2a2430"), "C": hx("9ad0f0"), "w": WHITE, "y": GOLD_L}), A)
    reg("acc_inspector", acc({8: "......R.....", 9: "nnnn..R.....", 10: "nwwn..R.....", 11: "nwwn........", 12: "nnnn........"},
                             {"R": RED, "n": WOOD_D, "w": WHITE}), A)
    sign = {0: "....oooooooo", 1: "....owwwwwwo", 2: "....owRRwRwo", 3: "....owwwwwwo", 4: "....oooooooo"}
    for y in range(5, 11):
        sign[y] = ".........n.."
    reg("acc_sign", acc(sign, {"o": OUT, "w": WHITE, "R": RED, "n": WOOD}), A)


# --------------------------------------------------------------------------
# fx bubbles (9x9, anchor 4,8) and ui icons (16x16)
# --------------------------------------------------------------------------
def make_fx():
    pal = {"o": OUT, "W": WHITE, "B": hx("3f72aa"), "R": hx("d04a4a"), "P": PURPLE, "K": hx("3a3040"), "G": hx("3f8a3f"),
           "Y": GOLD_L, "g": GOLD_D, "y": hx("fff4c0")}
    inner = {
        "zzz": ["....BBB", "BBB..B.", "..B.BBB", ".B.....", "BBB...."],
        "heart": [".RR.RR.", "RRRRRRR", ".RRRRR.", "..RRR..", "...R..."],
        "exclaim": ["...R...", "...R...", "...R...", ".......", "...R..."],
        "question": ["..PPP..", "....P..", "...P...", ".......", "...P..."],
        "speech": [".......", ".......", ".K.K.K.", ".......", "......."],
        "note": ["...KK..", "...K.K.", "...K...", ".KKK...", ".KKK..."],
        "money": ["..GGGG.", ".GG....", "..GGG..", "....GG.", ".GGGG.."],
        "angry": ["..R.R..", "RRR.RRR", ".......", "RRR.RRR", "..R.R.."],
    }
    for name in ("zzz", "heart", "exclaim", "question", "speech", "note", "money", "angry"):
        rows = [".ooooooo."] + ["o" + r.replace(".", "W") + "o" for r in inner[name]] + [".oooWooo.", "...oWo...", "....o...."]
        reg(f"fx_{name}", art(rows, pal), (4, 8))
    halo = [".........", ".......y.", ".........", "..ooooo..", ".oyYYYYo.", "oYo...oYo", "oYo...ogo", ".oYYYggo.", "..ooooo.."]
    reg("fx_halo", art(halo, pal), (4, 8))


def make_icons():
    A = (0, 0)
    # money: coin
    s = new(16, 16)
    pygame.draw.ellipse(s, GOLD, (2, 2, 12, 12))
    pygame.draw.ellipse(s, GOLD_L, (3, 3, 9, 9))
    pygame.draw.ellipse(s, GOLD, (5, 5, 7, 7))
    rect(s, 7, 5, 2, 6, GOLD_D)
    rect(s, 6, 6, 4, 1, GOLD_D)
    rect(s, 6, 9, 4, 1, GOLD_D)
    for x, y in ((12, 10), (11, 12), (10, 13), (12, 8)):
        put(s, x, y, GOLD_D)
    reg("icon_money", outline_outer(s), A)

    # food: wheat sheaf
    s = art([
        "................",
        ".......GY.......",
        "..GY...YG...YG..",
        "..YG...GY...GY..",
        "...GY..YG..YG...",
        "...YG..GY..GY...",
        "....GY.YG.YG....",
        "....YG.GY.GY....",
        ".....g.YG.g.....",
        "......gGgg......",
        "......PPPP......",
        "......gggg......",
        ".....g.gg.g.....",
        "....g..gg..g....",
        "................",
        "................",
    ], {"G": GOLD, "Y": GOLD_L, "g": GOLD_D, "P": RED})
    reg("icon_food", outline_outer(s), A)

    # meal: steaming bowl
    s = new(16, 16)
    pygame.draw.polygon(s, hx("b0623a"), [(2, 9), (13, 9), (11, 13), (4, 13)])
    rect(s, 5, 14, 6, 1, hx("8a4a2c"))
    pygame.draw.ellipse(s, CREAM, (2, 7, 12, 4))
    pygame.draw.ellipse(s, hx("e0a040"), (3, 8, 10, 2))
    for x in (11, 12):
        put(s, x, 11, hx("8a4a2c"))
        put(s, x - 1, 12, hx("8a4a2c"))
    for x, y in ((5, 5), (6, 4), (5, 3), (6, 2), (9, 5), (10, 4), (9, 3), (10, 2)):
        put(s, x, y, WHITE)
    reg("icon_meal", outline_outer(s), A)

    # enlightenment points: eye in triangle
    s = new(16, 16)
    pygame.draw.polygon(s, GOLD, [(7, 1), (8, 1), (14, 13), (1, 13)])
    pygame.draw.polygon(s, PURPLE, [(7, 5), (8, 5), (11, 11), (4, 11)])
    for x in range(1, 15):
        put(s, x, 13, GOLD_D)
    for k in range(6):
        put(s, 7 - k, 2 + 2 * k, GOLD_L)
        put(s, 7 - k, 3 + 2 * k, GOLD_L)
    rect(s, 6, 8, 4, 2, WHITE)
    put(s, 5, 9, WHITE)
    put(s, 10, 9, WHITE)
    rect(s, 7, 8, 2, 2, OUT)
    reg("icon_ep", outline_outer(s), A)

    # heat: flame
    s = new(16, 16)
    flame(s, 8.0, 14, 13, 4.6, 0.4, core=True)
    reg("icon_heat", outline_outer(s), A)

    # members: two robed figures
    s = new(16, 16)
    pygame.draw.ellipse(s, hx("c89870"), (9, 2, 5, 5))
    rect(s, 8, 7, 7, 7, PURPLE_D)
    outline_outer(s)
    t = new(16, 16)
    pygame.draw.ellipse(t, SKIN, (3, 3, 6, 6))
    pygame.draw.polygon(t, PURPLE, [(3, 9), (8, 9), (10, 14), (1, 14)])
    rect(t, 3, 9, 2, 5, PURPLE_L)
    put(t, 5, 5, OUT)
    put(t, 7, 5, OUT)
    rect(t, 4, 11, 4, 1, GOLD)
    outline_outer(t)
    s.blit(t, (0, 0))
    reg("icon_members", s, A)

    # tracts: pamphlet
    s = new(16, 16)
    rect(s, 3, 1, 10, 14, WHITE)
    rect(s, 11, 1, 2, 2, (0, 0, 0, 0))
    put(s, 11, 2, hx("c9c9cf"))
    put(s, 11, 1, (0, 0, 0, 0))
    put(s, 12, 3, hx("c9c9cf"))
    for k in range(3):
        rect(s, 7 - k, 3 + k, 2 + 2 * k, 1, PURPLE)
    put(s, 7, 5, GOLD_L)
    put(s, 8, 5, GOLD_L)
    for y in (8, 10, 12):
        rect(s, 5, y, 6 if y != 12 else 4, 1, hx("8a8690"))
    rect(s, 12, 4, 1, 11, hx("d8d4cc"))
    reg("icon_tracts", outline_outer(s), A)

    # faith: radiant sun-star with an eye
    s = new(16, 16)
    for ang in range(8):
        a = ang * math.pi / 4
        for r in (4.5, 5.5, 6.5):
            if ang % 2 and r > 6:
                continue
            put(s, int(8 + math.cos(a) * r), int(8 + math.sin(a) * r), GOLD)
            put(s, int(7.5 + math.cos(a) * r), int(7.5 + math.sin(a) * r), GOLD)
    pygame.draw.ellipse(s, GOLD, (4, 4, 8, 8))
    pygame.draw.ellipse(s, GOLD_L, (5, 5, 5, 5))
    rect(s, 7, 7, 2, 2, PURPLE)
    reg("icon_faith", outline_outer(s), A)

    # mood: smiley
    s = new(16, 16)
    pygame.draw.ellipse(s, hx("f0cc50"), (2, 2, 12, 12))
    pygame.draw.ellipse(s, hx("f8e080"), (3, 3, 8, 7))
    rect(s, 5, 5, 2, 3, OUT)
    rect(s, 9, 5, 2, 3, OUT)
    for x, y in ((4, 9), (5, 10), (6, 11), (7, 11), (8, 11), (9, 11), (10, 10), (11, 9)):
        put(s, x, y, hx("7a4a20"))
    reg("icon_mood", outline_outer(s), A)

    # bond: two overlapping hearts
    heart = ["RRR...RRR", "RRRR.RRRR", "RRRRRRRRR", "RRRRRRRRR", ".RRRRRRR.", "..RRRRR..", "...RRR...", "....R...."]
    s = new(16, 16)
    s.blit(art(heart, {"R": PURPLE}), (6, 2))
    put(s, 7, 3, PURPLE_L)
    outline_outer(s)
    t = new(16, 16)
    t.blit(art(heart, {"R": hx("d04a5a")}), (1, 6))
    put(t, 2, 7, hx("f09aa0"))
    put(t, 3, 7, hx("f09aa0"))
    put(t, 2, 8, hx("f09aa0"))
    outline_outer(t)
    s.blit(t, (0, 0))
    reg("icon_bond", s, A)


# --------------------------------------------------------------------------
# audio
# --------------------------------------------------------------------------
def write_wav(path: Path, samples, peak=0.8):
    m = max(1e-9, max(abs(v) for v in samples))
    k = peak * 32767 / m
    arr = array("h", (int(round(v * k)) for v in samples))
    if sys.byteorder == "big":
        arr.byteswap()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(arr.tobytes())


def tone(freq, dur, harm=((1, 1.0),), decay=None, attack=0.004, release=0.02, freq_end=None, vib=0.0):
    n = int(SR * dur)
    out = [0.0] * n
    ph = 0.0
    for i in range(n):
        t = i / SR
        f = freq if freq_end is None else freq + (freq_end - freq) * (t / dur)
        if vib:
            f *= 1 + vib * math.sin(2 * math.pi * 5.5 * t)
        ph += 2 * math.pi * f / SR
        e = min(1.0, t / attack) * min(1.0, (dur - t) / release)
        if decay:
            e *= math.exp(-t / decay)
        out[i] = e * sum(a * math.sin(k * ph) for k, a in harm)
    return out


def mixin(dst, src, t0, gain=1.0):
    o = int(t0 * SR)
    if len(dst) < o + len(src):
        dst.extend([0.0] * (o + len(src) - len(dst)))
    for i, v in enumerate(src):
        dst[o + i] += v * gain
    return dst


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


SOFT = ((1, 1.0), (2, 0.25), (3, 0.08))
BELL = ((1, 1.0), (2, 0.4), (3, 0.18), (4.2, 0.12), (5.4, 0.06))
TRI = ((1, 1.0), (3, 0.11), (5, 0.04))


def make_sfx():
    rng = random.Random(SEED)
    out = {}
    # click: tiny wooden tick
    s = tone(1250, 0.05, SOFT, decay=0.010, attack=0.001, release=0.01)
    mixin(s, tone(620, 0.05, decay=0.014, attack=0.001, release=0.01), 0, 0.5)
    out["click"] = (s, 0.5)
    # place: soft thud
    s = tone(210, 0.18, SOFT, decay=0.05, attack=0.002, release=0.03, freq_end=95)
    nz, lp = [], 0.0
    for i in range(int(SR * 0.05)):
        lp += 0.18 * (rng.uniform(-1, 1) - lp)
        nz.append(lp * math.exp(-i / (SR * 0.012)) * min(1.0, i / 30))
    mixin(s, nz, 0, 0.9)
    out["place"] = (s, 0.6)
    # build_done: cheerful three note arpeggio + chord
    s = []
    for k, m in enumerate((67, 72, 76)):
        mixin(s, tone(midi(m), 0.32, TRI, decay=0.16, release=0.05), k * 0.085, 0.8)
    for m in (72, 76, 79):
        mixin(s, tone(midi(m), 0.5, SOFT, decay=0.22, release=0.08), 0.27, 0.4)
    out["build_done"] = (s, 0.6)
    # convert: rising bell chime
    s = []
    for k, m in enumerate((72, 76, 79, 84, 88)):
        mixin(s, tone(midi(m), 0.7, BELL, decay=0.22, release=0.1), k * 0.09, 0.7 - k * 0.05)
    out["convert"] = (s, 0.7)
    # alert: two gentle double beeps
    s = []
    for k in range(2):
        mixin(s, tone(midi(81), 0.11, SOFT, attack=0.008, release=0.03), k * 0.36)
        mixin(s, tone(midi(86), 0.16, SOFT, attack=0.008, release=0.05), k * 0.36 + 0.13)
    out["alert"] = (s, 0.7)
    # event: gong
    s = []
    for ratio, amp, dec in ((1.0, 1.0, 0.9), (1.004, 0.6, 0.9), (2.02, 0.5, 0.6), (2.76, 0.35, 0.45), (3.41, 0.22, 0.35),
                            (4.3, 0.14, 0.25), (5.43, 0.09, 0.18)):
        mixin(s, tone(98.0 * ratio, 2.0, decay=dec, attack=0.012, release=0.3), 0, amp)
    out["event"] = (s, 0.8)
    # coin
    s = tone(midi(83), 0.07, TRI, attack=0.002, release=0.01)
    mixin(s, tone(midi(88), 0.38, TRI, decay=0.12, attack=0.002, release=0.05), 0.065)
    out["coin"] = (s, 0.6)
    # error: two low soft notes
    buzz = ((1, 1.0), (2, 0.3), (3, 0.3), (5, 0.1))
    s = tone(midi(55), 0.14, buzz, attack=0.008, release=0.03)
    mixin(s, tone(midi(50), 0.24, buzz, attack=0.008, release=0.1), 0.15)
    out["error"] = (s, 0.6)
    return out


def make_music():
    """40 s seamless 'cult organ' loop: every voice wraps around the loop point."""
    dur = 40.0
    n = int(SR * dur)
    buf = [0.0] * n
    ts = 4096
    mask = ts - 1

    def table(harm):
        t = [sum(a * math.sin(2 * math.pi * k * i / ts) for k, a in harm) for i in range(ts)]
        m = max(abs(x) for x in t)
        return [x / m for x in t]

    organ = table(((1, 1.0), (2, 0.5), (3, 0.22), (4, 0.12), (6, 0.05)))
    flute = table(((1, 1.0), (2, 0.18), (3, 0.07)))

    def add(t0, length, m, amp, tbl, attack, release, detune=0.0):
        inc = midi(m) * (1 + detune) * ts / SR
        start = int(t0 * SR)
        cnt = int(length * SR)
        an, rn = max(1, int(attack * SR)), max(1, int(release * SR))
        ph = 0.0
        for i in range(cnt):
            if i < an:
                e = i / an
            elif i >= cnt - rn:
                e = (cnt - i) / rn
            else:
                e = 1.0
            buf[(start + i) % n] += amp * e * e * (3 - 2 * e) * tbl[int(ph) & mask]
            ph += inc

    # drone (frequencies snapped so they complete whole cycles in the loop)
    lfo = [1 + 0.14 * math.sin(2 * math.pi * 6 * i / n) for i in range(n)]
    for m, amp in ((38, 0.15), (45, 0.07), (50, 0.05)):
        f = round(midi(m) * dur) / dur
        inc = f * ts / SR
        for i in range(n):
            buf[i] += amp * lfo[i] * organ[int(i * inc) & mask]

    bar = dur / 8
    chords = [(50, 53, 57), (46, 50, 53), (53, 57, 60), (48, 52, 55), (50, 53, 57), (55, 58, 62), (46, 50, 53), (45, 49, 52)]
    pats = ([0, 1, 2, 3, 2, 1, 2, 1], [0, 2, 1, 3, 2, 3, 1, 2])
    step = bar / 8
    for b, ch in enumerate(chords):
        t0 = b * bar
        for m in ch:  # pad, crossfading between bars
            add(t0 - 0.7, bar + 1.4, m, 0.060, organ, 1.3, 1.3)
            add(t0 - 0.7, bar + 1.4, m, 0.045, organ, 1.3, 1.3, detune=0.004)
        tones_ = [ch[0] + 12, ch[1] + 12, ch[2] + 12, ch[0] + 24]
        for k, idx in enumerate(pats[b % 2]):
            add(t0 + k * step, 1.15, tones_[idx], 0.115, flute, 0.02, 0.8)
        add(t0 + 4 * step, 2.4, ch[2] + 24, 0.035, flute, 0.08, 1.9)  # sparkle
    return buf


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------
EXPECTED = (
    "terrain_grass terrain_dirt terrain_sand terrain_rock terrain_road terrain_water floor_wood floor_stone floor_carpet "
    "floor_tile floor_soil tile_mask cursor crop tree bush boulder wall_wood wall_stone door_wood wall_wood_low "
    "wall_stone_low door_wood_low fence_post fence_rail_ne fence_rail_nw fence_rail_se fence_rail_sw gate_post bed bed_guru "
    "table stove altar desk printer crate donation_box merch lamp campfire mat statue loudspeaker confession watchtower "
    "banner goat pawn_skin_front pawn_skin_back pawn_robe_front pawn_robe_back pawn_civ_front pawn_civ_back pawn_hair_front "
    "pawn_hair_back acc_guru acc_hood acc_guard acc_police acc_soldier acc_press acc_inspector acc_sign fx_zzz fx_heart "
    "fx_exclaim fx_question fx_speech fx_halo fx_note fx_money fx_angry icon_money icon_food icon_meal icon_ep icon_heat "
    "icon_members icon_tracts icon_faith icon_mood icon_bond"
).split()

FRAME_SIZES = {  # ids with a contractually fixed frame size
    "crop": (32, 24), "tree": (32, 52), "bush": (32, 20), "boulder": (32, 22), "mat": (32, 16), "statue": (32, 48),
    "loudspeaker": (32, 48), "confession": (32, 44), "watchtower": (32, 60), "banner": (32, 48), "goat": (16, 14),
}


def check_tessellation(tile, n=6):
    """Draw an n x n patch with the renderer's projection; assert no holes/seams."""
    w, h = n * 32, n * 16
    s = new(w, h)
    for ry in range(n):
        for rx in range(n):
            s.blit(tile, ((rx - ry) * 16 + w // 2 - 16, (rx + ry) * 8 + 8 - 8))
    for y in range(h):
        k = y if y < h // 2 else h - 1 - y
        xs = [x for x in range(w) if s.get_at((x, y))[3] > 0]
        assert xs == list(range(w // 2 - 2 * (k + 1), w // 2 + 2 * (k + 1))), f"tessellation hole/seam in row {y}"
        assert all(s.get_at((x, y))[3] == 255 for x in xs), f"non-opaque ground pixel in row {y}"


def run_checks():
    missing = [i for i in EXPECTED if i not in SPRITES]
    extra = [i for i in SPRITES if i not in EXPECTED]
    assert not missing and not extra, (missing, extra)
    for sid, (surf, anchor, n) in SPRITES.items():
        w, h = surf.get_size()
        assert w % n == 0, f"{sid}: width {w} not divisible by {n} frames"
        fw = w // n
        if sid.startswith(("terrain_", "floor_")) or sid in ("tile_mask", "cursor"):
            assert (fw, h) == (32, 16) and anchor == (16, 8), sid
        if sid.startswith(("pawn_", "acc_")):
            assert (fw, h) == (12, 18) and anchor == (6, 16), sid
        if sid.startswith("fx_"):
            assert (fw, h) == (9, 9) and anchor == (4, 8), sid
        if sid.startswith("icon_"):
            assert (fw, h) == (16, 16) and anchor == (0, 0), sid
        if sid.startswith(("fence_", "gate_")):
            assert (fw, h) == (32, 28) and anchor == (16, 20), sid
        if sid in FRAME_SIZES:
            assert (fw, h) == FRAME_SIZES[sid], (sid, fw, h)
    # tile shape + tessellation
    mask = SPRITES["tile_mask"][0]
    assert {(x, y) for y in range(16) for x in range(32) if mask.get_at((x, y))[3]} == DSET
    for sid, (surf, _, n) in SPRITES.items():
        if sid.startswith(("terrain_", "floor_")) or sid == "tile_mask":
            for f in range(n):
                fr = surf.subsurface((f * 32, 0, 32, 16))
                assert {(x, y) for y in range(16) for x in range(32) if fr.get_at((x, y))[3]} == DSET, sid
                check_tessellation(fr)
    # wall blocks keep the exact tile footprint
    for sid in ("wall_wood", "wall_stone", "door_wood", "wall_wood_low", "wall_stone_low", "door_wood_low"):
        surf, (ax, ay), _ = SPRITES[sid]
        hh = surf.get_height() - 16
        want = {(x, y + dz) for x, y in DIAMOND for dz in range(hh + 1)}
        got = {(x, y) for y in range(surf.get_height()) for x in range(32) if surf.get_at((x, y))[3]}
        assert got == want and (ax, ay) == (16, 8 + hh), sid
    # pawn layers register: clothes must cover the same hand holes the skin fills
    for face in ("front", "back"):
        skin = SPRITES[f"pawn_skin_{face}"][0]
        for kind in ("robe", "civ"):
            cl = SPRITES[f"pawn_{kind}_{face}"][0]
            for f, (ly, ry) in enumerate(HANDS):
                for x, y in ((3, ly), (8, ry)):
                    assert cl.get_at((f * 12 + x, y))[3] == 0, (kind, face, f, "hand hole")
                    assert skin.get_at((f * 12 + x, y))[:3] == (255, 255, 255), (face, f, "hand")


# --------------------------------------------------------------------------
# preview (contact sheets + iso test scene)
# --------------------------------------------------------------------------
def load_from_manifest(base: Path):
    man = json.loads((base / "manifest.json").read_text())
    out = {}
    for sid, e in man["sprites"].items():
        img = pygame.image.load(str(base / e["file"]))
        n = e["frames"]
        fw = img.get_width() // n
        out[sid] = ([img.subsurface((i * fw, 0, fw, img.get_height())).copy() for i in range(n)], tuple(e["anchor"]))
    return man, out


def preview_contact(sprites, outdir: Path, scale=4, page_w=1400, page_h=1000):
    pygame.font.init()
    font = pygame.font.Font(None, 15)
    cells = []
    for sid, (frames, anchor) in sprites.items():
        fw, fh = frames[0].get_size()
        gap = 4
        w = len(frames) * fw * scale + (len(frames) - 1) * gap
        lab = font.render(f"{sid} {fw}x{fh} a{anchor[0]},{anchor[1]}" + (f" x{len(frames)}" if len(frames) > 1 else ""), False, (20, 20, 20))
        cw = max(w, lab.get_width()) + 10
        c = pygame.Surface((cw, fh * scale + 16), pygame.SRCALPHA)
        for i, f in enumerate(frames):
            pygame.draw.rect(c, (118, 118, 118), (i * (fw * scale + gap), 0, fw * scale, fh * scale))
            c.blit(pygame.transform.scale(f, (fw * scale, fh * scale)), (i * (fw * scale + gap), 0))
        c.blit(lab, (0, fh * scale + 2))
        cells.append(c)
    pages, rows, row, x = [], [], [], 0
    for c in cells:
        if x + c.get_width() > page_w and row:
            rows.append(row)
            row, x = [], 0
        row.append(c)
        x += c.get_width()
    if row:
        rows.append(row)
    page, y = [], 0
    for r in rows:
        rh = max(c.get_height() for c in r) + 8
        if y + rh > page_h and page:
            pages.append(page)
            page, y = [], 0
        page.append((r, rh))
        y += rh
    if page:
        pages.append(page)
    paths = []
    for pi, pg in enumerate(pages):
        s = pygame.Surface((page_w, sum(rh for _, rh in pg) + 8))
        s.fill((128, 128, 128))
        y = 6
        for r, rh in pg:
            x = 6
            for c in r:
                s.blit(c, (x, y + rh - 8 - c.get_height()))
                x += c.get_width()
            y += rh
        p = outdir / f"contact_sheet_{pi + 1}.png"
        pygame.image.save(s, str(p))
        paths.append(p)
    return paths


def preview_scene(sprites, path: Path, scale=3, cutaway=True):
    n = 16
    w, h = n * 32 + 16, n * 16 + 84
    ox, oy = n * 16 + 8, 64
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    s.fill((40, 36, 48, 255))

    def blit(sid, rx, ry, frame=0, tint=None, flip=False, dx=0, dy=0):
        frames, (ax, ay) = sprites[sid]
        img = frames[frame % len(frames)]
        if tint:
            img = img.copy()
            img.fill(tint, special_flags=pygame.BLEND_RGBA_MULT)
        if flip:
            img = pygame.transform.flip(img, True, False)
            ax = img.get_width() - ax
        s.blit(img, (ox + (rx - ry) * 16 - ax + dx, oy + (rx + ry) * 8 - ay + dy))

    ground = {(x, y): ("terrain_grass", (x * 7 + y * 13 + x * y) % 4) for x in range(n) for y in range(n)}
    objs: dict[tuple[int, int], list] = {}

    def add(rx, ry, sid, **kw):
        objs.setdefault((rx, ry), []).append((sid, kw))

    for x in range(12, 16):
        for y in range(0, 7):
            ground[(x, y)] = ("terrain_dirt", (x + y) % 2)
    for x in range(13, 16):
        for y in range(0, 5):
            ground[(x, y)] = ("terrain_sand", (x + y) % 2)
    for x in range(14, 16):
        for y in range(0, 4):
            ground[(x, y)] = ("terrain_water", (x + y) % 2)
    for p in ((7, 0), (8, 0), (9, 0), (7, 1), (10, 0), (8, 1)):
        ground[p] = ("terrain_rock", (p[0] + p[1]) % 2)
    for x in range(n):
        ground[(x, 7)] = ("terrain_road", x % 2)
    for y in range(7, n):
        ground[(7, y)] = ("terrain_road", y % 2)

    def room(x0, y0, x1, y1, wall, doors, floor):
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                edge = x in (x0, x1) or y in (y0, y1)
                if not edge:
                    ground[(x, y)] = (floor(x, y), 0)
                    continue
                front = cutaway and (y == y1 or x == x1) and not (x == x0 or y == y0)
                sid = "door_wood" if (x, y) in doors else wall
                add(x, y, sid + ("_low" if front else ""))

    room(1, 1, 6, 5, "wall_wood", {(4, 5), (1, 3), (3, 1)}, lambda x, y: "floor_carpet" if x >= 4 and y <= 3 else "floor_wood")
    add(2, 2, "bed")
    add(2, 4, "bed_guru")
    add(3, 3, "table")
    add(5, 2, "altar")
    add(5, 4, "lamp", frame=1)
    add(4, 3, "mat")
    room(8, 1, 12, 5, "wall_stone", {(10, 5), (12, 3)}, lambda x, y: "floor_stone" if (x + y) % 2 else "floor_tile")
    add(9, 2, "stove")
    add(11, 2, "desk")
    add(9, 4, "crate")
    add(11, 4, "printer")
    # fence loop with two gates, rails picked from neighbours
    fence = {(x, y) for x in range(9, 15) for y in range(9, 14) if x in (9, 14) or y in (9, 13)}
    gates = {(11, 9), (9, 11)}
    for (x, y) in sorted(fence):
        nb = {"ne": (x, y - 1), "nw": (x - 1, y), "se": (x + 1, y), "sw": (x, y + 1)}
        for d in ("ne", "nw"):
            if nb[d] in fence:
                add(x, y, f"fence_rail_{d}")
        add(x, y, "gate_post" if (x, y) in gates else "fence_post")
        for d in ("se", "sw"):
            if nb[d] in fence:
                add(x, y, f"fence_rail_{d}")
    for x in range(10, 13):
        for y in range(10, 13):
            ground[(x, y)] = ("floor_soil", 0)
            add(x, y, "crop", frame=(x - 10) + (1 if y == 12 else 0))
    add(13, 10, "goat", frame=0)
    add(13, 12, "goat", frame=1, flip=True)
    for p, f in (((0, 9), 0), ((0, 15), 1), ((1, 15), 0), ((15, 9), 1), ((15, 15), 0)):
        add(*p, "tree", frame=f)
    add(4, 15, "bush")
    add(15, 13, "bush")
    add(5, 15, "boulder")
    add(15, 11, "boulder")
    for x, sid in ((2, "campfire"), (4, "donation_box"), (6, "merch")):
        add(x, 9, sid)
    add(3, 10, "mat")
    for x, sid in ((0, "banner"), (2, "loudspeaker"), (4, "statue"), (6, "confession")):
        add(x, 12, sid)
    add(3, 14, "watchtower")
    add(8, 9, "lamp")
    add(15, 6, "banner")
    add(13, 6, "crate")
    add(14, 5, "campfire", frame=1)

    skins = ((232, 184, 144), (198, 138, 92), (138, 90, 60), (244, 208, 176))
    hairs = ((58, 42, 30), (216, 176, 96), (136, 136, 136), (160, 60, 30), (30, 26, 34))
    robes = ((123, 75, 179), (232, 224, 208), (176, 96, 60), (90, 60, 140))
    civs = ((110, 150, 200), (200, 110, 100), (120, 170, 110), (220, 200, 120), (150, 150, 160))
    accs = [None, "acc_guru", "acc_hood", "acc_guard", "acc_police", "acc_soldier", "acc_press", "acc_inspector", "acc_sign"]

    def pawn(rx, ry, i, face="front", robe=True, acc=None, frame=0, flip=False, fx=None, hair=True):
        tag = f"pawn{i}"
        add(rx, ry, f"pawn_skin_{face}", frame=frame, flip=flip, tint=skins[i % 4])
        add(rx, ry, f"pawn_{'robe' if robe else 'civ'}_{face}", frame=frame, flip=flip, tint=(robes if robe else civs)[i % (4 if robe else 5)])
        if hair:
            add(rx, ry, f"pawn_hair_{face}", frame=frame, flip=flip, tint=hairs[i % 5])
        if acc:
            add(rx, ry, acc, flip=flip)
        if fx:
            add(rx, ry, fx, dy=-19)
        return tag

    for i, a in enumerate(accs):                      # row of fronts on the road, one per accessory
        pawn(i if i < 7 else i + 1, 7, i, robe=a in (None, "acc_guru", "acc_hood", "acc_guard"), acc=a, frame=i % 3,
             fx=(None, "fx_halo", None, "fx_exclaim", None, None, "fx_question", None, "fx_angry")[i])
    pawn(11, 7, 1, face="back", frame=1)
    pawn(12, 7, 2, face="back", robe=False, frame=2)
    pawn(13, 7, 3, face="front", flip=True, frame=1, fx="fx_heart")
    pawn(14, 7, 0, face="back", flip=True, frame=0, acc="acc_hood")
    pawn(7, 9, 4, robe=False, frame=1, fx="fx_speech")
    pawn(7, 11, 1, face="back", hair=False, frame=2, fx="fx_note")
    pawn(7, 14, 2, frame=0, hair=False, fx="fx_zzz")
    pawn(3, 2, 0, frame=0, fx="fx_money")
    pawn(4, 4, 3, face="back", frame=1)
    pawn(1, 10, 2, frame=2)
    pawn(11, 11, 1, frame=1)

    for (x, y), (sid, f) in sorted(ground.items(), key=lambda kv: (kv[0][0] + kv[0][1], kv[0][0])):
        blit(sid, x, y, f)
    blit("tile_mask", 9, 7, tint=(255, 70, 70, 120))
    blit("tile_mask", 10, 7, tint=(70, 255, 90, 120))
    blit("cursor", 10, 7)
    blit("cursor", 3, 9)
    for (x, y) in sorted(objs, key=lambda p: (p[0] + p[1], p[0])):
        for sid, kw in objs[(x, y)]:
            blit(sid, x, y, **kw)
    # ui icons along the bottom
    ix = 6
    for sid in sprites:
        if sid.startswith("icon_"):
            s.blit(sprites[sid][0][0], (ix, h - 20))
            ix += 20
    pygame.image.save(pygame.transform.scale(s, (w * scale, h * scale)), str(path))


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--preview", metavar="DIR", help="also write contact sheets + iso test scene into DIR")
    ap.add_argument("--skip-audio", action="store_true", help="do not (re)synthesise wav files")
    args = ap.parse_args()

    pygame.init()
    make_ground()
    make_nature()
    make_blocks()
    make_furniture()
    make_pawns()
    make_fx()
    make_icons()
    run_checks()

    for sub in ("sprites", "sfx", "music"):
        (ASSETS / sub).mkdir(parents=True, exist_ok=True)

    manifest = {"tile": [TW, TH], "sprites": {}, "sounds": {}, "music": []}
    for sid in EXPECTED:
        surf, anchor, n = SPRITES[sid]
        pygame.image.save(surf, str(ASSETS / "sprites" / f"{sid}.png"))
        manifest["sprites"][sid] = {"file": f"sprites/{sid}.png", "anchor": [anchor[0], anchor[1]], "frames": n}

    sfx_volumes = {"click": 0.5, "place": 0.6, "build_done": 0.6, "convert": 0.7, "alert": 0.7, "event": 0.8, "coin": 0.6, "error": 0.6}
    if not args.skip_audio:
        sfx = make_sfx()
        assert set(sfx) == set(sfx_volumes)
        for sid, (samples, _) in sfx.items():
            write_wav(ASSETS / "sfx" / f"{sid}.wav", samples, peak=0.8)
        write_wav(ASSETS / "music" / "drone_organ.wav", make_music(), peak=0.62)
    for sid, vol in sfx_volumes.items():
        manifest["sounds"][sid] = {"file": f"sfx/{sid}.wav", "volume": vol}
    manifest["music"].append({"file": "music/drone_organ.wav", "title": "Orgel der Erleuchtung"})

    (ASSETS / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # verify what is on disk against the manifest (the contract)
    man, loaded = load_from_manifest(ASSETS)
    for sid, e in man["sprites"].items():
        img = pygame.image.load(str(ASSETS / e["file"]))
        assert img.get_width() % e["frames"] == 0, f"{sid}: PNG width not divisible by frames"
    for e in list(man["sounds"].values()) + man["music"]:
        assert args.skip_audio or (ASSETS / e["file"]).is_file(), f"missing {e['file']}"

    print(f"wrote {len(man['sprites'])} sprites, {len(man['sounds'])} sfx, {len(man['music'])} music -> {ASSETS}")
    if args.preview:
        out = Path(args.preview)
        out.mkdir(parents=True, exist_ok=True)
        pages = preview_contact(loaded, out)
        preview_scene(loaded, out / "scene.png")
        print("preview:", ", ".join(str(p) for p in pages), out / "scene.png")


if __name__ == "__main__":
    main()
