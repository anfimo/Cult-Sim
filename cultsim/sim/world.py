"""Der Weltzustand des Sektengeländes: Gitter, Bauten, Räume, Ressourcen, Zeit.

Die Simulation ist bewusst frei von pygame – sie läuft auch headless (Tests, Server, KI-Spieler).
"""
from __future__ import annotations

import math
import pickle
import random

from ..config import *
from ..data import DATA
from . import events
from .path import astar, label_components
from .pawns import Pawn, make_member, make_outsider, MEMBER_KINDS
from .strategic import Strategic

N8 = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
N4 = ((1, 0), (0, 1), (-1, 0), (0, -1))


class Thing:
    __slots__ = ("id", "d", "x", "y", "built", "progress", "conn", "owner", "reserved")

    def __init__(self, tid, d, x, y, built):
        self.id, self.d, self.x, self.y, self.built = tid, d, x, y, built
        self.progress = 0.0
        self.conn = 0
        self.owner = None
        self.reserved = None

    @property
    def defn(self):
        return DATA.buildables[self.d]


class Room:
    def __init__(self, rid, tiles, kind):
        self.id, self.tiles, self.kind = rid, tiles, kind   # kind: 'raum' | 'hof'
        self.uses: dict[str, int] = {}
        self.pracht = 0.0
        self.role = "Leerer Raum"
        self.cx = self.cy = 0

    @property
    def size(self):
        return len(self.tiles)

    @property
    def pracht_text(self):
        p = self.pracht
        return ("karg" if p < 2 else "schlicht" if p < 6 else "ansehnlich" if p < 14
                else "prächtig" if p < 28 else "größenwahnsinnig")


ROOM_ROLES = [  # (use, min, Name im Raum, Name im Hof)
    ("altar", 1, "Tempel", "Freiluft-Tempel"),
    ("bed_guru", 1, "Gemach des Gurus", "Gemach des Gurus"),
    ("confession", 1, "Beichtraum", "Beichthof"),
    ("stove", 1, "Küche", "Kochplatz"),
    ("printer", 1, "Druckerei", "Druckerei"),
    ("desk", 1, "Schreibstube", "Schreibstube"),
    ("bed", 2, "Schlafsaal", "Freiluft-Schlafsaal"),
    ("bed", 1, "Kammer", "Schlafplatz"),
    ("table", 1, "Speisesaal", "Biergarten der Erleuchtung"),
    ("merch", 1, "Souvenirladen", "Marktplatz"),
    ("mat", 1, "Meditationsraum", "Meditationsgarten"),
    ("crate", 1, "Lager", "Lagerplatz"),
]


class World:
    def __init__(self, seed=None, cult_name="Kirche des Großen Bald", guru_name="Swami Günther", myth="sterne"):
        if not DATA.loaded:
            DATA.load()
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(self.seed)
        self.cult_name, self.guru_name, self.myth = cult_name, guru_name, myth
        S = self.size = MAP_SIZE
        n = S * S
        self.terrain = [T_GRASS] * n
        self.variant = [0] * n
        self.floor: list = [None] * n
        self.things: list = [None] * n
        self.zone = [0] * n
        self.room_of = [-1] * n
        self.thing_list: list[Thing] = []
        self.thing_ids: dict[int, Thing] = {}
        self.blueprints: list[Thing] = []
        self.crops: dict[int, float] = {}
        self.rooms: list[Room] = []
        self.by_use: dict[str, list[Thing]] = {}
        self.pawns: list[Pawn] = []
        self.pawn_ids: dict[int, Pawn] = {}
        self.next_id = 1
        self.tick_n = START_TICK
        # Ressourcen
        self.money = 1200.0
        self.food = 45.0
        self.meals = 10.0
        self.ep = 12.0
        self.tracts = 6.0
        self.heat = 0.0
        self.evidence = 0.0
        self.ledger: dict[str, float] = {}
        self.ledger_last: dict[str, float] = {}
        # Lehre
        self.doctrine = {a: 0.0 for a in AXES}
        self.bias = {a: 0.0 for a in AXES}
        for a, v in next(m for m in DATA.doctrine["myths"] if m["id"] == myth)["doctrine"].items():
            self.doctrine[a] = float(v)
            self.bias[a] = float(v)
        self.edicts: set[str] = set()
        self.projects_done: list[str] = []
        self.project = None           # [id, tage_rest]
        self.lawyers = 0
        self.archetype = "gemischt"
        # Meldungen
        self.notes: list[dict] = []
        self.popups: list[dict] = []
        self.cues: list[str] = []
        self.flags: dict = {}
        self.event_cd: dict[str, int] = {}
        self.event_hour = 12
        self.schism = None
        self.over = None              # ('win'|'lose', text)
        self.dirty = True
        self.ground_rev = 0
        self.struct_rev = 0
        self.passmap = [[1.0] * n for _ in range(4)]
        self.comp = [[0] * n for _ in range(4)]
        self._mods, self._adds, self._flags, self._sched = {}, {}, set(), {}
        self.field_busy: set[int] = set()
        self._fields: list[int] = []
        self._fields_rev = -1
        self.preach_tick, self.preach_skill, self.preach_pos = -99, 0.0, (0.0, 0.0)
        self.strategic = Strategic(self)
        self.generate()
        self.recompute_mods()
        self.rebuild()
        events.welcome(self)

    # ------------------------------------------------------------------ Zeit
    @property
    def day(self):
        return self.tick_n // TICKS_PER_DAY + 1

    @property
    def hour(self):
        return (self.tick_n % TICKS_PER_DAY) / TICKS_PER_HOUR

    @property
    def phase(self):
        return self.strategic.phase

    def clock(self):
        h = self.hour
        return f"Tag {self.day}, {int(h):02d}:{int(h % 1 * 60) // 10 * 10:02d}"

    # ------------------------------------------------------------------ Gitter
    def idx(self, x, y):
        return x + y * self.size

    def inb(self, x, y):
        return 0 <= x < self.size and 0 <= y < self.size

    def thing_at(self, x, y):
        return self.things[x + y * self.size] if self.inb(x, y) else None

    def room_at(self, x, y):
        r = self.room_of[x + y * self.size] if self.inb(x, y) else -1
        return self.rooms[r] if r >= 0 else None

    def generate(self):
        S, rng = self.size, self.rng
        c = S // 2

        def noise(cells):
            g = [[rng.random() for _ in range(cells + 2)] for _ in range(cells + 2)]
            out = []
            for y in range(S):
                fy = y / S * cells; y0 = int(fy); ty = fy - y0
                for x in range(S):
                    fx = x / S * cells; x0 = int(fx); tx = fx - x0
                    a = g[y0][x0] * (1 - tx) + g[y0][x0 + 1] * tx
                    b = g[y0 + 1][x0] * (1 - tx) + g[y0 + 1][x0 + 1] * tx
                    out.append(a * (1 - ty) + b * ty)
            return out

        n1, n2 = noise(7), noise(9)
        ang = rng.uniform(math.pi * 0.9, math.pi * 2.1)
        px, py = int(c + math.cos(ang) * 17), int(c + math.sin(ang) * 15)
        for y in range(S):
            for x in range(S):
                i = x + y * S
                self.variant[i] = rng.randrange(8)
                d_c = math.hypot(x - c, y - c)
                t = T_GRASS
                if n1[i] > 0.70:
                    t = T_DIRT
                if n2[i] > 0.80 and d_c > 12:
                    t = T_ROCK
                dp = math.hypot(x - px, (y - py) * 1.3) + n1[i] * 2
                if dp < 4.2:
                    t = T_WATER
                elif dp < 5.6:
                    t = T_SAND
                self.terrain[i] = t
        # Zufahrt von Süden
        self.road = []
        for y in range(S - 1, c + 5, -1):
            x = c + (1 if 44 < y < 50 else 0)
            for xx in (x, x + 1):
                self.terrain[xx + y * S] = T_ROAD
            self.road.append((x, y))
        self.exit = (c, S - 1)
        road_set = {(x, y) for x, y in self.road} | {(x + 1, y) for x, y in self.road}
        # Natur
        for y in range(S):
            for x in range(S):
                i = x + y * S
                if self.terrain[i] in (T_WATER, T_ROAD) or (x, y) in road_set:
                    continue
                d_c = math.hypot(x - c, y - c) / (S / 2)
                if d_c < 0.42:
                    continue
                r = rng.random()
                if self.terrain[i] == T_ROCK and r < 0.25:
                    self._add_thing("boulder", x, y, True)
                elif r < 0.03 + 0.42 * max(0.0, d_c - 0.45) ** 1.3 and abs(x - c) > 2:
                    self._add_thing("tree", x, y, True)
                elif r > 0.975:
                    self._add_thing("bush", x, y, True)
        # Startgelände: eine zugige Hütte, eine Feuerstelle, ein Obstkisten-Altar
        x0, y0 = c - 4, c - 2
        for x in range(x0, x0 + 6):
            for y in range(y0, y0 + 5):
                edge = x in (x0, x0 + 5) or y in (y0, y0 + 4)
                self.terrain[x + y * S] = T_GRASS
                if edge:
                    self._add_thing("door_wood" if (x, y) == (x0 + 3, y0 + 4) else "wall_wood", x, y, True)
                else:
                    self.floor[x + y * S] = "floor_wood"
        for k, (bx, by) in enumerate([(x0 + 1, y0 + 1), (x0 + 2, y0 + 1), (x0 + 4, y0 + 1), (x0 + 1, y0 + 3)]):
            self._add_thing("bed", bx, by, True)
        self._add_thing("campfire", c + 4, c + 1, True)
        self._add_thing("table", c + 5, c + 2, True)
        self._add_thing("crate", c + 4, c - 1, True)
        self._add_thing("altar", c + 6, c - 4, True)
        self._add_thing("mat", c + 5, c - 3, True)
        self._add_thing("mat", c + 7, c - 3, True)
        for x in range(c - 9, c - 5):
            for y in range(c, c + 3):
                self.terrain[x + y * S] = T_GRASS
                self.zone[x + y * S] = Z_FIELD
        for x in range(c, c + 3):
            for y in range(c + 5, c + 7):
                self.zone[x + y * S] = Z_VISIT
        # Gründungsmitglieder
        g = make_member(self, c + 1, c + 4, guru=True)
        g.name = self.guru_name
        for k in range(3):
            m = make_member(self, c - 1 + k, c + 5)
            m.faith, m.bond = 70 + k * 5, 35
            m.role = ("worker", "cook", "preacher")[k]

    # ------------------------------------------------------------------ Bauen
    def _add_thing(self, did, x, y, built):
        i = x + y * self.size
        old = self.things[i]
        if old is not None:
            self._del_thing(old)
        th = Thing(self.next_id, did, x, y, built)
        self.next_id += 1
        self.things[i] = th
        self.thing_list.append(th)
        self.thing_ids[th.id] = th
        if not built:
            self.blueprints.append(th)
        self.dirty = True
        return th

    def _del_thing(self, th):
        self.things[th.x + th.y * self.size] = None
        self.thing_list.remove(th)
        self.thing_ids.pop(th.id, None)
        if th in self.blueprints:
            self.blueprints.remove(th)
        if th.owner:
            p = self.pawn_ids.get(th.owner)
            if p and p.bed == th.id:
                p.bed = None
        self.dirty = True

    def can_place(self, did, x, y):
        d = DATA.buildables[did]
        if not self.inb(x, y):
            return "Außerhalb der Karte"
        i = x + y * self.size
        if self.terrain[i] == T_WATER:
            return "Im Wasser baut nur der Glaube"
        k = d["kind"]
        if k == "floor":
            return None if self.floor[i] != did else "Schon vorhanden"
        if k == "animal":
            return None if self.passmap[C_ANIMAL][i] else "Blockiert"
        if abs(x - self.exit[0]) <= 1 and y >= self.size - 2:
            return "Die Zufahrt muss frei bleiben"
        th = self.things[i]
        if th is not None and th.defn["kind"] != "nature":
            return "Feld belegt"
        return None

    def place_cost(self, did, x, y):
        d = DATA.buildables[did]
        th = self.things[x + y * self.size]
        return d["cost"] + (3 if th is not None and d["kind"] not in ("floor", "animal") else 0)

    def place(self, did, x, y, free=False):
        """Setzt einen Bauauftrag (oder Boden/Tier sofort). Liefert None bei Erfolg, sonst Fehlertext."""
        err = self.can_place(did, x, y)
        if err:
            return err
        d = DATA.buildables[did]
        cost = 0 if free else self.place_cost(did, x, y)
        if self.money < cost:
            return "Zu wenig Geld"
        self.spend("Bau", cost)
        i = x + y * self.size
        if d["kind"] == "floor":
            self.floor[i] = did
            self.ground_rev += 1
        elif d["kind"] == "animal":
            g = Pawn(self, "goat", x, y)
            g.name = self.rng.choice(DATA.names["goat"])
            self.notify(f"Die heilige Ziege {g.name} ist eingezogen.", "good", (x, y))
        else:
            self._add_thing(did, x, y, False)
        return None

    def remove(self, x, y):
        if not self.inb(x, y):
            return False
        i = x + y * self.size
        th = self.things[i]
        if th is not None:
            d = th.defn
            if d["kind"] == "nature":
                if self.money < 3:
                    return False
                self.spend("Bau", 3)
            else:
                self.money += d["cost"] if not th.built else int(d["cost"] * 0.3)
            self._del_thing(th)
            return True
        if self.floor[i]:
            self.floor[i] = None
            self.ground_rev += 1
            return True
        return False

    def finish(self, th):
        th.built = True
        th.progress = 1.0
        if th in self.blueprints:
            self.blueprints.remove(th)
        self.dirty = True
        self.cues.append("build_done")

    def set_zone(self, x, y, z):
        if not self.inb(x, y):
            return
        i = x + y * self.size
        if self.terrain[i] == T_WATER:
            return
        if self.zone[i] == Z_FIELD and z != Z_FIELD:
            self.crops.pop(i, None)
        self.zone[i] = z
        self.ground_rev += 1

    # ------------------------------------------------------------------ Analyse: Passierbarkeit, Räume, Gehege
    def rebuild(self):
        S = self.size
        n = S * S
        base = [1.0] * n
        for i in range(n):
            t = self.terrain[i]
            if t == T_WATER:
                base[i] = 0.0
            elif t == T_ROAD:
                base[i] = 0.8
            elif t == T_SAND:
                base[i] = 1.3
            elif self.floor[i]:
                base[i] = 0.9
        pm = [base[:], base[:], base[:], base[:]]
        barrier = [False] * n
        open_gates = "open_gates" in self._flags
        by_use: dict[str, list] = {}
        for th in self.thing_list:
            d = th.defn
            k = d["kind"]
            i = th.x + th.y * S
            if not th.built:
                continue
            if "use" in d:
                by_use.setdefault(d["use"], []).append(th)
            if k in ("wall", "fence") or (k in ("object", "nature") and d.get("blocks")):
                for p in pm:
                    p[i] = 0.0
                barrier[i] = k in ("wall", "fence")
            elif k == "gate":
                barrier[i] = True
                pm[C_ANIMAL][i] = 0.0
                pm[C_RAID][i] = 8.0
                if not open_gates:
                    pm[C_OUTSIDER][i] = 0.0
            elif k == "door":
                barrier[i] = True
                pm[C_ANIMAL][i] = 0.0
                pm[C_RAID][i] = 4.0
                pm[C_MEMBER][i] = pm[C_OUTSIDER][i] = 1.5
        self.passmap = pm
        self.comp = [label_components(p, S) for p in pm]
        self.by_use = by_use
        # Zaunverbindungen (auch für Baupläne, damit es beim Planen gut aussieht)
        for th in self.thing_list:
            if th.defn["kind"] in ("fence", "gate"):
                m = 0
                for b, (dx, dy) in enumerate(N4):
                    o = self.thing_at(th.x + dx, th.y + dy)
                    if o is not None and o.defn["kind"] in BARRIERS:
                        m |= 1 << b
                th.conn = m
        # Räume & Gehege per Flutfüllung
        room_of = [-1] * n
        seen = [False] * n
        rooms: list[Room] = []
        for s in range(n):
            if seen[s] or barrier[s]:
                continue
            tiles, edge, fenced = [], False, False
            seen[s] = True
            stack = [s]
            while stack:
                i = stack.pop()
                tiles.append(i)
                x, y = i % S, i // S
                if x == 0 or y == 0 or x == S - 1 or y == S - 1:
                    edge = True
                for dx, dy in N4:
                    nx, ny = x + dx, y + dy
                    if nx < 0 or ny < 0 or nx >= S or ny >= S:
                        continue
                    j = nx + ny * S
                    if barrier[j]:
                        if self.things[j].defn["kind"] in ("fence", "gate"):
                            fenced = True
                    elif not seen[j]:
                        seen[j] = True
                        stack.append(j)
            if edge or len(tiles) > 700:
                continue
            r = Room(len(rooms), tiles, "hof" if fenced else "raum")
            rooms.append(r)
            for i in tiles:
                room_of[i] = r.id
        for r in rooms:
            sx = sy = 0
            fields = 0
            for i in r.tiles:
                sx += i % S; sy += i // S
                th = self.things[i]
                if th is not None and th.built:
                    d = th.defn
                    if "use" in d:
                        r.uses[d["use"]] = r.uses.get(d["use"], 0) + 1
                    r.pracht += d.get("pracht", 0)
                if self.floor[i]:
                    r.pracht += DATA.buildables[self.floor[i]].get("pracht", 0)
                if self.zone[i] == Z_FIELD:
                    fields += 1
            r.cx, r.cy = sx // len(r.tiles), sy // len(r.tiles)
            r.pracht += min(6.0, math.sqrt(len(r.tiles)) * 0.6)
            r.role = "Hof" if r.kind == "hof" else "Leerer Raum"
            if r.kind == "hof" and fields:
                r.role = "Garten"
            for use, mn, name_r, name_h in ROOM_ROLES:
                if r.uses.get(use, 0) >= mn:
                    r.role = name_r if r.kind == "raum" else name_h
                    break
        self.rooms, self.room_of = rooms, room_of
        for p in self.pawns:
            if p.kind == "goat" and not p.away:
                rm = self.room_at(*p.tile)
                if rm is not None and rm.kind == "hof" and rm.role in ("Hof", "Garten"):
                    rm.role = "Ziegengehege"
        # Figuren aus frisch verbauten Feldern schieben
        for p in self.pawns:
            if p.away:
                continue
            x, y = p.tile
            if pm[p.cls][x + y * S] == 0:
                spot = self.free_near(x, y, p.cls)
                if spot:
                    p.x, p.y = spot
                p.cancel_job(self)
        self.dirty = False
        self.struct_rev += 1
        self.ground_rev += 1

    def free_near(self, x, y, cls=C_MEMBER, radius=6):
        pm, S = self.passmap[cls], self.size
        for r in range(0, radius + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < S and 0 <= ny < S and pm[nx + ny * S]:
                        return nx, ny
        return None

    def stand_tiles(self, x, y, cls=C_MEMBER, include_self=False):
        pm, S = self.passmap[cls], self.size
        out = set()
        if include_self and pm[x + y * S]:
            out.add(x + y * S)
        for dx, dy in N8:
            nx, ny = x + dx, y + dy
            if 0 <= nx < S and 0 <= ny < S and pm[nx + ny * S]:
                out.add(nx + ny * S)
        return out

    def reachable(self, cls, sx, sy, goals):
        comp = self.comp[cls]
        c = comp[sx + sy * self.size]
        return c >= 0 and any(comp[g] == c for g in goals)

    def path(self, cls, sx, sy, goals):
        goals = {g for g in goals if self.passmap[cls][g]}
        if not goals or not self.reachable(cls, sx, sy, goals):
            return None
        return astar(self.passmap[cls], self.size, sx, sy, goals)

    def field_tiles(self):
        if self._fields_rev != self.ground_rev:
            self._fields = [i for i, z in enumerate(self.zone) if z == Z_FIELD]
            self._fields_rev = self.ground_rev
        return self._fields

    def count_use(self, use):
        return len(self.by_use.get(use, ()))

    @property
    def storage_cap(self):
        return 60 + 40 * self.count_use("crate")

    def focus_point(self):
        for use in ("altar", "statue", "stove", "bed"):
            lst = self.by_use.get(use)
            if lst:
                return lst[0].x, lst[0].y
        return self.size // 2, self.size // 2

    def visitor_spot(self):
        """Wo Außenstehende sich hinstellen: Besucherzone, sonst nahe dem Zentrum, sonst vor dem Tor."""
        S, comp = self.size, self.comp[C_OUTSIDER]
        c0 = comp[self.exit[0] + self.exit[1] * S]
        zs = [i for i in range(S * S) if self.zone[i] == Z_VISIT and comp[i] == c0]
        if zs:
            i = self.rng.choice(zs)
            return i % S, i // S
        fx, fy = self.focus_point()
        for _ in range(30):
            x, y = fx + self.rng.randint(-5, 5), fy + self.rng.randint(-5, 5)
            if self.inb(x, y) and comp[x + y * S] == c0 and self.room_of[x + y * S] < 0:
                return x, y
        best = self.exit
        for x, y in self.road:
            if comp[x + y * S] == c0:
                best = (x, y)
            else:
                break
        return best

    # ------------------------------------------------------------------ Regeln & Lehre
    def recompute_mods(self):
        mods, adds, flags = {}, {}, set()
        sched = {"sleep": (22, 6), "work_end": 18, "evening_sermon": False}
        arch = next((a for a in DATA.doctrine["archetypes"] if a["id"] == self.archetype), {})
        srcs = [DATA.edicts[e] for e in self.edicts if e in DATA.edicts] + [arch]
        srcs += [DATA.doctrine["projects"][p] for p in self.projects_done]
        for s in srcs:
            for k, v in s.get("mods", {}).items():
                mods[k] = mods.get(k, 1.0) * v
            for k, v in s.get("adds", {}).items():
                adds[k] = adds.get(k, 0.0) + v
            flags.update(s.get("flags", ()))
            for k, v in s.get("sched", {}).items():
                sched[k] = tuple(v) if isinstance(v, list) else max(sched[k], v) if k == "work_end" else v
        mods["heat_gain"] = mods.get("heat_gain", 1.0) * (1 - 0.1 * self.lawyers)
        old_open = "open_gates" in self._flags
        self._mods, self._adds, self._flags, self._sched = mods, adds, flags, sched
        if old_open != ("open_gates" in flags):
            self.dirty = True

    def mod(self, key):
        return self._mods.get(key, 1.0)

    def add(self, key):
        return self._adds.get(key, 0.0)

    def flag(self, key):
        return key in self._flags

    def schedule(self, pawn=None):
        h = self.hour
        s = self._sched
        if pawn is not None and pawn.role == "guard" and pawn.kind == "member":
            if 9 <= h < 16:
                return "sleep"
            if 7 <= h < 9:
                return "sermon"
            return "work"
        s0, s1 = s["sleep"]
        if (s0 <= h < s1) if s0 < s1 else (h >= s0 or h < s1):
            return "sleep"
        if 7 <= h < 9 or (s["evening_sermon"] and 19 <= h < 21):
            return "sermon"
        if 9 <= h < s["work_end"]:
            return "work"
        return "free"

    @property
    def edict_slots(self):
        return 3 + 2 * self.phase + len(self.projects_done)

    def edict_block(self, eid):
        e = DATA.edicts[eid]
        if eid in self.edicts:
            return None
        if e.get("phase", 1) > self.phase:
            return f"Erst ab Phase {e['phase']}"
        if len(self.edicts) >= self.edict_slots:
            return "Alle Regel-Plätze belegt"
        if self.ep < e["cost"]:
            return "Zu wenig Erleuchtung"
        if e.get("requires_use") and not self.count_use(e["requires_use"]):
            return "Benötigtes Gebäude fehlt"
        return None

    def toggle_edict(self, eid):
        e = DATA.edicts[eid]
        if eid in self.edicts:
            self.edicts.discard(eid)
            self.notify(f"Regel aufgehoben: {e['name']}", "info")
        else:
            if self.edict_block(eid):
                return False
            self.ep -= e["cost"]
            self.edicts.add(eid)
            if eid == "endzeit":
                self.flags["doomsday_day"] = self.day + 30
            self.notify(f"Neue Regel: {e['name']}", "info")
            self.cues.append("event")
        self.recompute_mods()
        return True

    def doctrine_target(self):
        t = dict(self.bias)
        for e in self.edicts:
            for a, v in DATA.edicts.get(e, {}).get("doctrine", {}).items():
                t[a] += v
        per_def: dict[str, float] = {}
        for th in self.thing_list:
            dd = th.defn.get("doctrine")
            if dd and th.built:
                for a, v in dd.items():
                    key = th.d + a
                    if abs(per_def.get(key, 0.0)) < 20:
                        per_def[key] = per_def.get(key, 0.0) + v
                        t[a] += v
        return {a: max(-100.0, min(100.0, v)) for a, v in t.items()}

    def shift_doctrine(self, axis, delta):
        self.bias[axis] = max(-100.0, min(100.0, self.bias[axis] + delta))

    def update_archetype(self):
        d = self.doctrine
        for a in DATA.doctrine["archetypes"]:
            if all(lo <= d[ax] <= hi for ax, (lo, hi) in a["cond"].items()):
                if a["id"] != self.archetype:
                    self.archetype = a["id"]
                    if self.day > 1:
                        self.notify(f"Die Lehre wandelt sich: {self.cult_name} gilt nun als »{a['name']}«.", "info")
                        self.cues.append("event")
                break

    def archetype_def(self):
        return next(a for a in DATA.doctrine["archetypes"] if a["id"] == self.archetype)

    # ------------------------------------------------------------------ Ressourcen & Meldungen
    def spend(self, cat, amount):
        if amount:
            self.money -= amount
            self.ledger[cat] = self.ledger.get(cat, 0.0) - amount

    def earn(self, cat, amount):
        if amount:
            self.money += amount
            self.ledger[cat] = self.ledger.get(cat, 0.0) + amount

    def add_heat(self, v):
        if v > 0:
            v *= self.mod("heat_gain")
        self.heat = max(0.0, min(100.0, self.heat + v))

    def add_evidence(self, v):
        self.evidence = max(0.0, min(100.0, self.evidence + v))

    def notify(self, text, kind="info", pos=None, pid=None):
        self.notes.append({"t": self.tick_n, "day": self.day, "text": text, "kind": kind, "pos": pos, "pid": pid})
        if len(self.notes) > 80:
            del self.notes[0]
        if kind == "bad":
            self.cues.append("alert")

    def buy_food(self, n=20):
        cost = n * 2.5
        if self.money < cost:
            return False
        self.spend("Einkauf", cost)
        self.food += n
        return True

    # ------------------------------------------------------------------ Figuren
    def members(self, present=False):
        return [p for p in self.pawns if p.kind in MEMBER_KINDS and not (present and p.away)]

    @property
    def guru(self):
        for p in self.pawns:
            if p.kind == "guru":
                return p
        return None

    def outsiders(self, kind=None):
        return [p for p in self.pawns if p.kind not in MEMBER_KINDS and p.kind != "goat"
                and (kind is None or p.kind == kind) and not p.away]

    def remove_pawn(self, p):
        p.cancel_job(self)
        if p in self.pawns:
            self.pawns.remove(p)
        self.pawn_ids.pop(p.id, None)
        if p.bed:
            th = self.thing_ids.get(p.bed)
            if th:
                th.owner = None
        for th in self.thing_list:
            if th.reserved == p.id:
                th.reserved = None
        self.strategic.unassign(p.id)

    def spawn(self, kind, **kw):
        cap = {"visitor": 7, "journalist": 2, "inspector": 1, "relative": 3}.get(kind)
        if cap is not None and len(self.outsiders(kind)) >= cap:
            return None
        return make_outsider(self, kind, **kw)

    def start_raid(self):
        military = self.phase >= 3 and self.doctrine["apocalypse"] > 45
        kind = "soldier" if military else "police"
        n = (4 if self.phase == 1 else 6) + (3 if military else 0)
        for k in range(n):
            make_outsider(self, kind, offset=k)
        self.flags["raid_active"] = self.tick_n + 9 * TICKS_PER_HOUR
        who = "Das Militär rückt an" if military else "RAZZIA! Die Polizei rückt an"
        self.notify(f"{who}! Sie suchen {self.guru_name}.", "bad", self.exit)

    def convert(self, v, by=None):
        """Aus einem Besucher wird ein Mitglied."""
        v.become_member(self)
        self.notify(f"{v.name} ist der Gemeinschaft beigetreten! ({v.former_job})", "good", v.tile, v.id)
        self.cues.append("convert")
        if by is not None:
            by.log(self, f"Hat {v.name} bekehrt.")

    def defect(self, p, reason="hat die Gemeinschaft verlassen"):
        self.notify(f"{p.name} {reason}.", "bad", p.tile)
        self.add_heat(3 + p.rank * 2)
        self.add_evidence(2 + p.rank * 3 + (4 if "plaudertasche" in p.traits else 0))
        self.flags["defector"] = True
        for m in self.members(True):
            if m is not p:
                m.faith = max(0, m.faith - 2)
                m.add_thought("left", f"{p.name.split()[0]} ist gegangen", -4, 48, self)
        self.remove_pawn(p)

    # ------------------------------------------------------------------ Tick
    def tick(self):
        if self.over:
            return
        if self.dirty:
            self.rebuild()
        self.tick_n += 1
        t = self.tick_n
        for p in self.pawns[:]:
            p.update(self)
        if t % 20 == 0:
            g = 20 / (3.0 * TICKS_PER_DAY)
            for i in self.crops:
                if self.crops[i] < 1.0:
                    self.crops[i] = min(1.0, self.crops[i] + g)
        if t % TICKS_PER_HOUR == 0:
            self.hourly()
            if t % TICKS_PER_DAY == 0:
                self.daily()

    def hourly(self):
        h = int(self.hour)
        rng = self.rng
        for p in self.pawns[:]:
            p.hourly(self)
        # Besucherstrom
        home = self.strategic.home_local()
        if 8 <= h <= 17:
            rate = (0.035 + home.aware * 0.002 + home.camp_power() * 0.015) * self.mod("visitor_rate")
            if rng.random() < rate:
                self.spawn("visitor")
            if self.heat > 25 and rng.random() < self.heat / 2200:
                if self.spawn("journalist"):
                    self.notify("Ein Journalist schleicht ums Gelände.", "warn", self.exit)
            if self.heat > 45 and rng.random() < self.heat / 4500:
                if self.spawn("inspector"):
                    self.notify("Unangekündigte Behördenkontrolle!", "warn", self.exit)
        if h == self.event_hour:
            events.daily_roll(self)
        if h == 2:
            events.night_checks(self)
        ra = self.flags.get("raid_active")
        if ra and self.tick_n > ra:
            events.raid_end(self, reached=False)
        # Lautsprecher: Glaube rauf, Laune runter
        for sp in self.by_use.get("speaker", ()):
            for m in self.members(True):
                if abs(m.x - sp.x) + abs(m.y - sp.y) < 9 and not m.asleep:
                    m.faith = min(100, m.faith + 0.35)
                    m.add_thought("speaker", "Dauerbeschallung", -3, 3, self)

    def daily(self):
        rng = self.rng
        mem = self.members()
        # Abgaben der Mitglieder
        rate = 0.012 * self.mod("tithe")
        for m in mem:
            if m.kind == "guru":
                continue
            give = min(m.wealth, m.wealth * min(0.9, rate * m.tm("tithe")) * (0.4 + m.faith / 100))
            m.wealth -= give
            self.earn("Abgaben der Mitglieder", give)
            m.wealth += rng.uniform(0, 6) * m.tm("wealth") ** 0.5   # Kindergeld, Rente, Omas Umschlag
            ci = self.add("course_income")
            if ci:
                self.earn("Kursgebühren", ci * (m.rank + 1))
        # Vorräte
        if self.food > self.storage_cap:
            lost = (self.food - self.storage_cap) * 0.5
            self.food -= lost
            if lost > 3:
                self.notify(f"{lost:.0f} Nahrung verdorben – zu wenig Lagerplatz (Vorratskisten bauen).", "warn")
        goats = [p for p in self.pawns if p.kind == "goat" and not p.away]
        if goats:
            self.food += 2.5 * len(goats)
            for m in mem:
                m.faith = min(100, m.faith + 0.4 * min(4, len(goats)))
        # Anwälte, Projekte
        law = DATA.campaigns["lawyers"][self.lawyers]["cost"] * self.strategic.phase_scale()
        self.spend("Anwälte", min(self.money, law)) if law else None
        if self.project:
            self.project[1] -= 1
            if self.project[1] <= 0:
                events.project_done(self, self.project[0])
                self.project = None
        # Strategische Ebene
        self.strategic.daily()
        fol = self.strategic.total_followers()
        self.ep += 1.2 * math.log10(1 + fol) + self.add("ep_daily")
        # Verdacht
        home = self.strategic.home_local()
        loc = self.strategic.levels["local"]
        d = self.doctrine
        extrem = max(0.0, d["apocalypse"]) / 100 * 1.5 + max(0.0, d["isolation"]) / 100 * 0.7 + max(0.0, d["commerce"]) / 100 * 0.4
        avg_heat = sum(r.heat for r in loc.regions.values()) / len(loc.regions)
        dh = self.add("heat_daily") + home.heat * 0.02 + avg_heat * 0.04 + extrem * 1.1 - 0.9 - 0.25 * self.lawyers
        for key in ("country", "world")[: self.phase - 1]:      # später schaut auch die große Politik aufs Hauptquartier
            lv = self.strategic.levels[key]
            dh += sum(r.heat * r.pop for r in lv.regions.values()) / lv.pop() * 0.035
        self.add_heat(dh)
        self.add_evidence(self.add("evidence_daily") - 0.4)
        leak = sum(m.tm_add("leak") for m in mem if not m.away)
        self.add_evidence(min(2.0, leak * 0.35))
        # Lehre driftet zum Ziel, Ereignis-Einflüsse verblassen langsam
        tgt = self.doctrine_target()
        for a in AXES:
            self.doctrine[a] += (tgt[a] - self.doctrine[a]) * 0.18
            self.bias[a] *= 0.985
        self.update_archetype()
        self.recompute_mods()
        for p in self.pawns[:]:
            p.daily(self)
        events.daily_checks(self)
        self.event_hour = rng.randint(9, 19)
        self.ledger_last, self.ledger = self.ledger, {}
        if self.money < -500 and not self.over:
            self.over = ("lose", "Insolvenz! Der Gerichtsvollzieher hat sogar die Guru-Statue gepfändet.")
        if not [m for m in self.members() if m.kind != "guru"] and self.day > 3 and not self.over:
            self.over = ("lose", "Der Guru predigt jetzt vor leeren Matten. Alle Mitglieder sind fort.")

    # ------------------------------------------------------------------ Speichern
    def save(self, path):
        with open(path, "wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def load(path) -> "World":
        if not DATA.loaded:
            DATA.load()
        with open(path, "rb") as f:
            return pickle.load(f)
