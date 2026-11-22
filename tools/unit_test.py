"""Gezielte Tests einzelner Mechaniken (Räume, Gehege, Flucht, Razzia, Karte). uv run python tools/unit_test.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cultsim.config import *
from cultsim.data import DATA
from cultsim.sim.world import World
from cultsim.sim import events
from cultsim.sim.pawns import make_member

DATA.load()
w = World(seed=3)
w.popups.clear()
c = w.size // 2
w.money = 1e6

def build(did, x, y):
    assert w.place(did, x, y) is None, (did, x, y, w.can_place(did, x, y))
    th = w.thing_at(x, y)
    if th is not None and not th.built:
        w.finish(th)

# Gehege: Zaun-Rechteck mit Tor
for x in range(c - 12, c - 6):
    for y in range(c - 10, c - 5):
        if x in (c - 12, c - 7) or y in (c - 10, c - 6):
            build("gate" if (x, y) == (c - 10, c - 6) else "fence", x, y)
w.rebuild()
print("Räume:", [(r.role, r.kind, r.size, r.pracht_text) for r in w.rooms])
assert any(r.kind == "hof" for r in w.rooms)
assert w.place("goat", c - 10, c - 8) is None
w.rebuild()
print("mit Ziege:", [(r.role, r.kind) for r in w.rooms])
# Tempel
for x in range(c + 10, c + 17):
    for y in range(c + 4, c + 10):
        if x in (c + 10, c + 16) or y in (c + 4, c + 9):
            build("door_wood" if (x, y) == (c + 13, c + 9) else "wall_stone", x, y)
        else:
            w.place("floor_carpet", x, y)
build("statue", c + 13, c + 5); build("altar", c + 13, c + 6)
w.rebuild()
print("Räume:", [(r.role, r.kind, r.size, r.pracht_text) for r in w.rooms])
# 3 Tage laufen: Ziege muss noch da sein
for _ in range(3 * TICKS_PER_DAY):
    w.popups.clear(); w.tick()
assert any(p.kind == "goat" for p in w.pawns), "Ziege entkommen trotz Gehege"
print("Ziege noch da. Nahrung:", round(w.food), "Mahlzeiten:", round(w.meals), "Felder:", len(w.crops))
# Flucht
m = [p for p in w.members() if p.kind == "member"][0]
m.faith = 5; m.doubter = True; m.mood = 10
w.tick_n = (w.tick_n // TICKS_PER_DAY) * TICKS_PER_DAY + 2 * TICKS_PER_HOUR - 1
n0 = len(w.members())
for _ in range(600):
    w.tick()
    if m.fleeing: break
print("flieht:", m.fleeing, m.status_text(w))
for _ in range(900):
    w.popups.clear(); w.tick()
print("Mitglieder vorher/nachher:", n0, len(w.members()), "| Verdacht", round(w.heat, 1))
# Razzia
w.heat = 90
w.start_raid()
for _ in range(1500):
    w.tick()
    if not w.flags.get("raid_active"): break
print("Razzia:", [p["title"] for p in w.popups], "Guru weg:", w.guru.away if w.guru else None, w.over)
w.popups.clear()
for _ in range(2 * TICKS_PER_DAY + 400):
    w.popups.clear(); w.tick()
print("Guru zurück:", not w.guru.away, "Polizei übrig:", len(w.outsiders("police")))
# Strategie
st = w.strategic
for lv in st.levels.values():
    print(lv.key, lv.rw, lv.rh, "Regionen", len(lv.regions), "min px", min(r.pixels for r in lv.regions.values()),
          "ohne Nachbarn:", [r for r, a in lv.adj.items() if not a])
st.phase = 3
for lv in st.levels.values():
    st._hops(lv)
    for r in lv.regions.values():
        if not r.aggregate:
            r.chapter = 1; r.followers = r.pop * 0.001; st.start_campaign(lv, r, "social")
for d in range(40):
    st.daily()
wl = st.levels["world"]
print("Welt-Anteil nach 40 Tagen:", f"{st.world_share()*100:.3f} %", "Status:", sorted({r.status for r in wl.regions.values()}),
      "max hops", max(r.hops for r in wl.regions.values()), "Einnahmen", round(w.ledger.get('Spenden der Anhänger (Welt)', 0)))
print("OK")
