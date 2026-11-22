"""Zentrale Konstanten. Alles Inhaltliche (Gebäude, Ereignisse, Karten ...) liegt in data/*.json."""

TITLE = "Cult-Sim"
VERSION = "0.1 Prototyp"

# Isometrie
TILE_W, TILE_H = 32, 16
MAP_SIZE = 56

# Zeit
TPS = 20                 # Simulationsticks pro Sekunde bei 1x
TICKS_PER_HOUR = 100
TICKS_PER_DAY = TICKS_PER_HOUR * 24
START_TICK = 6 * TICKS_PER_HOUR

# Terrain
T_GRASS, T_DIRT, T_SAND, T_ROCK, T_ROAD, T_WATER = range(6)
TERRAIN_SPRITES = ["terrain_grass", "terrain_dirt", "terrain_sand", "terrain_rock", "terrain_road", "terrain_water"]
TERRAIN_NAMES = ["Wiese", "Erde", "Sand", "Fels", "Zufahrt", "Wasser"]

# Zonen
Z_NONE, Z_FIELD, Z_VISIT, Z_FORBID = 0, 1, 2, 3
ZONES = {
    Z_FIELD: ("Anbaufeld", (130, 200, 70), "Arbeiter säen und ernten hier."),
    Z_VISIT: ("Besucherzone", (90, 170, 235), "Hier werden Interessierte empfangen (und bearbeitet)."),
    Z_FORBID: ("Sperrzone", (235, 80, 80), "Außenstehende, die hier herumschnüffeln, werden von Wächtern entfernt."),
}

# Passierbarkeits-Klassen
C_MEMBER, C_OUTSIDER, C_RAID, C_ANIMAL = 0, 1, 2, 3

BARRIERS = ("wall", "door", "fence", "gate")

ROLES = {
    "worker": "Arbeiter", "cook": "Koch", "preacher": "Prediger",
    "recruiter": "Werber", "guard": "Wächter", "clerk": "Schreiber",
}
ROLE_SKILL = {"worker": "work", "cook": "cook", "preacher": "preach", "recruiter": "preach", "guard": "guard", "clerk": "admin"}
ROLE_DESC = {
    "worker": "Baut, sät und erntet.",
    "cook": "Kocht Mahlzeiten, hilft sonst beim Bau.",
    "preacher": "Hält Predigten, bekehrt Besucher, betreut Zweifler.",
    "recruiter": "Zieht in die Stadt und bringt Interessierte mit.",
    "guard": "Nachtschicht: fängt Ausreißer, entfernt Schnüffler.",
    "clerk": "Schreibt Spendenbriefe und druckt Traktate.",
}
SKILLS = {"work": "Handwerk", "cook": "Kochen", "preach": "Predigen", "admin": "Verwaltung", "guard": "Wachsamkeit"}
AXES = ("commerce", "isolation", "apocalypse")
