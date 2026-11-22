"""Hauptschleife: Eingabe, Werkzeuge (Bauen/Zonen/Abriss), Kamera, Simulationstakt, Speichern/Laden."""
from __future__ import annotations

import random
import sys

import pygame

from ..assets import Assets
from ..config import *
from ..data import DATA, ROOT
from ..sim.world import World
from . import hud
from .mapview import MapView
from .render import IsoView
from .widgets import UI, GOLD, TEXT, BAD, WARN

PANEL_SIZE = {"members": (1000, 580), "doctrine": (1100, 600), "finance": (860, 540), "help": (860, 520), "pause": (320, 330)}
PANEL_DRAW = {"members": hud.draw_members, "doctrine": hud.draw_doctrine, "finance": hud.draw_finance,
              "help": hud.draw_help, "pause": hud.draw_pause}


class App:
    def __init__(self, size=(1280, 720), fullscreen=False, audio=True):
        pygame.init()
        pygame.display.set_caption(f"{TITLE} – {VERSION}")
        flags = pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE
        self.screen = pygame.display.set_mode((0, 0) if fullscreen else size, flags)
        self.windowed_size = size
        self.fullscreen = fullscreen
        DATA.load()
        self.assets = Assets(audio=audio)
        self.ui = UI(self.assets)
        self.rng = random.Random()
        self.clock = pygame.time.Clock()
        self.running = True
        self.mode = "menu"
        self.w: World | None = None
        self.view: IsoView | None = None
        self.mapview: MapView | None = None
        self.save_path = ROOT / "saves" / "quicksave.sav"
        nm = DATA.names
        self.new_cult = f"{self.rng.choice(nm['cult_prefix'])} {self.rng.choice(nm['cult_core'])}"
        self.new_guru = self.rng.choice(nm["guru_names"])
        self.new_myth = DATA.doctrine["myths"][0]["id"]
        self.reset_ui()
        self.assets.start_music()

    def reset_ui(self):
        self.speed = 1
        self.acc = 0.0
        self.tool = None
        self.menu = None
        self.build_cat = "Struktur"
        self.panel = None
        self.sel = None
        self.follow = None
        self.confirm = None
        self.drag = None
        self.flash = None

    # ------------------------------------------------------------ Spielstände
    def start_world(self, w):
        self.w = w
        self.view = IsoView(self.assets, w.size)
        self.mapview = MapView(self)
        g = w.guru
        if g is not None:
            self.view.cx, self.view.cy = g.x, g.y - 3
        self.reset_ui()
        self.mode = "game"

    def new_game(self):
        self.start_world(World(None, self.new_cult.strip(), self.new_guru.strip(), self.new_myth))

    def save_game(self):
        try:
            self.save_path.parent.mkdir(exist_ok=True)
            self.w.save(self.save_path)
            self.w.notify("Spielstand gespeichert.", "info")
        except Exception as e:
            self.say(f"Speichern fehlgeschlagen: {e}")

    def load_game(self):
        if not self.save_path.exists():
            return self.say("Kein Spielstand vorhanden.")
        try:
            w = World.load(self.save_path)
        except Exception as e:
            return self.say(f"Laden fehlgeschlagen: {e}")
        self.start_world(w)
        w.notify("Spielstand geladen.", "info")

    def menu_action(self, act):
        if act == "resume":
            self.panel = None
        elif act == "save":
            self.save_game()
            self.panel = None
        elif act == "load":
            self.load_game()
        elif act == "music":
            self.assets.toggle_music()
        elif act == "menu":
            self.mode, self.w = "menu", None
        elif act == "quit":
            self.running = False

    # ------------------------------------------------------------ UI-Zustand
    def say(self, text):
        self.flash = (text, pygame.time.get_ticks() + 2600)
        self.assets.play("error")

    def select(self, sel):
        self.sel = sel
        self.confirm = None

    def set_tool(self, tool):
        self.tool = tool
        self.drag = None

    def toggle_menu(self, m):
        self.menu = None if self.menu == m else m
        self.set_tool(None)
        if self.menu:
            self.panel = None

    def toggle_panel(self, p):
        self.panel = None if self.panel == p else p
        if self.panel:
            self.menu = None
            self.set_tool(None)

    def panel_rect(self):
        W, H = self.screen.get_size()
        if self.panel == "map":
            return pygame.Rect(0, hud.TOP_H + 1, W, H - hud.TOP_H - hud.BOT_H - 1)
        return hud.panel_rect(self, *PANEL_SIZE[self.panel])

    # ------------------------------------------------------------ Werkzeuge
    def drag_tiles(self, a, b):
        tool = self.tool
        shape = "rect"
        if tool[0] == "build":
            shape = DATA.buildables[tool[1]].get("drag", "single")
        x0, y0 = a
        x1, y1 = b
        if shape == "single":
            return [b]
        shift = pygame.key.get_mods() & pygame.KMOD_SHIFT
        xa, xb, ya, yb = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
        if shape == "line":
            if shift:
                return [(x, y) for y in range(ya, yb + 1) for x in range(xa, xb + 1) if x in (xa, xb) or y in (ya, yb)]
            if abs(x1 - x0) >= abs(y1 - y0):
                return [(x, y0) for x in range(xa, xb + 1)]
            return [(x0, y) for y in range(ya, yb + 1)]
        return [(x, y) for y in range(ya, yb + 1) for x in range(xa, xb + 1)]

    def preview(self, hover):
        w, tool = self.w, self.tool
        if tool is None or hover is None:
            return [], 0
        tiles = self.drag_tiles(self.drag, hover) if self.drag else [hover]
        tiles = [t for t in tiles if w.inb(*t)][:900]
        if tool[0] == "build":
            out, cost = [], 0
            for x, y in tiles:
                ok = w.can_place(tool[1], x, y) is None
                if ok:
                    cost += w.place_cost(tool[1], x, y)
                out.append((x, y, tool[1], ok))
            return out, cost
        if tool[0] == "zone":
            return [(x, y, tool[1] if tool[1] else -1, True) for x, y in tiles], 0
        return [(x, y, None, True) for x, y in tiles], 0

    def apply_tool(self, a, b):
        w, tool = self.w, self.tool
        tiles = [t for t in self.drag_tiles(a, b) if w.inb(*t)]
        if tool[0] == "build":
            n, err = 0, None
            for x, y in tiles:
                e = w.place(tool[1], x, y)
                if e is None:
                    n += 1
                else:
                    err = e
            if n:
                self.assets.play("place")
            elif err:
                self.say(err)
        elif tool[0] == "zone":
            for x, y in tiles:
                w.set_zone(x, y, tool[1])
            self.assets.play("place")
        elif tool[0] == "demolish":
            if sum(1 for x, y in tiles if w.remove(x, y)):
                self.assets.play("place")

    def pick(self, pos):
        """Was liegt unter dem Mauszeiger? Figur vor Objekt vor Kachel."""
        w, v = self.w, self.view
        z = v.zoom
        best, bd = None, 1e9
        for p in w.pawns:
            if p.away:
                continue
            sx, sy = v.to_window(p.x, p.y)
            dx, dy = pos[0] - sx, pos[1] - (sy - 8 * z)
            if abs(dx) < 7 * z and abs(dy) < 11 * z and dx * dx + dy * dy < bd:
                best, bd = p, dx * dx + dy * dy
        if best is not None:
            return ("pawn", best.id)
        tx, ty = v.tile_at(*pos)
        if not w.inb(tx, ty):
            return None
        th = w.thing_at(tx, ty)
        if th is None:                      # hohe Objekte: Klick auf den oberen Teil trifft die Kachel dahinter
            for k in (1, 2):
                ax, ay = v.tile_at(pos[0], pos[1] + 16 * z * k)
                o = w.thing_at(ax, ay) if w.inb(ax, ay) else None
                if o is not None and o.defn["kind"] in ("wall", "door", "object", "nature") and \
                        self.assets.frames(o.defn["sprite"])[2] >= 16 * k + 8:
                    th = o
                    break
        if th is not None:
            return ("thing", th.id)
        return ("tile", tx, ty)

    def world_input(self, events, hover):
        w, v, ui = self.w, self.view, self.ui
        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN:
                if ui.over_ui(e.pos):
                    continue
                if e.button == 1 and self.tool is not None:
                    self.drag = v.tile_at(*e.pos)
            elif e.type == pygame.MOUSEBUTTONUP:
                if e.button == 1:
                    if self.drag is not None:
                        self.apply_tool(self.drag, v.tile_at(*e.pos))
                        self.drag = None
                    elif not ui.over_ui(e.pos) and not ui.used and self.tool is None:
                        self.select(self.pick(e.pos))
                        self.follow = None
                elif e.button == 3 and not ui.over_ui(e.pos):
                    if self.tool is not None or self.drag is not None:
                        self.set_tool(None)
                    elif self.sel and self.sel[0] == "pawn" and w.pawn_ids.get(self.sel[1]) is w.guru and w.guru is not None:
                        tx, ty = v.tile_at(*e.pos)
                        g = w.guru
                        if w.inb(tx, ty) and not g.away:
                            g.orders = [("goto", tx, ty)]
                            g.cancel_job(w)
                    else:
                        self.sel = None
            elif e.type == pygame.MOUSEWHEEL:
                if not ui.over_ui() and ui.wheel:
                    v.zoom = max(1, min(4, v.zoom + (1 if e.y > 0 else -1)))
            elif e.type == pygame.MOUSEMOTION:
                if e.buttons[1]:
                    v.pan_screen(-e.rel[0], -e.rel[1])
                    self.follow = None

    def keys(self, events):
        v = self.view
        for e in events:
            if e.type != pygame.KEYDOWN:
                continue
            k = e.key
            if k == pygame.K_ESCAPE:
                if self.tool is not None:
                    self.set_tool(None)
                elif self.menu:
                    self.menu = None
                elif self.panel:
                    self.panel = None
                elif self.sel:
                    self.sel = None
                else:
                    self.panel = "pause"
            elif k == pygame.K_SPACE:
                self.speed = 0 if self.speed else 1
            elif k in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.speed = {pygame.K_1: 1, pygame.K_2: 2, pygame.K_3: 4}[k]
            elif k == pygame.K_q:
                v.rotate(-1)
            elif k == pygame.K_e:
                v.rotate(1)
            elif k == pygame.K_b:
                self.toggle_menu("build")
            elif k == pygame.K_z:
                self.toggle_menu("zone")
            elif k == pygame.K_x:
                self.menu = None
                self.set_tool(None if self.tool == ("demolish",) else ("demolish",))
            elif k == pygame.K_m or k == pygame.K_TAB:
                self.toggle_panel("map")
            elif k == pygame.K_F1:
                self.toggle_panel("members")
            elif k == pygame.K_F2:
                self.toggle_panel("doctrine")
            elif k == pygame.K_F3:
                self.toggle_panel("finance")
            elif k == pygame.K_F10:
                self.toggle_panel("help")
            elif k == pygame.K_r:
                v.show_rooms = not v.show_rooms
            elif k == pygame.K_h:
                v.low_walls = not v.low_walls
            elif k == pygame.K_n:
                self.assets.toggle_music()
            elif k == pygame.K_F5:
                self.save_game()
            elif k == pygame.K_F9:
                self.load_game()
            elif k in (pygame.K_PLUS, pygame.K_KP_PLUS):
                v.zoom = min(4, v.zoom + 1)
            elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
                v.zoom = max(1, v.zoom - 1)

    # ------------------------------------------------------------ Frame
    def frame(self, events, dt):
        for e in events:
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                self.fullscreen = not self.fullscreen
                pygame.display.set_mode((0, 0) if self.fullscreen else self.windowed_size,
                                        pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE)
        self.screen = pygame.display.get_surface()
        ui = self.ui
        ui.begin(self.screen, events)
        if self.mode == "menu":
            hud.draw_menu(self)
            ui.end()
            return
        w, v = self.w, self.view
        W, H = self.screen.get_size()
        modal = bool(w.popups) or bool(w.over)
        if modal:
            ui.blockers.append((2, self.screen.get_rect(), True))
        if self.panel:
            ui.blockers.append((1, self.panel_rect(), self.panel == "pause"))
        if not modal and ui.focus is None:
            self.keys(events)
            if self.mode != "game":         # Laden/Hauptmenü per Taste
                return
            w, v = self.w, self.view
        # Simulation
        if not modal and self.panel != "pause" and self.speed:
            self.acc += dt * TPS * self.speed
            n = min(int(self.acc), 200)
            self.acc -= int(self.acc)
            for _ in range(n):
                w.tick()
                if w.popups or w.over:
                    self.acc = 0.0
                    break
        if w.cues:
            for c in set(w.cues):
                self.assets.play(c)
            w.cues.clear()
        # Kamera
        if not modal and ui.focus is None and self.panel is None:
            ks = pygame.key.get_pressed()
            dx = (ks[pygame.K_d] or ks[pygame.K_RIGHT]) - (ks[pygame.K_a] or ks[pygame.K_LEFT])
            dy = (ks[pygame.K_s] or ks[pygame.K_DOWN]) - (ks[pygame.K_w] or ks[pygame.K_UP])
            if dx or dy:
                v.pan_screen(dx * 700 * dt, dy * 700 * dt)
                self.follow = None
        fp = w.pawn_ids.get(self.follow) if self.follow else None
        if fp is not None and not fp.away:
            v.cx, v.cy = fp.x, fp.y
        v.set_view(W, H)
        blocked = modal or self.panel is not None
        hover = None
        if not blocked and not ui.over_ui():
            hover = v.tile_at(ui.mx, ui.my)
            if not w.inb(*hover):
                hover = None
        prev, cost = self.preview(hover)
        st = {"tick": pygame.time.get_ticks() // 50, "hover": hover if self.tool is None else None, "preview": prev}
        if self.sel:
            if self.sel[0] == "pawn":
                st["sel_pawn"] = w.pawn_ids.get(self.sel[1])
            elif self.sel[0] == "thing":
                st["sel_thing"] = w.thing_ids.get(self.sel[1])
            else:
                st["sel_tile"] = (self.sel[1], self.sel[2])
        if self.panel == "map":
            self.screen.fill((14, 17, 24))
        else:
            v.draw(self.screen, w, st, self.acc if self.speed and not modal else 0.0)
            self.world_labels(st)
        # HUD (Ebene 0)
        if self.panel != "map":
            hud.draw_notes(self)
        hud.draw_top(self)
        hud.draw_bottom(self)
        if self.menu and self.panel is None:
            hud.draw_build_menu(self)
        if self.panel != "map":
            hud.draw_inspector(self)
        if self.tool is not None and not blocked:
            self.tool_hint(cost)
        # Panels (Ebene 1), Popups (Ebene 2)
        ui.layer = 1
        if self.panel == "map":
            self.mapview.draw()
        elif self.panel:
            PANEL_DRAW[self.panel](self)
            if self.mode != "game":
                return
        ui.layer = 2
        if modal:
            hud.draw_popup(self)
            if self.mode != "game" or not self.running:
                return
        elif not blocked or self.drag is not None:
            ui.layer = 0
            self.world_input(events, hover)
        if self.flash and pygame.time.get_ticks() < self.flash[1]:
            s = ui.render(self.flash[0], BAD, "m")
            r = s.get_rect(center=(W // 2, H - hud.BOT_H - 40)).inflate(24, 12)
            pygame.draw.rect(self.screen, (16, 12, 22), r, border_radius=5)
            pygame.draw.rect(self.screen, BAD, r, 1, border_radius=5)
            self.screen.blit(s, s.get_rect(center=r.center))
        ui.end()

    def world_labels(self, st):
        w, v, ui = self.w, self.view, self.ui
        z = v.zoom
        sel = st.get("sel_pawn")
        for p in w.pawns:
            if p.away or not (p.favorite or p is sel or p.kind == "guru" or p.fleeing):
                continue
            sx, sy = v.to_window(p.x, p.y)
            col = GOLD if p.kind == "guru" else BAD if p.fleeing else TEXT
            name = p.name.split()[0] if p.kind == "member" else p.name
            s = ui.render(name, col, "s")
            sh = ui.render(name, (10, 8, 14), "s")
            x, y = sx - s.get_width() // 2, sy - 27 * z - 8
            self.screen.blit(sh, (x + 1, y + 1))
            self.screen.blit(s, (x, y))
        if v.show_rooms:
            for r in w.rooms:
                sx, sy = v.to_window(r.cx, r.cy)
                s = ui.render(r.role, (255, 250, 235), "s")
                bg = pygame.Rect(0, 0, s.get_width() + 10, 19)
                bg.center = (sx, sy - 6 * z)
                pygame.draw.rect(self.screen, (16, 12, 22), bg, border_radius=4)
                self.screen.blit(s, (bg.x + 5, bg.y + 2))

    def tool_hint(self, cost):
        ui, tool = self.ui, self.tool
        W, H = self.screen.get_size()
        if tool[0] == "build":
            d = DATA.buildables[tool[1]]
            txt = f"{d['name']}: " + {"line": "Ziehen für eine Linie · Shift: Rechteck-Umriss", "rect": "Ziehen für eine Fläche",
                                     "single": "Klicken zum Platzieren"}[d.get("drag", "single")]
        elif tool[0] == "zone":
            txt = (ZONES[tool[1]][0] if tool[1] else "Zone löschen") + ": Fläche aufziehen"
        else:
            txt = "Abriss: Fläche aufziehen (Bauaufträge werden voll erstattet)"
        txt += " · Rechtsklick: ablegen"
        s = ui.render(txt, TEXT, "s")
        r = s.get_rect(midbottom=(W // 2, H - hud.BOT_H - 8)).inflate(20, 10)
        if self.menu:
            r.bottom = hud.TOP_H + 40
        pygame.draw.rect(self.screen, (16, 12, 22), r, border_radius=5)
        self.screen.blit(s, s.get_rect(center=r.center))
        if cost and not ui.over_ui():
            ok = self.w.money >= cost
            ui.text(ui.mx + 18, ui.my + 14, f"{cost} €", GOLD if ok else BAD, "m")

    def run(self):
        while self.running:
            dt = min(0.1, self.clock.tick(60) / 1000.0)
            self.frame(pygame.event.get(), dt)
            pygame.display.flip()
        pygame.quit()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    size = (1280, 720)
    for a in argv:
        if a.startswith("--size="):
            w, h = a.split("=")[1].lower().split("x")
            size = (int(w), int(h))
    app = App(size, fullscreen="--fullscreen" in argv, audio="--no-audio" not in argv)
    if "--load" in argv:
        app.load_game()
    app.run()
