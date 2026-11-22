"""Lädt alle Spieldaten aus data/*.json (+ optionale Überlagerungen aus mods/<name>/data/)."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def root_dir() -> Path:
    if getattr(sys, "frozen", False):          # PyInstaller-Build: Daten liegen neben der .exe
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


ROOT = root_dir()


def mod_dirs() -> list[Path]:
    m = ROOT / "mods"
    return sorted(p for p in m.iterdir() if p.is_dir()) if m.exists() else []


def _merge(a: dict, b: dict) -> None:
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            _merge(a[k], v)
        elif isinstance(v, list) and isinstance(a.get(k), list):
            a[k].extend(v)
        else:
            a[k] = v


def load_json(rel: str, default=None):
    path = ROOT / "data" / rel
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    base = json.loads(path.read_text("utf-8"))
    for mod in mod_dirs():
        p = mod / "data" / rel
        if p.exists():
            _merge(base, json.loads(p.read_text("utf-8")))
    return base


class Data:
    loaded = False

    def load(self) -> "Data":
        self.buildables = load_json("buildables.json")
        self.traits = load_json("traits.json")
        self.names = load_json("names.json")
        self.edicts = load_json("edicts.json")
        self.doctrine = load_json("doctrine.json")
        self.campaigns = load_json("campaigns.json")
        self.events = load_json("events.json")["events"]
        self.maps = {k: load_json(f"maps/{k}.json", default={}) for k in ("local", "country", "world")}
        for k, d in self.buildables.items():
            d["id"] = k
            d.setdefault("sprite", k)
            d.setdefault("blocks", d["kind"] in ("wall", "fence"))
        self.loaded = True
        return self


DATA = Data()
