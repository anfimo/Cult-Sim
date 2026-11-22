"""Einzeln simulierte Figuren: Mitglieder, Guru, Besucher, Presse, Behörden, Polizei, Ziegen."""
from __future__ import annotations

import math

from ..config import *
from ..data import DATA

MEMBER_KINDS = ("member", "guru")
KIND_NAMES = {"member": "Mitglied", "guru": "Guru", "visitor": "Besucher", "journalist": "Journalist",
              "inspector": "Behördenkontrolleur", "relative": "Besorgte Angehörige", "police": "Polizei",
              "soldier": "Militär", "goat": "Heilige Ziege"}


class Job:
    __slots__ = ("kind", "path", "thing", "other", "dur", "t", "stage", "mode", "cls", "chase")

    def __init__(self, kind, path, thing=None, other=None, dur=0, mode=None, cls=0):
        self.kind, self.path, self.thing, self.other = kind, path, thing, other
        self.dur, self.mode, self.cls = dur, mode, cls
        self.t = 0.0
        self.stage = 0
        self.chase = False


def clamp(v, lo=0.0, hi=100.0):
    return lo if v < lo else hi if v > hi else v


class Pawn:
    def __init__(self, w, kind, x, y):
        rng = w.rng
        self.id = w.next_id
        w.next_id += 1
        self.kind = kind
        self.x, self.y = float(x), float(y)
        self.cls = (C_ANIMAL if kind == "goat" else C_RAID if kind in ("police", "soldier")
                    else C_MEMBER if kind in MEMBER_KINDS else C_OUTSIDER)
        self.speed = 0.12 if kind != "goat" else 0.05
        self.name = KIND_NAMES.get(kind, "?")
        self.job: Job | None = None
        self.think_cd = rng.randint(0, 20)
        self.face = (1, 0)
        self.moving = self.asleep = self.away = False
        self.away_until = None
        self.away_kind = None
        self.food, self.rest = 75.0 + rng.random() * 20, 70.0 + rng.random() * 25
        self.faith, self.mood, self.bond = 50.0, 60.0, 12.0
        self.skills = {k: 0.0 for k in SKILLS}
        self.traits: list[str] = []
        self.role, self.rank = "worker", 0
        self.age, self.female, self.former_job, self.bio = 30, False, "", ""
        self.wealth = 0.0
        self.thoughts: dict[str, tuple] = {}
        self.journal: list[tuple] = []
        self.joined = w.day
        self.doubter = self.favorite = self.fleeing = self.watched = False
        self.bed = None
        self.starve = 0
        self.engaged = None
        self.state = "arrive"
        self.leave_at = w.tick_n + 10 ** 9
        self.evidence = 0.0
        self.interest = 50.0
        self.tries = 0
        self.target_id = None
        self.checks = 0
        self.charmed = self.expelled = False
        self.orders: list[tuple] = []
        self.post = None
        self.bubble = None
        self.look = (rng.randrange(6), rng.randrange(8), rng.randrange(8))
        self._tm: dict | None = None
        w.pawns.append(self)
        w.pawn_ids[self.id] = self

    # ------------------------------------------------------------ Hilfen
    @property
    def tile(self):
        return int(self.x + 0.5), int(self.y + 0.5)

    def dist(self, o):
        return math.hypot(self.x - o.x, self.y - o.y)

    def tm(self, key):
        c = self._tm
        if c is None:
            c = self._tm = {}
        v = c.get(key)
        if v is None:
            v = 1.0
            for t in self.traits:
                v *= DATA.traits[t].get("mods", {}).get(key, 1.0)
            c[key] = v
        return v

    def tm_add(self, key):
        return sum(DATA.traits[t].get("mods", {}).get(key, 0.0) for t in self.traits)

    def visible_traits(self, reveal=False):
        return [t for t in self.traits if reveal or not DATA.traits[t].get("hidden")]

    def add_thought(self, tid, text, value, hours, w):
        self.thoughts[tid] = (text, value, w.tick_n + int(hours * TICKS_PER_HOUR))

    def log(self, w, text):
        self.journal.append((w.day, text))
        if len(self.journal) > 14:
            del self.journal[0]

    def say(self, w, fx, ticks=40):
        self.bubble = (fx, w.tick_n + ticks)

    @property
    def role_name(self):
        if self.kind == "guru":
            return "Guru"
        if self.kind != "member":
            return KIND_NAMES.get(self.kind, self.kind)
        return ROLES[self.role]

    @property
    def rank_name(self):
        return "Guru" if self.kind == "guru" else DATA.doctrine["ranks"][self.rank]["name"]

    def status_text(self, w):
        if self.away:
            return {"trip": "Auf Werbetour in der Stadt", "jail": "In Untersuchungshaft",
                    "post": "Leitet eine Regionalgruppe"}.get(self.away_kind, "Abwesend")
        j = self.job
        if j is None:
            return "Überlegt"
        if j.stage == 0 and j.kind not in ("wander", "patrol", "flee", "exit", "walk", "goto", "trip"):
            return "Unterwegs " + GO_NAMES.get(j.kind, "")
        if j.kind == "talk":
            return TALK_NAMES.get(j.mode, "Spricht")
        return JOB_NAMES.get(j.kind, j.kind)

    # ------------------------------------------------------------ Aufträge
    def go(self, w, kind, goals, thing=None, other=None, dur=0, mode=None, cls=None):
        cls = self.cls if cls is None else cls
        if isinstance(goals, tuple):
            goals = {goals[0] + goals[1] * w.size}
        x, y = self.tile
        path = w.path(cls, x, y, goals)
        if path is None:
            return False
        self.job = Job(kind, path, thing, other, dur, mode, cls)
        if thing is not None:
            thing.reserved = self.id
        return True

    def end_job(self, w):
        j = self.job
        self.moving = self.asleep = self.fleeing = False
        if j is None:
            return
        if j.thing is not None and j.thing.reserved == self.id:
            j.thing.reserved = None
        if j.kind in ("sow", "harvest"):
            w.field_busy.discard(j.mode)
        if j.other is not None:
            o = w.pawn_ids.get(j.other)
            if o is not None and o.engaged == self.id:
                o.engaged = None
                if o.job is not None and o.job.kind == "listen":
                    o.job = None
        self.job = None
        self.think_cd = 2

    cancel_job = end_job

    def start_talk(self, w, o, mode, dur, chase=False):
        if o.job is not None and not chase:
            o.end_job(w)
        ox, oy = o.tile
        if not self.go(w, "talk", w.stand_tiles(ox, oy, self.cls, True), other=o.id, dur=dur, mode=mode):
            return False
        self.job.chase = chase
        o.engaged = self.id
        if not chase:
            o.job = Job("listen", [], dur=700)
            o.job.stage = 1
        return True

    # ------------------------------------------------------------ Tick
    def update(self, w):
        if self.away:
            if self.away_until is not None and w.tick_n >= self.away_until:
                self.come_back(w)
            return
        if self.kind in MEMBER_KINDS:
            self.food -= 0.035 * self.tm("food_use") * (w.mod("food_use") if self.kind == "member" else 1.0)
            if self.food < 0:
                self.food = 0.0
            if not self.asleep:
                self.rest -= 0.045 * self.tm("rest_use")
                if self.rest < 0:
                    self.rest = 0.0
        j = self.job
        if j is None:
            self.think_cd -= 1
            if self.think_cd <= 0:
                self.think(w)
                if self.job is None:
                    self.think_cd = 15 + w.rng.randint(0, 25)
            return
        if j.stage == 0:
            if j.path:
                if j.kind == "patrol" and w.tick_n % 15 == 0 and self.spots_runner(w):
                    return self.end_job(w)      # Alarm! Patrouille abbrechen, neu entscheiden
                self.step(w, j)
                return
            j.stage = 1
            self.moving = False
        if getattr(self, "h_" + j.kind)(w, j) and self.job is j:
            self.end_job(w)

    def step(self, w, j):
        S = w.size
        if j.chase:
            o = w.pawn_ids.get(j.other)
            if o is None or o.away:
                return self.end_job(w)
            if self.dist(o) < 1.5:              # eingeholt
                j.path = []
                return
        if j.chase and w.tick_n % 10 == 0:
            ox, oy = o.tile
            lx, ly = j.path[-1]
            if abs(ox - lx) > 1 or abs(oy - ly) > 1:
                p = w.path(j.cls, *self.tile, w.stand_tiles(ox, oy, j.cls, True))
                if p is None:
                    return self.end_job(w)
                j.path = p
                if not p:
                    return
        nx, ny = j.path[0]
        if w.passmap[j.cls][nx + ny * S] == 0:
            fx, fy = j.path[-1]
            p = w.path(j.cls, *self.tile, {fx + fy * S})
            if not p:
                return self.end_job(w)
            j.path = p
            nx, ny = p[0]
        dx, dy = nx - self.x, ny - self.y
        d = math.hypot(dx, dy)
        sp = self.speed * (1.45 if j.mode in ("catch", "escort") else 1.0)
        if d <= sp:
            self.x, self.y = float(nx), float(ny)
            j.path.pop(0)
        else:
            self.x += dx / d * sp
            self.y += dy / d * sp
        if abs(dx) > 0.01 or abs(dy) > 0.01:
            self.face = ((dx > 0.01) - (dx < -0.01), (dy > 0.01) - (dy < -0.01))
        self.moving = True

    def think(self, w):
        k = self.kind
        if k in MEMBER_KINDS:
            self.think_member(w)
        elif k == "goat":
            self.think_goat(w)
        elif k in ("police", "soldier"):
            self.think_raid(w)
        else:
            self.think_outsider(w)

    # ------------------------------------------------------------ Mitglieder-KI
    def think_member(self, w):
        if self.kind == "guru" and self.orders:
            o = self.orders.pop(0)
            if o[0] == "goto":
                if self.go(w, "goto", (o[1], o[2]), dur=60):
                    return
            else:
                t = w.pawn_ids.get(o[1])
                if t is not None and not t.away and self.start_talk(w, t, o[0], 110, chase=t.kind not in MEMBER_KINDS):
                    return
        sched = w.schedule(self)
        if self.food < 22 and self.try_eat(w):
            return
        if self.rest < 10:
            return self.start_sleep(w)
        if sched == "sleep":
            if self.rest < 92:
                return self.start_sleep(w)
            sched = "free"
        if self.food < 50 and self.try_eat(w):
            return
        if sched == "sermon" and self.try_sermon(w):
            return
        if sched in ("work", "sermon") and self.try_work(w):
            return
        self.leisure(w)

    def try_eat(self, w):
        if w.meals < 1 and w.food < 1.5:
            self.add_thought("hunger", "Es gibt nichts zu essen!", -12, 10, w)
            return False
        if w.meals >= 1:
            x, y = self.tile
            tables = sorted(w.by_use.get("table", ()), key=lambda t: abs(t.x - x) + abs(t.y - y))
            for tb in tables[:3]:
                if self.go(w, "eat", w.stand_tiles(tb.x, tb.y), dur=35, mode="table"):
                    return True
        return self.go(w, "eat", self.tile, dur=35, mode="stand")

    def start_sleep(self, w):
        bed = w.thing_ids.get(self.bed) if self.bed else None
        if bed is None or not bed.built or bed.owner != self.id:
            self.bed = None
            x, y = self.tile
            cands = []
            if self.kind == "guru":
                cands = [b for b in w.by_use.get("bed_guru", ()) if b.owner is None]
            if not cands:
                cands = [b for b in w.by_use.get("bed", ()) if b.owner is None]
            bed = min(cands, key=lambda b: abs(b.x - x) + abs(b.y - y)) if cands else None
            if bed is not None:
                bed.owner, self.bed = self.id, bed.id
        if bed is not None and self.go(w, "sleep", (bed.x, bed.y), thing=bed, mode="bed"):
            return
        rooms = [r for r in w.rooms if r.kind == "raum"]
        if rooms:
            x, y = self.tile
            r = min(rooms, key=lambda r: abs(r.cx - x) + abs(r.cy - y))
            i = w.rng.choice(r.tiles)
            if self.go(w, "sleep", {i}, mode="floor"):
                return
        self.go(w, "sleep", self.tile, mode="floor")

    def try_sermon(self, w):
        altars = w.by_use.get("altar")
        if not altars:
            return False
        altar = altars[0]
        pr = sermon_preacher(w)
        if pr is None:
            return False
        if pr is self:
            return self.go(w, "preach", w.stand_tiles(altar.x, altar.y), mode=altar.id)
        room = w.room_at(altar.x, altar.y)
        S = w.size
        if room is not None:
            cands = [i for i in room.tiles if w.passmap[0][i]]
        else:
            cands = [i for i in ((altar.x + dx) + (altar.y + dy) * S for dx in range(-4, 5) for dy in range(-4, 5)
                                 if w.inb(altar.x + dx, altar.y + dy))
                     if w.passmap[0][i] and w.room_of[i] < 0]
        for _ in range(3):
            if cands and self.go(w, "attend", {w.rng.choice(cands)}, mode=altar.id):
                return True
        return False

    def try_work(self, w):
        if self.kind == "guru":
            return self.work_preacher(w)
        if getattr(self, "work_" + self.role)(w):
            return True
        if self.role in ("cook", "clerk", "preacher", "recruiter"):
            return self.work_worker(w)
        return False

    def work_worker(self, w):
        x, y = self.tile
        S = w.size
        if w.blueprints:
            cands = [t for t in w.blueprints if t.reserved in (None, self.id) or t.reserved not in w.pawn_ids]
            cands.sort(key=lambda t: abs(t.x - x) + abs(t.y - y))
            for th in cands[:4]:
                if self.go(w, "build", w.stand_tiles(th.x, th.y, 0, not th.defn["blocks"]), thing=th,
                           dur=th.defn.get("work", 40)):
                    return True
        best, bd, bk = None, 1e9, None
        crops, busy = w.crops, w.field_busy
        for i in w.field_tiles():
            if i in busy or w.things[i] is not None:
                continue
            g = crops.get(i)
            if g is None or g >= 1.0:
                d = abs(i % S - x) + abs(i // S - y)
                if d < bd:
                    best, bd, bk = i, d, ("sow" if g is None else "harvest")
        if best is not None and self.go(w, bk, {best}, dur=45 if bk == "sow" else 30, mode=best):
            busy.add(best)
            return True
        return False

    def work_cook(self, w):
        if w.food < 3 or w.meals >= max(6, len(w.members()) * 2.5):
            return False
        x, y = self.tile
        stoves = [s for s in w.by_use.get("stove", ()) if s.reserved in (None, self.id)]
        stoves.sort(key=lambda t: abs(t.x - x) + abs(t.y - y))
        for st in stoves[:2]:
            if self.go(w, "cook", w.stand_tiles(st.x, st.y), thing=st, dur=70 / st.defn.get("speed", 1.0)):
                return True
        return False

    def work_clerk(self, w):
        x, y = self.tile
        pr = [t for t in w.by_use.get("printer", ()) if t.reserved in (None, self.id)]
        if pr and w.tracts < 25 + 15 * w.phase and w.money >= 5:
            t = min(pr, key=lambda t: abs(t.x - x) + abs(t.y - y))
            if self.go(w, "print", w.stand_tiles(t.x, t.y), thing=t, dur=90):
                return True
        ds = [t for t in w.by_use.get("desk", ()) if t.reserved in (None, self.id)]
        if ds:
            t = min(ds, key=lambda t: abs(t.x - x) + abs(t.y - y))
            return self.go(w, "desk", w.stand_tiles(t.x, t.y), thing=t, dur=110)
        return False

    def work_preacher(self, w):
        vs = [v for v in w.outsiders("visitor") if v.state == "browse" and v.engaged is None and v.tries < 2]
        if vs:
            v = min(vs, key=self.dist)
            if self.start_talk(w, v, "convert", 90):
                return True
        ds = [m for m in w.members(True) if m.doubter and m.engaged is None and not m.asleep and m is not self
              and not m.fleeing]
        if ds:
            return self.start_talk(w, min(ds, key=self.dist), "counsel", 100)
        return False

    def work_recruiter(self, w):
        if 8 <= w.hour < 15:
            return self.go(w, "trip", w.exit)
        return self.work_preacher(w)

    def guard_sight(self, w):
        sight = 10 * w.mod("guard")
        if any(abs(t.x - self.x) + abs(t.y - self.y) < 14 for t in w.by_use.get("tower", ())):
            sight += 8
        return sight

    def spots_runner(self, w):
        sight = self.guard_sight(w)
        return any(m.fleeing and m.engaged is None and self.dist(m) < sight for m in w.members(True))

    def work_guard(self, w):
        S = w.size
        sight = self.guard_sight(w)
        for m in w.members(True):
            if m.fleeing and m.engaged is None and self.dist(m) < sight:
                if self.start_talk(w, m, "catch", 8, chase=True):
                    self.say(w, "fx_exclaim")
                    return True
        for o in w.outsiders():
            if o.engaged is not None or o.state == "leave" or o.kind in ("police", "soldier", "inspector"):
                continue
            ox, oy = o.tile
            i = ox + oy * S
            room = w.room_at(ox, oy)
            bad = o.expelled or w.zone[i] == Z_FORBID
            bad = bad or (o.kind == "journalist" and room is not None and room.kind == "raum")
            bad = bad or (o.kind == "relative" and w.flag("contact_ban"))
            if bad and self.dist(o) < 30 and self.start_talk(w, o, "escort", 15, chase=True):
                return True
        pts = [(t.x, t.y) for t in w.thing_list if t.built and t.defn["kind"] == "gate"]
        pts += [(t.x, t.y) for t in w.by_use.get("tower", ())]
        fx, fy = w.focus_point()
        if not pts or w.rng.random() < 0.4:
            a = w.rng.random() * 6.283
            pts = [(int(fx + math.cos(a) * 8), int(fy + math.sin(a) * 8))]
        px, py = w.rng.choice(pts)
        if w.inb(px, py):
            return self.go(w, "patrol", w.stand_tiles(px, py, 0, True), dur=50)
        return False

    def leisure(self, w):
        rng = w.rng
        r = rng.random()
        x, y = self.tile
        if r < 0.3:
            mats = [m for m in w.by_use.get("mat", ()) if m.reserved in (None, self.id)]
            if mats:
                m = min(mats, key=lambda t: abs(t.x - x) + abs(t.y - y))
                if self.go(w, "meditate", (m.x, m.y), thing=m, dur=150):
                    return
        if r < 0.55:
            near = [m for m in w.members(True) if m is not self and m.engaged is None and not m.asleep
                    and not m.fleeing and (m.job is None or m.job.kind in ("wander", "meditate"))
                    and self.dist(m) < 9]
            if near and self.start_talk(w, rng.choice(near), "chat", 50):
                return
        fx, fy = w.focus_point()
        for _ in range(4):
            tx, ty = fx + rng.randint(-7, 7), fy + rng.randint(-7, 7)
            if w.inb(tx, ty) and self.go(w, "wander", (tx, ty), dur=rng.randint(20, 90)):
                return

    # ------------------------------------------------------------ Tätigkeiten (Handler: True = fertig)
    def work_rate(self, w, skill):
        r = (0.55 + self.skills[skill] * 0.1) * self.tm("work") * w.mod("work")
        if self.rest < 20 or self.food < 15:
            r *= 0.6
        self.skills[skill] = min(10.0, self.skills[skill] + 0.0004)
        return r

    def h_goto(self, w, j):
        j.t += 1
        return j.t >= j.dur or bool(self.orders)

    def h_wander(self, w, j):
        j.t += 1
        return j.t >= j.dur

    def h_patrol(self, w, j):
        j.t += 1
        return j.t >= j.dur or (w.tick_n % 15 == 0 and self.spots_runner(w))

    def h_listen(self, w, j):
        j.t += 1
        if j.t > j.dur or self.engaged is None:
            self.engaged = None
            return True
        return False

    def h_eat(self, w, j):
        j.t += 1
        if j.t < j.dur:
            return False
        if w.meals >= 1:
            w.meals -= 1
            self.food = min(100.0, self.food + 65)
            if j.mode == "table":
                self.add_thought("eat", "Gemeinsam am Tisch gegessen", 4, 14, w)
            else:
                self.add_thought("eat", "Im Stehen gegessen", -2, 10, w)
        elif w.food >= 1.5:
            w.food -= 1.5
            self.food = min(100.0, self.food + 40)
            if not w.flag("raw_ok") and self.kind != "guru":
                self.add_thought("eat", "Rohe Rüben gekaut", -6, 12, w)
        return True

    def h_sleep(self, w, j):
        self.asleep = True
        bed = j.mode == "bed"
        x, y = self.tile
        indoor = w.room_of[x + y * w.size] >= 0
        self.rest += 0.14 if bed else 0.09 if indoor else 0.07
        if w.tick_n % 60 == 0:
            self.say(w, "fx_zzz", 30)
        if self.rest >= 100 or self.food < 6 or (w.schedule(self) != "sleep" and self.rest > 55):
            self.rest = min(100.0, self.rest)
            room = w.room_at(x, y)
            if not bed:
                self.add_thought("sleep", "Auf dem nackten Boden geschlafen", -7, 16, w)
            elif room is None:
                self.add_thought("sleep", "Unter freiem Himmel geschlafen", -3, 16, w)
            elif room.pracht >= 6:
                self.add_thought("sleep", f"Schöner Schlafplatz ({room.pracht_text})", 4, 16, w)
            else:
                self.thoughts.pop("sleep", None)
            return True
        return False

    def h_build(self, w, j):
        th = j.thing
        if th.built or w.things[th.x + th.y * w.size] is not th:
            return True
        j.t += self.work_rate(w, "work")
        th.progress = min(1.0, j.t / j.dur)
        if j.t >= j.dur:
            w.finish(th)
            return True
        return False

    def h_sow(self, w, j):
        j.t += self.work_rate(w, "work")
        if j.t >= j.dur:
            if w.zone[j.mode] == Z_FIELD:
                w.crops[j.mode] = 0.0
            return True
        return False

    def h_harvest(self, w, j):
        j.t += self.work_rate(w, "work")
        if j.t >= j.dur:
            if w.crops.get(j.mode, 0) >= 1.0:
                del w.crops[j.mode]
                w.food += 5.0 * (0.7 + self.skills["work"] * 0.08)
            return True
        return False

    def h_cook(self, w, j):
        j.t += self.work_rate(w, "cook")
        if j.t >= j.dur:
            if w.food >= 3:
                w.food -= 3
                s = self.skills["cook"]
                w.meals += 4 + (s >= 5) + (s >= 9)
            return True
        return False

    def h_print(self, w, j):
        j.t += self.work_rate(w, "admin")
        if j.t >= j.dur:
            w.spend("Druckkosten", 4)
            w.tracts += 3 + int(self.skills["admin"] // 3)
            return True
        return False

    def h_desk(self, w, j):
        j.t += self.work_rate(w, "admin")
        if j.t >= j.dur:
            fol = w.strategic.total_followers()
            w.earn("Spendenbriefe", (5 + self.skills["admin"] * 2.0) * (1 + math.log10(1 + fol)) * w.mod("income"))
            self.say(w, "fx_money")
            return True
        return False

    def h_preach(self, w, j):
        if w.schedule(self) != "sermon" or (self.kind == "guru" and self.orders):
            return True
        w.preach_tick = w.tick_n
        w.preach_skill = self.skills["preach"] + (2 if self.kind == "guru" else 0)
        w.preach_pos = (self.x, self.y)
        self.skills["preach"] = min(10.0, self.skills["preach"] + 0.0006)
        if w.tick_n % 50 == 0:
            self.say(w, "fx_note", 30)
        return False

    def h_attend(self, w, j):
        if w.schedule(self) != "sermon":
            return True
        if w.tick_n - w.preach_tick < 5:
            px, py = w.preach_pos
            if abs(px - self.x) + abs(py - self.y) < 16:
                x, y = self.tile
                room = w.room_at(x, y)
                f = 1.0 + (min(30.0, room.pracht) / 30.0 if room is not None else 0.0)
                self.faith = min(100.0, self.faith + 0.03 * (0.6 + w.preach_skill / 8) * f
                                 * self.tm("faith_gain") * w.mod("faith_gain"))
                w.ep += 0.0035 * f
                self.add_thought("sermon", "Erbauliche Predigt gehört", 4, 8, w)
        else:
            j.t += 1
            if j.t > 120:           # niemand predigt – dann eben nicht
                return True
        return False

    def h_meditate(self, w, j):
        j.t += 1
        self.faith = min(100.0, self.faith + 0.012 * self.tm("faith_gain"))
        self.rest = min(100.0, self.rest + 0.02)
        if j.t >= j.dur:
            self.add_thought("meditate", "Innere Einkehr", 3, 8, w)
            return True
        return False

    def h_trip(self, w, j):
        self.away, self.away_kind = True, "trip"
        self.away_until = w.tick_n + w.rng.randint(280, 460)
        return True

    def h_flee(self, w, j):
        w.defect(self, "ist bei Nacht und Nebel geflohen")
        return True

    def h_talk(self, w, j):
        o = w.pawn_ids.get(j.other)
        if o is None or o.away:
            return True
        if self.dist(o) > 2.7:
            if j.chase and j.t < 1:             # Ziel ist weitergelaufen: hinterher
                p = w.path(j.cls, *self.tile, w.stand_tiles(*o.tile, j.cls, True))
                if p:
                    j.path, j.stage = p, 0
                    return False
            return True
        j.t += 1
        if j.chase:
            if j.mode in ("catch", "escort", "arrest"):
                getattr(self, "talk_" + j.mode)(w, o)
                return True
            if j.t == 1:                        # Gesprächspartner bleibt stehen
                if o.job is not None:
                    o.end_job(w)
                o.engaged = self.id
                o.job = Job("listen", [], dur=700)
                o.job.stage = 1
        if j.t == 1:
            dx, dy = o.x - self.x, o.y - self.y
            self.face = ((dx > 0.3) - (dx < -0.3), (dy > 0.3) - (dy < -0.3)) if (abs(dx) > 0.3 or abs(dy) > 0.3) else self.face
            o.face = (-self.face[0], -self.face[1])
        if int(j.t) % 30 == 5:
            self.say(w, "fx_speech", 20)
        if j.t < j.dur:
            return False
        getattr(self, "talk_" + j.mode)(w, o)
        return True

    # ------------------------------------------------------------ Gesprächsergebnisse
    def talk_convert(self, w, o):
        s = self.skills["preach"]
        self.skills["preach"] = min(10.0, s + 0.12)
        ch = (0.04 + s * 0.018 + o.interest / 600 + (0.03 if self.kind == "guru" else 0)) * self.tm("convert") * w.mod("convert")
        if w.tracts >= 1:
            w.tracts -= 1
            ch += 0.04
        n = sum(1 for m in w.members() if m.kind == "member")
        ch /= 1 + (n / 22) ** 2             # je größer die Kommune, desto wählerischer (und voller) wird es
        if w.count_use("bed") <= n:          # kein freies Bett: Interessenten springen eher ab
            ch *= 0.35
            if not w.flags.get("bed_hint") or w.day - w.flags["bed_hint"] > 3:
                w.flags["bed_hint"] = w.day
                w.notify("Kein freies Bett für Neuzugänge – Interessierte lassen sich kaum überzeugen.", "warn")
        if w.rng.random() < ch:
            w.convert(o, self)
        else:
            o.interest -= 15
            o.tries += 1
            o.say(w, "fx_question", 60)

    def talk_counsel(self, w, o):
        o.faith = min(100.0, o.faith + 7 + self.skills["preach"] * 1.3)
        o.add_thought("counsel", "Seelsorge-Gespräch (mit sanftem Druck)", 2, 24, w)
        o.say(w, "fx_halo", 60)

    def talk_bond(self, w, o):
        o.bond = min(100.0, o.bond + 9 + w.rng.random() * 7)
        o.faith = min(100.0, o.faith + 8)
        o.add_thought("guru_talk", "Der Guru hat sich Zeit für mich genommen", 10, 60, w)
        o.log(w, "Einzelgespräch mit dem Guru.")
        o.say(w, "fx_heart", 80)
        from . import events
        events.after_guru_talk(w, o)

    def talk_interview(self, w, o):
        if w.rng.random() < 0.35 + self.skills["preach"] * 0.05:
            o.evidence, o.charmed = 0.0, True
            w.notify(f"{self.name} hat den Journalisten um den Finger gewickelt.", "good", o.tile)
            o.say(w, "fx_heart", 80)
        else:
            o.evidence += 6
            w.notify("Das Interview lief ... suboptimal. Der Journalist notiert eifrig.", "warn", o.tile)
            o.say(w, "fx_exclaim", 80)
        o.state = "leave"

    def talk_escort(self, w, o):
        o.state, o.expelled = "leave", True
        o.cancel_job(w)
        o.say(w, "fx_angry", 80)
        if o.kind in ("journalist", "relative"):
            w.add_heat(2)
        w.notify(f"{self.name} hat {'einen ' + KIND_NAMES[o.kind] if o.kind != 'relative' else 'Angehörige'} "
                 "vom Gelände begleitet.", "info", o.tile)

    def talk_catch(self, w, o):
        o.cancel_job(w)
        o.watched = True
        o.faith = min(100.0, o.faith + 8)
        o.add_thought("caught", "Beim Weglaufen erwischt", -10, 72, w)
        o.log(w, f"Fluchtversuch – von {self.name} zurückgebracht.")
        w.notify(f"{self.name} hat {o.name} beim Fluchtversuch erwischt.", "good", o.tile, o.id)
        self.skills["guard"] = min(10.0, self.skills["guard"] + 0.3)

    def talk_relative(self, w, o):
        o.faith = max(0.0, o.faith - max(4.0, 24 - o.bond / 4))
        o.add_thought("family", "Besuch von daheim – Mutti hat geweint", -5, 48, w)
        o.log(w, "Besuch von der Familie.")
        self.state = "leave"
        if o.faith < 18 and w.rng.random() < 0.6:
            w.defect(o, "ist mit der Familie nach Hause gefahren")

    def talk_arrest(self, w, o):
        from . import events
        events.raid_end(w, reached=True)

    def talk_chat(self, w, o):
        for a, b in ((self, o), (o, self)):
            a.add_thought("chat", "Nettes Gespräch", 3, 10, w)
            if b.doubter and not a.doubter:
                if a.faith > 85:
                    if not b.watched:
                        b.watched = True
                        w.notify(f"{a.name} meldet pflichtbewusst: {b.name} äußert Zweifel.", "warn", b.tile, b.id)
                else:
                    a.faith = max(0.0, a.faith - 3 * a.tm("faith_decay"))
            elif not b.doubter:
                a.faith += (b.faith - a.faith) * 0.04

    # ------------------------------------------------------------ Außenstehende
    def think_outsider(self, w):
        rng = w.rng
        if self.state == "leave" or w.tick_n > self.leave_at:
            self.state = "leave"
            if not self.go(w, "exit", w.exit):
                self.h_exit(w, None)
            return
        k = self.kind
        if self.state == "arrive":
            if k == "relative":
                t = w.pawn_ids.get(self.target_id)
                if t is not None and not t.away and self.start_talk(w, t, "relative", 100, chase=True):
                    self.state = "browse"
                    return
            spot = w.visitor_spot()
            if not self.go(w, "walk", spot):
                self.state = "leave"
            return
        x, y = self.tile
        if k == "visitor" or k == "relative":
            if k == "relative" and not w.flag("contact_ban"):
                t = w.pawn_ids.get(self.target_id)
                if t is not None and not t.away and t.engaged is None and self.start_talk(w, t, "relative", 100, chase=True):
                    return
            self.interest -= 1.5
            for _ in range(3):
                tx, ty = x + rng.randint(-3, 3), y + rng.randint(-3, 3)
                if w.inb(tx, ty) and self.go(w, "wander", (tx, ty), dur=rng.randint(40, 110)):
                    return
        elif k == "journalist":
            ms = [m for m in w.members(True) if m.kind == "member"]
            for _ in range(3):
                if ms and rng.random() < 0.7:
                    tx, ty = rng.choice(ms).tile
                else:
                    tx, ty = x + rng.randint(-8, 8), y + rng.randint(-8, 8)
                if w.inb(tx, ty) and self.go(w, "snoop", w.stand_tiles(tx, ty, self.cls, True), dur=90):
                    return
            self.go(w, "snoop", self.tile, dur=90)
        elif k == "inspector":
            targets = [w.by_use.get(u, [None])[0] for u in ("stove", "bed", "table")]
            targets = [t for t in targets if t is not None]
            while self.checks < len(targets):
                t = targets[self.checks]
                self.checks += 1
                if self.go(w, "inspect", w.stand_tiles(t.x, t.y, self.cls, True), dur=80):
                    self.target_id = 1          # hat mindestens etwas gesehen
                    return
            self.state = "leave"

    def h_walk(self, w, j):
        self.state = "browse"
        if self.kind == "visitor":
            pr = sum(r.pracht for r in w.rooms)
            self.interest += min(20.0, pr / 4) + (15 if w.flag("love_bombing") else 0)
        return True

    def h_inspect(self, w, j):
        j.t += 1
        return j.t >= j.dur

    def h_snoop(self, w, j):
        j.t += 1
        if int(j.t) % 10 == 0:
            x, y = self.tile
            e = 0.0
            for m in w.members(True):
                if abs(m.x - x) + abs(m.y - y) < 6:
                    e += (m.mood < 35) * 0.25 + m.doubter * 0.5 + (m.food < 20) * 0.3
                    e += (m.asleep and m.job is not None and m.job.mode == "floor") * 0.25
            i = x + y * w.size
            if w.zone[i] == Z_FORBID:
                e += 0.8
            for use in ("confession", "tower", "speaker"):
                if any(abs(t.x - x) + abs(t.y - y) < 6 for t in w.by_use.get(use, ())):
                    e += 0.3
            e += 0.12 * len(w._flags & {"curfew", "contact_ban", "confession_duty", "doomsday"})
            if w.room_of[i] >= 0:
                e *= 1.3
            self.evidence += e * 0.25
            if e > 0.5 and int(j.t) % 30 == 0:
                self.say(w, "fx_exclaim", 30)
        return j.t >= j.dur

    def h_exit(self, w, j):
        from . import events
        events.outsider_left(w, self)
        w.remove_pawn(self)
        return True

    def think_raid(self, w):
        if self.state == "leave":
            if not self.go(w, "exit", w.exit):
                w.remove_pawn(self)
            return
        g = w.guru
        if g is None or g.away:
            self.state = "leave"
            return
        if self.start_talk(w, g, "arrest", 25, chase=True):
            return
        fx, fy = w.focus_point()
        for _ in range(3):
            tx, ty = fx + w.rng.randint(-9, 9), fy + w.rng.randint(-9, 9)
            if w.inb(tx, ty) and self.go(w, "wander", (tx, ty), dur=60):
                return

    def think_goat(self, w):
        x, y = self.tile
        S = w.size
        rng = w.rng
        if x <= 1 or y <= 1 or x >= S - 2 or y >= S - 2:
            w.notify(f"Die heilige Ziege {self.name} ist ausgebüxt. Ein Gehege (Zaun + Tor) hätte geholfen.", "warn", (x, y))
            return w.remove_pawn(self)
        loose = w.room_at(x, y) is None
        for _ in range(3):
            r = 6 if loose else 3
            tx, ty = x + rng.randint(-r, r), y + rng.randint(-r, r) + (2 if loose else 0)
            if w.inb(tx, ty) and self.go(w, "wander", (tx, ty), dur=rng.randint(60, 200)):
                return

    # ------------------------------------------------------------ Lebenslauf
    def come_back(self, w):
        kind = self.away_kind
        self.away, self.away_until, self.away_kind = False, None, None
        self.x, self.y = float(w.exit[0]), float(w.exit[1] - 1)
        self.job = None
        if kind == "trip":
            s = self.skills["preach"]
            self.skills["preach"] = min(10.0, s + 0.1)
            home = w.strategic.home_local()
            home.aware = min(100.0, home.aware + 0.8 + s * 0.15)
            n = 0
            tries = 2 + (1 if w.tracts >= 3 else 0)
            if tries == 3:
                w.tracts -= 3
            for _ in range(tries):
                if w.rng.random() < (0.12 + s * 0.03) * self.tm("convert"):
                    if w.spawn("visitor", bonus=15):
                        n += 1
            if n:
                self.log(w, f"Hat {n} Interessierte aus der Stadt mitgebracht.")
        elif kind == "jail":
            w.notify(f"{self.name} ist aus der Untersuchungshaft zurück. Halleluja!", "good", self.tile)
            for m in w.members(True):
                m.faith = min(100.0, m.faith + 6)

    def become_member(self, w):
        self.kind, self.cls = "member", C_MEMBER
        self.engaged, self.job, self.state = None, None, None
        self.leave_at = 10 ** 12
        self.joined = w.day
        self.faith = clamp(42 + self.interest / 4 + (15 if w.flag("love_bombing") else 0))
        self.mood = 68.0 + (10 if w.flag("love_bombing") else 0)
        self.bond = 10.0
        self.food, self.rest = 70.0, 75.0
        self.role = best_role(self)
        self.log(w, "Der Gemeinschaft beigetreten.")
        if w.flag("love_bombing"):
            self.add_thought("lovebomb", "Alle sind sooo nett zu mir!", 12, 96, w)

    def promote(self, w):
        ranks = DATA.doctrine["ranks"]
        if self.kind != "member" or self.rank >= len(ranks) - 1:
            return False
        cost = ranks[self.rank + 1]["cost"]
        if w.ep < cost:
            return False
        w.ep -= cost
        self.rank += 1
        self.bond = min(100.0, self.bond + 10)
        self.faith = min(100.0, self.faith + 8)
        self.add_thought("promo", f"Zum {self.rank_name} erhoben!", 10, 120, w)
        self.log(w, f"Aufstieg zum Rang »{self.rank_name}«.")
        w.notify(f"{self.name} wurde zum {self.rank_name} erhoben.", "good", self.tile, self.id)
        for m in w.members(True):
            if m.kind == "member" and m is not self and m.rank < self.rank and "ehrgeizig" in m.traits:
                m.add_thought("envy", f"Warum {self.name.split()[0]} und nicht ich?", -6, 96, w)
        w.cues.append("convert")
        return True

    def gift(self, w, cost=50):
        if w.money < cost:
            return False
        w.spend("Geschenke", cost)
        self.bond = min(100.0, self.bond + 6)
        self.add_thought("gift", "Ein Geschenk vom Guru (signiertes Porträt)", 6, 72, w)
        self.say(w, "fx_heart", 80)
        return True

    def hourly(self, w):
        if self.kind not in MEMBER_KINDS:
            return
        if self.away:
            if self.away_kind == "post":
                self.bond = max(0.0, self.bond - 0.02)
            return
        t = w.tick_n
        for k in [k for k, v in self.thoughts.items() if v[2] <= t]:
            del self.thoughts[k]
        target = 55.0 + sum(v[1] for v in self.thoughts.values()) + self.bond * 0.08
        for tr in self.traits:
            target += DATA.traits[tr].get("mood", 0)
        if self.kind == "member":
            target += w.add("mood")
        if self.food < 25:
            target -= 12
        if self.rest < 20:
            target -= 8
        self.mood += (clamp(target) - self.mood) * 0.15
        if self.kind == "member":
            dec = 0.2 * self.tm("faith_decay") * w.mod("faith_decay")
            if self.mood < 35:
                dec += 0.35
            elif self.mood > 70:
                dec -= 0.12
            self.faith = clamp(self.faith - dec)
            self.bond = max(0.0, self.bond - 0.025)
            was = self.doubter
            self.doubter = self.faith < 25 or (was and self.faith < 36)
            if self.doubter and not was:
                w.notify(f"{self.name} beginnt zu zweifeln.", "warn", self.tile, self.id)
                self.log(w, "Erste Zweifel an der Lehre.")
            if self.doubter and not self.asleep:
                self.say(w, "fx_question", 50)
        if self.food <= 0:
            self.starve += 1
            if self.starve == 8:
                w.notify(f"{self.name} hungert!", "bad", self.tile, self.id)
            if self.starve >= 30 and self.kind == "member":
                w.add_heat(8)
                w.add_evidence(6)
                w.defect(self, "wurde entkräftet vom Rettungsdienst abgeholt")
        else:
            self.starve = 0

    def daily(self, w):
        pass


JOB_NAMES = {"wander": "Schlendert herum", "patrol": "Patrouilliert", "eat": "Isst", "sleep": "Schläft",
             "build": "Baut", "sow": "Sät", "harvest": "Erntet", "cook": "Kocht Eintopf", "print": "Druckt Traktate",
             "desk": "Schreibt Spendenbriefe", "preach": "Predigt", "attend": "Lauscht der Predigt",
             "meditate": "Meditiert", "trip": "Bricht zur Werbetour auf", "flee": "FLIEHT!", "listen": "Hört zu",
             "goto": "Folgt deinem Befehl", "exit": "Verlässt das Gelände", "walk": "Kommt an",
             "snoop": "Schnüffelt herum", "inspect": "Kontrolliert", "talk": "Spricht"}
GO_NAMES = {"eat": "zum Essen", "sleep": "zum Schlafplatz", "build": "zur Baustelle", "sow": "aufs Feld", "harvest": "aufs Feld",
            "cook": "zur Kochstelle", "print": "zur Druckerpresse", "desk": "ins Spendenbüro", "preach": "zum Altar",
            "attend": "zur Predigt", "meditate": "zur Meditationsmatte", "talk": "zu einem Gespräch",
            "snoop": "… wohin eigentlich?", "inspect": "zur Kontrolle"}
TALK_NAMES = {"convert": "Bekehrt einen Besucher", "counsel": "Betreut einen Zweifler", "bond": "Einzelgespräch",
              "interview": "Gibt ein Interview", "escort": "Begleitet jemanden hinaus", "catch": "Stellt einen Ausreißer",
              "relative": "Redet auf ein Mitglied ein", "arrest": "Nimmt fest", "chat": "Plaudert"}


def sermon_preacher(w):
    g = w.guru
    if g is not None and not g.away and not g.orders and not g.asleep and w.flags.get("guru_preaches", True):
        return g
    cands = [m for m in w.members(True) if m.kind == "member" and m.role == "preacher" and not m.asleep]
    return max(cands, key=lambda m: m.skills["preach"]) if cands else None


def best_role(p):
    order = ("worker", "cook", "preacher", "clerk", "guard")
    return max(order, key=lambda r: p.skills[ROLE_SKILL[r]] + (0.5 if r == "worker" else 0))


def gen_identity(p, w, allow_mole=True):
    rng = w.rng
    nm = DATA.names
    p.female = rng.random() < 0.5
    p.name = f"{rng.choice(nm['first_f'] if p.female else nm['first_m'])} {rng.choice(nm['last'])}"
    p.age = int(clamp(rng.gauss(41, 14), 18, 79))
    job = rng.choice(nm["jobs"])
    p.former_job = job["name"]
    p.bio = rng.choice(nm["bios"])
    for k in p.skills:
        p.skills[k] = float(rng.randint(0, 3))
    for k, v in job.get("skills", {}).items():
        p.skills[k] += v
    pool = [(k, t["weight"]) for k, t in DATA.traits.items() if t.get("weight", 0) > 0]
    while len(p.traits) < 2:
        t = rng.choices([k for k, _ in pool], [wt for _, wt in pool])[0]
        if t not in p.traits:
            p.traits.append(t)
    if allow_mole and w.day > 6 and rng.random() < 0.04 + w.heat / 600:
        p.traits.append(rng.choice(["maulwurf_presse", "maulwurf_behoerde"]))
    for t in p.traits:
        for k, v in DATA.traits[t].get("skills", {}).items():
            p.skills[k] += v
    for k in p.skills:
        p.skills[k] = clamp(p.skills[k], 0, 10)
    p._tm = None
    p.wealth = rng.lognormvariate(6.6, 0.9) * p.tm("wealth")


def make_member(w, x, y, guru=False):
    p = Pawn(w, "guru" if guru else "member", x, y)
    gen_identity(p, w, allow_mole=False)
    if guru:
        p.traits = ["charismatisch"]
        p._tm = None
        p.skills["preach"] = 6.0
        p.faith, p.bond, p.rank = 100.0, 100.0, 3
        p.former_job = "Gebrauchtwagenhändler"
        p.bio = "Hatte nach der Insolvenz eine Eingebung: Menschen kaufen alles, wenn man es 'Erleuchtung' nennt."
    else:
        p.role = best_role(p)
    return p


def make_outsider(w, kind, offset=0, bonus=0, target=None):
    ex, ey = w.exit
    p = Pawn(w, kind, ex + (offset % 2), ey - offset // 2)
    rng = w.rng
    if kind == "visitor":
        gen_identity(p, w)
        p.interest = 30 + rng.random() * 35 + bonus
        p.leave_at = w.tick_n + rng.randint(450, 750)
    elif kind == "journalist":
        gen_identity(p, w, allow_mole=False)
        p.former_job = "Journalist"
        p.leave_at = w.tick_n + rng.randint(600, 850)
    elif kind == "inspector":
        p.name = rng.choice(["Herr Dr. Paragraphenreiter", "Frau Aktendeckel", "Herr Stempelmann", "Frau Vorschrift-Meyer"])
        p.leave_at = w.tick_n + 900
    elif kind == "relative":
        p.target_id = target
        t = w.pawn_ids.get(target)
        p.name = f"Familie {t.name.split()[-1]}" if t else "Besorgte Angehörige"
        p.leave_at = w.tick_n + rng.randint(500, 700)
    elif kind in ("police", "soldier"):
        p.name = ("Wachtmeister " if kind == "police" else "Feldwebel ") + rng.choice(DATA.names["last"])
        p.speed = 0.13
    return p
