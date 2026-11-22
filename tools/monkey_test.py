"""Affentest: klickt und tippt zufällig durch die echte Oberfläche (headless) und sucht Abstürze.
Aufruf: uv run python tools/monkey_test.py [frames] [seed]"""
import os, sys, random, time, traceback
os.environ.setdefault("SDL_VIDEODRIVER", "dummy"); os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pygame
from cultsim.ui.app import App
from cultsim.sim import events as ev
from cultsim.data import DATA

frames = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
rng = random.Random(seed)
app = App(audio=False)
import tempfile
app.save_path = Path(tempfile.gettempdir()) / "cultsim_monkey.sav"
KEYS = [pygame.K_b, pygame.K_z, pygame.K_x, pygame.K_m, pygame.K_F1, pygame.K_F2, pygame.K_F3, pygame.K_F10, pygame.K_q, pygame.K_e,
        pygame.K_r, pygame.K_h, pygame.K_SPACE, pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_ESCAPE, pygame.K_F5, pygame.K_F9,
        pygame.K_PLUS, pygame.K_MINUS, pygame.K_TAB]
t_frame = 0.0
games = 0
log = []
try:
    for f in range(frames):
        evs = []
        if app.mode == "menu":
            games += 1
            app.new_game()
            app.speed = 4
            if os.environ.get("MONKEY_LATE"):          # Spätspiel: erst 30 Tage Auto-Spieler, dann Phase 3 erzwingen
                from smoke_test import autoplay
                w0 = app.w
                while w0.day <= 30 and not w0.over:
                    autoplay(w0, rng); w0.tick()
                w0.strategic.phase = 3
                for lv in w0.strategic.levels.values():
                    w0.strategic._hops(lv)
                    for rg in lv.regions.values():
                        if not rg.aggregate:
                            rg.followers = rg.pop * rng.random() * 0.03
                w0.money = 3e8; w0.ep = 900
                for m in w0.members():
                    if m.kind == "member":
                        m.rank = rng.randint(0, 3)
            if games > 1 and rng.random() < 0.5:
                app.w.strategic.phase = rng.choice((2, 3))
                for lv in app.w.strategic.levels.values():
                    app.w.strategic._hops(lv)
                app.w.money = 5e7; app.w.ep = 500
        if not app.running:
            app.running = True
        r = rng.random()
        x, y = rng.randrange(1280), rng.randrange(720)
        if r < 0.45:
            app.ui.fake_mouse = (x, y)
            b = 1 if rng.random() < 0.85 else 3
            evs.append(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=b, pos=(x, y)))
            if rng.random() < 0.3:
                x2, y2 = x + rng.randint(-200, 200), y + rng.randint(-120, 120)
                app.frame(evs, 0.03); evs = []
                app.ui.fake_mouse = (x2, y2); x, y = x2, y2
            evs.append(pygame.event.Event(pygame.MOUSEBUTTONUP, button=b, pos=(x, y)))
            log.append(("click", b, x, y))
        elif r < 0.6:
            k = rng.choice(KEYS)
            evs.append(pygame.event.Event(pygame.KEYDOWN, key=k, unicode="", mod=0))
            log.append(("key", pygame.key.name(k)))
        elif r < 0.68:
            app.ui.fake_mouse = (x, y)
            evs.append(pygame.event.Event(pygame.MOUSEWHEEL, y=rng.choice((-1, 1)), x=0))
        if app.w is not None and app.w.over and rng.random() < 0.2:
            app.mode, app.w = "menu", None
            continue
        if app.w is not None and app.w.popups and rng.random() < 0.6:
            pop = app.w.popups[0]
            ok = [i for i, c in enumerate(pop["choices"]) if not ev.choice_block(app.w, c)]
            if ok:
                ev.choose(app.w, pop, rng.choice(ok))
        if app.w is not None and app.panel == "pause" and rng.random() < 0.7:
            app.panel = None
        if app.w is not None and rng.random() < 0.01:
            app.w.money += 3000
        t0 = time.perf_counter()
        app.frame(evs, 0.05)
        t_frame += time.perf_counter() - t0
        if app.w is not None and app.speed == 0 and rng.random() < 0.3:
            app.speed = 4
except Exception:
    traceback.print_exc()
    print("letzte Eingaben:", log[-8:])
    print("Zustand:", app.mode, app.panel, app.menu, app.tool, app.sel)
    sys.exit(1)
w = app.w
print(f"{frames} Frames ok · {t_frame / frames * 1000:.2f} ms/Frame · Spiele: {games}"
      + (f" · Tag {w.day}, Phase {w.phase}, {len(w.pawns)} Figuren, {len(w.thing_list)} Objekte, Ende: {w.over}" if w else ""))
