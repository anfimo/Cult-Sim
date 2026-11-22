"""Kartenmodus im Stil großer Strategiespiele: Stadt / Land / Welt mit umschaltbaren Kartenmodi."""
from __future__ import annotations

import pygame

from ..data import DATA
from ..sim.strategic import LEVELS, LEVEL_NAMES, fmt
from .hud import TOP_H, BOT_H, AX_SHORT
from .widgets import *

R = pygame.Rect
MODES = [("einfluss", "Einfluss", "Anteil der Anhänger an der Bevölkerung"),
         ("verdacht", "Verdacht", "Wie misstrauisch Behörden und Presse sind"),
         ("gegner", "Gegner", "Stand der Gegenmaßnahmen: Presse → Auflagen → Verbotsverfahren → Verbot"),
         ("potenzial", "Potenzial", "Wie gut unsere aktuelle Lehre zur Region passt (Kultur, Offenheit, Sprache)"),
         ("sprache", "Sprache", "Sprachräume – hell: Schriften übersetzt, dunkel: noch nicht"),
         ("logistik", "Logistik", "Versorgung mit Material: Entfernung zum nächsten Logistikzentrum")]
SEA = (22, 34, 56)
CAT = [(200, 110, 100), (110, 150, 210), (120, 190, 120), (210, 190, 100), (170, 120, 200), (100, 190, 190), (220, 150, 90),
       (150, 160, 110), (200, 130, 170), (130, 130, 190), (180, 200, 140), (210, 170, 150)]
STATUS_COL = [(92, 130, 100), (214, 196, 90), (226, 140, 60), (222, 70, 60), (90, 30, 40)]


def lerp(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def ramp(t, cols):
    t = max(0.0, min(1.0, t)) * (len(cols) - 1)
    i = min(len(cols) - 2, int(t))
    return lerp(cols[i], cols[i + 1], t - i)


class MapView:
    def __init__(self, app):
        self.app = app
        self.level = "local"
        self.mode = "einfluss"
        self.sel = None
        self.zoom = 0             # 0 = automatisch einpassen
        self.off = [0, 0]
        self.picking = False
        self._base: dict = {}
        self._scaled: dict = {}
        self._drag = None
        self._side_h = 0

    def base(self, lv):
        s = self._base.get(lv.key)
        if s is None:
            rw, rh, g = lv.rw, lv.rh, lv.grid
            buf = bytearray(rw * rh)
            for y in range(rh):
                row = y * rw
                for x in range(rw):
                    a = g[row + x]
                    if a < 0:
                        continue
                    border = coast = False
                    if x + 1 < rw:
                        o = g[row + x + 1]
                        if o != a:
                            border, coast = (o >= 0) or border, (o < 0) or coast
                    if y + 1 < rh:
                        o = g[row + rw + x]
                        if o != a:
                            border, coast = (o >= 0) or border, (o < 0) or coast
                    if x > 0 and g[row + x - 1] < 0 or y > 0 and g[row - rw + x] < 0:
                        coast = True
                    buf[row + x] = a + 1 + (64 if border else 128 if coast else 0)
            raw = pygame.image.frombuffer(bytes(buf), (rw, rh), "P")
            raw.set_palette([(i, i, i) for i in range(256)])
            s = raw.copy()
            self._base[lv.key] = s
        return s

    def region_color(self, lv, r, n):
        st = self.app.w.strategic
        m = self.mode
        if m == "einfluss":
            return ramp((r.share / 0.10) ** 0.5, [(78, 74, 92), (126, 84, 176), (190, 120, 220), (240, 200, 90)])
        if m == "verdacht":
            return ramp(r.heat / 100, [(70, 120, 84), (200, 196, 90), (226, 130, 60), (214, 56, 50)])
        if m == "gegner":
            return STATUS_COL[r.status]
        if m == "potenzial":
            f = (st.affinity_factor(r) - 0.45) / 1.15 * (0.5 + r.openness)
            c = ramp(f, [(160, 70, 66), (190, 170, 90), (90, 180, 100)])
            return c if st.lang_ok(r) else lerp(c, (30, 30, 40), 0.55)
        if m == "sprache":
            langs = list(lv.languages)
            c = CAT[langs.index(r.lang) % len(CAT)] if r.lang in langs else (120, 120, 120)
            return c if st.lang_ok(r) else lerp(c, (20, 20, 30), 0.6)
        if m == "logistik":
            if lv.key == "local":
                return (90, 170, 110)
            return [(90, 190, 110), (120, 180, 100), (170, 180, 90), (210, 160, 80), (214, 110, 70)][min(4, r.hops)] if r.hops < 9 else (120, 50, 50)
        return CAT[n % len(CAT)]

    def draw(self):
        app = self.app
        ui, w = app.ui, app.w
        st = w.strategic
        W, H = app.screen.get_size()
        full = R(0, TOP_H + 1, W, H - TOP_H - BOT_H - 1)
        ui.panel(full, alpha=255, edge=None)
        if self.level not in st.levels or LEVELS.index(self.level) >= st.phase:
            self.level = LEVELS[min(st.phase, len(LEVELS)) - 1] if LEVELS[st.phase - 1] in st.levels else "local"
        lv = st.levels[self.level]
        side = 350
        mrect = R(8, TOP_H + 50, W - side - 24, H - TOP_H - BOT_H - 100)
        # Ebenen-Reiter
        x = 10
        for k in LEVELS:
            if k not in st.levels:
                continue
            locked = LEVELS.index(k) >= st.phase
            if ui.button(R(x, TOP_H + 10, 96, 32), LEVEL_NAMES[k] + (" (zu)" if locked else ""),
                         "Wird mit der nächsten Phase freigeschaltet." if locked else st.levels[k].name,
                         enabled=not locked, active=self.level == k, font="m" if not locked else "s"):
                self.level, self.sel, self.zoom, self.off, self.picking = k, None, 0, [0, 0], False
            x += 101
        x += 14
        for mid, mname, mtip in MODES:
            if ui.button(R(x, TOP_H + 12, 86, 28), mname, mtip, active=self.mode == mid):
                self.mode = mid
            x += 90
        # Karte
        fit = min(mrect.w / lv.rw, mrect.h / lv.rh)
        k = fit * 1.5 ** self.zoom
        if ui.hover(mrect) and ui.wheel:
            nz = max(0, min(4, self.zoom + (1 if ui.wheel > 0 else -1)))
            if nz != self.zoom:
                mx, my = ui.mx - mrect.x, ui.my - mrect.y
                bx, by = (mx + self.off[0]) / k, (my + self.off[1]) / k
                self.zoom = nz
                k = fit * 1.5 ** nz
                self.off = [int(bx * k - mx), int(by * k - my)]
            ui.wheel = 0
        mw, mh = int(lv.rw * k), int(lv.rh * k)
        if mw <= mrect.w:
            self.off[0] = -(mrect.w - mw) // 2
        else:
            self.off[0] = max(0, min(mw - mrect.w, self.off[0]))
        if mh <= mrect.h:
            self.off[1] = -(mrect.h - mh) // 2
        else:
            self.off[1] = max(0, min(mh - mrect.h, self.off[1]))
        pygame.draw.rect(app.screen, SEA, mrect)
        hover = None
        if ui.hover(mrect):
            gx, gy = int((ui.mx - mrect.x + self.off[0]) / k), int((ui.my - mrect.y + self.off[1]) / k)
            if 0 <= gx < lv.rw and 0 <= gy < lv.rh:
                gi = lv.grid[gx + gy * lv.rw]
                if gi >= 0:
                    hover = lv.order[gi]
        pal = [SEA] * 256
        for n, rid in enumerate(lv.order):
            if n >= 63:
                break
            c = self.region_color(lv, lv.regions[rid], n)
            if rid == self.sel:
                c = lerp(c, (255, 255, 255), 0.35)
            elif rid == hover:
                c = lerp(c, (255, 255, 255), 0.18)
            pal[n + 1] = c
            pal[n + 65] = lerp(c, (10, 8, 16), 0.55) if rid != self.sel else (255, 255, 255)
            pal[n + 129] = lerp(c, (10, 8, 16), 0.3) if rid != self.sel else (255, 255, 255)
        key = (lv.key, mw)
        sc = self._scaled.get(key)
        if sc is None:
            if len(self._scaled) > 6:
                self._scaled.clear()
            sc = self._scaled[key] = pygame.transform.scale(self.base(lv), (mw, mh))
        sc.set_palette(pal)
        app.screen.set_clip(mrect)
        ox, oy = mrect.x - self.off[0], mrect.y - self.off[1]
        app.screen.blit(sc, (ox, oy))
        # Verbindungen (Fähren, Flugrouten)
        for a, b in lv.links:
            ra, rb = lv.regions[a], lv.regions[b]
            p1 = (ox + (ra.cx + 0.5) * k, oy + (ra.cy + 0.5) * k)
            p2 = (ox + (rb.cx + 0.5) * k, oy + (rb.cy + 0.5) * k)
            if abs(p1[0] - p2[0]) > mw * 0.6:
                continue
            n = max(2, int(((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5 / 9))
            for i in range(0, n, 2):
                q1 = (p1[0] + (p2[0] - p1[0]) * i / n, p1[1] + (p2[1] - p1[1]) * i / n)
                q2 = (p1[0] + (p2[0] - p1[0]) * (i + 1) / n, p1[1] + (p2[1] - p1[1]) * (i + 1) / n)
                pygame.draw.line(app.screen, (150, 170, 200), q1, q2, 1)
        # Beschriftung & Marker
        for rid in lv.order:
            r = lv.regions[rid]
            cx, cy = int(ox + (r.cx + 0.5) * k), int(oy + (r.cy + 0.5) * k)
            big = r.pixels * k * k > 4200
            if big or rid in (self.sel, hover):
                nm = r.name if r.pixels * k * k > 7000 or rid in (self.sel, hover) else r.name[:12]
                surf = ui.render(nm, (250, 246, 236), "s")
                sh = ui.render(nm, (12, 10, 18), "s")
                tx, ty = cx - surf.get_width() // 2, cy - 22
                for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                    app.screen.blit(sh, (tx + dx, ty + dy))
                app.screen.blit(surf, (tx, ty))
            mx = cx - (r.chapter * 9 + (10 if r.hub else 0) + (10 if r.leader else 0) + len(r.campaigns) * 8) // 2
            for c in range(r.chapter):
                pygame.draw.polygon(app.screen, (20, 14, 8), [(mx - 1, cy + 9), (mx + 4, cy - 2), (mx + 9, cy + 9)])
                pygame.draw.polygon(app.screen, GOLD, [(mx + 1, cy + 7), (mx + 4, cy + 1), (mx + 7, cy + 7)])
                mx += 9
            if r.hub or (rid == lv.home and lv.key != "local"):
                pygame.draw.rect(app.screen, (20, 14, 8), (mx, cy, 9, 9))
                pygame.draw.rect(app.screen, (110, 220, 230), (mx + 1, cy + 1, 7, 7))
                mx += 10
            if r.leader:
                pygame.draw.circle(app.screen, (20, 14, 8), (mx + 4, cy + 4), 5)
                pygame.draw.circle(app.screen, (240, 130, 180), (mx + 4, cy + 4), 4)
                mx += 10
            for c in r.campaigns:
                pygame.draw.circle(app.screen, (20, 14, 8), (mx + 3, cy + 4), 4)
                pygame.draw.circle(app.screen, (250, 250, 250), (mx + 3, cy + 4), 3)
                mx += 8
            if rid == lv.home:
                pygame.draw.circle(app.screen, (20, 14, 8), (cx, cy - 4), 5, 2)
                pygame.draw.circle(app.screen, GOLD, (cx, cy - 4), 4, 2)
        app.screen.set_clip(None)
        pygame.draw.rect(app.screen, EDGE, mrect, 1)
        # Interaktion
        if ui.hover(mrect):
            if hover:
                r = lv.regions[hover]
                ui.tip = (f"{r.name}\nAnhänger: {fmt(r.followers)} ({r.share * 100:.2f} %)\nVerdacht: {r.heat:.0f} % · "
                          f"{DATA.campaigns['status'][r.status]}")
            if ui.click and not ui.used:
                ui.used = True
                self.sel, self.picking = hover, False
            b = pygame.mouse.get_pressed()
            if (b[1] or b[2]) and self._drag:
                self.off[0] += self._drag[0] - ui.mx
                self.off[1] += self._drag[1] - ui.my
            self._drag = (ui.mx, ui.my)
        else:
            self._drag = None
        # Legende
        ly = mrect.bottom + 8
        ui.text(mrect.x, ly, next(t for i, _, t in MODES if i == self.mode), DIM)
        ui.text(mrect.x, ly + 18, "Dreieck: Ortsgruppe · Quadrat: Logistik · rosa Punkt: Regionalleitung · weiße Punkte: Kampagnen · "
                "Ring: Heimat · Mausrad: Zoom", DIM)
        self.draw_side(R(W - side - 8, TOP_H + 8, side, H - TOP_H - BOT_H - 16), lv)

    # ------------------------------------------------------------ Seitenleiste
    def draw_side(self, r, lv):
        app = self.app
        ui, w = app.ui, app.w
        st = w.strategic
        ui.panel(r)
        inner = r.inflate(-4, -8)
        off = ui.scroll_area("mapside", inner, self._side_h)
        self._side_h = self.side_content(r, lv, off) + off - r.y + 14
        ui.end_scroll()

    def side_content(self, r, lv, off):
        app = self.app
        ui, w = app.ui, app.w
        st = w.strategic
        x, y, cw = r.x + 12, r.y + 10 - off, r.w - 30
        reg = lv.regions.get(self.sel) if self.sel else None
        if reg is None:
            ui.text(x, y, lv.name, GOLD, "b")
            y += 30
            tot, pop = lv.total(), lv.pop()
            ui.text(x, y, f"Anhänger: {fmt(tot)} von {fmt(pop)}", TEXT)
            y += 20
            ui.text(x, y, f"Anteil: {tot / pop * 100:.3f} %", TEXT)
            y += 28
            y += ui.wrap(x, y, cw, "Region anklicken, um Kampagnen zu starten, Ortsgruppen zu gründen oder Mitglieder als "
                         "Regionalleitung zu entsenden.", DIM) + 12
            if st.phase < st.max_phase():
                nxt = ("", "Landesverband gründen", "Weltweite Dachorganisation gründen")[st.phase]
                ui.text(x, y, "Nächste Stufe: " + nxt, GOLD, "m")
                y += 26
                reqs = st.advance_req()
                for text, ok in reqs:
                    ui.text(x, y, ("[x] " if ok else "[  ] ") + text, GOOD if ok else DIM)
                    y += 19
                y += 6
                cost = "Kostet 2.000 € und 20 EP" if st.phase == 1 else "Kostet 3 Mio. € und 100 EP"
                if ui.button(R(x, y, cw, 36), nxt, cost, enabled=all(ok for _, ok in reqs), font="m"):
                    st.advance()
                    self.level = LEVELS[st.phase - 1]
                    self.sel, self.zoom = None, 0
                y += 48
            elif st.phase == 3:
                ui.text(x, y, f"Weltanteil: {st.world_share() * 100:.2f} %  (Ziel 5 %)", GOLD, "m")
                y += 24
                y += ui.wrap(x, y, cw, "Ab 5 % kann im Lehre-Menü (F2) die Anerkennung als Weltreligion beantragt werden.", DIM) + 10
            if st.phase >= 3:
                ui.text(x, y, "Übersetzte Sprachen", TEXT, "m")
                y += 24
                names = [lv.languages.get(l, l) for l in sorted(st.languages)] + [lv.languages.get(l, l) + " (in Arbeit)" for l in st.translating]
                y += ui.wrap(x, y, cw, ", ".join(names), DIM) + 10
            ui.text(x, y, "Größte Gemeinden", TEXT, "m")
            y += 24
            for rg in sorted(lv.regions.values(), key=lambda q: -q.followers)[:10]:
                if ui.button(R(x, y, cw, 22), "", None):
                    self.sel = rg.id
                ui.text(x + 6, y + 3, rg.name[:24], TEXT)
                ui.text(x + cw - 6, y + 3, fmt(rg.followers), DIM, right=True)
                y += 24
            return y
        # --- gewählte Region
        if ui.button(R(r.right - 36, y - 4, 24, 24), "x"):
            self.sel, self.picking = None, False
            return y
        ui.text(x, y, reg.name[:26], GOLD, "b")
        y += 28
        if self.picking:
            return self.draw_pick(r, lv, reg, x, y, cw)
        q = reg.quirk
        if q.get("name"):
            ui.text(x, y, q["name"], PURPLE)
            y += 19
            y += ui.wrap(x, y, cw, q["text"], DIM) + 2
            qm = " · ".join(f"{ {'growth': 'Wachstum', 'income': 'Spenden', 'heat': 'Verdacht', 'cost': 'Kosten', 'legal': 'Rechtsweg'}.get(k, k)} ×{v:g}"
                            for k, v in q.get("mods", {}).items())
            if qm:
                ui.text(x, y, qm, WARN)
                y += 20
        y += 4
        ui.text(x, y, f"Einwohner {fmt(reg.pop)}", DIM)
        ui.text(x + cw, y, f"Sprache: {lv.languages.get(reg.lang, reg.lang)}" + ("" if st.lang_ok(reg) else " (!)"),
                DIM if st.lang_ok(reg) else BAD, right=True)
        y += 20
        ui.text(x, y, f"Anhänger {fmt(reg.followers)}", TEXT, "m")
        ui.text(x + cw, y + 1, f"{reg.delta:+,.0f}/Tag".replace(",", "."), GOOD if reg.delta >= 0 else BAD, right=True)
        y += 23
        ui.bar(R(x, y, cw, 14), (reg.share / 0.10) ** 0.5, PURPLE, f"{reg.share * 100:.2f} % der Bevölkerung")
        y += 20
        stat = DATA.campaigns["status"][reg.status]
        ui.bar(R(x, y, cw, 14), reg.heat / 100, BAD if reg.heat > 55 else WARN if reg.heat > 35 else GOOD, f"Verdacht {reg.heat:.0f} % · {stat}")
        ui.tooltip(R(x, y, cw, 14), "35 %: Presse · 55 %: Auflagen (alles teurer) · 75 %: Verbotsverfahren (12 Tage) → Verbot.\n"
                   f"Staat {reg.state * 100:.0f} · Presse {reg.press * 100:.0f} · Militär {reg.military * 100:.0f}")
        y += 20
        ui.bar(R(x, y, cw, 14), reg.aware / 100, (110, 160, 230), f"Bekanntheit {reg.aware:.0f} %")
        y += 22
        af = st.affinity_factor(reg)
        ui.text(x, y, "Lehre kommt hier " + ("hervorragend an" if af > 1.25 else "gut an" if af > 1.05 else "mäßig an" if af > 0.85 else "schlecht an")
                + f" (×{af:.2f})", GOOD if af > 1.05 else WARN if af > 0.85 else BAD)
        ui.tooltip(R(x, y, cw, 18), "Vorlieben der Region: " + ", ".join(f"{AX_SHORT[a]} {v:+.1f}" for a, v in reg.affinity.items())
                   + "\nPasst die Lehre (F2) dazu, wachsen Anhängerzahl und Obergrenze.")
        y += 20
        if lv.key != "local":
            sup = st.supply_factor(lv, reg)
            ui.text(x, y, f"Versorgung: {reg.hops} Etappen zum Logistikzentrum (×{sup:.2f})", GOOD if sup >= 1 else WARN)
            y += 20
        if reg.aggregate:
            y += 8
            return y + ui.wrap(x, y, cw, "Das Heimatland wird über die Landeskarte gesteuert. Die Werte hier sind die Summe aller Landesteile.", DIM)
        if not st.lang_ok(reg):
            a = DATA.campaigns["actions"]["translate"]
            block = st.action_block(lv, reg, "translate")
            if ui.button(R(x, y, cw, 28), f"Schriften übersetzen ({fmt(a['cost'])} €, {a['ep']} EP)", a["text"] + (f"\n{block}" if block else ""), enabled=not block):
                st.do_action(lv, reg, "translate")
            y += 34
        # Ortsgruppe
        chs = DATA.campaigns["chapters"]
        y += 4
        ui.text(x, y, f"Ortsgruppe: {chs[reg.chapter]['name']}", TEXT, "m")
        y += 23
        if reg.chapter < len(chs) - 1:
            nx = chs[reg.chapter + 1]
            block = st.chapter_block(lv, reg)
            if ui.button(R(x, y, cw, 28), f"{nx['name']} ({fmt(st.cost(reg, nx['cost']))} €)",
                         nx.get("text", "") + f"\nMehr Wachstum, höhere Obergrenze, +1 Kampagne. Unterhalt {fmt(nx['upkeep'] * reg.scale)} €/Tag."
                         + (f"\n{block}" if block else ""), enabled=not block):
                st.build_chapter(lv, reg)
            y += 32
        lead = st.leader_of(reg)
        if ui.button(R(x, y, cw, 28), f"Leitung: {lead.name} (Bindung {lead.bond:.0f})" if lead else "Regionalleitung entsenden …",
                     "Ein Mitglied (ab Rang Eingeweihter) leitet die Mission: Predigen-Wert beschleunigt das Wachstum.\n"
                     "Achtung: Fern vom Guru sinkt die Bindung – fällt sie zu tief, macht sich die Leitung selbstständig."):
            if lead:
                st.recall_leader(reg)
            else:
                self.picking = True
        y += 36
        # Kampagnen
        ui.text(x, y, f"Kampagnen ({len(reg.campaigns)}/{2 + reg.chapter})", TEXT, "m")
        y += 23
        for cid, c in DATA.campaigns["campaigns"].items():
            if c["phase"] > st.phase:
                continue
            running = reg.campaigns.get(cid)
            block = st.campaign_block(lv, reg, cid)
            tip = (f"{c['text']}\nWirkung {c['power']:g} · Verdacht +{c['heat']} · {c['days']} Tage"
                   + (f" · {c['tracts']} Traktate/Tag" if c["tracts"] and lv.key == "local" else "") + (f"\n{block}" if block and not running else ""))
            if ui.button(R(x, y, cw, 25), "", tip, enabled=not block, active=bool(running)):
                st.start_campaign(lv, reg, cid)
            ui.text(x + 8, y + 4, c["name"][:30], TEXT if not block or running else DIM)
            ui.text(x + cw - 8, y + 4, f"noch {running} T." if running else f"{fmt(st.cost(reg, c['cost']))} €",
                    GOOD if running else GOLD if not block else DIM, right=True)
            y += 27
        y += 6
        bw = (cw - 8) // 3
        n = 0
        for aid in ("pr", "lobby", "hub"):
            a = DATA.campaigns["actions"][aid]
            if a["phase"] > st.phase or (aid == "hub" and lv.key == "local"):
                continue
            block = st.action_block(lv, reg, aid)
            lab = {"pr": "PR", "lobby": "Lobby", "hub": "Logistik"}[aid]
            if ui.button(R(x + n * (bw + 4), y, bw, 40), "", f"{a['name']} – {fmt(st.cost(reg, a['cost']))} €\n{a['text']}" + (f"\n{block}" if block else ""),
                         enabled=not block):
                st.do_action(lv, reg, aid)
            ui.text(x + n * (bw + 4) + bw // 2, y + 3, lab, TEXT if not block else DIM, center=True)
            ui.text(x + n * (bw + 4) + bw // 2, y + 21, f"{fmt(st.cost(reg, a['cost']))} €", GOLD if not block else DIM, center=True)
            n += 1
        return y + 44

    def draw_pick(self, r, lv, reg, x, y, cw):
        app = self.app
        ui, w = app.ui, app.w
        ui.text(x, y, "Wer soll die Mission leiten?", TEXT, "m")
        y += 26
        cands = [m for m in w.members(True) if m.kind == "member" and m.rank >= 1]
        if not cands:
            y += ui.wrap(x, y, cw, "Kein geeignetes Mitglied anwesend. Befördere jemanden mindestens zum »Eingeweihten« "
                         "(Mitglied anklicken → Befördern).", WARN) + 8
        for m in sorted(cands, key=lambda m: -m.skills["preach"])[:14]:
            if ui.button(R(x, y, cw, 30), "", f"{m.rank_name} · {m.role_name}\nGlaube {m.faith:.0f} · Bindung {m.bond:.0f}"):
                w.strategic.assign_leader(lv, reg, m)
                self.picking = False
                if app.sel == ("pawn", m.id):
                    app.sel = None
            ui.text(x + 8, y + 6, m.name[:22], TEXT)
            ui.text(x + cw - 8, y + 6, f"Predigen {m.skills['preach']:.0f} · Bindung {m.bond:.0f}", GOOD if m.bond > 50 else WARN, right=True)
            y += 32
        if ui.button(R(x, y + 6, 120, 28), "Abbrechen"):
            self.picking = False
        return y + 40
