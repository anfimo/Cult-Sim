# Schritt 8: Tests und Werkzeuge

[Zurück zur Übersicht](README.md) · Vorher: [Schritt 7](07-oberflaeche.md) · Weiter: [Schritt 9](09-erweitern.md)

Dateien: `tools/*.py`.

Das Projekt hat kein Test-Framework. Die Tests sind eigenständige Skripte, die mit `assert` und
Ausgaben arbeiten und bei einem Fehler mit einer Ausnahme abbrechen. Alle laufen ohne Fenster. Jedes
Skript trägt das Projektverzeichnis selbst in den Suchpfad ein und wird vom Projektverzeichnis aus
gestartet.

## Übersicht

| Skript | Prüft | Aufruf | Dauer (gemessen am 22.11.2026) |
|---|---|---|---|
| [smoke_test.py](../../tools/smoke_test.py) | ganze Simulation über viele Tage | `uv run python tools/smoke_test.py [tage] [seed]` | 1,5 s für 30 Tage, 5 s für 60 Tage |
| [unit_test.py](../../tools/unit_test.py) | einzelne Mechaniken gezielt | `uv run python tools/unit_test.py` | unter 1 s |
| [monkey_test.py](../../tools/monkey_test.py) | Oberfläche mit Zufallseingaben | `uv run python tools/monkey_test.py [frames] [seed]` | 8 s für 5.000 Frames |
| [screenshot.py](../../tools/screenshot.py) | Aussehen der Oberfläche | `uv run python tools/screenshot.py <ordner> [tage]` | 1 s |
| [preview_maps.py](../../tools/preview_maps.py) | Kartendateien | `uv run python tools/preview_maps.py <ordner> [karte.json …]` | unter 1 s |
| [gen_assets.py](../../tools/gen_assets.py) | erzeugt Platzhalter-Grafik und -Ton | `uv run python tools/gen_assets.py` | nicht gemessen (überschreibt `assets/`) |

## `smoke_test.py`: Auto-Spieler

Die Funktion `autoplay(w, rng)` ist ein einfacher programmierter Spieler: Er beantwortet Popups
zufällig, baut am ersten Tag Felder, eine Hütte mit Betten, Herd, Schreibtisch und Druckerpresse,
kauft bei Bedarf Essen, verteilt Rollen, startet Kampagnen, baut Ortsgruppen, erlässt Regeln,
befördert Mitglieder und wechselt die Phase, sobald es geht.

`main()` lässt ihn die angegebene Zahl Tage spielen, gibt alle fünf Tage eine Zeile mit Kennzahlen
aus (Mitglieder, Geld, Vorräte, Glaube, Laune, Verdacht, Anhänger, Ausrichtung, Räume), am Ende die
Rechengeschwindigkeit in Ticks pro Sekunde, die letzten Meldungen und die Tagesbilanz. Zum Schluss
wird die Welt einmal mit `pickle` gespeichert, geladen und einen Tick weitergerechnet.

Der Test ist nützlich für drei Dinge:

- **Absturzsuche:** Eine Änderung an der Simulation, die nach 60 Tagen noch läuft, ist grob in Ordnung.
- **Balance:** Die Kennzahlen zeigen, ob eine Änderung das Spiel leichter oder schwerer macht.
  Verschiedene Seeds vergleichen, da einzelne Läufe stark streuen.
- **Speicherbarkeit:** Der Schlussabschnitt fällt auf, wenn etwas nicht Speicherbares an der `World` hängt.

`autoplay()` wird auch von `screenshot.py` und `monkey_test.py` importiert. Wer die Signatur von
Methoden ändert, die der Auto-Spieler benutzt (`w.place()`, `st.start_campaign()` …), muss ihn anpassen.

## `unit_test.py`: gezielte Mechaniken

Ein lineares Skript, das eine Welt mit festem Seed aufbaut und nacheinander prüft:

1. Zaun mit Tor ergibt ein Gehege; mit Ziege darin ein Ziegengehege.
2. Steinmauern mit Tür, Teppich, Statue und Altar ergeben einen Tempel.
3. Nach drei Tagen ist die Ziege noch im Gehege.
4. Ein Mitglied mit minimalem Glauben flieht in der Nacht.
5. Eine Razzia läuft ab, der Guru kommt zurück, die Polizei zieht ab.
6. Jede Kartenstufe hat Regionen mit Pixeln und Nachbarn; 40 Tage Kartenebene in Phase 3 laufen durch.

Die Hilfsfunktion `build()` setzt ein Objekt und stellt es sofort fertig. Das ist das Muster für
eigene Prüfungen: Zustand direkt setzen (`w.money = 1e6`, `m.faith = 5`), Ticks laufen lassen,
Ergebnis prüfen.

## `monkey_test.py`: Zufallseingaben

Startet die echte `App` mit den Dummy-Treibern von SDL, also ohne Fenster und Ton, und füttert
`App.frame()` mit zufälligen Klicks, Tasten und Mausradbewegungen. Bei einer Ausnahme gibt das
Skript die letzten Eingaben und den Zustand der Oberfläche aus.

Dieser Test findet Fehler, die nur in bestimmten Kombinationen der Oberfläche auftreten, etwa ein
Klick im Inspektor, während die ausgewählte Figur gerade verschwindet. Nach jeder Änderung an
`ui/` lohnt sich ein Lauf mit einigen tausend Frames.

Mit der Umgebungsvariable `MONKEY_LATE=1` spielt zuerst der Auto-Spieler 30 Tage, dann wird Phase 3
mit viel Geld erzwungen. So werden auch die späten Teile der Oberfläche erreicht.

## `screenshot.py`: Sichtkontrolle

Spielt eine Partie einige Tage, stellt dann nacheinander Situationen her (Inspektor, gedrehte
Ansicht mit Raumfarben, Bauvorschau, jedes Panel, alle Kartenstufen, ein Ereignis, eine Razzia) und
speichert je ein Bild in den Zielordner. Die Hilfsfunktionen `shot()`, `click()` und `key()` zeigen,
wie man die Oberfläche fernsteuert. Nützlich, um Änderungen am Layout zu prüfen.

## `preview_maps.py`: Kartenprüfung

Prüft Kartendateien streng gegen das erwartete Schema, rastert sie wie das Spiel und schreibt eine
Vorschau als Bild. Das Skript meldet Regionen ohne Pixel oder ohne Nachbarn. Nach jeder Änderung an
`data/maps/*.json` ausführen, da das Spiel selbst Kartendaten beim Laden nicht prüft.

## `gen_assets.py`: Platzhalter erzeugen

Zeichnet alle Platzhalter-Sprites per Code, erzeugt Töne und Musik und schreibt
`assets/manifest.json`. Das Skript ist mit rund 2.100 Zeilen die größte Datei des Projekts, gehört
aber nicht zum Spiel. **Es überschreibt den Inhalt von `assets/`.** Liegen dort von Hand erstellte
Dateien, darf es nicht ausgeführt werden. Der Kommentar am Dateianfang beschreibt die
Zeichenkonventionen, die zum Renderer passen müssen.

## Was nach welcher Änderung laufen sollte

| Änderung an | Mindestens ausführen |
|---|---|
| `cultsim/sim/` | `unit_test.py` und `smoke_test.py 60` |
| `cultsim/ui/` | `monkey_test.py 5000`, bei Layoutänderungen `screenshot.py` |
| `data/*.json` außer Karten | `smoke_test.py 30` |
| `data/maps/*.json` | `preview_maps.py` und `unit_test.py` |
| Attributen von `World`, `Pawn`, `Thing`, `Job`, `Region` | `smoke_test.py` (prüft Speichern und Laden) |

## Fehlersuche

- **Reproduzieren:** Seed festhalten. `World(seed=…)` und der zweite Parameter der Testskripte
  ergeben denselben Verlauf.
- **Zustand ansehen:** In einem Skript oder der Python-Konsole eine Welt bis zum fraglichen Tag
  laufen lassen und Objekte direkt untersuchen (`w.members()`, `p.job.kind`, `w.rooms`).
- **Meldungen:** `w.notes` enthält die letzten 80 Meldungen mit Tag und Text.
- **Ausgaben des Asset-Laders** beginnen mit `[assets]` und weisen auf fehlende oder defekte Dateien hin.

## Übung

1. Alle vier Testskripte einmal ausführen.
2. In `unit_test.py` eine Prüfung ergänzen: Ein Raum mit Herd heißt „Küche“.
3. `screenshot.py` mit einem temporären Zielordner ausführen und die Bilder ansehen.
