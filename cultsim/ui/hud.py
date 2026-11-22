"""HUD und Panels: Leisten, Baumenü, Inspektor, Mitglieder, Lehre, Finanzen, Ereignis-Popups, Menüs."""
from __future__ import annotations

import pygame

from ..config import *
from ..data import DATA
from ..sim import events
from ..sim.pawns import MEMBER_KINDS, KIND_NAMES
from ..sim.strategic import fmt
from .widgets import *

R = pygame.Rect
TOP_H, BOT_H = 36, 46
CATS = ("Struktur", "Boden", "Möbel", "Kult")
MOD_NAMES = {"tithe": "Abgaben", "convert": "Bekehrung", "work": "Arbeitstempo", "faith_gain": "Glaubensgewinn",
             "faith_decay": "Glaubensverfall", "food_use": "Nahrungsbedarf", "flee": "Fluchtneigung",
             "heat_gain": "Verdachtszuwachs", "growth": "Anhängerwachstum", "income": "Spenden",
             "visitor_rate": "Besucherstrom", "guard": "Wächter-Sichtweite"}
ADD_NAMES = {"mood": "Laune", "heat_daily": "Verdacht/Tag", "evidence_daily": "Beweise/Tag", "course_income": "€/Tag je Rangstufe"}
AX_SHORT = {"commerce": "Geschäftssinn", "isolation": "Abschottung", "apocalypse": "Endzeit"}


def effects_text(d):
    out = []
    for k, v in d.get("mods", {}).items():
        out.append(f"{MOD_NAMES.get(k, k)} ×{v:g}")
    for k, v in d.get("adds", {}).items():
        out.append(f"{ADD_NAMES.get(k, k)} {v:+g}")
    for k, v in d.get("doctrine", {}).items():
        out.append(f"{AX_SHORT.get(k, k)} {v:+g}")
    return " · ".join(out)


# ---------------------------------------------------------------- Leisten
def draw_top(app):
    ui, w, a = app.ui, app.w, app.assets
    W = app.screen.get_width()
    ui.panel(R(0, 0, W, TOP_H), alpha=250, edge=None)
    pygame.draw.line(app.screen, EDGE, (0, TOP_H), (W, TOP_H))
    x = 10
    x += ui.text(x, 8, w.cult_name if W >= 1500 or len(w.cult_name) < 22 else w.cult_name[:20] + "…", GOLD, "m") + 16
    ui.tooltip(R(0, 0, x, TOP_H), f"{w.cult_name}\nGuru: {w.guru_name}\nAusrichtung: {w.archetype_def()['name']}")
    st = w.strategic
    mem = [m for m in w.members() if m.kind == "member"]
    net = sum(w.ledger_last.values())

    def stat(icon, txt, tip, col=TEXT):
        nonlocal x
        ic = a.icon(icon)
        app.screen.blit(ic, (x, 10))
        wd = ui.text(x + 20, 9, txt, col, "m")
        ui.tooltip(R(x, 2, wd + 24, TOP_H - 4), tip)
        x += wd + 34

    stat("icon_money", fmt(w.money) + " €", f"Geld. Bilanz gestern: {net:+,.0f} €\nDetails: Finanzen (F3)".replace(",", "."),
         BAD if w.money < 100 else TEXT)
    stat("icon_food", f"{w.food:.0f}/{w.storage_cap}", "Rohkost / Lagerkapazität. Wächst auf Anbaufeldern, wird am Herd zu Mahlzeiten.\n"
         "Mehr Lager: Vorratskisten bauen.", BAD if w.food < 5 else TEXT)
    stat("icon_meal", f"{w.meals:.0f}", "Fertige Mahlzeiten (Eintopf). Ein Koch braucht eine Feuerstelle oder einen Herd.",
         BAD if w.meals < 2 else TEXT)
    stat("icon_ep", f"{w.ep:.0f}", "Erleuchtung: entsteht bei Predigten und durch Anhänger. Bezahlt Regeln, Beförderungen, Expansion.", PURPLE)
    stat("icon_tracts", f"{w.tracts:.0f}", "Traktate: Schreiber drucken sie an der Druckerpresse. Werbekampagnen in der Stadt verbrauchen sie.")
    beds = w.count_use("bed")
    stat("icon_members", f"{len(mem)}", f"Mitglieder: {len(mem)} · Betten: {beds}\nOhne freies Bett lassen sich Besucher kaum bekehren.",
         WARN if beds <= len(mem) else TEXT)
    stat("icon_faith", fmt(st.total_followers()), "Anhänger außerhalb des Geländes (Kartenmodus: M). Sie spenden täglich.")
    # rechts: Zeit & Tempo
    rx = W - 8
    for sp, lab, tip in ((4, ">>>", "Sehr schnell (3)"), (2, ">>", "Schnell (2)"), (1, ">", "Normal (1)"), (0, "II", "Pause (Leertaste)")):
        rx -= 34
        if ui.button(R(rx, 5, 32, 26), lab, tip, active=app.speed == sp):
            app.speed = sp
    rx -= 10
    rx -= ui.text(rx, 9, w.clock(), TEXT, "m", right=True) + 16
    # Verdacht & Beweise
    bw = 96
    if x + 62 + bw < rx:
        ui.text(x, 10, "Verdacht", DIM, "s")
        ui.bar(R(x + 62, 10, bw, 16), w.heat / 100, BAD if w.heat > 65 else WARN if w.heat > 35 else GOOD, f"{w.heat:.0f} %")
        ui.tooltip(R(x, 2, bw + 62, TOP_H - 4), "Verdacht der Behörden gegen das Gelände.\nAb 25 % kommen Journalisten, ab 45 % Kontrollen, "
                   "ab 85 % droht eine Razzia.\nSenken: PR-Offensive (Karte), Anwälte (Finanzen), harmlose Lehre, Zeit.")
        x += bw + 74
    if x + 58 + 70 < rx:
        ui.text(x, 10, "Beweise", DIM, "s")
        ui.bar(R(x + 58, 10, 70, 16), w.evidence / 100, BAD if w.evidence > 60 else WARN, f"{w.evidence:.0f} %")
        ui.tooltip(R(x, 2, 130, TOP_H - 4), "Beweislage gegen den Guru. Entscheidet bei einer Razzia: unter 70 % kommt er wieder frei.\n"
                   "Quellen: Aussteiger, Enthüllungsartikel, Maulwürfe, Plaudertaschen.")
        x += 140
    ph = ("Phase 1: Stadt", "Phase 2: Land", "Phase 3: Welt")[w.phase - 1]
    if x + 110 < rx:
        ui.text(rx, 10, ph, GOLD, "s", right=True)


def draw_bottom(app):
    ui = app.ui
    W, H = app.screen.get_size()
    y = H - BOT_H
    ui.panel(R(0, y, W, BOT_H), alpha=250, edge=None)
    pygame.draw.line(app.screen, EDGE, (0, y), (W, y))
    x = 8
    v = app.view

    def btn(label, tip, active=False, w=92):
        nonlocal x
        r = ui.button(R(x, y + 7, w, 32), label, tip, active=active, font="m")
        x += w + 5
        return r

    if btn("Bauen", "Baumenü (B)", app.menu == "build"):
        app.toggle_menu("build")
    if btn("Zonen", "Zonen und Bereiche malen (Z)", app.menu == "zone"):
        app.toggle_menu("zone")
    if btn("Abriss", "Abreißen / Aufträge abbrechen (X)", app.tool == ("demolish",)):
        app.set_tool(None if app.tool == ("demolish",) else ("demolish",))
    x += 14
    if btn("Mitglieder", "Mitgliederliste (F1)", app.panel == "members", 110):
        app.toggle_panel("members")
    if btn("Lehre", "Lehre, Regeln, Ränge (F2)", app.panel == "doctrine"):
        app.toggle_panel("doctrine")
    if btn("Finanzen", "Einnahmen, Ausgaben, Einkauf, Anwälte (F3)", app.panel == "finance"):
        app.toggle_panel("finance")
    if btn("KARTE", "Kartenmodus: Stadt, Land, Welt (M)", app.panel == "map", 100):
        app.toggle_panel("map")
    x += 14
    if btn("Räume", "Räume und Gehege einfärben (R)", v.show_rooms, 80):
        v.show_rooms = not v.show_rooms
    if btn("Wände", "Wände niedrig darstellen (H)", v.low_walls, 80):
        v.low_walls = not v.low_walls
    if btn("<", "Ansicht drehen (Q)", w=34):
        v.rotate(-1)
    if btn(">", "Ansicht drehen (E)", w=34):
        v.rotate(1)
    if ui.button(R(W - 178, y + 7, 80, 32), "Hilfe", "Steuerung anzeigen (F10)", font="m", active=app.panel == "help"):
        app.toggle_panel("help")
    if ui.button(R(W - 92, y + 7, 84, 32), "Menü", "Speichern, Laden, Beenden (Esc)", font="m"):
        app.toggle_panel("pause")


def sprite_icon(app, did):
    d = DATA.buildables[did]
    sid = {"fence": "fence_post", "gate": "gate_post", "animal": "goat"}.get(d["kind"], d["sprite"])
    s = app.assets.get(sid)[0]
    if s.get_height() > 34:
        key = ("ic", sid)
        c = app.assets._cache.get(key)
        if c is None:
            f = 34 / s.get_height()
            c = app.assets._cache[key] = pygame.transform.scale(s, (int(s.get_width() * f), 34))
        s = c
    return s


def draw_build_menu(app):
    ui, w = app.ui, app.w
    W, H = app.screen.get_size()
    if app.menu == "zone":
        r = ui.panel(R(8, H - BOT_H - 58, 560, 52))
        x = r.x + 8
        for z, (name, col, tip) in ZONES.items():
            if ui.button(R(x, r.y + 8, 150, 36), name, tip + "\nZiehen, um ein Rechteck zu malen.", active=app.tool == ("zone", z), color=col, font="m"):
                app.set_tool(("zone", z))
            x += 156
        if ui.button(R(x, r.y + 8, 76, 36), "Löschen", "Zone entfernen", active=app.tool == ("zone", 0), font="m"):
            app.set_tool(("zone", 0))
        return
    items = [(k, d) for k, d in DATA.buildables.items() if d["cat"] == app.build_cat and not d.get("hidden")]
    cols = 5
    bw, bh = 196, 44
    rows = (len(items) + cols - 1) // cols
    ph = 46 + rows * (bh + 4) + 6
    r = ui.panel(R(8, H - BOT_H - ph - 6, cols * (bw + 4) + 12, ph))
    x = r.x + 8
    for c in CATS:
        if ui.button(R(x, r.y + 8, 110, 30), c, active=app.build_cat == c, font="m"):
            app.build_cat = c
        x += 116
    for n, (k, d) in enumerate(items):
        bx = r.x + 8 + (n % cols) * (bw + 4)
        by = r.y + 46 + (n // cols) * (bh + 4)
        tip = f"{d['name']} – {d['cost']} €\n{d.get('desc', '')}"
        if d.get("pracht"):
            tip += f"\nPracht +{d['pracht']:g}"
        if d.get("doctrine"):
            tip += "\nLehre: " + ", ".join(f"{AX_SHORT[a]} {v:+g}" for a, v in d["doctrine"].items())
        rr = R(bx, by, bw, bh)
        if ui.button(rr, "", tip, active=app.tool == ("build", k)):
            app.set_tool(("build", k))
        ic = sprite_icon(app, k)
        app.screen.blit(ic, (bx + 22 - ic.get_width() // 2, by + bh // 2 - ic.get_height() // 2))
        ui.text(bx + 44, by + 5, d["name"][:22], TEXT, "s")
        ui.text(bx + 44, by + 23, f"{d['cost']} €", GOLD if w.money >= d["cost"] else BAD, "s")


def draw_notes(app):
    ui, w = app.ui, app.w
    now = w.tick_n
    notes = [n for n in w.notes if now - n["t"] < 1400][-7:]
    y = TOP_H + 8
    for n in notes:
        col = KIND_COL.get(n["kind"], TEXT)
        surf = ui.render(n["text"][:110], col, "s")
        r = R(8, y, surf.get_width() + 14, 22)
        s = pygame.Surface(r.size, pygame.SRCALPHA)
        s.fill((14, 11, 20, 190))
        app.screen.blit(s, r)
        app.screen.blit(surf, (r.x + 7, r.y + 3))
        if n.get("pos") or n.get("pid"):
            ui.rects.append(r)
            if ui.hover(r):
                pygame.draw.rect(app.screen, col, r, 1)
                if ui.click and not ui.used:
                    ui.used = True
                    p = w.pawn_ids.get(n.get("pid"))
                    if p is not None and not p.away:
                        app.select(("pawn", p.id))
                        app.view.cx, app.view.cy = p.x, p.y
                    elif n.get("pos"):
                        app.view.cx, app.view.cy = n["pos"]
        y += 24


# ---------------------------------------------------------------- Inspektor
def draw_inspector(app):
    sel = app.sel
    if sel is None:
        return
    ui, w = app.ui, app.w
    W, H = app.screen.get_size()
    pw = 318
    r = R(W - pw - 8, TOP_H + 8, pw, H - TOP_H - BOT_H - 16)
    x, y, cw = r.x + 12, r.y + 10, pw - 24
    if sel[0] == "pawn":
        p = w.pawn_ids.get(sel[1])
        if p is None:
            app.sel = None
            return
        ui.panel(r)
        if ui.button(R(r.right - 30, r.y + 6, 24, 24), "x"):
            app.sel = None
        draw_pawn(app, p, x, y, cw, r)
        return
    S = w.size
    tx, ty = (sel[1], sel[2]) if sel[0] == "tile" else (None, None)
    th = w.thing_ids.get(sel[1]) if sel[0] == "thing" else None
    if sel[0] == "thing" and th is None:
        app.sel = None
        return
    if th is not None:
        tx, ty = th.x, th.y
    r.h = 300
    ui.panel(r)
    if ui.button(R(r.right - 30, r.y + 6, 24, 24), "x"):
        app.sel = None
    i = tx + ty * S
    if th is not None:
        d = th.defn
        ui.text(x, y, d["name"] + ("" if th.built else " (Bauauftrag)"), GOLD, "b")
        y += 30
        y += ui.wrap(x, y, cw, d.get("desc", ""), DIM) + 6
        if not th.built:
            ui.bar(R(x, y, cw, 14), th.progress, GOOD)
            y += 22
        if th.owner:
            o = w.pawn_ids.get(th.owner)
            ui.text(x, y, f"Schlafplatz von: {o.name if o else '–'}", TEXT)
            y += 20
        lab = "Entfernen" if d["kind"] == "nature" else "Auftrag abbrechen" if not th.built else f"Abreißen (+{int(d['cost'] * 0.3)} €)"
        if ui.button(R(x, y, 170, 28), lab):
            w.remove(tx, ty)
            app.sel = None
        y += 36
    else:
        ui.text(x, y, TERRAIN_NAMES[w.terrain[i]], GOLD, "b")
        y += 30
        if w.floor[i]:
            ui.text(x, y, "Boden: " + DATA.buildables[w.floor[i]]["name"], TEXT)
            y += 20
    z = w.zone[i]
    if z:
        ui.text(x, y, "Zone: " + ZONES[z][0], ZONES[z][1])
        y += 20
        if z == Z_FIELD:
            g = w.crops.get(i)
            ui.text(x, y, "Brach – wartet auf Aussaat" if g is None else f"Wachstum: {g * 100:.0f} %", DIM)
            y += 20
    room = w.room_at(tx, ty)
    if room is not None:
        y += 6
        ui.text(x, y, f"{room.role}", GOLD, "m")
        y += 22
        ui.text(x, y, f"{'Raum (überdacht)' if room.kind == 'raum' else 'Gehege / Hof (umzäunt)'} · {room.size} Felder", TEXT)
        y += 20
        ui.text(x, y, f"Pracht: {room.pracht:.0f} ({room.pracht_text})", TEXT)
        ui.tooltip(R(x, y, cw, 18), "Pracht entsteht durch Böden, Deko und Größe.\nSchöne Tempel verstärken Predigten, schöne Schlafsäle heben die Laune.")
        y += 20
    else:
        ui.text(x, y, "Im Freien", DIM)


def draw_pawn(app, p, x, y, cw, r):
    ui, w = app.ui, app.w
    member = p.kind in MEMBER_KINDS
    ui.text(x, y, p.name[:24], GOLD, "b")
    if p.kind == "member":
        if ui.button(R(r.right - 60, r.y + 6, 24, 24), "*", "Als Favorit markieren (Name wird im Spiel eingeblendet)", active=p.favorite,
                     color=GOLD if p.favorite else DIM):
            p.favorite = not p.favorite
    y += 28
    if member:
        ui.text(x, y, f"{p.rank_name} · {p.role_name} · {p.age} J.", TEXT)
        y += 19
        ui.text(x, y, f"Früher: {p.former_job}"[:44], DIM)
        y += 19
        y += ui.wrap(x, y, cw, p.bio, DIM) + 4
    else:
        ui.text(x, y, KIND_NAMES.get(p.kind, p.kind), TEXT)
        y += 22
    ui.text(x, y, p.status_text(w), WARN if p.fleeing else GOOD)
    y += 24
    if p.kind == "goat":
        ui.wrap(x, y, cw, "Gibt täglich Milch (+2,5 Nahrung) und hebt den Glauben. Braucht ein Gehege aus Zaun und Tor, sonst läuft sie weg.", DIM)
        return

    def bar(label, v, col, tip):
        nonlocal y
        ui.text(x, y, label, DIM)
        ui.bar(R(x + 82, y + 1, cw - 82, 14), v / 100, col, f"{v:.0f}")
        ui.tooltip(R(x, y, cw, 16), tip)
        y += 20

    if member:
        if p.kind == "member":
            bar("Glaube", p.faith, PURPLE, "Unter 25 beginnt das Mitglied zu zweifeln. Steigt durch Predigten, Meditation, Zuwendung.")
            bar("Bindung", p.bond, (230, 120, 170), "Persönliche Bindung an den Guru (Einzelgespräche, Geschenke, Beförderung).\n"
                "Hohe Bindung verhindert Flucht und Abspaltung – wichtig für Regionalleiter und Nachfolger.")
        bar("Laune", p.mood, GOOD if p.mood > 45 else WARN if p.mood > 30 else BAD, "Ergibt sich aus den Gedanken unten. Miese Laune frisst den Glauben.")
        bar("Sättigung", p.food, (220, 160, 80), "Hunger macht unglücklich und irgendwann sehr abwesend.")
        bar("Energie", p.rest, (110, 160, 230), "Schlaf im Bett erholt am besten.")
        y += 2
        tx = x
        for t in p.visible_traits():
            td = DATA.traits[t]
            wd = ui.render(td["name"], TEXT, "s").get_width() + 12
            if tx + wd > x + cw:
                tx = x
                y += 24
            rr = R(tx, y, wd, 21)
            pygame.draw.rect(app.screen, BG3, rr, border_radius=9)
            ui.text(tx + 6, y + 2, td["name"], TEXT)
            ui.tooltip(rr, td["desc"])
            tx += wd + 5
        y += 27
        ui.text(x, y, "  ".join(f"{SKILLS[k][:4]} {p.skills[k]:.0f}" for k in SKILLS), DIM)
        ui.tooltip(R(x, y, cw, 16), "Fähigkeiten (0–10): " + ", ".join(SKILLS.values()) + ". Wachsen durch Übung.")
        y += 22
        ths = sorted(p.thoughts.values(), key=lambda t: t[1])[:5]
        for text, val, _ in ths:
            ui.text(x, y, text[:38], DIM)
            ui.text(x + cw, y, f"{val:+.0f}", GOOD if val > 0 else BAD, right=True)
            y += 17
        if p.kind == "member":
            y += 2
            ui.text(x, y, f"Privatvermögen: {fmt(p.wealth)} €   ·   dabei seit Tag {p.joined}", DIM)
            y += 22
    else:
        if p.kind == "visitor":
            bar("Interesse", p.interest, PURPLE, "Je höher, desto leichter lässt sich der Besucher bekehren.")
        elif p.kind == "journalist":
            ev = p.evidence
            ui.text(x, y, "Notizblock: " + ("leer" if ev < 2 else "ein paar Zeilen" if ev < 6 else "gut gefüllt" if ev < 12 else "BRISANT"),
                    GOOD if ev < 6 else BAD)
            y += 22
    # ---- Aktionen
    g = w.guru
    bw = (cw - 6) // 2

    def act(n, label, tip, enabled=True):
        return ui.button(R(x + (n % 2) * (bw + 6), y + (n // 2) * 32, bw, 28), label, tip, enabled)

    if p.kind == "member" and not p.away:
        ui.text(x, y, "Aufgabe:", DIM)
        y += 19
        rw6 = (cw - 10) // 3
        for n, (rk, rn) in enumerate(ROLES.items()):
            if ui.button(R(x + (n % 3) * (rw6 + 5), y + (n // 3) * 28, rw6, 25), rn, ROLE_DESC[rk] + f"\nFähigkeit: {SKILLS[ROLE_SKILL[rk]]} {p.skills[ROLE_SKILL[rk]]:.0f}",
                         active=p.role == rk):
                p.role = rk
                p.cancel_job(w)
        y += 62
        ranks = DATA.doctrine["ranks"]
        if act(0, "Einzelgespräch", "Der Guru nimmt sich Zeit: Bindung und Glaube steigen.", g is not None and not g.away):
            g.orders.append(("bond", p.id))
        nxt = ranks[p.rank + 1] if p.rank + 1 < len(ranks) else None
        if act(1, f"Befördern ({nxt['cost']} EP)" if nxt else "Höchster Rang", f"Aufstieg zum {nxt['name']}: +Bindung, +Glaube, +Laune." if nxt else "",
               nxt is not None and w.ep >= nxt["cost"]):
            p.promote(w)
        if act(2, "Geschenk (50 €)", "Ein signiertes Guru-Porträt. Bindung +6.", w.money >= 50):
            p.gift(w)
        if act(3, "Folgen" if app.follow != p.id else "Nicht folgen", "Kamera folgt der Figur."):
            app.follow = None if app.follow == p.id else p.id
        cf = app.confirm == ("exile", p.id)
        if act(4, "Wirklich verstoßen?" if cf else "Verstoßen", "Wirft das Mitglied hinaus. Es wird draußen reden."):
            if cf:
                w.defect(p, "wurde verstoßen")
                app.sel = None
                app.confirm = None
                return
            app.confirm = ("exile", p.id)
        y += 100
    elif p.kind == "member" and p.away_kind == "post":
        post = w.strategic.find_post(p.id)
        if post:
            ui.text(x, y, f"Leitet: {post[1].name}", TEXT)
            y += 22
            if act(0, "Zurückrufen", "Kehrt aufs Gelände zurück."):
                w.strategic.recall_leader(post[1])
        y += 36
    elif p.kind == "guru":
        y += ui.wrap(x, y, cw, "Rechtsklick auf den Boden: Guru dorthin schicken. Er predigt, bekehrt Besucher und führt Einzelgespräche.", DIM) + 6
        gp = w.flags.get("guru_preaches", True)
        if act(0, "Predigt: selbst" if gp else "Predigt: Prediger", "Wer hält die Andacht? Der Guru predigt am besten, hat dann aber weniger Zeit."):
            w.flags["guru_preaches"] = not gp
        if act(1, "Folgen" if app.follow != p.id else "Nicht folgen", "Kamera folgt der Figur."):
            app.follow = None if app.follow == p.id else p.id
        y += 36
    elif p.kind in ("visitor", "journalist", "relative"):
        n = 0
        if p.kind == "visitor":
            if act(n, "Guru spricht an", "Der Guru persönlich versucht die Bekehrung.", g is not None and not g.away and p.engaged is None):
                g.orders.append(("convert", p.id))
            n += 1
        if p.kind == "journalist":
            if act(n, "Interview geben", "Der Guru versucht, den Journalisten einzuwickeln. Klappt es, wird der Bericht positiv.",
                   g is not None and not g.away and p.engaged is None):
                g.orders.append(("interview", p.id))
            n += 1
            if act(n, "Bestechen (300 €)", "Notizblock gegen Umschlag. 15 % Risiko, dass es auffliegt.", w.money >= 300 and not p.charmed):
                w.spend("Bestechung", 300)
                if w.rng.random() < 0.15:
                    w.add_heat(10)
                    w.notify("Bestechungsversuch aufgeflogen! Das wird eine Schlagzeile.", "bad")
                else:
                    p.evidence, p.charmed = 0.0, True
                    w.notify("Der Journalist steckt den Umschlag ein und den Notizblock weg.", "good")
            n += 1
        guards = any(m.role == "guard" for m in w.members(True) if m.kind == "member")
        if act(n, "Hinauswerfen", "Ein Wächter begleitet die Person vom Gelände." + ("" if guards else "\n(Kein Wächter eingeteilt!)"),
               guards and not p.expelled):
            p.expelled = True
        y += 70
    if member and p.journal:
        y += 4
        ui.text(x, y, "Chronik", DIM)
        y += 18
        for day, text in p.journal[-4:]:
            if y > r.bottom - 22:
                break
            ui.text(x, y, f"T{day}: {text}"[:46], DIM)
            y += 17


# ---------------------------------------------------------------- Panels
def panel_rect(app, pw=1000, ph=580):
    W, H = app.screen.get_size()
    pw, ph = min(pw, W - 20), min(ph, H - TOP_H - BOT_H - 16)
    return R((W - pw) // 2, TOP_H + 8 + (H - TOP_H - BOT_H - 16 - ph) // 2, pw, ph)


def close_btn(app, r):
    if app.ui.button(R(r.right - 34, r.y + 8, 26, 26), "x", "Schließen (Esc)"):
        app.panel = None


def draw_members(app):
    ui, w = app.ui, app.w
    r = ui.panel(panel_rect(app), "Mitglieder")
    close_btn(app, r)
    mem = sorted(w.members(), key=lambda m: (m.kind != "guru", -m.rank, m.name))
    cols = [(14, "Name"), (236, "Rang"), (350, "Aufgabe"), (450, "Glaube"), (540, "Bindung"), (630, "Laune"), (720, "Zustand")]
    for cx, cn in cols:
        ui.text(r.x + cx, r.y + 44, cn, DIM)
    area = R(r.x + 6, r.y + 66, r.w - 12, r.h - 104)
    off = ui.scroll_area("members", area, len(mem) * 26)
    roles = list(ROLES)
    for n, m in enumerate(mem):
        y = area.y + n * 26 - off
        if y < area.y - 26 or y > area.bottom:
            continue
        row = R(area.x, y, area.w - 8, 24)
        if ui.hover(row):
            pygame.draw.rect(app.screen, BG2, row, border_radius=3)
        x = r.x
        name = ("* " if m.favorite else "") + m.name[:24]
        col = GOLD if m.kind == "guru" else BAD if m.doubter else TEXT
        if ui.button(R(x + 10, y + 1, 218, 22), name, "Auswählen und Kamera zentrieren", color=col, align="left"):
            app.panel = None
            app.select(("pawn", m.id))
            if not m.away:
                app.view.cx, app.view.cy = m.x, m.y
        ui.text(x + 236, y + 4, m.rank_name, TEXT)
        if m.kind == "member":
            if ui.button(R(x + 346, y + 1, 96, 22), m.role_name, "Klick: nächste Aufgabe · Rechtsklick-Alternative: im Inspektor wählen",
                         enabled=not m.away):
                m.role = roles[(roles.index(m.role) + 1) % len(roles)]
                m.cancel_job(w)
            ui.bar(R(x + 450, y + 5, 80, 13), m.faith / 100, PURPLE)
            ui.bar(R(x + 540, y + 5, 80, 13), m.bond / 100, (230, 120, 170))
        ui.bar(R(x + 630, y + 5, 80, 13), m.mood / 100, GOOD if m.mood > 45 else WARN if m.mood > 30 else BAD)
        stx = m.status_text(w) + ("  · ZWEIFLER" if m.doubter else "")
        ui.text(x + 720, y + 4, stx[:36], BAD if m.doubter or m.fleeing else DIM)
    ui.end_scroll()
    n_m = sum(1 for m in mem if m.kind == "member")
    cnt = {rn: sum(1 for m in mem if m.kind == "member" and m.role == rk) for rk, rn in ROLES.items()}
    ui.text(r.x + 14, r.bottom - 28, f"{n_m} Mitglieder · Betten: {w.count_use('bed')} · " + " · ".join(f"{k}: {v}" for k, v in cnt.items()), DIM)


def draw_doctrine(app):
    ui, w = app.ui, app.w
    r = ui.panel(panel_rect(app, 1100, 600), "Lehre & Regeln")
    close_btn(app, r)
    x, y = r.x + 16, r.y + 48
    lw = 330
    arch = w.archetype_def()
    ui.text(x, y, arch["name"], GOLD, "m")
    y += 24
    y += ui.wrap(x, y, lw, arch["text"], DIM) + 2
    et = effects_text(arch)
    if et:
        y += ui.wrap(x, y, lw, et, GOOD) + 4
    y += 10
    tgt = w.doctrine_target()
    for a, ad in DATA.doctrine["axes"].items():
        ui.text(x, y, ad["name"], TEXT)
        ui.text(x + lw, y, f"{w.doctrine[a]:+.0f}", DIM, right=True)
        ui.axis_bar(R(x, y + 22, lw, 14), w.doctrine[a], tgt[a], ad["neg"], ad["pos"])
        ui.tooltip(R(x, y, lw, 54), ad["desc"] + "\nDie Lehre wandert täglich Richtung Zielmarke (Dreieck). Regeln, Gebäude und "
                   "Entscheidungen bei Ereignissen verschieben das Ziel.")
        y += 66
    myth = next(m for m in DATA.doctrine["myths"] if m["id"] == w.myth)
    ui.text(x, y, "Gründungsmythos: " + myth["name"], TEXT)
    y += 20
    y += ui.wrap(x, y, lw, myth["text"], DIM) + 10
    s = w._sched
    ui.text(x, y, "Tagesablauf", TEXT)
    y += 20
    ui.wrap(x, y, lw, f"Schlaf {s['sleep'][0]}–{s['sleep'][1]} Uhr · Predigt 7–9 Uhr" + (" und 19–21 Uhr" if s["evening_sermon"] else "")
            + f" · Arbeit 9–{s['work_end']} Uhr · Wächter haben Nachtschicht", DIM)
    # Regeln
    x2 = x + lw + 28
    mw = r.right - x2 - 300
    ui.text(x2, r.y + 48, f"Regeln der Gemeinschaft  ({len(w.edicts)}/{w.edict_slots} Plätze)", TEXT, "m")
    eds = [(k, e) for k, e in DATA.edicts.items()]
    area = R(x2, r.y + 76, mw, r.h - 92)
    off = ui.scroll_area("edicts", area, len(eds) * 50)
    for n, (k, e) in enumerate(eds):
        yy = area.y + n * 50 - off
        if yy < area.y - 50 or yy > area.bottom:
            continue
        on = k in w.edicts
        block = w.edict_block(k)
        rr = R(area.x, yy, area.w - 10, 46)
        tip = f"{e['text']}\n\n{effects_text(e)}" + (f"\n\n{block}" if block and not on else "")
        if ui.button(rr, "", tip, enabled=on or not block, active=on):
            w.toggle_edict(k)
        locked = e.get("phase", 1) > w.phase
        ui.text(rr.x + 10, yy + 4, e["name"] + ("  (Phase 2)" if locked else ""), GOLD if on else (TEXT if not block else DIM), "m")
        ui.text(rr.x + 10, yy + 25, effects_text(e)[:64], DIM)
        ui.text(rr.right - 10, yy + 4, "AKTIV" if on else f"{e['cost']} EP", GOOD if on else (PURPLE if not block else DIM), right=True)
    ui.end_scroll()
    # Ränge & Projekte
    x3 = r.right - 280
    y = r.y + 48
    ui.text(x3, y, "Ränge", TEXT, "m")
    y += 26
    mem = [m for m in w.members() if m.kind == "member"]
    for n, rk in enumerate(DATA.doctrine["ranks"]):
        pygame.draw.rect(app.screen, rk["robe"], (x3, y + 2, 14, 14), border_radius=3)
        ui.text(x3 + 22, y, f"{rk['name']}: {sum(1 for m in mem if m.rank == n)}", TEXT)
        ui.text(x3 + 264, y, f"{rk['cost']} EP" if rk["cost"] else "", DIM, right=True)
        y += 20
    y += 14
    ui.text(x3, y, "Großprojekte", TEXT, "m")
    y += 26
    if w.phase < 3:
        ui.wrap(x3, y, 264, "Ab Phase 3 (weltweite Dachorganisation): Fernsehsender, Partei, Steuerparadies-Insel, Satellit – "
                "und die Anerkennung als Weltreligion.", DIM)
        return
    share = w.strategic.world_share()
    for k, p in DATA.doctrine["projects"].items():
        done = k in w.projects_done
        running = w.project and w.project[0] == k
        need = p.get("need_share", 0)
        ok = not done and not w.project and w.money >= p["money"] and w.ep >= p["ep"] and share >= need
        lab = p["name"][:30]
        tip = f"{p['text']}\n\nKosten: {fmt(p['money'])} € und {p['ep']} EP · Dauer {p['days']} Tage\n{effects_text(p)}"
        if need:
            tip += f"\nBenötigt {need * 100:.0f} % Weltanteil (aktuell {share * 100:.2f} %)"
        if ui.button(R(x3, y, 264, 40), "", tip, enabled=ok, active=done or running):
            w.spend("Großprojekte", p["money"])
            w.ep -= p["ep"]
            w.project = [k, p["days"]]
        ui.text(x3 + 8, y + 3, lab, GOLD if done else TEXT)
        ui.text(x3 + 8, y + 21, "Vollendet" if done else f"Noch {w.project[1]} Tage" if running else f"{fmt(p['money'])} € · {p['ep']} EP",
                GOOD if done or running else DIM)
        y += 44


def draw_finance(app):
    ui, w = app.ui, app.w
    r = ui.panel(panel_rect(app, 860, 540), "Finanzen")
    close_btn(app, r)
    x, y = r.x + 16, r.y + 50
    for title, led in (("Gestern", w.ledger_last), ("Heute (laufend)", w.ledger)):
        ui.text(x, y, title, TEXT, "m")
        yy = y + 26
        for k, v in sorted(led.items(), key=lambda kv: -kv[1]):
            ui.text(x, yy, k[:34], DIM)
            ui.text(x + 330, yy, f"{fmt(v)} €", GOOD if v > 0 else BAD, right=True)
            yy += 19
        pygame.draw.line(app.screen, DIM, (x, yy + 2), (x + 330, yy + 2))
        ui.text(x, yy + 6, "Summe", TEXT)
        s = sum(led.values())
        ui.text(x + 330, yy + 6, f"{fmt(s)} €", GOOD if s >= 0 else BAD, right=True)
        x += 370
    x = r.x + 16
    y = r.bottom - 150
    ui.text(x, y, "Großeinkauf im Discounter", TEXT, "m")
    for n, amt in enumerate((20, 60)):
        if ui.button(R(x + n * 190, y + 26, 180, 30), f"{amt} Rohkost ({amt * 2.5:.0f} €)", "Wenn die Felder nicht reichen.", w.money >= amt * 2.5):
            w.buy_food(amt)
    if ui.button(R(x + 400, y + 26, 250, 30), "Akten schreddern (10 EP)", "Beweise −12. Der Reißwolf heißt intern 'Bruder Vergessen'.",
                 w.ep >= 10 and w.evidence > 0):
        w.ep -= 10
        w.add_evidence(-12)
        w.notify("Bruder Vergessen hat gründlich gearbeitet: Beweise −12.", "info")
    ui.text(x, y + 68, "Rechtsbeistand (senkt Verdachtszuwachs, hilft bei Verbotsverfahren und Razzien)", TEXT, "m")
    sc = w.strategic.phase_scale()
    for n, l in enumerate(DATA.campaigns["lawyers"]):
        if ui.button(R(x + n * 206, y + 94, 200, 30), l["name"][:28], f"{fmt(l['cost'] * sc)} € pro Tag", active=w.lawyers == n):
            w.lawyers = n
            w.recompute_mods()
        ui.text(x + n * 206 + 100, y + 126, f"{fmt(l['cost'] * sc)} €/Tag", DIM, center=True)


HELP = [
    ("Kamera", "WASD / Pfeiltasten oder mittlere Maustaste ziehen · Mausrad: Zoom · Q / E: Ansicht drehen"),
    ("Zeit", "Leertaste: Pause · 1 / 2 / 3: Tempo"),
    ("Bauen", "B: Baumenü · Wände und Zäune ziehen (Shift: Rechteck-Umriss) · Böden und Zonen als Fläche · X: Abriss · Rechtsklick: Werkzeug ablegen"),
    ("Räume", "Von Wänden und Türen umschlossene Flächen werden automatisch Räume, von Zäunen umschlossene Gehege. "
              "Die Funktion ergibt sich aus der Einrichtung (R blendet sie ein)."),
    ("Mitglieder", "Anklicken: Aufgabe, Beförderung, Einzelgespräch, Geschenk · F1: Liste · Guru auswählen + Rechtsklick: hinschicken"),
    ("Sekte führen", "F2: Lehre und Regeln · F3: Finanzen, Einkauf, Anwälte · M: Karte (Kampagnen, Ortsgruppen, Regionalleiter, Expansion)"),
    ("Gefahren", "Verdacht (Presse, Behörden, Razzia), Zweifler und Ausreißer, Abweichler, Maulwürfe, Hunger, Pleite"),
    ("Sonstiges", "H: Wände niedrig · N: Musik an/aus · F5: Schnellspeichern · F9: Schnellladen · F11: Vollbild · Esc: Menü"),
]


def draw_help(app):
    ui = app.ui
    r = ui.panel(panel_rect(app, 860, 520), "Steuerung & Kurzanleitung")
    close_btn(app, r)
    y = r.y + 52
    for k, t in HELP:
        ui.text(r.x + 18, y, k, GOLD, "m")
        y += ui.wrap(r.x + 150, y + 1, r.w - 172, t, TEXT) + 12


def draw_pause(app):
    ui = app.ui
    r = ui.panel(panel_rect(app, 320, 330), "Menü")
    items = [("Weiter", "resume"), ("Speichern (F5)", "save"), ("Laden (F9)", "load"),
             ("Musik: " + ("an" if app.assets.music_on else "aus"), "music"), ("Hauptmenü", "menu"), ("Beenden", "quit")]
    for n, (lab, act) in enumerate(items):
        if ui.button(R(r.x + 30, r.y + 50 + n * 44, r.w - 60, 36), lab, font="m"):
            app.menu_action(act)


def draw_popup(app):
    ui, w = app.ui, app.w
    W, H = app.screen.get_size()
    dim = pygame.Surface((W, H), pygame.SRCALPHA)
    dim.fill((6, 4, 10, 150))
    app.screen.blit(dim, (0, 0))
    if w.over and not w.popups:
        win = w.over[0] == "win"
        r = ui.panel(R(W // 2 - 320, H // 2 - 160, 640, 320), "HALLELUJA!" if win else "Das Ende", edge=GOLD if win else BAD)
        ui.wrap(r.x + 20, r.y + 54, r.w - 40, w.over[1], TEXT, "m")
        ui.text(r.x + 20, r.bottom - 96, f"Tag {w.day} · {len(w.members())} Mitglieder · {fmt(w.strategic.total_followers())} Anhänger", DIM)
        if ui.button(R(r.x + 20, r.bottom - 56, 290, 38), "Hauptmenü", font="m"):
            app.menu_action("menu")
        if ui.button(R(r.right - 310, r.bottom - 56, 290, 38), "Beenden", font="m"):
            app.menu_action("quit")
        return
    pop = w.popups[0]
    pw = 660
    th = ui.wrap(0, 0, pw - 48, pop["text"], font="m", draw=False)
    ph = 66 + th + 14 + len(pop["choices"]) * 44 + 12
    r = ui.panel(R(W // 2 - pw // 2, max(TOP_H + 6, H // 2 - ph // 2), pw, ph), pop["title"],
                 alpha=252, edge=BAD if pop.get("kind") == "bad" else EDGE)
    ui.wrap(r.x + 24, r.y + 52, pw - 48, pop["text"], TEXT, "m")
    y = r.y + 66 + th
    for i, ch in enumerate(pop["choices"]):
        block = events.choice_block(w, ch)
        c = ch.get("cost", {})
        cost = " · ".join(([f"{fmt(c['money'])} €"] if c.get("money") else []) + ([f"{c['ep']} EP"] if c.get("ep") else []))
        tip = ch.get("tip", "") + (("\n" if ch.get("tip") else "") + block if block else "")
        rr = R(r.x + 24, y, pw - 48, 38)
        if ui.button(rr, ch["label"][:74], tip or None, enabled=not block, font="m", align="left"):
            events.choose(w, pop, i)
        if cost:
            ui.text(rr.right - 10, y + 10, cost, GOLD if not block else BAD, right=True)
        y += 44


def draw_menu(app):
    """Hauptmenü / Neues Spiel."""
    ui = app.ui
    scr = app.screen
    W, H = scr.get_size()
    scr.fill((18, 14, 26))
    t = pygame.time.get_ticks() / 1000
    tile = app.assets.get("floor_carpet")[0]
    big = app.assets._cache.get("menu_tile")
    if big is None:
        big = app.assets._cache["menu_tile"] = pygame.transform.scale(tile, (128, 64))
        big.set_alpha(46)
    off = int(t * 12) % 64
    for yy in range(-2, H // 32 + 2):
        for xx in range(-1, W // 128 + 2):
            scr.blit(big, (xx * 128 + (64 if yy % 2 else 0), yy * 32 - off))
    ui.text(W // 2, 54, "CULT-SIM", GOLD, "t", center=True)
    ui.text(W // 2, 98, "Bau dir deine Sekte. Eine Satire.", DIM, "m", center=True)
    r = ui.panel(R(W // 2 - 380, 140, 760, 500))
    x, y = r.x + 30, r.y + 24
    nm = DATA.names
    ui.text(x, y, "Name der Gemeinschaft", DIM)
    app.new_cult = ui.textfield("cult", R(x, y + 22, 560, 34), app.new_cult, 46)
    if ui.button(R(x + 570, y + 22, 130, 34), "Würfeln"):
        app.new_cult = f"{app.rng.choice(nm['cult_prefix'])} {app.rng.choice(nm['cult_core'])}"
    y += 72
    ui.text(x, y, "Name des Gurus", DIM)
    app.new_guru = ui.textfield("guru", R(x, y + 22, 560, 34), app.new_guru, 30)
    if ui.button(R(x + 570, y + 22, 130, 34), "Würfeln"):
        app.new_guru = app.rng.choice(nm["guru_names"])
    y += 76
    ui.text(x, y, "Gründungsmythos (prägt die Lehre zu Beginn)", DIM)
    y += 24
    for n, m in enumerate(DATA.doctrine["myths"]):
        rr = R(x, y, 700, 62)
        if ui.button(rr, "", active=app.new_myth == m["id"]):
            app.new_myth = m["id"]
        ui.text(rr.x + 12, rr.y + 6, m["name"], GOLD if app.new_myth == m["id"] else TEXT, "m")
        ui.text(rr.x + 12, rr.y + 28, m["text"][:92], DIM)
        ui.text(rr.right - 12, rr.y + 6, ", ".join(f"{AX_SHORT[a]} {v:+d}" for a, v in m["doctrine"].items()), DIM, right=True)
        y += 68
    y += 10
    if ui.button(R(x, y, 340, 44), "Sekte gründen", font="b") and app.new_cult.strip() and app.new_guru.strip():
        app.new_game()
    has_save = app.save_path.exists()
    if ui.button(R(x + 360, y, 200, 44), "Spielstand laden", "Schnellspeicherstand (F5/F9)", enabled=has_save, font="m"):
        app.load_game()
    if ui.button(R(x + 570, y, 130, 44), "Beenden", font="m"):
        app.running = False
    ui.text(W // 2, H - 30, f"{VERSION} · Platzhalter-Grafik und -Ton sind austauschbar (assets/manifest.json, siehe README)", DIM, center=True)
