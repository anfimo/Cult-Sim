#!/usr/bin/env python3
"""Validiert und rendert die Kartendaten aus ``data/maps/*.json``.

Aufruf (vom Projektwurzelverzeichnis)::

    SDL_VIDEODRIVER=dummy uv run python tools/preview_maps.py [--width N] AUSGABE_VERZEICHNIS [karte.json ...]

Ohne explizite Dateien werden alle ``data/maps/*.json`` geprüft. ``--width N`` ändert die
Rasterbreite (Standard 300 px wie im Spiel), z. B. um zu sehen, ab wann Europa lesbar wird. Pro Karte:

* strenge Schema-Prüfung (Pflichtschlüssel, Wertebereiche, Verweise),
* Rasterung wie im Spiel: 300 px breit, Höhe aus dem Seitenverhältnis,
  Geo-Karten mit x = (lon - lon_min) * cos(mittlere Breite), y = lat_max - lat,
  Regionen in Dateireihenfolge (spätere liegen oben),
* PNG-Vorschau (4x, Nearest Neighbour) mit Grenzen, Kürzeln und Links,
* berechnete Land-Nachbarschaften (Pixelabstand <= 1 bzw. <= 2) und Warnungen.

Exit-Code 1 bei Schemafehlern, sonst 0 (Warnungen brechen nicht ab).
"""

from __future__ import annotations

import colorsys
import json
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

RASTER_W = 300
SCALE = 4
MIN_PIXELS = 12
NEAR = 2  # Pixelabstand (Chebyshev), bis zu dem Regionen als Nachbarn gelten

TOP_KEYS = {"id", "name", "geo", "bounds", "home", "pop_unit", "languages", "regions", "links"}
REGION_KEYS = {
    "id", "name", "polys", "pop", "lang", "wealth", "openness", "state",
    "press", "military", "affinity", "quirk",
}
UNIT_KEYS = ("wealth", "openness", "state", "press", "military")
AFFINITY_KEYS = {"commerce", "isolation", "apocalypse"}
QUIRK_KEYS = {"name", "text", "mods"}
MOD_KEYS = {"growth", "income", "heat", "cost", "legal"}
MOD_MIN, MOD_MAX = 0.5, 1.6
POP_UNITS = {"Mio.", "Tsd."}

SEA = (22, 34, 58)
BORDER = (12, 14, 22)


def is_num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


# --------------------------------------------------------------------------- #
# Validierung
# --------------------------------------------------------------------------- #
def validate(data: object) -> tuple[list[str], list[str]]:
    """Gibt (Fehler, Warnungen) zurück. Fehler = Schema verletzt."""
    err: list[str] = []
    warn: list[str] = []
    if not isinstance(data, dict):
        return ["Wurzel ist kein Objekt"], warn

    missing = TOP_KEYS - data.keys()
    extra = data.keys() - TOP_KEYS
    if missing:
        err.append(f"fehlende Schlüssel: {sorted(missing)}")
    if extra:
        err.append(f"unbekannte Schlüssel: {sorted(extra)}")
    if missing:
        return err, warn

    for key in ("id", "name", "home"):
        if not isinstance(data[key], str) or not data[key]:
            err.append(f"'{key}' muss ein nicht-leerer String sein")
    if not isinstance(data["geo"], bool):
        err.append("'geo' muss true/false sein")
    if data["pop_unit"] not in POP_UNITS:
        err.append(f"'pop_unit' muss eines von {sorted(POP_UNITS)} sein")

    b = data["bounds"]
    bounds_ok = isinstance(b, list) and len(b) == 4 and all(is_num(v) for v in b) and b[0] < b[2] and b[1] < b[3]
    if not bounds_ok:
        err.append("'bounds' muss [x_min, y_min, x_max, y_max] mit min < max sein")
    elif data["geo"] is True and not (-180 <= b[0] and b[2] <= 180 and -90 <= b[1] and b[3] <= 90):
        err.append("'bounds' einer Geo-Karte liegt außerhalb von lon/lat")

    langs = data["languages"]
    if not isinstance(langs, dict) or not langs or not all(
        isinstance(k, str) and isinstance(v, str) and k and v for k, v in langs.items()
    ):
        err.append("'languages' muss ein nicht-leeres Objekt {kürzel: name} sein")
        langs = {}

    regions = data["regions"]
    if not isinstance(regions, list) or not regions:
        err.append("'regions' muss eine nicht-leere Liste sein")
        return err, warn

    ids: list[str] = []
    used_langs: set[str] = set()
    for n, reg in enumerate(regions):
        if not isinstance(reg, dict):
            err.append(f"regions[{n}] ist kein Objekt")
            continue
        rid = reg.get("id")
        tag = f"Region '{rid}'" if isinstance(rid, str) else f"regions[{n}]"
        r_missing = REGION_KEYS - reg.keys()
        r_extra = reg.keys() - REGION_KEYS
        if r_missing:
            err.append(f"{tag}: fehlende Schlüssel {sorted(r_missing)}")
        if r_extra:
            err.append(f"{tag}: unbekannte Schlüssel {sorted(r_extra)}")
        if r_missing:
            continue
        if not isinstance(rid, str) or not rid:
            err.append(f"{tag}: 'id' muss ein nicht-leerer String sein")
        else:
            ids.append(rid)
        if not isinstance(reg["name"], str) or not reg["name"].strip():
            err.append(f"{tag}: 'name' leer")

        polys = reg["polys"]
        if not isinstance(polys, list) or not polys:
            err.append(f"{tag}: 'polys' muss eine nicht-leere Liste sein")
        else:
            for pn, poly in enumerate(polys):
                if not isinstance(poly, list) or len(poly) < 3:
                    err.append(f"{tag}: polys[{pn}] braucht mindestens 3 Punkte")
                    continue
                bad = [p for p in poly if not (isinstance(p, list) and len(p) == 2 and all(is_num(c) for c in p))]
                if bad:
                    err.append(f"{tag}: polys[{pn}] enthält ungültige Punkte, z. B. {bad[0]!r}")
                    continue
                if bounds_ok:
                    out = [p for p in poly if not (b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3])]
                    if out:
                        err.append(f"{tag}: polys[{pn}] hat {len(out)} Punkt(e) außerhalb der bounds, z. B. {out[0]}")
                if len(poly) > 3 and poly[0] == poly[-1]:
                    warn.append(f"{tag}: polys[{pn}] ist geschlossen (erster == letzter Punkt), unnötig")

        if not is_num(reg["pop"]) or reg["pop"] <= 0:
            err.append(f"{tag}: 'pop' muss > 0 sein")
        if reg["lang"] not in langs:
            err.append(f"{tag}: lang '{reg['lang']}' fehlt in 'languages'")
        else:
            used_langs.add(reg["lang"])
        for key in UNIT_KEYS:
            if not is_num(reg[key]) or not 0 <= reg[key] <= 1:
                err.append(f"{tag}: '{key}' muss in 0..1 liegen (ist {reg[key]!r})")

        aff = reg["affinity"]
        if not isinstance(aff, dict) or set(aff) != AFFINITY_KEYS:
            err.append(f"{tag}: 'affinity' braucht genau die Schlüssel {sorted(AFFINITY_KEYS)}")
        else:
            for key, val in aff.items():
                if not is_num(val) or not -1 <= val <= 1:
                    err.append(f"{tag}: affinity.{key} muss in -1..1 liegen (ist {val!r})")

        quirk = reg["quirk"]
        if not isinstance(quirk, dict) or set(quirk) != QUIRK_KEYS:
            err.append(f"{tag}: 'quirk' braucht genau die Schlüssel {sorted(QUIRK_KEYS)}")
        else:
            for key in ("name", "text"):
                if not isinstance(quirk[key], str) or not quirk[key].strip():
                    err.append(f"{tag}: quirk.{key} leer")
            mods = quirk["mods"]
            if not isinstance(mods, dict):
                err.append(f"{tag}: quirk.mods muss ein Objekt sein")
            else:
                bad_keys = set(mods) - MOD_KEYS
                if bad_keys:
                    err.append(f"{tag}: quirk.mods mit unbekannten Schlüsseln {sorted(bad_keys)}")
                for key, val in mods.items():
                    if not is_num(val) or not MOD_MIN <= val <= MOD_MAX:
                        err.append(f"{tag}: quirk.mods.{key} muss in {MOD_MIN}..{MOD_MAX} liegen (ist {val!r})")
                    elif val == 1:
                        warn.append(f"{tag}: quirk.mods.{key} ist 1.0 und kann entfallen")
                if not mods:
                    warn.append(f"{tag}: quirk ohne mods")

    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        err.append(f"doppelte Regions-ids: {dupes}")
    idset = set(ids)
    if isinstance(data["home"], str) and data["home"] not in idset:
        err.append(f"home '{data['home']}' ist keine Region")
    unused = sorted(set(langs) - used_langs)
    if unused:
        warn.append(f"unbenutzte Sprachen: {unused}")

    links = data["links"]
    if not isinstance(links, list):
        err.append("'links' muss eine Liste sein")
    else:
        seen: set[frozenset[str]] = set()
        for n, link in enumerate(links):
            if not (isinstance(link, list) and len(link) == 2 and all(isinstance(v, str) for v in link)):
                err.append(f"links[{n}] muss ein Paar aus zwei ids sein")
                continue
            a, c = link
            if a == c:
                err.append(f"links[{n}] verbindet '{a}' mit sich selbst")
            for v in link:
                if v not in idset:
                    err.append(f"links[{n}]: unbekannte id '{v}'")
            key = frozenset(link)
            if key in seen:
                warn.append(f"links[{n}] {link} ist doppelt")
            seen.add(key)
    return err, warn


# --------------------------------------------------------------------------- #
# Rasterung
# --------------------------------------------------------------------------- #
def projector(data: dict):
    """Liefert (project(x, y) -> Pixel, Breite, Höhe) wie im Spiel."""
    x0, y0, x1, y1 = data["bounds"]
    if data["geo"]:
        k = math.cos(math.radians((y0 + y1) / 2))
        scale = RASTER_W / ((x1 - x0) * k)
        height = max(1, round((y1 - y0) * scale))

        def project(x: float, y: float) -> tuple[float, float]:
            return (x - x0) * k * scale, (y1 - y) * scale
    else:
        scale = RASTER_W / (x1 - x0)
        height = max(1, round((y1 - y0) * scale))

        def project(x: float, y: float) -> tuple[float, float]:
            return (x - x0) * scale, (y - y0) * scale

    return project, RASTER_W, height


def rasterise(data: dict) -> tuple[list[list[int]], int, int]:
    """Index-Raster: -1 = Hintergrund, sonst Index in data['regions']."""
    project, w, h = projector(data)
    surf = pygame.Surface((w, h))
    surf.fill((0, 0, 0))
    for i, reg in enumerate(data["regions"]):
        code = i + 1
        colour = (code & 0xFF, (code >> 8) & 0xFF, 0)
        for poly in reg["polys"]:
            pygame.draw.polygon(surf, colour, [project(x, y) for x, y in poly])
    raw = pygame.image.tobytes(surf, "RGB")
    grid = [[raw[(y * w + x) * 3] + (raw[(y * w + x) * 3 + 1] << 8) - 1 for x in range(w)] for y in range(h)]
    return grid, w, h


def analyse(grid: list[list[int]], w: int, h: int, n: int):
    """Pixelzahl, Label-Anker, Nachbarschaften (Abstand 1 und <= NEAR)."""
    count = [0] * n
    sx = [0] * n
    sy = [0] * n
    direct: set[tuple[int, int]] = set()
    near: set[tuple[int, int]] = set()
    offsets = [(dx, dy) for dy in range(0, NEAR + 1) for dx in range(-NEAR, NEAR + 1) if (dy, dx) > (0, 0)]
    for y in range(h):
        row = grid[y]
        for x in range(w):
            a = row[x]
            if a < 0:
                continue
            count[a] += 1
            sx[a] += x
            sy[a] += y
            for dx, dy in offsets:
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and yy < h:
                    c = grid[yy][xx]
                    if c >= 0 and c != a:
                        pair = (a, c) if a < c else (c, a)
                        near.add(pair)
                        if abs(dx) <= 1 and dy <= 1:
                            direct.add(pair)
    # Abstand jedes Pixels zum Rand seiner Region (Chamfer, 2 Durchläufe) für lesbare Labels
    depth = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            a = grid[y][x]
            if a < 0 or x == 0 or y == 0 or grid[y][x - 1] != a or grid[y - 1][x] != a:
                depth[y][x] = 1 if a >= 0 else 0
            else:
                depth[y][x] = min(depth[y][x - 1], depth[y - 1][x]) + 1
    for y in range(h - 1, -1, -1):
        for x in range(w - 1, -1, -1):
            a = grid[y][x]
            if a < 0:
                continue
            if x == w - 1 or y == h - 1 or grid[y][x + 1] != a or grid[y + 1][x] != a:
                depth[y][x] = 1
            else:
                depth[y][x] = min(depth[y][x], depth[y][x + 1] + 1, depth[y + 1][x] + 1)
    # Label-Anker: Pixelschwerpunkt; liegt er außerhalb oder direkt am Rand, das innerste Pixel
    best: list[tuple[float, int, int] | None] = [None] * n
    for y in range(h):
        row = grid[y]
        for x in range(w):
            a = row[x]
            if a < 0:
                continue
            cx, cy = sx[a] / count[a], sy[a] / count[a]
            key = (depth[y][x] - 0.001 * math.hypot(x - cx, y - cy), x, y)
            if best[a] is None or key > best[a]:
                best[a] = key
    anchors: list[tuple[int, int] | None] = []
    for i in range(n):
        if not count[i]:
            anchors.append(None)
            continue
        cx, cy = round(sx[i] / count[i]), round(sy[i] / count[i])
        inner = best[i]
        if grid[cy][cx] == i and depth[cy][cx] >= min(4, inner[0] * 0.6):
            anchors.append((cx, cy))
        else:
            anchors.append((inner[1], inner[2]))
    return count, anchors, direct, near


def region_colour(i: int, n: int) -> tuple[int, int, int]:
    hue = (i * 0.61803398875) % 1.0
    sat = (0.45, 0.62, 0.78)[i % 3]
    val = (0.92, 0.78, 0.66)[(i // 3) % 3]
    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return int(r * 255), int(g * 255), int(b * 255)


def render(data: dict, grid, w: int, h: int, anchors, out_path: Path) -> None:
    regions = data["regions"]
    n = len(regions)
    small = pygame.Surface((w, h))
    small.fill(SEA)
    for y in range(h):
        row = grid[y]
        for x in range(w):
            a = row[x]
            if a < 0:
                continue
            # 1 px Grenze nur zwischen zwei Regionen (rechts/unten); Küsten hebt das Meer genug ab,
            # sonst bestünden Kleinregionen der Weltkarte nur aus Grenzpixeln
            right = row[x + 1] if x + 1 < w else a
            below = grid[y + 1][x] if y + 1 < h else a
            edge = (right >= 0 and right != a) or (below >= 0 and below != a)
            small.set_at((x, y), BORDER if edge else region_colour(a, n))
    big = pygame.transform.scale(small, (w * SCALE, h * SCALE))

    def centre(i: int) -> tuple[int, int] | None:
        a = anchors[i]
        return None if a is None else (a[0] * SCALE + SCALE // 2, a[1] * SCALE + SCALE // 2)

    index = {reg["id"]: i for i, reg in enumerate(regions)}
    for a, c in data["links"]:
        pa, pc = centre(index[a]), centre(index[c])
        if pa and pc:
            steps = max(2, int(math.dist(pa, pc) // 6))
            for s in range(0, steps, 2):
                p0 = (pa[0] + (pc[0] - pa[0]) * s / steps, pa[1] + (pc[1] - pa[1]) * s / steps)
                p1 = (pa[0] + (pc[0] - pa[0]) * (s + 1) / steps, pa[1] + (pc[1] - pa[1]) * (s + 1) / steps)
                pygame.draw.line(big, (255, 240, 150), p0, p1, 1)

    font = pygame.font.Font(None, 15)
    for i, reg in enumerate(regions):
        pos = centre(i)
        if pos is None:
            continue
        text = reg["id"] + ("*" if reg["id"] == data["home"] else "")
        label = font.render(text, True, (255, 255, 255))
        shadow = font.render(text, True, (0, 0, 0))
        rect = label.get_rect(center=pos)
        rect.clamp_ip(big.get_rect())
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            big.blit(shadow, rect.move(dx, dy))
        big.blit(label, rect)
    pygame.image.save(big, str(out_path))


# --------------------------------------------------------------------------- #
# Bericht
# --------------------------------------------------------------------------- #
def components(ids: list[str], pairs: set[frozenset[str]]) -> list[list[str]]:
    graph = {i: set() for i in ids}
    for pair in pairs:
        a, c = tuple(pair)
        graph[a].add(c)
        graph[c].add(a)
    seen: set[str] = set()
    comps = []
    for start in ids:
        if start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nxt in graph[cur] - seen:
                seen.add(nxt)
                stack.append(nxt)
        comps.append(sorted(comp))
    return comps


def process(path: Path, out_dir: Path) -> bool:
    print(f"\n=== {path} ===")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  FEHLER: nicht lesbar: {exc}")
        return False
    errors, warnings = validate(data)
    for msg in errors:
        print(f"  FEHLER: {msg}")
    if errors:
        print(f"  Schema: {len(errors)} Fehler - keine Vorschau")
        return False

    regions = data["regions"]
    ids = [r["id"] for r in regions]
    grid, w, h = rasterise(data)
    count, anchors, direct, near = analyse(grid, w, h, len(regions))
    out_path = out_dir / f"{path.stem}.png"
    render(data, grid, w, h, anchors, out_path)

    total_pop = sum(r["pop"] for r in regions)
    verts = sum(len(p) for r in regions for p in r["polys"])
    print(f"  Schema OK - '{data['name']}', {len(regions)} Regionen, home={data['home']}, "
          f"Raster {w}x{h}, {verts} Stützpunkte, Summe pop {total_pop:.1f} {data['pop_unit']}")
    print(f"  Vorschau: {out_path}")

    print("  Regionen (id: Pixel / Polygone / Stützpunkte):")
    line = "   "
    for i, reg in enumerate(regions):
        item = f" {reg['id']}:{count[i]}/{len(reg['polys'])}/{sum(len(p) for p in reg['polys'])}"
        if len(line) + len(item) > 100:
            print(line)
            line = "   "
        line += item
    print(line)

    direct_ids = {frozenset((ids[a], ids[c])) for a, c in direct}
    near_ids = {frozenset((ids[a], ids[c])) for a, c in near}
    link_ids = {frozenset(link) for link in data["links"]}

    def fmt(pairs) -> str:
        return ", ".join("-".join(sorted(p)) for p in sorted(pairs, key=lambda p: sorted(p))) or "(keine)"

    print(f"  Land-Nachbarschaft, direkt (Abstand 1 px), {len(direct_ids)} Paare:")
    print(f"    {fmt(direct_ids)}")
    print(f"  zusätzlich bei Abstand <= {NEAR} px, {len(near_ids - direct_ids)} Paare:")
    print(f"    {fmt(near_ids - direct_ids)}")
    print(f"  links ({len(link_ids)}): {fmt(link_ids)}")
    print("  Nachbarn je Region (<= 2 px, +links):")
    for rid in ids:
        land = sorted(next(iter(p - {rid})) for p in near_ids if rid in p)
        extra = sorted(next(iter(p - {rid})) for p in link_ids - near_ids if rid in p)
        print(f"    {rid:10s} {' '.join(land) or '-'}" + (f"   | links: {' '.join(extra)}" if extra else ""))

    for i, reg in enumerate(regions):
        if count[i] < MIN_PIXELS:
            warnings.append(f"Region '{reg['id']}' hat nur {count[i]} Rasterpixel (< {MIN_PIXELS})")
        rid = reg["id"]
        if not any(rid in p for p in near_ids | link_ids):
            warnings.append(f"Region '{rid}' hat weder Nachbarn noch links")
    redundant = link_ids & direct_ids
    if redundant:
        print(f"  Hinweis: links, die im Raster ohnehin direkt benachbart sind (z. B. Meerengen): {fmt(redundant)}")
    comps = components(ids, near_ids | link_ids)
    if len(comps) > 1:
        warnings.append(f"Graph aus Nachbarn + links zerfällt in {len(comps)} Teile: {comps}")
    for msg in warnings:
        print(f"  WARNUNG: {msg}")
    if not warnings:
        print("  keine Warnungen")
    return True


def main(argv: list[str]) -> int:
    global RASTER_W
    argv = list(argv)
    if "--width" in argv:
        pos = argv.index("--width")
        try:
            RASTER_W = int(argv[pos + 1])
        except (IndexError, ValueError):
            print("--width braucht eine ganze Zahl")
            return 2
        if not 50 <= RASTER_W <= 4000:
            print("--width muss zwischen 50 und 4000 liegen")
            return 2
        del argv[pos:pos + 2]
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 2
    out_dir = Path(argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    if len(argv) > 2:
        paths = [Path(p) for p in argv[2:]]
    else:
        root = Path(__file__).resolve().parent.parent
        paths = sorted((root / "data" / "maps").glob("*.json"))
    if not paths:
        print("keine Kartendateien gefunden")
        return 1
    pygame.init()
    pygame.font.init()
    ok = True
    for path in paths:
        ok = process(path, out_dir) and ok
    pygame.quit()
    print("\nErgebnis:", "alle Karten gültig" if ok else "FEHLER gefunden")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
