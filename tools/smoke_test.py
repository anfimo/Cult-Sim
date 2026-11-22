"""Headless-Test: lässt einen simplen Auto-Spieler N Tage spielen und gibt Kennzahlen aus.
Aufruf: uv run python tools/smoke_test.py [tage] [seed]"""
import sys, time, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cultsim.config import *
from cultsim.data import DATA
from cultsim.sim.world import World
from cultsim.sim import events
from cultsim.sim.strategic import fmt


def autoplay(w, rng):
    """Dümmlicher KI-Guru: klickt Popups weg, baut ein wenig, wirbt."""
    while w.popups:
        pop = w.popups[0]
        opts = [i for i, c in enumerate(pop["choices"]) if not events.choice_block(w, c)]
        events.choose(w, pop, rng.choice(opts))
    c = w.size // 2
    d = w.day
    if d == 1 and not w.flags.get("ai1"):
        w.flags["ai1"] = True
        for x in range(c - 9, c - 3):
            for y in range(c + 3, c + 6):
                w.set_zone(x, y, Z_FIELD)
        for x in range(c + 8, c + 14):
            for y in range(c - 6, c + 1):
                edge = x in (c + 8, c + 13) or y in (c - 6, c)
                if edge:
                    w.place("door_wood" if (x, y) == (c + 10, c) else "wall_wood", x, y)
                else:
                    w.place("floor_wood", x, y)
        for k in range(4):
            w.place("bed", c + 9 + k, c - 5)
        w.place("stove", c + 3, c + 2)
        w.place("desk", c + 9, c - 2); w.place("printer", c + 11, c - 2)
    if w.hour < 0.02:
        st = w.strategic
        mem = [m for m in w.members() if m.kind == "member"]
        if w.food + w.meals < len(mem) * 3 and w.money > 150:
            w.buy_food(10 + len(mem) * 3)
        if w.day in (4, 8, 12) and not w.flags.get(f"ai{w.day}"):
            w.flags[f"ai{w.day}"] = True
            for x in range(c + 8, c + 14):
                for y in range(c - 6, c + 1):
                    if x in (c + 8, c + 13) or y in (c - 6, c):
                        w.place("door_wood" if (x, y) == (c + 10, c) else "wall_wood", x, y)
            for did, x, y in (("desk", c + 9, c - 2), ("printer", c + 11, c - 2), ("stove", c + 3, c + 2)):
                w.place(did, x, y)
        beds = w.count_use("bed") + sum(1 for t in w.blueprints if t.d == "bed")
        if beds < len(mem) + 1 and w.money > 100:
            for _ in range(40):
                x, y = c + rng.randint(-8, 8), c + rng.randint(-8, 8)
                if w.place("bed", x, y) is None:
                    break
        roles = [m.role for m in mem]
        for want in ("recruiter", "clerk", "guard"):
            if want not in roles and len(mem) >= {"recruiter": 3, "clerk": 5, "guard": 7}[want]:
                cand = [m for m in mem if m.role in ("worker", "preacher") and roles.count(m.role) > 1 and not m.away]
                if cand:
                    cand[0].role = want; roles = [m.role for m in mem]
        for lv in st.active():
            rs = sorted(lv.regions.values(), key=lambda r: -r.pop)
            for r in rs:
                if r.aggregate:
                    continue
                if lv.key == "world" and not st.lang_ok(r) and st.action_block(lv, r, "translate") is None and w.money > 400000:
                    st.do_action(lv, r, "translate")
                if st.chapter_block(lv, r) is None and w.money > st.cost(r, 4000):
                    st.build_chapter(lv, r)
                if r.heat > 50 and st.action_block(lv, r, "pr") is None and w.money > st.cost(r, 900):
                    st.do_action(lv, r, "pr")
                for cid in ("flyer", "infostand", "social", "tv"):
                    if st.campaign_block(lv, r, cid) is None and w.money > st.cost(r, DATA.campaigns["campaigns"][cid]["cost"]) * 3 + 200:
                        st.start_campaign(lv, r, cid)
                        break
        if st.advance():
            print(f"  >>> Phase {st.phase} an Tag {w.day}")
        if w.heat > 60 and w.lawyers < 3:
            w.lawyers += 1; w.recompute_mods()
        for e in ("zehnt", "love_bombing", "handyverbot"):
            if e not in w.edicts and w.edict_block(e) is None and w.day > 4:
                w.toggle_edict(e)
        for m in mem:
            if m.rank < 1 and w.ep > 40:
                m.promote(w)


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    DATA.load()
    w = World(seed=seed)
    rng = random.Random(seed)
    t0 = time.time()
    last = 0
    while w.day <= days and not w.over:
        autoplay(w, rng)
        w.tick()
        if w.day != last and (w.day % 5 == 0 or w.day == 1):
            last = w.day
            mem = [m for m in w.members() if m.kind == "member"]
            n = max(1, len(mem))
            print(f"Tag {w.day:3d} | Mitgl {len(mem):2d} Besucher {len(w.outsiders())} | € {fmt(w.money):>10} Nahr {w.food:4.0f} Mahlz {w.meals:3.0f} "
                  f"EP {w.ep:4.0f} Trakt {w.tracts:3.0f} | Glaube {sum(m.faith for m in mem)/n:3.0f} Laune {sum(m.mood for m in mem)/n:3.0f} "
                  f"| Verd {w.heat:3.0f} Bew {w.evidence:3.0f} | Anh {fmt(w.strategic.total_followers())} | {w.archetype} | Räume {[r.role for r in w.rooms]}")
    dt = time.time() - t0
    ticks = w.tick_n - START_TICK
    print(f"{ticks} Ticks in {dt:.1f}s = {ticks/dt:.0f} Ticks/s  | Ende: {w.over}")
    for nt in w.notes[-12:]:
        print("   ", nt["day"], nt["text"])
    print("Bilanz gestern:", {k: round(v) for k, v in w.ledger_last.items()})
    import pickle
    w2 = pickle.loads(pickle.dumps(w)); w2.tick()
    print("Save/Load ok")


if __name__ == "__main__":
    main()
