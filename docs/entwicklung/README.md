# Entwicklerdokumentation Cult-Sim

Diese Dokumentation erklärt den Aufbau des Quellcodes. Sie richtet sich an Entwickler mit
Programmiererfahrung, aber ohne Vorwissen in der Spielentwicklung. Begriffe aus der Spielentwicklung
werden beim ersten Auftreten erklärt; ein Glossar steht in [Schritt 1](01-ueberblick.md#glossar).

Was das Spiel aus Spielersicht kann, wie man es startet und wie man Grafiken ersetzt, steht in der
[README im Projektwurzelverzeichnis](../../README.md). Hier geht es nur um den Code.

## Einarbeitung in neun Schritten

Die Schritte bauen aufeinander auf. Jeder nennt die Dateien, die man dabei lesen sollte, und endet
mit einer kleinen Übung. Wer nur eine bestimmte Stelle sucht, nimmt die Tabelle
[„Wo finde ich was?“](#wo-finde-ich-was) weiter unten.

| Schritt | Thema | Dateien | Danach weiß man |
|---|---|---|---|
| [1](01-ueberblick.md) | Überblick und Architektur | `main.py`, `cultsim/config.py` | wie das Projekt in Schichten zerfällt und wer wen aufrufen darf |
| [2](02-spielschleife-und-zeit.md) | Spielschleife und Zeit | `ui/app.py` (`run`, `frame`), `sim/world.py` (`tick`, `hourly`, `daily`) | was pro Bild, pro Tick, pro Stunde und pro Tag passiert |
| [3](03-daten-und-assets.md) | Daten und Assets | `data.py`, `assets.py`, `data/*.json`, `assets/manifest.json` | welche Inhalte in JSON liegen und wie der Code sie liest |
| [4](04-welt.md) | Die Welt: Gitter, Bauen, Räume, Regeln | `sim/world.py` | wie der Zustand des Geländes gespeichert und ausgewertet wird |
| [5](05-figuren.md) | Figuren und Wegfindung | `sim/pawns.py`, `sim/path.py` | wie eine Figur entscheidet, läuft und arbeitet |
| [6](06-karte-und-ereignisse.md) | Kartenebene und Ereignisse | `sim/strategic.py`, `sim/events.py` | wie Regionen wachsen und wie Ereignisse ausgelöst werden |
| [7](07-oberflaeche.md) | Oberfläche und Darstellung | `ui/widgets.py`, `ui/render.py`, `ui/hud.py`, `ui/mapview.py` | wie gezeichnet wird und wie Eingaben bei der Simulation ankommen |
| [8](08-tests-und-werkzeuge.md) | Tests und Werkzeuge | `tools/*.py` | wie man Änderungen ohne Fenster prüft |
| [9](09-erweitern.md) | Erweitern: Rezepte und Stolperfallen | – | welche Stellen man für typische Erweiterungen anfassen muss |

Für die Schritte 1 bis 3 reicht etwa eine Stunde. Die Schritte 4 bis 7 sind der Kern und brauchen je
nach Gründlichkeit einen halben bis ganzen Tag.

## Wo finde ich was?

| Ich suche … | Datei | Einstiegspunkt |
|---|---|---|
| Programmstart, Kommandozeilenoptionen | [ui/app.py](../../cultsim/ui/app.py) | `main()` |
| Hauptschleife, Reihenfolge innerhalb eines Bildes | [ui/app.py](../../cultsim/ui/app.py) | `App.run()`, `App.frame()` |
| Tastenbelegung | [ui/app.py](../../cultsim/ui/app.py) | `App.keys()` |
| Mausklicks in der Spielwelt, Auswahl | [ui/app.py](../../cultsim/ui/app.py) | `App.world_input()`, `App.pick()` |
| Bau-, Zonen- und Abrisswerkzeug | [ui/app.py](../../cultsim/ui/app.py) | `drag_tiles()`, `preview()`, `apply_tool()` |
| Konstanten (Kachelgröße, Zeit, Rollen, Zonen) | [config.py](../../cultsim/config.py) | ganze Datei |
| Laden der JSON-Daten, Mods | [data.py](../../cultsim/data.py) | `Data.load()`, `load_json()` |
| Sprites, Platzhalter, Ton | [assets.py](../../cultsim/assets.py) | `Assets` |
| Spielzustand des Geländes | [sim/world.py](../../cultsim/sim/world.py) | `World.__init__()` |
| Kartengenerierung, Startgelände | [sim/world.py](../../cultsim/sim/world.py) | `World.generate()` |
| Bauen und Abreißen | [sim/world.py](../../cultsim/sim/world.py) | `can_place()`, `place()`, `remove()`, `finish()` |
| Raum- und Gehege-Erkennung, Begehbarkeit | [sim/world.py](../../cultsim/sim/world.py) | `World.rebuild()` |
| Wirkung von Regeln und Ausrichtung | [sim/world.py](../../cultsim/sim/world.py) | `recompute_mods()`, `mod()`, `add()`, `flag()`, `schedule()` |
| Lehre (Achsen, Ausrichtung) | [sim/world.py](../../cultsim/sim/world.py) | `doctrine_target()`, `update_archetype()` |
| Tagesabrechnung, Niederlage | [sim/world.py](../../cultsim/sim/world.py) | `World.daily()` |
| Speichern und Laden | [sim/world.py](../../cultsim/sim/world.py) | `World.save()`, `World.load()` |
| Entscheidungen der Mitglieder | [sim/pawns.py](../../cultsim/sim/pawns.py) | `Pawn.think_member()` |
| Arbeit je Rolle | [sim/pawns.py](../../cultsim/sim/pawns.py) | `work_worker()`, `work_cook()`, … |
| Ausführung einer Tätigkeit | [sim/pawns.py](../../cultsim/sim/pawns.py) | `h_build()`, `h_eat()`, … |
| Gesprächsergebnisse (Bekehrung, Festnahme …) | [sim/pawns.py](../../cultsim/sim/pawns.py) | `talk_convert()`, `talk_arrest()`, … |
| Besucher, Presse, Behörden, Polizei | [sim/pawns.py](../../cultsim/sim/pawns.py) | `think_outsider()`, `think_raid()`, `make_outsider()` |
| Laune, Glaube, Zweifel | [sim/pawns.py](../../cultsim/sim/pawns.py) | `Pawn.hourly()` |
| Wegfindung | [sim/path.py](../../cultsim/sim/path.py) | `astar()`, `label_components()` |
| Regionen, Wachstum, Verdacht auf der Karte | [sim/strategic.py](../../cultsim/sim/strategic.py) | `Strategic.daily()`, `_status()` |
| Kampagnen, Ortsgruppen, Phasenwechsel | [sim/strategic.py](../../cultsim/sim/strategic.py) | `start_campaign()`, `build_chapter()`, `advance()` |
| Zufallsereignisse und ihre Effekte | [sim/events.py](../../cultsim/sim/events.py) | `daily_roll()`, `eligible()`, `apply()` |
| Razzia, Spaltung, Maulwürfe | [sim/events.py](../../cultsim/sim/events.py) | `daily_checks()`, `raid_end()` |
| Schaltflächen, Text, Scrollbereiche | [ui/widgets.py](../../cultsim/ui/widgets.py) | `UI` |
| Isometrische Darstellung | [ui/render.py](../../cultsim/ui/render.py) | `IsoView.draw()` |
| Leisten, Baumenü, Inspektor, Panels, Popups | [ui/hud.py](../../cultsim/ui/hud.py) | `draw_*()` |
| Kartenansicht | [ui/mapview.py](../../cultsim/ui/mapview.py) | `MapView.draw()`, `side_content()` |

## Pflege dieser Dokumentation

Die Dokumentation wird zusammen mit dem Code gepflegt: Wer eine Erweiterung einbaut, passt im selben
Arbeitsgang die betroffenen Schritte an. Welche Änderung welche Datei betrifft, steht in der Tabelle
am Ende von [Schritt 9](09-erweitern.md#doku-aktuell-halten). Zielgruppe und Schreibregeln sind in
der [CLAUDE.md](../../CLAUDE.md) im Projektverzeichnis festgelegt, die Claude Code in jeder Sitzung
automatisch liest.

Die Dokumentation verweist auf Funktionsnamen und nicht auf Zeilennummern, damit sie beim Bearbeiten
des Codes nicht sofort veraltet. Ein Funktionsname lässt sich im Editor über die Symbolsuche finden.

Stand: 22.11.2026, Version „0.1 Prototyp“.
