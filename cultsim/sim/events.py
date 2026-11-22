"""Ereignisse: datengetriebene Zufallsereignisse (data/events.json) + Systemereignisse
(Razzia, Kirchenspaltung, Maulwürfe, Weltuntergang, Phasenwechsel)."""
from __future__ import annotations

from ..config import *
from ..data import DATA


# ---------------------------------------------------------------- Popups
def popup(w, title, text, choices=None, ctx=None, kind="event"):
    w.popups.append({"title": title, "text": text, "choices": choices or [{"label": "Verstanden", "effects": {}}],
                     "ctx": ctx or {}, "kind": kind})
    w.cues.append("event")


def fill(w, text, ctx):
    m = w.pawn_ids.get(ctx.get("member"))
    return (text.replace("{cult}", w.cult_name).replace("{guru}", w.guru_name)
            .replace("{member}", m.name if m else "Ein Mitglied"))


def choice_block(w, ch):
    c = ch.get("cost", {})
    if w.money < c.get("money", 0):
        return "Zu wenig Geld"
    if w.ep < c.get("ep", 0):
        return "Zu wenig Erleuchtung"
    return None


def choose(w, pop, i):
    """Spieler wählt Option i des Popups."""
    ch = pop["choices"][i]
    if choice_block(w, ch):
        return False
    if pop in w.popups:
        w.popups.remove(pop)
    c = ch.get("cost", {})
    w.spend("Ereignisse", c.get("money", 0))
    w.ep -= c.get("ep", 0)
    result = apply(w, ch.get("effects", {}), pop["ctx"])
    if result:
        popup(w, pop["title"], fill(w, result, pop["ctx"]), ctx=pop["ctx"], kind="result")
    return True


def apply(w, fx, ctx):
    """Wendet ein Effekt-Dict an. Liefert ggf. einen Ergebnistext (bei Zufallsausgängen)."""
    result = None
    mem = [m for m in w.members(True) if m.kind == "member"]
    for k, v in fx.items():
        if k == "money":
            w.earn("Ereignisse", v) if v > 0 else w.spend("Ereignisse", -v)
        elif k == "food":
            w.food = max(0.0, w.food + v)
        elif k == "food_pct":
            w.food = max(0.0, w.food * (1 + v / 100))
        elif k == "meals":
            w.meals = max(0.0, w.meals + v)
        elif k == "ep":
            w.ep = max(0.0, w.ep + v)
        elif k == "tracts":
            w.tracts = max(0.0, w.tracts + v)
        elif k == "heat":
            w.add_heat(v)
        elif k == "evidence":
            w.add_evidence(v)
        elif k == "faith_all":
            for m in mem:
                m.faith = max(0.0, min(100.0, m.faith + v))
        elif k == "mood_all":
            for m in mem:
                m.add_thought("event", "Jüngste Ereignisse", v, 72, w)
        elif k == "awareness":
            h = w.strategic.home_local()
            h.aware = max(0.0, min(100.0, h.aware + v))
            for lv in w.strategic.active()[1:]:
                for r in lv.regions.values():
                    r.aware = min(100.0, r.aware + v * 0.4)
        elif k == "followers_pct":
            for lv in w.strategic.active():
                for r in lv.regions.values():
                    r.followers *= 1 + v / 100
        elif k == "doctrine":
            for a, d in v.items():
                w.shift_doctrine(a, d)
        elif k == "spawn":
            for s in ([v] if isinstance(v, str) else v):
                if s == "raid":
                    w.start_raid()
                elif s == "relative":
                    w.spawn("relative", target=ctx.get("member"))
                else:
                    w.spawn(s)
        elif k == "recruit":
            from .pawns import make_outsider
            for n in range(v):
                p = make_outsider(w, "visitor", offset=n)
                w.convert(p)
        elif k == "member":
            m = w.pawn_ids.get(ctx.get("member"))
            if m is not None:
                m.faith = max(0.0, min(100.0, m.faith + v.get("faith", 0)))
                m.bond = max(0.0, min(100.0, m.bond + v.get("bond", 0)))
                if v.get("mood"):
                    m.add_thought("event_me", "Entscheidung des Gurus", v["mood"], 72, w)
        elif k == "flag":
            w.flags[v] = True
        elif k == "call":
            r = globals()["fx_" + v](w, ctx)
            result = r or result
        elif k == "random":
            x = w.rng.random()
            for o in v:
                x -= o["p"]
                if x <= 0:
                    sub = apply(w, o.get("effects", {}), ctx)
                    result = o.get("text") or sub
                    break
    return result


# ---------------------------------------------------------------- Zufallsereignisse
def eligible(w, eid, e):
    lo, hi = e.get("phase", [1, 3])
    if not lo <= w.phase <= hi:
        return False
    if w.event_cd.get(eid, 0) > w.day:
        return False
    c = e.get("cond", {})
    n = len(w.members())
    mem = [m for m in w.members(True) if m.kind == "member"]
    if n < c.get("members_min", 0) or w.day < c.get("day_min", 0):
        return False
    if w.heat < c.get("heat_min", 0) or w.heat > c.get("heat_max", 100):
        return False
    if "mood_max" in c and (not mem or sum(m.mood for m in mem) / len(mem) > c["mood_max"]):
        return False
    if w.strategic.total_followers() < c.get("followers_min", 0):
        return False
    if "flag" in c and not w.flags.get(c["flag"]):
        return False
    if "edict" in c and c["edict"] not in w.edicts:
        return False
    for a, (dl, dh) in c.get("doctrine", {}).items():
        if not dl <= w.doctrine[a] <= dh:
            return False
    return True


def daily_roll(w):
    if w.day < 2 or w.popups or w.rng.random() > 0.5:
        return
    pool = [(k, e) for k, e in DATA.events.items() if eligible(w, k, e)]
    if not pool:
        return
    eid, e = w.rng.choices(pool, [e.get("weight", 1.0) for _, e in pool])[0]
    w.event_cd[eid] = w.day + e.get("cooldown", 10)
    mem = [m for m in w.members(True) if m.kind == "member"]
    ctx = {"member": w.rng.choice(mem).id} if mem else {}
    choices = [dict(c, label=fill(w, c["label"], ctx)) for c in e["choices"]]
    popup(w, e["title"], fill(w, e["text"], ctx), choices, ctx)


def welcome(w):
    popup(w, f"Willkommen, {w.guru_name}!",
          f"Ein zugiger Schuppen am Waldrand, drei treue Seelen und eine Vision: {w.cult_name} soll die Welt "
          "erleuchten (und nebenbei deine Schulden tilgen).\n\n"
          "• Baue Schlafplätze, Küche und Tempel – Wände und Zäune bilden automatisch Räume und Gehege.\n"
          "• Lege Anbaufelder an, damit niemand hungert.\n"
          "• Predigten stärken den Glauben, Werber und Prediger gewinnen neue Mitglieder.\n"
          "• Öffne die KARTE (M), um die Stadt zu missionieren – später das Land und die Welt.\n"
          "• Behalte den VERDACHT im Auge: Presse, Behörden und Zweifler in den eigenen Reihen schlafen nie.",
          [{"label": "Die Erleuchtung möge beginnen", "effects": {}}], kind="info")


def phase_popup(w, phase):
    if phase == 2:
        popup(w, "Phase 2: Landesverband",
              f"{w.cult_name} ist der Kleinstadt entwachsen. Der neu gegründete Landesverband e.V. (i.G.) "
              "missioniert nun bundesweit.\n\nNeu: Landeskarte, TV-Kampagnen, Logistikzentren, Lobbyarbeit, "
              "weitere Regeln – und neue Gegner: Sektenbeauftragte, Untersuchungsausschüsse, die Kriminalpolizei.",
              [{"label": "Deutschland, wir kommen", "effects": {}}], kind="info")
    else:
        popup(w, "Phase 3: Weltweite Dachorganisation",
              f"{w.cult_name} International Holding Ltd. nimmt die Arbeit auf.\n\nNeu: Weltkarte, Übersetzungen "
              "der Heiligen Schrift, weltweite Logistik, Großprojekte – und Gegner von anderem Kaliber: "
              "Regierungen, Geheimdienste, Militär. Ziel: 5 % der Weltbevölkerung und die Anerkennung als Weltreligion.",
              [{"label": "Die Welt ist nicht genug", "effects": {}}], kind="info")


# ---------------------------------------------------------------- Außenstehende verlassen das Gelände
def outsider_left(w, p):
    k = p.kind
    rng = w.rng
    home = w.strategic.home_local()
    if k == "visitor":
        home.aware = min(100.0, home.aware + 0.3)
        if w.count_use("donation"):
            w.earn("Opferstock", rng.uniform(2, 9) * (1 + p.interest / 100))
        if w.count_use("merch") and rng.random() < 0.55:
            w.earn("Merch-Stand", rng.uniform(8, 30))
    elif k == "journalist":
        ev = p.evidence
        if p.charmed or ev < 4:
            home.aware = min(100.0, home.aware + 8)
            w.add_heat(-3)
            w.notify("Zeitungsbericht: »Harmlose Spinner mit gutem Eintopf« – beste Werbung!", "good")
        elif ev < 12:
            w.add_heat(ev * 0.6)
            home.aware = min(100.0, home.aware + 4)
            w.notify("Zeitungsbericht: »Seltsame Dinge am Waldrand«. Etwas mehr Verdacht.", "warn")
        else:
            w.add_heat(ev * 0.8)
            w.add_evidence(ev * 0.4)
            home.aware = min(100.0, home.aware + 6)
            w.notify("ENTHÜLLUNGSSTORY: »Im Inneren der Sekte – Zwang, Zäune, Zehnter«. Der Verdacht steigt stark!", "bad")
    elif k == "inspector":
        if p.target_id is None:
            w.add_heat(9)
            w.notify("Der Kontrolleur wurde nicht eingelassen. Das gibt einen Vermerk. Einen dicken.", "bad")
            return
        n = len([m for m in w.members() if m.kind == "member"])
        faults = []
        if w.count_use("bed") < n:
            faults.append("zu wenige Betten")
        if not w.count_use("stove"):
            faults.append("keine Kochstelle")
        if w.food + w.meals < n * 1.5:
            faults.append("kaum Vorräte")
        if any(m.food < 15 for m in w.members(True)):
            faults.append("unterernährte Bewohner")
        if faults:
            fine = 120 * len(faults) * w.strategic.phase_scale() ** 0.5
            w.spend("Bußgelder", min(max(0.0, w.money), fine))
            w.add_heat(5 * len(faults))
            w.add_evidence(2 * len(faults))
            w.notify(f"Kontrollbericht: {', '.join(faults)}. Bußgeld {fine:.0f} €.", "bad")
        else:
            w.add_heat(-8)
            w.notify("Kontrollbericht: »Keine Beanstandungen. Sehr ordentliche Sekte.«", "good")
    elif k == "relative" and not p.expelled and w.flag("contact_ban"):
        w.add_heat(2)


# ---------------------------------------------------------------- Nacht: Fluchtversuche
def night_checks(w):
    rng = w.rng
    for m in w.members(True):
        if m.kind != "member" or not m.doubter or m.fleeing or m.engaged is not None:
            continue
        ch = 0.22 * m.tm("flee") * w.mod("flee") * (1.4 if m.mood < 30 else 1.0) * (0.5 if m.bond > 60 else 1.0)
        if rng.random() < ch:
            m.cancel_job(w)
            cls = C_OUTSIDER if (w.flag("curfew") and m.rank < 2) else C_MEMBER
            if m.go(w, "flee", w.exit, cls=cls):
                m.fleeing = True
                m.log(w, "Schleicht sich nachts davon ...")
            else:
                m.add_thought("locked", "Das Tor ist zu. Natürlich ist es zu.", -8, 48, w)
                m.log(w, "Wollte fliehen – das Tor war verschlossen.")


# ---------------------------------------------------------------- Tägliche Systemprüfungen
def daily_checks(w):
    rng = w.rng
    mem = [m for m in w.members(True) if m.kind == "member"]
    day = w.day
    # Razzia
    rd = w.flags.get("raid_day")
    if rd is None and (w.heat >= 85 or (w.heat >= 70 and w.evidence >= 60)):
        w.flags["raid_day"] = day + 2
        popup(w, "Ein Tipp aus dem Rathaus",
              "Ein Sympathisant im Ordnungsamt flüstert: In zwei Tagen kommt die Polizei zur Durchsuchung. "
              f"Verdacht: {w.heat:.0f} %, Beweislage: {w.evidence:.0f} %.\n\n"
              "Sinkt der Verdacht bis dahin unter 65 %, wird die Aktion abgeblasen.",
              [{"label": "Akten schreddern (Beweise −20)", "cost": {"ep": 10}, "effects": {"evidence": -20}},
               {"label": "Benefiz-Suppenküche & Pressefotos (Verdacht −22)", "cost": {"money": 400 * w.strategic.phase_scale()},
                "effects": {"heat": -22}},
               {"label": "Sollen sie kommen. Wir haben nichts zu verbergen. (Hüstel.)", "effects": {}}], kind="bad")
    elif rd is not None and day >= rd:
        w.flags["raid_day"] = None
        if w.heat >= 65:
            w.start_raid()
        else:
            w.notify("Die geplante Durchsuchung wurde abgeblasen. Die Suppenküche hat gewirkt.", "good")
    # Maulwürfe
    guards = sum(1 for m in mem if m.role == "guard")
    for m in mem:
        mole = [t for t in m.traits if t.startswith("maulwurf")]
        if not mole:
            continue
        ch = 0.03 + 0.04 * guards + (0.15 if w.flag("confession_duty") else 0)
        if rng.random() < ch:
            mole_found(w, m)
            break
    # Kirchenspaltung
    s = w.schism
    if s is None:
        if len(mem) >= 7:
            cands = [m for m in mem if m.skills["preach"] >= 4 and m.bond < 35 and (m.faith < 55 or "ehrgeizig" in m.traits)]
            if cands and rng.random() < 0.05 + 0.03 * sum("ehrgeizig" in m.traits for m in cands):
                lead = max(cands, key=lambda m: m.skills["preach"])
                w.schism = {"leader": lead.id, "members": [], "day": day, "known": False}
    else:
        lead = w.pawn_ids.get(s["leader"])
        if lead is None or lead.away:
            w.schism = None
        else:
            s["members"] = [i for i in s["members"] if i in w.pawn_ids]
            pool = [m for m in mem if m.id != lead.id and m.id not in s["members"] and m.bond < 50 and m.faith < 75]
            if pool and rng.random() < 0.5:
                s["members"].append(rng.choice(pool).id)
            if not s["known"] and (len(s["members"]) >= 2 or w.flag("confession_duty") or day - s["day"] > 6):
                s["known"] = True
                s["deadline"] = day + 5
                popup(w, "Abweichler in den eigenen Reihen!",
                      f"{lead.name} hält heimlich eigene Andachten ab und behauptet, {w.guru_name} habe 'die reine "
                      f"Lehre verwässert'. Schon {len(s['members'])} Mitglieder hören zu. In fünf Tagen droht die Spaltung.",
                      [{"label": "Einzelgespräche mit allen Beteiligten", "cost": {"ep": 12}, "effects": {"call": "schism_talk"}},
                       {"label": f"{lead.name} verstoßen", "effects": {"call": "schism_exile"}},
                       {"label": "Zum Stellvertreter befördern (gekaufte Loyalität)", "cost": {"money": 300},
                        "effects": {"call": "schism_promote"}},
                       {"label": "Ignorieren", "effects": {}}], ctx={"member": lead.id}, kind="bad")
            elif s["known"] and day >= s.get("deadline", day):
                fx_schism_split(w, {})
    # Weltuntergang ausgeblieben
    dd = w.flags.get("doomsday_day")
    if dd and day >= dd and "endzeit" in w.edicts:
        w.flags["doomsday_day"] = None
        popup(w, "Der Weltuntergang ... findet nicht statt",
              "Mitternacht ist vorbei. Die Welt steht noch. Die Mitglieder stehen in ihren besten Roben auf dem Hügel "
              "und schauen dich an. Einer hat seinen Bausparvertrag gekündigt.",
              [{"label": "'Unser Glaube hat die Welt gerettet!'", "effects": {"random": [
                  {"p": 0.65, "text": "Jubel! Der Glaube ist stärker denn je. (Das klappt erstaunlich oft.)",
                   "effects": {"faith_all": 12, "ep": 15, "call": "doomsday_off"}},
                  {"p": 0.35, "text": "Betretenes Schweigen. Einige packen ihre Sachen.",
                   "effects": {"faith_all": -18, "heat": 5, "call": "doomsday_off"}}]}},
               {"label": "'Ich habe mich verrechnet. Neuer Termin in 30 Tagen.'",
                "effects": {"faith_all": -6, "call": "doomsday_again"}},
               {"label": "'Es war ein Test. Ihr habt bestanden. Gegen Gebühr.'",
                "effects": {"money": 300, "faith_all": -8, "doctrine": {"commerce": 10}, "call": "doomsday_off"}}], kind="event")
    # Hinweise
    if day == 3 and not w.strategic.home_local().campaigns and not any(r.campaigns for r in w.strategic.levels["local"].regions.values()):
        w.notify("Tipp: Öffne die Karte (M) und starte in der Stadt eine Werbekampagne.", "info")


def mole_found(w, m):
    t = next(t for t in m.traits if t.startswith("maulwurf"))
    what = DATA.traits[t]["name"]
    popup(w, "Maulwurf enttarnt!",
          f"{m.name} ist in Wahrheit: {what}! In der Matratze steckten ein Diktiergerät und 40 Seiten Notizen.",
          [{"label": "Hinauswerfen", "effects": {"call": "mole_kick"}},
           {"label": "Umdrehen: 'Du schreibst ab jetzt, was WIR dir diktieren.'", "cost": {"ep": 18}, "effects": {"call": "mole_turn"}},
           {"label": "Vor versammelter Gemeinde bloßstellen", "effects": {"call": "mole_kick", "faith_all": 4, "heat": 6}}],
          ctx={"member": m.id}, kind="bad")


def after_guru_talk(w, o):
    if any(t.startswith("maulwurf") for t in o.traits) and w.rng.random() < 0.15:
        mole_found(w, o)
    s = w.schism
    if s and (o.id == s["leader"] or o.id in s["members"]) and o.bond > 45:
        if o.id == s["leader"]:
            w.schism = None
            w.notify(f"{o.name} schwört dem Abweichlertum ab. Die Spaltung ist abgewendet.", "good")
        else:
            s["members"].remove(o.id)


def fx_mole_kick(w, ctx):
    m = w.pawn_ids.get(ctx.get("member"))
    if m:
        w.add_evidence(4)
        w.notify(f"{m.name} wurde samt Diktiergerät vor die Tür gesetzt.", "info")
        w.remove_pawn(m)


def fx_mole_turn(w, ctx):
    m = w.pawn_ids.get(ctx.get("member"))
    if m:
        m.traits = [t for t in m.traits if not t.startswith("maulwurf")] + ["loyal"]
        m._tm = None
        m.bond = min(100.0, m.bond + 20)
        w.add_evidence(-15)
        w.add_heat(-5)
        m.log(w, "Als Maulwurf enttarnt – arbeitet jetzt für uns.")
        return f"{m.name} liefert der Gegenseite ab sofort Berichte über Yoga, Dinkelbrot und allgemeine Harmlosigkeit."


def _schism_people(w):
    s = w.schism or {"leader": None, "members": []}
    return w.pawn_ids.get(s["leader"]), [w.pawn_ids[i] for i in s["members"] if i in w.pawn_ids]


def fx_schism_talk(w, ctx):
    lead, fol = _schism_people(w)
    g = w.guru
    for m in fol:
        m.bond = min(100.0, m.bond + 15)
        m.faith = min(100.0, m.faith + 8)
    ok = lead is None or w.rng.random() < 0.35 + (g.skills["preach"] if g else 5) * 0.05
    if ok:
        if lead:
            lead.bond = min(100.0, lead.bond + 25)
            lead.faith = min(100.0, lead.faith + 15)
        w.schism = None
        return "Tränen, Umarmungen, ein gemeinsames Mantra. Die Abweichler kehren reumütig zurück."
    return "Die Mitläufer sind besänftigt – aber der Rädelsführer lächelt nur dünn. Es ist nicht vorbei."


def fx_schism_exile(w, ctx):
    lead, fol = _schism_people(w)
    w.schism = None
    gone = 0
    if lead:
        for m in fol:
            m.faith = max(0.0, m.faith - 10)
            if w.rng.random() < 0.3:
                w.remove_pawn(m)
                gone += 1
        w.defect(lead, "wurde als Ketzer verstoßen")
    return f"Der Rädelsführer ist fort{f' – und hat {gone} Mitglieder mitgenommen' if gone else ''}. Draußen erzählt er jetzt allerlei."


def fx_schism_promote(w, ctx):
    lead, fol = _schism_people(w)
    w.schism = None
    if lead:
        lead.rank = len(DATA.doctrine["ranks"]) - 1
        lead.bond = min(100.0, lead.bond + 35)
        lead.faith = min(100.0, lead.faith + 20)
        lead.log(w, "Vom Abweichler zum Stellvertreter des Gurus.")
        for m in w.members(True):
            if m.kind == "member" and m is not lead and m.rank >= 1:
                m.add_thought("envy", f"{lead.name.split()[0]} wird für Meuterei belohnt?!", -8, 120, w)
        return f"{lead.name} trägt jetzt die dunkle Robe des Inneren Kreises – und hält plötzlich flammende Reden für dich."


def fx_schism_split(w, ctx):
    lead, fol = _schism_people(w)
    w.schism = None
    if not lead:
        return
    name = w.rng.choice(DATA.names["splinter"]).replace("{cult}", w.cult_name)
    loss = w.money * 0.2 if w.money > 0 else 0
    w.spend("Kirchenspaltung", loss)
    for m in fol:
        w.remove_pawn(m)
    w.remove_pawn(lead)
    for lv in w.strategic.active():
        for r in lv.regions.values():
            r.followers *= 0.85
    w.add_heat(4)
    popup(w, "Kirchenspaltung!",
          f"{lead.name} hat mit {len(fol)} Mitgliedern und {loss:.0f} € aus der Kasse eine eigene Gemeinschaft gegründet: "
          f"»{name}«. 15 % unserer Anhänger laufen über.", kind="bad")


def fx_doomsday_off(w, ctx):
    if "endzeit" in w.edicts:
        w.edicts.discard("endzeit")
        w.recompute_mods()


def fx_doomsday_again(w, ctx):
    w.flags["doomsday_day"] = w.day + 30


def leader_splits(w, lv, r, leader):
    name = w.rng.choice(DATA.names["splinter"]).replace("{cult}", w.cult_name)
    r.followers *= 0.4
    r.chapter = 0
    r.leader = None
    popup(w, "Regionalleitung macht sich selbstständig",
          f"{leader.name}, fern vom Guru und lange ohne Zuwendung, hat in {r.name} die »{name}« ausgerufen. "
          "60 % der dortigen Anhänger und die Ortsgruppe sind verloren.\n\n(Regionalleiter brauchen Bindung: "
          "vor dem Entsenden Einzelgespräche führen oder rechtzeitig zurückrufen.)", kind="bad")
    w.remove_pawn(leader)


def project_done(w, pid):
    p = DATA.doctrine["projects"][pid]
    w.projects_done.append(pid)
    w.recompute_mods()
    popup(w, f"Großprojekt vollendet: {p['name']}", p["text"], kind="info")


# ---------------------------------------------------------------- Razzia
def raid_end(w, reached):
    if not w.flags.get("raid_active"):
        return
    w.flags["raid_active"] = None
    cops = [p for p in w.pawns if p.kind in ("police", "soldier")]
    military = any(p.kind == "soldier" for p in cops)
    for p in cops:
        p.cancel_job(w)
        p.state = "leave"
    g = w.guru
    if not reached:
        w.heat = max(w.heat, 60.0)
        w.add_evidence(8)
        popup(w, "Die Einsatzkräfte ziehen ab",
              f"Stundenlang haben sie das Gelände belagert, aber {w.guru_name} war nicht zu fassen. "
              "Der Verdacht bleibt hoch – sie kommen wieder.", kind="info")
        return
    seized = max(0.0, w.money) * (0.5 if military else 0.35)
    w.spend("Beschlagnahmt", seized)
    w.tracts *= 0.3
    severe = w.evidence >= 70 and w.rng.random() > 0.25 * w.lawyers
    for m in w.members(True):
        if m.kind == "member":
            if "fanatisch" in m.traits or m.faith > 85:
                m.faith = min(100.0, m.faith + 5)
                m.add_thought("raid", "Der Guru ist ein Märtyrer!", 4, 96, w)
            else:
                m.faith = max(0.0, m.faith - 12)
                m.add_thought("raid", "Die Polizei hat alles durchsucht", -10, 96, w)
    if severe:
        heirs = [m for m in w.members(True) if m.kind == "member" and m.bond >= 75 and m.rank >= 2]
        if heirs and g is not None:
            h = max(heirs, key=lambda m: m.bond)
            old = g.name
            w.remove_pawn(g)
            h.kind, h.rank, h.faith, h.bond = "guru", 3, 100.0, 100.0
            h.role = "preacher"
            w.guru_name = h.name
            w.heat, w.evidence = 35.0, 15.0
            popup(w, "Der Guru ist tot, es lebe der Guru",
                  f"{old} wurde verhaftet und wird die nächsten Jahre gesiebte Luft atmen ({seized:.0f} € beschlagnahmt). "
                  f"Doch {h.name}, treu ergeben und rechtzeitig aufgebaut, übernimmt die Führung. Die Lehre lebt weiter!",
                  kind="bad")
        else:
            w.over = ("lose", f"{w.guru_name} wurde verhaftet. Die Beweislage war erdrückend, ein Nachfolger nicht "
                              "in Sicht (dafür braucht es ein Mitglied im Rang »Auserwählter« mit Bindung ≥ 75). "
                              f"{w.cult_name} ist Geschichte.")
    else:
        if g is not None:
            g.cancel_job(w)
            g.orders.clear()
            g.away, g.away_kind = True, "jail"
            g.away_until = w.tick_n + 2 * TICKS_PER_DAY
        w.heat, w.evidence = 38.0, max(0.0, w.evidence - 25)
        popup(w, "Razzia!",
              f"{'Soldaten' if military else 'Polizisten'} haben das Gelände durchsucht, {seized:.0f} € beschlagnahmt und "
              f"{w.guru_name} zur Vernehmung mitgenommen. Die Beweise reichen (noch) nicht – in zwei Tagen ist er zurück. "
              "Bis dahin predigt, wer kann.", kind="bad")
