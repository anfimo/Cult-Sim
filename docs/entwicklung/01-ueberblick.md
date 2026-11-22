# Schritt 1: Überblick und Architektur

[Zurück zur Übersicht](README.md) · Weiter: [Schritt 2](02-spielschleife-und-zeit.md)

## Technische Basis

- **Sprache:** Python ab 3.11, reiner Python-Code ohne Build-Schritt.
- **Einzige Abhängigkeit:** [pygame-ce](https://pyga.me/) für Fenster, Zeichnen, Eingabe und Ton.
  pygame ist eine dünne Schicht über der Bibliothek SDL: Es liefert eine Zeichenfläche, eine
  Ereignisliste und einen Mixer, aber keine Spiel-Engine. Szenenverwaltung, Oberfläche und Wegfindung
  sind im Projekt selbst geschrieben.
- **Paketverwaltung:** [uv](https://docs.astral.sh/uv/). `uv run main.py` installiert beim ersten
  Aufruf Python und pygame-ce in `.venv/`.
- **Umfang:** rund 5.000 Zeilen Spielcode in `cultsim/`, dazu rund 3.000 Zeilen Werkzeuge in `tools/`.

## Verzeichnisse

```
main.py                 Einstieg: ruft cultsim.ui.app.main() auf
cultsim/
  config.py             Konstanten (Kachelgröße, Zeit, Zonen, Rollen)
  data.py               lädt data/*.json in das globale Objekt DATA
  assets.py             lädt Sprites und Ton über assets/manifest.json
  sim/                  Simulation, ohne pygame
    world.py            Zustand des Geländes, Bauen, Räume, Regeln, Tagesabrechnung
    pawns.py            Figuren: Mitglieder, Besucher, Presse, Polizei, Ziegen
    path.py             Wegfindung (A*)
    strategic.py        Kartenebene: Regionen, Kampagnen, Phasen
    events.py           Ereignisse und Popups
  ui/                   Darstellung und Eingabe, mit pygame
    app.py              Hauptschleife, Eingabe, Werkzeuge
    widgets.py          Bausteine der Oberfläche (Schaltfläche, Text, Scrollbereich)
    render.py           isometrische Ansicht des Geländes
    hud.py              Leisten, Baumenü, Inspektor, Panels, Popups, Hauptmenü
    mapview.py          Kartenansicht
data/                   alle Spielinhalte als JSON
assets/                 Grafik, Ton, manifest.json
tools/                  Tests und Generatoren (siehe Schritt 8)
saves/                  Spielstände (wird beim ersten Speichern angelegt)
docs/                   Screenshots und diese Dokumentation
CLAUDE.md               Arbeitsregeln für Claude Code, darunter die Pflege dieser Dokumentation
```

## Die drei Schichten

```
┌──────────────────────────────────────────────────────────────┐
│ ui/        app.py · widgets.py · render.py · hud.py ·        │
│            mapview.py                     (braucht pygame)   │
└───────────────┬──────────────────────────────▲───────────────┘
                │ ruft Methoden auf,           │ liest Zustand,
                │ setzt einzelne Attribute     │ leert Meldungslisten
┌───────────────▼──────────────────────────────┴───────────────┐
│ sim/       world.py · pawns.py · path.py · strategic.py ·    │
│            events.py                      (ohne pygame)      │
└───────────────┬──────────────────────────────────────────────┘
                │ liest
┌───────────────▼──────────────────────────────────────────────┐
│ Grundlage  config.py (Konstanten) · data.py (DATA aus JSON)  │
└──────────────────────────────────────────────────────────────┘
```

Die wichtigste Regel des Projekts: **`cultsim/sim/` importiert kein pygame und nichts aus
`cultsim/ui/`.** Die Simulation läuft dadurch ohne Fenster, was alle Tests in `tools/` nutzen. Die
Oberfläche darf die Simulation beliebig lesen und aufrufen, aber nicht umgekehrt.

`assets.py` braucht pygame und gehört damit zur Oberfläche, auch wenn die Datei neben `config.py` liegt.

### Wie die Oberfläche die Simulation steuert

Es gibt keine Befehlsschicht dazwischen. Die Oberfläche hält eine Referenz auf das `World`-Objekt
(`app.w`) und

- ruft Methoden auf, zum Beispiel `w.place("bed", x, y)`, `w.toggle_edict("zehnt")`,
  `p.promote(w)` oder `w.strategic.start_campaign(lv, r, "flyer")`;
- setzt in wenigen Fällen Attribute direkt, zum Beispiel `p.role = "cook"`, `w.lawyers = 2` oder
  `g.orders.append(("bond", p.id))` für Befehle an den Guru.

Aktionen, die scheitern können, folgen einem festen Muster: Eine Funktion `…_block()` oder
`can_…()` liefert `None`, wenn die Aktion möglich ist, sonst einen deutschen Fehlertext. Die
Oberfläche nutzt denselben Aufruf, um Schaltflächen auszugrauen und den Grund im Tooltip zu zeigen.
Beispiele: `World.can_place()`, `World.edict_block()`, `Strategic.campaign_block()`.

### Wie die Simulation der Oberfläche etwas mitteilt

Die Simulation kennt die Oberfläche nicht. Sie legt Meldungen in Listen am `World`-Objekt ab, die
die Oberfläche in jedem Bild ausliest:

| Liste | Inhalt | Wer liest sie |
|---|---|---|
| `w.notes` | Meldungen am linken Bildrand (`w.notify(text, kind, pos, pid)`) | `hud.draw_notes()` |
| `w.popups` | Ereignisfenster mit Auswahl, halten das Spiel an | `hud.draw_popup()` |
| `w.cues` | Namen von Tönen, die abgespielt werden sollen | `App.frame()`, leert die Liste danach |
| `w.over` | `None` oder `("win" \| "lose", Text)` für das Spielende | `App.frame()`, `hud.draw_popup()` |

## Zwei Spielebenen

Das Spiel besteht aus zwei Simulationen, die sich Geld, Erleuchtung und Verdacht teilen:

| | Gelände | Karte |
|---|---|---|
| Vorbild | Kolonie-Simulation | globales Strategiespiel |
| Datenmodell | Kachelgitter 56 × 56, einzelne Figuren | Regionen mit Kennzahlen |
| Taktung | 20 Schritte pro Sekunde | einmal pro Spieltag |
| Code | `world.py`, `pawns.py`, `path.py` | `strategic.py` |
| Ansicht | `render.py` | `mapview.py` |

Die Karte hat drei Stufen (Stadt, Land, Welt), die über Phasen freigeschaltet werden.
`w.phase` ist 1, 2 oder 3.

## Konventionen im Code

- **Sprache:** Bezeichner sind englisch, Kommentare, Docstrings und alle Texte im Spiel deutsch.
- **Kurze Namen:** `w` ist immer die `World`, `p` eine Figur (`Pawn`), `th` ein Objekt (`Thing`),
  `j` ein Auftrag (`Job`), `st` die Kartenebene (`Strategic`), `lv` eine Kartenstufe (`Level`),
  `r` je nach Datei eine Region oder ein Rechteck, `ui` das `UI`-Objekt, `S` die Kartengröße.
- **`from ..config import *`:** Die Konstanten aus `config.py` stehen in fast allen Modulen ohne
  Präfix zur Verfügung (`TICKS_PER_DAY`, `Z_FIELD`, `ROLES` …).
- **Aufruf über Namensschema:** Mehrere Stellen suchen eine Methode über ihren Namen, zum Beispiel
  `getattr(self, "h_" + j.kind)`. Eine neue Tätigkeit entsteht dadurch, dass man eine Methode mit dem
  passenden Namen anlegt. Die Schemata stehen in [Schritt 5](05-figuren.md#namensschemata).
- **Kein Typsystem für Spielinhalte:** Gebäude, Regeln oder Ereignisse sind Dictionaries aus den
  JSON-Dateien. Welche Schlüssel es gibt, steht in [Schritt 3](03-daten-und-assets.md).

## Glossar

| Begriff | Bedeutung |
|---|---|
| Frame (Bild) | Ein Durchlauf der Hauptschleife: Eingabe lesen, Simulation fortschreiben, alles neu zeichnen. Hier höchstens 60 pro Sekunde. |
| Tick | Ein Rechenschritt der Simulation, unabhängig von der Bildrate. Hier 20 pro Sekunde bei einfacher Geschwindigkeit. |
| Spielschleife | Die Endlosschleife, die Frames erzeugt (`App.run()`). |
| Headless | Betrieb ohne Fenster, etwa für Tests. |
| Kachel (Tile) | Ein Feld des Gitters. Positionen sind `(x, y)` mit ganzzahligen Koordinaten. |
| Sprite | Ein kleines Bild, das an eine Stelle gezeichnet wird. Mehrere Einzelbilder nebeneinander ergeben Varianten oder eine Animation. |
| Anker | Der Bildpunkt eines Sprites, der auf der Kachelmitte liegen soll. |
| Isometrie | Schrägansicht, in der Kacheln als Rauten erscheinen. Die Umrechnung steht in [Schritt 7](07-oberflaeche.md#isometrische-projektion). |
| Pawn | Eine einzeln simulierte Figur. Der Begriff stammt aus Kolonie-Simulationen. |
| Bauplan (Blueprint) | Ein gesetztes, noch nicht fertig gebautes Objekt. |
| HUD | Die ständig sichtbaren Anzeigen über der Spielwelt (Leisten, Meldungen). |
| Immediate-Mode-UI | Oberfläche ohne dauerhafte Widget-Objekte: Jede Schaltfläche wird in jedem Bild neu gezeichnet und dabei abgefragt. Siehe [Schritt 7](07-oberflaeche.md#immediate-mode-oberfläche). |
| A* | Standardalgorithmus für kürzeste Wege auf einem Gitter. |
| Flutfüllung | Verfahren, das von einem Feld aus alle zusammenhängenden Felder einsammelt. Hier für die Raumerkennung. |
| Seed | Startwert des Zufallsgenerators. Gleicher Seed ergibt denselben Spielverlauf. |
| Modifikator | Ein Faktor oder Zuschlag, den Regeln, Eigenschaften oder die Ausrichtung auf einen Spielwert legen. |

## Übung

1. Das Spiel mit `uv run main.py` starten und ein paar Minuten spielen: etwas bauen, eine Figur
   anklicken, mit `M` die Karte öffnen.
2. `uv run python tools/smoke_test.py 10` ausführen. Das Skript spielt zehn Tage ohne Fenster und
   gibt Kennzahlen aus. Es belegt, dass die Simulation ohne pygame läuft.
3. In [config.py](../../cultsim/config.py) nachlesen, wie viele Ticks ein Spieltag hat.
