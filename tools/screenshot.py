"""Headless-Screenshots der Oberfläche (zur Sichtkontrolle ohne Fenster).
Aufruf: SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy uv run python tools/screenshot.py <zielordner> [tage]"""
import os, sys, random
os.environ.setdefault("SDL_VIDEODRIVER", "dummy"); os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pygame
from cultsim.ui.app import App
from cultsim.sim.world import World
from cultsim.sim import events
from smoke_test import autoplay

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
days = int(sys.argv[2]) if len(sys.argv) > 2 else 12
app = App(audio=False)
ui = app.ui
ui.fake_mouse = (640, 400)

def shot(name, ev=(), n=2):
    for i in range(n):
        app.frame(list(ev) if i == 0 else [], 0.0)
    pygame.image.save(app.screen, str(out / f"{name}.png"))

def click(x, y):
    ui.fake_mouse = (x, y)
    app.frame([pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(x, y))], 0.0)
    app.frame([pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(x, y))], 0.0)

def key(k):
    app.frame([pygame.event.Event(pygame.KEYDOWN, key=k, unicode="", mod=0)], 0.0)

shot("00_menu")
app.new_cult, app.new_guru = "Kirche der Kosmischen Durchlüftung", "Swami Günther"
random.seed(4)
app.start_world(World(11, app.new_cult, app.new_guru, "sterne"))
w = app.w
app.speed = 0
shot("01_start_popup")
rng = random.Random(1)
while w.day <= days and not w.over:
    autoplay(w, rng); w.tick()
w.popups.clear()
c = w.size // 2
m = [p for p in w.members() if p.kind == "member"][0]
m.favorite = True
app.select(("pawn", m.id)); app.view.cx, app.view.cy = c + 2, c
ui.fake_mouse = (500, 300)
shot("02_game_inspector")
key(pygame.K_e); app.view.zoom = 3; app.view.show_rooms = True
shot("03_rotated_rooms")
app.view.zoom = 2; app.view.show_rooms = False; key(pygame.K_q); app.sel = None
key(pygame.K_b); app.set_tool(("build", "wall_stone"))
t0 = app.view.to_window(c + 2, c - 12); t1 = app.view.to_window(c + 8, c - 8)
ui.fake_mouse = t0
app.frame([pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=t0)], 0.0)
ui.fake_mouse = t1
pygame.key.set_mods(pygame.KMOD_SHIFT)
shot("04_build_drag")
app.frame([pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=t1)], 0.0)
pygame.key.set_mods(0)
app.set_tool(None); app.menu = None
ui.fake_mouse = (700, 200)
key(pygame.K_F1); shot("05_members")
key(pygame.K_F2); shot("06_doctrine")
key(pygame.K_F3); shot("07_finance")
key(pygame.K_m); shot("08_map_local")
lv = w.strategic.levels["local"]; app.mapview.sel = lv.order[0]; shot("09_map_region")
w.strategic.phase = 3
for l in w.strategic.levels.values():
    w.strategic._hops(l)
    for r in l.regions.values():
        if not r.aggregate:
            r.followers = r.pop * rng.random() * 0.04; r.heat = rng.random() * 80; r.chapter = rng.randint(0, 2)
for d in range(3): w.strategic.daily()
app.mapview.level = "country"; app.mapview.sel = "by"; shot("10_map_country")
app.mapview.level = "world"; app.mapview.sel = None; app.mapview.mode = "verdacht"; shot("11_map_world")
app.mapview.mode = "sprache"; app.mapview.sel = "us"; app.mapview.zoom = 2; app.mapview.off = [900, 150]; shot("12_map_world_zoom")
key(pygame.K_m)
pool = [(k, e) for k, e in __import__("cultsim.data", fromlist=["DATA"]).DATA.events.items()]
e = dict(pool[0][1]); ctx = {"member": m.id}
events.popup(w, e["title"], events.fill(w, e["text"], ctx), [dict(ch, label=events.fill(w, ch["label"], ctx)) for ch in e["choices"]], ctx)
shot("13_event")
w.popups.clear()
w.tick_n += 1700 - (w.tick_n % 2400) if (w.tick_n % 2400) < 1700 else 0
w.heat = 90; w.start_raid()
for _ in range(260): w.tick()
app.view.cx, app.view.cy = c, c + 12
shot("14_raid")
key(pygame.K_F10); shot("15_help")
print("ok", sorted(p.name for p in out.glob("*.png")))
