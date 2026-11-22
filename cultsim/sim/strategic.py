"""Strategische Ebene (Kartenmodus): Stadt → Land → Welt.

Jede Ebene besteht aus Regionen mit Anhängern, Bekanntheit und Verdacht. Kampagnen, Ortsgruppen,
Regionalleiter (echte Mitglieder!), Logistik, Sprache und Gegenspieler wirken auf das Wachstum.
"""
from __future__ import annotations

import math

from ..config import AXES
from ..data import DATA

LEVELS = ("local", "country", "world")
LEVEL_NAMES = {"local": "Stadt", "country": "Land", "world": "Welt"}
RASTER_MAX = {"local": (300, 180), "country": (300, 180), "world": (460, 200)}
FALLBACK_MAP = {
    "id": "local", "name": "Umgebung", "geo": False, "bounds": [0, 0, 100, 70], "home": "hof", "pop_unit": "Tsd.",
    "languages": {"de": "Deutsch"}, "links": [],
    "regions": [
        {"id": "hof", "name": "Aussiedlerhof", "polys": [[[55, 10], [95, 10], [95, 60], [55, 60]]], "pop": 1.0},
        {"id": "stadt", "name": "Stadt", "polys": [[[5, 10], [55, 10], [55, 60], [5, 60]]], "pop": 12.0},
    ],
}


class Region:
    def __init__(self, d, unit):
        self.id, self.name = d["id"], d["name"]
        self.pop = d["pop"] * unit
        self.lang = d.get("lang", "de")
        self.wealth = d.get("wealth", 0.5)
        self.openness = d.get("openness", 0.4)
        self.state = d.get("state", 0.5)
        self.press = d.get("press", 0.5)
        self.military = d.get("military", 0.0)
        self.affinity = d.get("affinity", {})
        self.quirk = d.get("quirk", {"name": "", "text": "", "mods": {}})
        self.followers = 0.0
        self.aware = 0.0
        self.heat = 0.0
        self.chapter = 0
        self.leader = None
        self.campaigns: dict[str, int] = {}
        self.hub = False
        self.status = 0
        self.status_timer = 0
        self.lobby = 0
        self.pr = 0
        self.hops = 0
        self.delta = 0.0
        self.aggregate = False
        self.cx = self.cy = 0
        self.pixels = 0

    def qm(self, key):
        return self.quirk.get("mods", {}).get(key, 1.0)

    def camp_power(self):
        c = DATA.campaigns["campaigns"]
        return sum(c[k]["power"] for k in self.campaigns if k in c)

    @property
    def scale(self):
        return max(1.0, (self.pop / 5000.0) ** 0.65)

    @property
    def share(self):
        return self.followers / self.pop if self.pop else 0.0


class Level:
    def __init__(self, key, d):
        self.key = key
        self.name = d["name"]
        self.geo = d.get("geo", False)
        self.bounds = d["bounds"]
        self.home = d["home"]
        self.pop_unit = d.get("pop_unit", "Tsd.")
        self.languages = d.get("languages", {"de": "Deutsch"})
        unit = 1e6 if self.pop_unit.startswith("Mio") else 1e3
        self.regions: dict[str, Region] = {r["id"]: Region(r, unit) for r in d["regions"]}
        self.order = [r["id"] for r in d["regions"]]
        self._rasterize(d)
        for a, b in d.get("links", []):
            if a in self.regions and b in self.regions:
                self.adj[a].add(b)
                self.adj[b].add(a)
        self.links = [tuple(l) for l in d.get("links", [])]

    def _rasterize(self, d):
        """Füllt ein grobes Pixelraster (Region-Index je Pixel) – Basis für Darstellung, Klick und Nachbarschaft."""
        x0, y0, x1, y1 = self.bounds
        kx = math.cos(math.radians((y0 + y1) / 2)) if self.geo else 1.0
        wu, hu = (x1 - x0) * kx, (y1 - y0)
        mw, mh = RASTER_MAX[self.key]
        s = min(mw / wu, mh / hu)
        rw, rh = max(1, math.ceil(wu * s)), max(1, math.ceil(hu * s))
        grid = [-1] * (rw * rh)
        geo = self.geo
        for ri, rd in enumerate(d["regions"]):
            for poly in rd["polys"]:
                if geo:
                    pts = [((p[0] - x0) * kx * s, (y1 - p[1]) * s) for p in poly]
                else:
                    pts = [((p[0] - x0) * s, (p[1] - y0) * s) for p in poly]
                ys = [p[1] for p in pts]
                n = len(pts)
                for y in range(max(0, int(min(ys))), min(rh, int(max(ys)) + 1)):
                    yc = y + 0.5
                    xs = []
                    for k in range(n):
                        ax, ay = pts[k]
                        bx, by = pts[(k + 1) % n]
                        if (ay <= yc < by) or (by <= yc < ay):
                            xs.append(ax + (yc - ay) / (by - ay) * (bx - ax))
                    xs.sort()
                    for k in range(0, len(xs) - 1, 2):
                        for x in range(max(0, math.ceil(xs[k] - 0.5)), min(rw, math.floor(xs[k + 1] - 0.5) + 1)):
                            grid[x + y * rw] = ri
        self.rw, self.rh, self.grid = rw, rh, grid
        ids = self.order
        adj = {i: set() for i in ids}
        sx, sy, cnt = [0] * len(ids), [0] * len(ids), [0] * len(ids)
        for y in range(rh):
            for x in range(rw):
                a = grid[x + y * rw]
                if a < 0:
                    continue
                sx[a] += x; sy[a] += y; cnt[a] += 1
                for dx, dy in ((1, 0), (0, 1), (1, 1), (-1, 1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < rw and ny < rh:
                        b = grid[nx + ny * rw]
                        if b >= 0 and b != a:
                            adj[ids[a]].add(ids[b])
                            adj[ids[b]].add(ids[a])
        self.adj = adj
        for k, rid in enumerate(ids):
            r = self.regions[rid]
            r.pixels = cnt[k]
            if not cnt[k]:
                continue
            cx, cy = sx[k] // cnt[k], sy[k] // cnt[k]
            if grid[cx + cy * rw] != k:     # Schwerpunkt liegt außerhalb (Inseln, Bögen) → nächstes eigenes Pixel
                best = None
                for y in range(rh):
                    for x in range(rw):
                        if grid[x + y * rw] == k:
                            dd = (x - cx) ** 2 + (y - cy) ** 2
                            if best is None or dd < best[0]:
                                best = (dd, x, y)
                cx, cy = best[1], best[2]
            r.cx, r.cy = cx, cy

    def total(self):
        return sum(r.followers for r in self.regions.values())

    def pop(self):
        return sum(r.pop for r in self.regions.values())


class Strategic:
    def __init__(self, w):
        self.w = w
        self.phase = 1
        self.levels: dict[str, Level] = {}
        for k in LEVELS:
            d = DATA.maps.get(k)
            if d:
                self.levels[k] = Level(k, d)
        if "local" not in self.levels:
            self.levels["local"] = Level("local", FALLBACK_MAP)
        self.languages = {"de"}
        self.translating: dict[str, int] = {}
        home = self.home_local()
        home.aware = 6.0
        home.followers = 4.0
        if "world" in self.levels and "country" in self.levels:
            wl = self.levels["world"]
            wl.regions[wl.home].aggregate = True

    # ------------------------------------------------------------ Abfragen
    def active(self):
        return [self.levels[k] for k in LEVELS[: self.phase] if k in self.levels]

    def max_phase(self):
        return sum(1 for k in LEVELS if k in self.levels)

    def home_local(self) -> Region:
        lv = self.levels["local"]
        return lv.regions[lv.home]

    def phase_scale(self):
        return (1, 60, 2500)[self.phase - 1]

    def total_followers(self):
        return self.levels[LEVELS[self.phase - 1]].total() if LEVELS[self.phase - 1] in self.levels else 0.0

    def world_share(self):
        wl = self.levels.get("world")
        return wl.total() / wl.pop() if wl and self.phase >= 3 else 0.0

    def affinity_factor(self, r: Region):
        d = self.w.doctrine
        m = sum(d[a] / 100.0 * r.affinity.get(a, 0.0) for a in AXES) / 1.5
        return max(0.45, min(1.6, 1.0 + 0.6 * m))

    def cost(self, r: Region, base):
        c = base * r.scale * r.qm("cost") * (1.5 if r.status >= 2 else 1.0)
        return int(round(c, -1)) if c >= 100 else int(round(c))

    def lang_ok(self, r: Region):
        return r.lang in self.languages

    def supply_factor(self, lv: Level, r: Region):
        if lv.key == "local":
            return 1.0
        return 1.0 if r.hops <= 2 else 0.6 if r.hops <= 4 else 0.35

    def leader_of(self, r: Region):
        return self.w.pawn_ids.get(r.leader) if r.leader else None

    def find_post(self, pid):
        for lv in self.levels.values():
            for r in lv.regions.values():
                if r.leader == pid:
                    return lv, r
        return None

    # ------------------------------------------------------------ Aktionen (liefern Fehlertext oder None)
    def _pay(self, cat, money, ep=0):
        w = self.w
        if w.money < money:
            return "Zu wenig Geld"
        if w.ep < ep:
            return "Zu wenig Erleuchtung"
        w.spend(cat, money)
        w.ep -= ep
        return None

    def campaign_block(self, lv, r, cid):
        c = DATA.campaigns["campaigns"][cid]
        if r.aggregate:
            return "Wird über die Landeskarte gesteuert"
        if c["phase"] > self.phase:
            return f"Erst ab Phase {c['phase']}"
        if cid in r.campaigns:
            return "Läuft bereits"
        if r.status == 4:
            return "Hier sind wir verboten"
        if len(r.campaigns) >= 2 + r.chapter:
            return "Kampagnen-Limit (größere Ortsgruppe nötig)"
        if self.w.money < self.cost(r, c["cost"]):
            return "Zu wenig Geld"
        return None

    def start_campaign(self, lv, r, cid):
        err = self.campaign_block(lv, r, cid)
        if err:
            return err
        c = DATA.campaigns["campaigns"][cid]
        self._pay("Kampagnen", self.cost(r, c["cost"]))
        r.campaigns[cid] = c["days"]
        self.w.notify(f"Kampagne »{c['name']}« in {r.name} gestartet.", "info")
        self.w.cues.append("coin")
        return None

    def chapter_block(self, lv, r):
        ch = DATA.campaigns["chapters"]
        if r.aggregate:
            return "Wird über die Landeskarte gesteuert"
        if r.chapter >= len(ch) - 1:
            return "Maximal ausgebaut"
        if r.status == 4:
            return "Hier sind wir verboten"
        need = (0, 0, 0.004, 0.02)[r.chapter + 1]
        if r.share < need:
            return f"Braucht {need * 100:.1f} % Anhänger in der Region"
        if self.w.money < self.cost(r, ch[r.chapter + 1]["cost"]):
            return "Zu wenig Geld"
        return None

    def build_chapter(self, lv, r):
        err = self.chapter_block(lv, r)
        if err:
            return err
        ch = DATA.campaigns["chapters"][r.chapter + 1]
        self._pay("Ortsgruppen", self.cost(r, ch["cost"]))
        r.chapter += 1
        r.followers = max(r.followers, 3.0 * r.scale)
        self.w.notify(f"{ch['name']} in {r.name} eröffnet.", "good")
        self.w.cues.append("build_done")
        return None

    def action_block(self, lv, r, aid):
        a = DATA.campaigns["actions"][aid]
        if r.aggregate:
            return "Wird über die Landeskarte gesteuert"
        if a["phase"] > self.phase:
            return f"Erst ab Phase {a['phase']}"
        if aid == "hub":
            if lv.key == "local":
                return "In der Stadt nicht nötig"
            if r.hub or r.id == lv.home:
                return "Schon vorhanden"
            if r.chapter < 1:
                return "Braucht eine Ortsgruppe"
        if aid == "lobby" and r.lobby > 0:
            return "Wirkt noch"
        if aid == "pr" and r.pr > 0:
            return "Wirkt noch"
        if aid == "translate":
            if r.lang in self.languages:
                return "Bereits übersetzt"
            if r.lang in self.translating:
                return "Übersetzung läuft"
            if self.w.money < a["cost"] or self.w.ep < a["ep"]:
                return "Zu wenig Geld/Erleuchtung"
            return None
        if self.w.money < self.cost(r, a["cost"]):
            return "Zu wenig Geld"
        return None

    def do_action(self, lv, r, aid):
        err = self.action_block(lv, r, aid)
        if err:
            return err
        a = DATA.campaigns["actions"][aid]
        w = self.w
        if aid == "translate":
            self._pay("Übersetzungen", a["cost"], a["ep"])
            self.translating[r.lang] = a["days"]
            w.notify(f"Die Heilige Schrift wird ins {lv.languages.get(r.lang, r.lang)}e übersetzt.", "info")
            return None
        self._pay("Öffentlichkeitsarbeit" if aid != "hub" else "Logistik", self.cost(r, a["cost"]))
        if aid == "pr":
            r.heat = max(0.0, r.heat - 25)
            r.pr = 20
            if lv.key == "local":
                w.add_heat(-8)
        elif aid == "lobby":
            r.lobby = 30
        elif aid == "hub":
            r.hub = True
            self._hops(lv)
        w.notify(f"{a['name']} in {r.name}.", "info")
        w.cues.append("coin")
        return None

    def assign_leader(self, lv, r, p):
        if r.aggregate or p.kind != "member" or p.away or p.rank < 1:
            return "Nur anwesende Mitglieder ab Rang »Eingeweihter«"
        if r.leader:
            self.recall_leader(r)
        p.cancel_job(self.w)
        p.away, p.away_kind, p.away_until = True, "post", None
        p.post = (lv.key, r.id)
        r.leader = p.id
        p.log(self.w, f"Als Regionalleitung nach {r.name} entsandt.")
        self.w.notify(f"{p.name} leitet nun die Mission in {r.name}.", "info")
        return None

    def recall_leader(self, r):
        p = self.leader_of(r)
        r.leader = None
        if p is not None:
            p.post = None
            p.away_kind = "return"
            p.away_until = self.w.tick_n + 150

    def unassign(self, pid):
        for lv in self.levels.values():
            for r in lv.regions.values():
                if r.leader == pid:
                    r.leader = None

    def advance_req(self):
        """Voraussetzungen für die nächste Phase: Liste (Text, erfüllt)."""
        w = self.w
        if self.phase == 1:
            fol = self.levels["local"].total()
            mem = len(w.members())
            return [(f"400 Anhänger in der Stadt ({fol:.0f})", fol >= 400), (f"8 Mitglieder ({mem})", mem >= 8),
                    (f"3.000 € ({w.money:.0f})", w.money >= 3000), (f"30 Erleuchtung ({w.ep:.0f})", w.ep >= 30)]
        if self.phase == 2:
            fol = self.levels["country"].total()
            return [(f"1 Mio. Anhänger im Land ({fmt(fol)})", fol >= 1e6), (f"5 Mio. € ({fmt(w.money)})", w.money >= 5e6),
                    (f"150 Erleuchtung ({w.ep:.0f})", w.ep >= 150)]
        return []

    def advance(self):
        if self.phase >= self.max_phase() or not all(ok for _, ok in self.advance_req()):
            return False
        w = self.w
        if self.phase == 1:
            self._pay("Expansion", 2000, 20)
            self.phase = 2
            lv = self.levels["country"]
            h = lv.regions[lv.home]
            h.followers, h.aware, h.chapter = self.levels["local"].total(), 15.0, 1
            self._hops(lv)
            from . import events
            events.phase_popup(w, 2)
        else:
            self._pay("Expansion", 3_000_000, 100)
            self.phase = 3
            self._hops(self.levels["world"])
            from . import events
            events.phase_popup(w, 3)
        w.recompute_mods()
        return True

    # ------------------------------------------------------------ Tagesabrechnung
    def _hops(self, lv: Level):
        hubs = [r.id for r in lv.regions.values() if r.hub or r.id == lv.home]
        dist = {h: 0 for h in hubs}
        q = list(hubs)
        while q:
            a = q.pop(0)
            for b in lv.adj[a]:
                if b not in dist:
                    dist[b] = dist[a] + 1
                    q.append(b)
        for r in lv.regions.values():
            r.hops = dist.get(r.id, 9)

    def daily(self):
        w = self.w
        rng = w.rng
        camps = DATA.campaigns["campaigns"]
        chs = DATA.campaigns["chapters"]
        d = w.doctrine
        extrem = max(0.0, d["apocalypse"]) / 100 * 1.5 + max(0.0, d["isolation"]) / 100 * 0.7 + max(0.0, d["commerce"]) / 100 * 0.4
        for lang in list(self.translating):
            self.translating[lang] -= 1
            if self.translating[lang] <= 0:
                del self.translating[lang]
                self.languages.add(lang)
                w.notify(f"Übersetzung fertig: {self.levels['world'].languages.get(lang, lang)}.", "good")
        for lv in self.active():
            local = lv.key == "local"
            # Traktate (nur Stadt-Ebene verbraucht direkt aus dem Lager)
            tract_f = 1.0
            if local:
                need = sum(camps[c]["tracts"] for r in lv.regions.values() for c in r.campaigns)
                if need > 0:
                    if w.tracts >= need:
                        w.tracts -= need
                    else:
                        tract_f = 0.4
                        w.tracts = 0.0
                        if not w.flags.get("tract_warn") or w.day - w.flags["tract_warn"] > 4:
                            w.flags["tract_warn"] = w.day
                            w.notify("Die Traktate sind aus! Kampagnen wirken kaum (Druckerpresse + Schreiber).", "warn")
            for r in lv.regions.values():
                if r.aggregate:
                    sub = self.levels["country"]
                    r.followers = sub.total()
                    r.heat = sum(x.heat * x.pop for x in sub.regions.values()) / sub.pop()
                    r.aware = sum(x.aware * x.pop for x in sub.regions.values()) / sub.pop()
                    continue
                aff = self.affinity_factor(r)
                lang_f = 1.0 if self.lang_ok(r) else 0.2
                sup = self.supply_factor(lv, r) * tract_f
                leader = self.leader_of(r)
                lead_f = 1.0 + (leader.skills["preach"] * 0.08 if leader else 0.0)
                stat_f = (1.0, 0.85, 0.65, 0.4, 0.0)[r.status]
                eff_open = r.openness * (0.6 + 0.4 * r.aware / 100)
                cap = r.pop * (0.015 + 0.09 * r.openness) * (1 + 0.5 * r.chapter) * aff
                room = max(0.0, 1 - r.followers / cap) if cap > 0 else 0.0
                power = r.camp_power() * tract_f
                spill = sum(n.followers for n in (lv.regions[x] for x in lv.adj[r.id]) if n.followers > r.followers) * 0.003
                rate = 0.05 * aff * r.qm("growth") * w.mod("growth") * (1 + 0.25 * r.chapter) * lead_f * lang_f * sup * stat_f
                seed = (r.pop * eff_open * (0.002 if local else 0.0008) * power * lead_f + spill * r.openness) * lang_f * sup * stat_f * w.mod("growth")
                if r.status == 4:
                    delta = -0.04 * r.followers
                else:
                    delta = (r.followers * rate + seed) * room
                    if r.followers > cap:
                        delta = -(r.followers - cap) * 0.05
                r.delta = delta
                r.followers = max(0.0, r.followers + delta)
                # Bekanntheit
                r.aware = min(100.0, r.aware * 0.985 + sum(camps[c]["aware"] for c in r.campaigns) / camps_len(r) * tract_f
                              + r.share * 30)
                # Verdacht
                tgt = (r.share * 600 + sum(camps[c]["heat"] for c in r.campaigns) + extrem * 40) * r.state
                tgt *= (0.7 + 0.6 * r.press) * r.qm("heat") * w.mod("heat_gain")
                if r.lobby > 0:
                    tgt *= 0.6
                if r.pr > 0:
                    tgt *= 0.7
                r.heat += (min(100.0, tgt) - r.heat) * 0.08
                r.lobby = max(0, r.lobby - 1)
                r.pr = max(0, r.pr - 1)
                self._status(lv, r)
                # Kampagnen-Laufzeit
                for c in list(r.campaigns):
                    r.campaigns[c] -= 1
                    if r.campaigns[c] <= 0:
                        del r.campaigns[c]
                # Geld
                inc = r.followers * r.wealth * 0.12 * math.sqrt(w.mod("tithe")) * r.qm("income") * w.mod("income")
                if r.status == 4:
                    inc *= 0.4
                w.earn(f"Spenden der Anhänger ({LEVEL_NAMES[lv.key]})", inc)
                up = chs[r.chapter]["upkeep"] * r.scale + (DATA.campaigns["actions"]["hub"]["upkeep"] * r.scale if r.hub else 0)
                w.spend("Unterhalt Ortsgruppen", up)
                # Regionalleiter: fern vom Guru bröckelt die Bindung
                if leader is not None:
                    leader.bond = max(0.0, leader.bond - 0.5)
                    if leader.bond < 12 and r.followers > 20 and rng.random() < 0.05:
                        from . import events
                        events.leader_splits(w, lv, r, leader)
            if lv.key == "country":
                h = lv.regions[lv.home]
                h.followers = max(h.followers, self.levels["local"].total())
        # Sieg?
        proj = DATA.doctrine["projects"]
        if "weltreligion" in w.projects_done and not w.over:
            w.over = ("win", proj["weltreligion"]["text"])

    def _status(self, lv, r):
        w = self.w
        names = DATA.campaigns["status"]
        h = r.heat
        if r.status == 4:
            r.status_timer -= 1
            if r.status_timer <= 0:
                r.status = 2
                r.heat = 50.0
                w.notify(f"Das Verbot in {r.name} ist ausgelaufen.", "good")
            return
        if r.status == 3:
            r.status_timer -= 1
            if h < 55:
                r.status = 2
                w.notify(f"{r.name}: Das Verbotsverfahren wurde eingestellt.", "good")
            elif r.status_timer <= 0:
                p_win = (0.15 + 0.2 * w.lawyers) * r.qm("legal") + (0.2 if r.lobby > 0 else 0)
                if w.rng.random() < p_win:
                    r.status, r.heat = 2, 50.0
                    w.notify(f"{r.name}: Unsere Anwälte haben das Verbot abgewendet! (Verfahrensfehler)", "good")
                else:
                    r.status, r.status_timer = 4, 40
                    r.chapter = 0
                    r.campaigns.clear()
                    r.hub = False
                    mil = lv.key == "world" and r.military > 0.6
                    if mil:
                        r.followers *= 0.5
                    w.notify(f"{r.name}: {w.cult_name} wurde VERBOTEN. "
                             + ("Das Militär riegelt die Tempel ab." if mil else "Die Ortsgruppe arbeitet im Untergrund weiter."), "bad")
                    if lv.key != "world" and r.id == lv.home:
                        w.add_heat(25)
            return
        if r.status == 2 and h >= 75:
            r.status, r.status_timer = 3, 12
            w.notify(f"{r.name}: Die Behörden leiten ein VERBOTSVERFAHREN ein (12 Tage). Anwälte, Lobby oder PR helfen.", "bad")
        elif r.status == 1 and h >= 55:
            r.status = 2
            w.notify(f"{r.name}: Behördliche Auflagen – Kampagnen und Ausbau werden teurer.", "warn")
        elif r.status == 0 and h >= 35:
            r.status = 1
            w.notify(f"{r.name}: Die Presse wird aufmerksam.", "warn")
        elif r.status > 0 and h < (0, 22, 42)[r.status]:
            r.status -= 1
            w.notify(f"{r.name}: Lage entspannt sich ({names[r.status]}).", "info")


def camps_len(r):
    return max(1, len(r.campaigns)) ** 0.5


def fmt(v):
    """Kompakte Zahlendarstellung: 1.234 / 12,3 Tsd. / 4,5 Mio. / 1,2 Mrd."""
    a = abs(v)
    if a >= 1e9:
        s = f"{v / 1e9:.2f} Mrd."
    elif a >= 1e6:
        s = f"{v / 1e6:.2f} Mio."
    elif a >= 1e4:
        s = f"{v / 1e3:.1f} Tsd."
    else:
        return f"{v:,.0f}".replace(",", ".")
    return s.replace(".", ",", 1) if "," not in s else s
