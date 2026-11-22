"""Asset-Verwaltung: Sprites, Sounds, Musik – alles über assets/manifest.json austauschbar.

Reihenfolge: assets/manifest.json, danach überlagern mods/<name>/assets/manifest.json.
Fehlt eine Datei, erzeugt das Spiel einen (hässlichen, aber funktionierenden) Platzhalter.
"""
from __future__ import annotations

import json

import pygame

from .data import ROOT, mod_dirs


class Assets:
    def __init__(self, audio=True):
        self.entries: dict[str, dict] = {}
        self.sound_entries: dict[str, dict] = {}
        self.music: list[dict] = []
        for d in [ROOT / "assets"] + [m / "assets" for m in mod_dirs()]:
            mf = d / "manifest.json"
            if not mf.exists():
                continue
            try:
                man = json.loads(mf.read_text("utf-8"))
            except Exception as e:                     # kaputtes Manifest soll das Spiel nicht verhindern
                print(f"[assets] {mf}: {e}")
                continue
            for k, v in man.get("sprites", {}).items():
                self.entries[k] = dict(v, _dir=d)
            for k, v in man.get("sounds", {}).items():
                self.sound_entries[k] = dict(v, _dir=d)
            if man.get("music"):
                self.music = [dict(m, _dir=d) for m in man["music"]]
        self._frames: dict[str, tuple] = {}
        self._cache: dict = {}
        self._sounds: dict = {}
        self.audio = False
        self.music_on = True
        if audio:
            try:
                pygame.mixer.init(22050, -16, 2, 512)
                self.audio = True
            except Exception as e:
                print(f"[assets] kein Ton: {e}")

    # ------------------------------------------------------------ Sprites
    def has(self, sid):
        e = self.entries.get(sid)
        return e is not None and (e["_dir"] / e["file"]).exists()

    def frames(self, sid):
        f = self._frames.get(sid)
        if f is None:
            f = self._frames[sid] = self._load(sid)
        return f

    def _load(self, sid):
        e = self.entries.get(sid)
        if e is not None:
            try:
                img = pygame.image.load(str(e["_dir"] / e["file"])).convert_alpha()
                n = max(1, int(e.get("frames", 1)))
                fw = img.get_width() // n
                fr = [img.subsurface((i * fw, 0, fw, img.get_height())).copy() for i in range(n)]
                ax, ay = e.get("anchor", [fw // 2, img.get_height() - 8])
                return fr, ax, ay
            except Exception as ex:
                print(f"[assets] {sid}: {ex}")
        return self._placeholder(sid)

    def _placeholder(self, sid):
        h = sum(ord(c) * (i + 3) for i, c in enumerate(sid))
        col = (60 + h % 160, 60 + (h // 7) % 160, 60 + (h // 53) % 160)
        dia = [(16, 0), (31, 7), (31, 8), (16, 15), (15, 15), (0, 8), (0, 7), (15, 0)]
        if sid.startswith(("terrain_", "floor_", "tile_mask", "cursor", "mat")):
            s = pygame.Surface((32, 16), pygame.SRCALPHA)
            if sid == "cursor":
                pygame.draw.polygon(s, (255, 255, 255), dia, 1)
            else:
                pygame.draw.polygon(s, (255, 255, 255) if sid == "tile_mask" else col, dia)
            return [s], 16, 8
        if sid.startswith(("pawn_", "acc_")):
            s = pygame.Surface((12, 18), pygame.SRCALPHA)
            if sid.startswith("pawn_skin"):
                pygame.draw.rect(s, (255, 255, 255), (4, 1, 4, 4))
            elif sid.startswith(("pawn_robe", "pawn_civ")):
                pygame.draw.rect(s, (230, 230, 230), (3, 5, 6, 11))
            elif sid.startswith("pawn_hair"):
                pygame.draw.rect(s, (255, 255, 255), (4, 0, 4, 2))
            return [s, s, s], 6, 16
        if sid.startswith("fx_"):
            s = pygame.Surface((9, 9), pygame.SRCALPHA)
            pygame.draw.circle(s, col, (4, 4), 4)
            return [s], 4, 8
        if sid.startswith("icon_"):
            s = pygame.Surface((16, 16), pygame.SRCALPHA)
            pygame.draw.rect(s, col, (2, 2, 12, 12), border_radius=3)
            return [s], 0, 0
        if sid.startswith(("fence_", "gate_")):
            s = pygame.Surface((32, 28), pygame.SRCALPHA)
            if sid.endswith("post"):
                pygame.draw.rect(s, col, (14, 8, 4, 14))
            else:
                dx = 8 if sid.endswith("e") else -8
                dy = 4 if "_s" in sid else -4
                pygame.draw.line(s, col, (16, 14), (16 + dx, 14 + dy), 2)
            return [s], 16, 20
        if sid == "goat":
            s = pygame.Surface((16, 14), pygame.SRCALPHA)
            pygame.draw.rect(s, (235, 235, 225), (2, 4, 11, 6))
            return [s, s], 8, 12
        low = sid.endswith("_low")
        hgt = 5 if low else 16
        s = pygame.Surface((32, 16 + hgt), pygame.SRCALPHA)
        top = [(x, y) for x, y in dia]
        pygame.draw.polygon(s, tuple(c * 6 // 10 for c in col), [(0, 8), (15, 15), (15, 15 + hgt), (0, 8 + hgt)])
        pygame.draw.polygon(s, tuple(c * 4 // 10 for c in col), [(16, 15), (31, 8), (31, 8 + hgt), (16, 15 + hgt)])
        pygame.draw.polygon(s, col, top)
        s2 = pygame.Surface((32, 16 + hgt), pygame.SRCALPHA)
        s2.blit(s, (0, hgt))
        s2.blit(s, (0, 0))
        return [s2], 16, 8 + hgt

    def get(self, sid, frame=0):
        fr, ax, ay = self.frames(sid)
        return fr[frame % len(fr)], ax, ay

    def nframes(self, sid):
        return len(self.frames(sid)[0])

    def tinted(self, sid, frame, color, alpha=255):
        key = ("t", sid, frame, color, alpha)
        s = self._cache.get(key)
        if s is None:
            s = self.get(sid, frame)[0].copy()
            s.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
            if alpha < 255:
                s.set_alpha(alpha)
            self._cache[key] = s
        return s

    def ghost(self, sid, frame=0, ok=True):
        key = ("g", sid, frame, ok)
        s = self._cache.get(key)
        if s is None:
            s = self.get(sid, frame)[0].copy()
            s.fill((150, 200, 255, 255) if ok else (255, 110, 110, 255), special_flags=pygame.BLEND_RGBA_MULT)
            s.set_alpha(150)
            self._cache[key] = s
        return s

    def icon(self, sid, scale=1):
        key = ("i", sid, scale)
        s = self._cache.get(key)
        if s is None:
            s = self.get(sid)[0]
            if scale != 1:
                s = pygame.transform.scale(s, (int(s.get_width() * scale), int(s.get_height() * scale)))
            self._cache[key] = s
        return s

    # ------------------------------------------------------------ Ton
    def play(self, sid):
        if not self.audio:
            return
        snd = self._sounds.get(sid)
        if snd is None:
            e = self.sound_entries.get(sid)
            if e is None:
                return
            try:
                snd = pygame.mixer.Sound(str(e["_dir"] / e["file"]))
                snd.set_volume(e.get("volume", 0.6))
            except Exception:
                snd = False
            self._sounds[sid] = snd
        if snd:
            snd.play()

    def start_music(self):
        if not self.audio or not self.music:
            return
        try:
            m = self.music[0]
            pygame.mixer.music.load(str(m["_dir"] / m["file"]))
            pygame.mixer.music.set_volume(0.35)
            pygame.mixer.music.play(-1)
        except Exception as e:
            print(f"[assets] Musik: {e}")

    def toggle_music(self):
        if not self.audio:
            return
        self.music_on = not self.music_on
        pygame.mixer.music.unpause() if self.music_on else pygame.mixer.music.pause()
