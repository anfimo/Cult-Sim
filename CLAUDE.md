# Cult-Sim

Satirische Siedlungssimulation in Python (ab 3.11) mit pygame-ce als einziger Abhängigkeit,
verwaltet mit uv. Bezeichner im Code sind englisch; Kommentare, Docstrings, Spieltexte und die
Dokumentation sind deutsch.

## Befehle

```
uv run main.py                              # Spiel starten
uv run python tools/unit_test.py            # einzelne Mechaniken
uv run python tools/smoke_test.py 60        # Auto-Spieler, 60 Tage ohne Fenster
uv run python tools/monkey_test.py 5000     # Zufallseingaben durch die echte Oberfläche
uv run python tools/preview_maps.py <ordner>  # Kartendateien prüfen
```

`tools/gen_assets.py` nicht ungefragt ausführen: Es überschreibt den Inhalt von `assets/`.

Nach Änderungen an `cultsim/sim/` laufen `unit_test.py` und `smoke_test.py 60`, nach Änderungen an
`cultsim/ui/` läuft `monkey_test.py 5000`, nach Änderungen an `data/maps/` läuft `preview_maps.py`.

## Architekturregeln

- `cultsim/sim/` importiert weder pygame noch etwas aus `cultsim/ui/`. Die Simulation meldet sich
  bei der Oberfläche nur über `w.notes`, `w.popups`, `w.cues` und `w.over`.
- Zufall in der Simulation nur über `w.rng`, nie über das Modul `random` direkt.
- Spielinhalte gehören nach `data/*.json`, Mechanik in den Code.
- Spielstände sind Pickles des `World`-Objekts: Nichts daran hängen, was sich nicht speichern lässt.
  Neue Felder von `Thing` und `Job` in `__slots__` eintragen.

Weitere Stolperfallen stehen in `docs/entwicklung/09-erweitern.md`.

## Entwicklerdokumentation aktuell halten

Die Entwicklerdokumentation liegt in `docs/entwicklung/` (Übersicht `README.md` und die Schritte
`01` bis `09`). Sie ist Teil jeder Änderung: Wer Code, Daten oder Werkzeuge erweitert oder umbaut,
passt im selben Arbeitsgang die betroffenen Doku-Dateien an, ohne gesonderte Aufforderung.

### Zielgruppe

Fortgeschrittene Programmierer ohne Erfahrung in der Spielentwicklung. Daraus folgt:

- Allgemeine Programmierkenntnisse voraussetzen. Python, Datenstrukturen, Zustandsautomaten oder
  JSON nicht erklären.
- Jeden Begriff aus der Spielentwicklung beim ersten Auftreten in einem Satz erklären (zum Beispiel
  Tick, Sprite, Maleralgorithmus, Dirty-Flag) und in das Glossar in `01-ueberblick.md` aufnehmen.
- Bei spieltypischen Entwurfsentscheidungen den Grund nennen, also warum man es in Spielen so macht,
  nicht nur was der Code tut.
- Die Doku dient der schrittweisen Einarbeitung: Jeder Schritt baut auf den vorigen auf, nennt die
  zu lesenden Dateien und endet mit einer Übung. Neue Themen in den passenden Schritt einordnen;
  einen neuen Schritt nur anlegen, wenn ein neues Teilsystem entsteht.

### Vorgehen bei jeder Änderung

1. Die Tabelle „Doku aktuell halten“ am Ende von `docs/entwicklung/09-erweitern.md` ordnet jeder Art
   von Änderung die betroffene Doku-Datei zu. Danach vorgehen.
2. Listen, die den Code spiegeln, vollständig halten: Felder von Klassen, Schlüssel der JSON-Dateien,
   Bedingungen und Effekte von Ereignissen, Schlüssel für `mods`, `adds`, `flags`, Funktionstabellen,
   die Tabelle „Wo finde ich was?“ in der Übersicht.
3. Kommt eine neue Erweiterungsmöglichkeit oder Stolperfalle hinzu, ein Rezept oder einen Eintrag in
   `09-erweitern.md` ergänzen.
4. Ändern sich Bedienung, Startoptionen oder Funktionsumfang aus Spielersicht, auch die `README.md`
   im Projektverzeichnis anpassen.
5. Das Datum unter „Stand“ in `docs/entwicklung/README.md` aktualisieren.
6. Im Abschlussbericht nennen, welche Doku-Dateien angepasst wurden. War keine Anpassung nötig, das
   mit einem Satz begründen.

Keine Anpassung brauchen reine Fehlerkorrekturen und Balance-Werte, die das in der Doku Beschriebene
nicht berühren. Nennt die Doku den geänderten Wert ausdrücklich, wird sie angepasst.

### Schreibregeln

- Auf Funktions-, Klassen- und Dateinamen verweisen, nie auf Zeilennummern.
- Wird etwas umbenannt oder entfernt, den alten Namen in `docs/entwicklung/` suchen und ersetzen.
- Nur beschreiben, was im Code steht. Aussagen über Verhalten vor dem Schreiben am Code prüfen,
  Befehle vor dem Dokumentieren ausführen.
- Dateiverweise als relative Markdown-Links setzen, Sprungmarken nach dem Ändern von Überschriften
  prüfen.
- Sachlich und knapp schreiben, in ganzen Sätzen; Tabellen für Aufzählbares, Fließtext für Abläufe
  und Begründungen.
