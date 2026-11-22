"""Minimales Immediate-Mode-UI (Buttons, Text, Balken, Tooltips, Scrollbereiche)."""
from __future__ import annotations

import pygame

from ..data import ROOT

BG = (27, 22, 36)
BG2 = (40, 33, 54)
BG3 = (58, 48, 78)
EDGE = (196, 158, 72)
TEXT = (236, 229, 212)
DIM = (158, 148, 170)
GOOD = (126, 214, 126)
BAD = (238, 98, 88)
WARN = (242, 192, 84)
GOLD = (236, 190, 80)
PURPLE = (150, 100, 210)
KIND_COL = {"info": TEXT, "good": GOOD, "bad": BAD, "warn": WARN}


class UI:
    def __init__(self, assets):
        self.assets = assets
        f = ROOT / "assets" / "fonts" / "ui.ttf"
        if f.exists():                      # eigene Schrift: assets/fonts/ui.ttf (+ optional ui-bold.ttf)
            reg = bold = str(f)
            fb = f.with_name("ui-bold.ttf")
            if fb.exists():
                bold = str(fb)
        else:
            names = "dejavusans,segoeui,verdana,notosans,liberationsans,arial"
            reg, bold = pygame.font.match_font(names), pygame.font.match_font(names, bold=True)
        self.fonts = {k: pygame.font.Font(bold if b else reg, s)
                      for k, s, b in (("s", 13, 0), ("m", 15, 0), ("b", 18, 1), ("t", 40, 1))}
        self._tc: dict = {}
        self.rects: list[pygame.Rect] = []
        self.rects_prev: list[pygame.Rect] = []
        self.blockers: list[tuple] = []          # (layer, rect, exklusiv)
        self.layer = 0
        self.fake_mouse = None
        self.scroll: dict[str, int] = {}
        self.focus = None
        self.mx = self.my = 0
        self.click = self.rclick = self.used = False
        self.wheel = 0
        self.typed = ""
        self.keys: list[int] = []
        self.tip = None
        self.screen = None
        self.clip = None

    # ------------------------------------------------------------ Rahmen
    def begin(self, screen, events):
        self.screen = screen
        self.mx, self.my = self.fake_mouse or pygame.mouse.get_pos()
        self.click = self.rclick = self.used = False
        self.wheel = 0
        self.typed = ""
        self.keys = []
        for e in events:
            if e.type == pygame.MOUSEBUTTONUP:
                if e.button == 1:
                    self.click = True
                elif e.button == 3:
                    self.rclick = True
            elif e.type == pygame.MOUSEWHEEL:
                self.wheel += e.y
            elif e.type == pygame.KEYDOWN:
                self.keys.append(e.key)
                if e.unicode and e.unicode.isprintable():
                    self.typed += e.unicode
        self.rects_prev, self.rects = self.rects, []
        self.clip = None
        self.blockers = []
        self.tip = None
        self.layer = 0

    def end(self):
        if self.tip:
            lines = self._wrap_lines(self.tip, 360, self.fonts["s"])
            w = max(self.fonts["s"].size(l)[0] for l in lines) + 16
            h = len(lines) * 18 + 12
            sw, sh = self.screen.get_size()
            x = min(self.mx + 16, sw - w - 4)
            y = self.my + 20 if self.my + 20 + h < sh else self.my - h - 6
            r = pygame.Rect(x, y, w, h)
            pygame.draw.rect(self.screen, (16, 13, 22), r, border_radius=4)
            pygame.draw.rect(self.screen, EDGE, r, 1, border_radius=4)
            for i, l in enumerate(lines):
                self.text(x + 8, y + 6 + i * 18, l, TEXT, "s")

    def can_input(self):
        for layer, rect, excl in self.blockers:
            if layer > self.layer and (excl or rect.collidepoint(self.mx, self.my)):
                return False
        return True

    def over_ui(self, pos=None):
        x, y = pos or (self.mx, self.my)
        return any(r.collidepoint(x, y) for r in self.rects) or any(r.collidepoint(x, y) for r in self.rects_prev)

    def hover(self, rect):
        if self.clip is not None and not self.clip.collidepoint(self.mx, self.my):
            return False
        return rect.collidepoint(self.mx, self.my) and self.can_input()

    # ------------------------------------------------------------ Zeichnen
    def render(self, s, color=TEXT, font="s"):
        key = (font, s, color)
        surf = self._tc.get(key)
        if surf is None:
            if len(self._tc) > 3000:
                self._tc.clear()
            surf = self._tc[key] = self.fonts[font].render(s, True, color)
        return surf

    def text(self, x, y, s, color=TEXT, font="s", right=False, center=False):
        surf = self.render(str(s), color, font)
        if right:
            x -= surf.get_width()
        elif center:
            x -= surf.get_width() // 2
        self.screen.blit(surf, (x, y))
        return surf.get_width()

    def _wrap_lines(self, s, w, font):
        out = []
        for para in str(s).split("\n"):
            line = ""
            for word in para.split(" "):
                t = (line + " " + word) if line else word
                if font.size(t)[0] <= w:
                    line = t
                else:
                    if line:
                        out.append(line)
                    line = word
            out.append(line)
        return out

    def wrap(self, x, y, w, s, color=TEXT, font="s", lh=None, draw=True):
        f = self.fonts[font]
        lh = lh or f.get_linesize() + 2
        lines = self._wrap_lines(s, w, f)
        if draw:
            for i, l in enumerate(lines):
                if l:
                    self.text(x, y + i * lh, l, color, font)
        return len(lines) * lh

    def panel(self, rect, title=None, alpha=240, edge=EDGE):
        rect = pygame.Rect(rect)
        if alpha >= 255:
            pygame.draw.rect(self.screen, BG, rect, border_radius=5)
        else:
            s = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(s, (*BG, alpha), s.get_rect(), border_radius=5)
            self.screen.blit(s, rect)
        if edge:
            pygame.draw.rect(self.screen, edge, rect, 1, border_radius=5)
        self.rects.append(rect)
        if title:
            self.text(rect.x + 12, rect.y + 8, title, GOLD, "b")
        return rect

    def button(self, rect, label, tip=None, enabled=True, active=False, icon=None, font="s", color=None, align="center"):
        rect = pygame.Rect(rect)
        hov = self.hover(rect)
        bg = BG3 if active else BG2
        if hov and enabled:
            bg = tuple(min(255, c + 24) for c in bg)
        pygame.draw.rect(self.screen, bg, rect, border_radius=4)
        pygame.draw.rect(self.screen, EDGE if active else (88, 76, 110), rect, 1, border_radius=4)
        col = color or (TEXT if enabled else (112, 104, 124))
        x = rect.x + 6
        if icon is not None:
            self.screen.blit(icon, (x, rect.centery - icon.get_height() // 2))
            x += icon.get_width() + 5
        if label:
            surf = self.render(label, col, font)
            if align == "center" and icon is None:
                x = rect.centerx - surf.get_width() // 2
            self.screen.blit(surf, (x, rect.centery - surf.get_height() // 2))
        if hov and tip:
            self.tip = tip
        if hov and enabled and self.click and not self.used:
            self.used = True
            self.assets.play("click")
            return True
        return False

    def bar(self, rect, frac, color, label=None, bg=(18, 15, 24), mark=None):
        rect = pygame.Rect(rect)
        pygame.draw.rect(self.screen, bg, rect, border_radius=3)
        f = max(0.0, min(1.0, frac))
        if f > 0:
            pygame.draw.rect(self.screen, color, (rect.x, rect.y, max(2, int(rect.w * f)), rect.h), border_radius=3)
        if mark is not None:
            mx = rect.x + int(rect.w * max(0.0, min(1.0, mark)))
            pygame.draw.line(self.screen, TEXT, (mx, rect.y - 2), (mx, rect.bottom + 1), 2)
        pygame.draw.rect(self.screen, (80, 70, 100), rect, 1, border_radius=3)
        if label:
            ls = self.render(label, TEXT, "s")
            sh = self.render(label, (12, 10, 18), "s")
            lx, ly = rect.centerx - ls.get_width() // 2, rect.centery - ls.get_height() // 2
            self.screen.blit(sh, (lx + 1, ly + 1))
            self.screen.blit(ls, (lx, ly))

    def axis_bar(self, rect, value, target, neg, pos):
        """Balken von -100 bis +100 mit Mittelstrich."""
        rect = pygame.Rect(rect)
        pygame.draw.rect(self.screen, (18, 15, 24), rect, border_radius=3)
        mid = rect.centerx
        w = int(rect.w / 2 * max(-1.0, min(1.0, value / 100)))
        col = GOLD if value >= 0 else PURPLE
        pygame.draw.rect(self.screen, col, (min(mid, mid + w), rect.y + 1, abs(w), rect.h - 2))
        tx = mid + int(rect.w / 2 * max(-1.0, min(1.0, target / 100)))
        pygame.draw.polygon(self.screen, TEXT, [(tx - 4, rect.y - 5), (tx + 4, rect.y - 5), (tx, rect.y + 1)])
        pygame.draw.line(self.screen, DIM, (mid, rect.y), (mid, rect.bottom - 1))
        pygame.draw.rect(self.screen, (80, 70, 100), rect, 1, border_radius=3)
        self.text(rect.x, rect.bottom + 2, neg, PURPLE if value < -15 else DIM, "s")
        self.text(rect.right, rect.bottom + 2, pos, GOLD if value > 15 else DIM, "s", right=True)

    def tooltip(self, rect, text):
        if self.hover(pygame.Rect(rect)):
            self.tip = text

    def textfield(self, key, rect, value, maxlen=40):
        rect = pygame.Rect(rect)
        if self.click and self.can_input():
            if rect.collidepoint(self.mx, self.my):
                self.focus = key
            elif self.focus == key:
                self.focus = None
        foc = self.focus == key
        if foc:
            for k in self.keys:
                if k == pygame.K_BACKSPACE:
                    value = value[:-1]
                elif k in (pygame.K_RETURN, pygame.K_ESCAPE):
                    self.focus = None
            value = (value + self.typed)[:maxlen]
        pygame.draw.rect(self.screen, (16, 13, 22), rect, border_radius=4)
        pygame.draw.rect(self.screen, EDGE if foc else (88, 76, 110), rect, 1, border_radius=4)
        self.text(rect.x + 8, rect.centery - 10, value + ("|" if foc and pygame.time.get_ticks() % 900 < 450 else ""), TEXT, "m")
        return value

    def scroll_area(self, key, rect, content_h):
        """Beginnt einen geklippten Scrollbereich. Liefert den y-Versatz. Mit end_scroll() schließen."""
        rect = pygame.Rect(rect)
        off = self.scroll.get(key, 0)
        mx = max(0, content_h - rect.h)
        if self.hover(rect) and self.wheel:
            off -= self.wheel * 40
            self.wheel = 0
        off = max(0, min(mx, off))
        self.scroll[key] = off
        self.screen.set_clip(rect)
        self.clip = rect
        if mx > 0:
            h = max(20, rect.h * rect.h // content_h)
            y = rect.y + (rect.h - h) * off // mx
            pygame.draw.rect(self.screen, (90, 78, 112), (rect.right - 5, y, 4, h), border_radius=2)
        return off

    def end_scroll(self):
        self.screen.set_clip(None)
        self.clip = None
