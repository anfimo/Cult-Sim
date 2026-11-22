# Schritt 9: Erweitern – Rezepte und Stolperfallen

[Zurück zur Übersicht](README.md) · Vorher: [Schritt 8](08-tests-und-werkzeuge.md)

Dieser Schritt sammelt, welche Stellen man für typische Erweiterungen anfassen muss. Die Rezepte
sind nach Aufwand geordnet: zuerst reine Datenänderungen, dann Änderungen mit Code.

## Zuerst prüfen: Daten oder Code?

| Vorhaben | Reicht JSON? |
|---|---|
| Neues Möbel mit vorhandener Funktion (`use`) oder reine Dekoration | ja |
| Neue Regel aus vorhandenen Modifikatoren | ja |
| Neue Eigenschaft aus vorhandenen Modifikatoren | ja |
| Neues Zufallsereignis aus vorhandenen Bedingungen und Effekten | ja |
| Neue Kampagne, neue Ausrichtung, neuer Mythos, neuer Rang, neues Großprojekt | ja |
| Neue Region oder geänderte Karte | ja |
| Möbel mit neuer Funktion, neue Tätigkeit, neue Rolle | nein |
| Neuer Modifikator, neuer Schalter, neuer Ereigniseffekt | nein |
| Neue Art von Außenstehenden, neue Ressource, neues Panel | nein |

## Rezepte ohne Code

### Neues Möbel mit vorhandener Funktion

1. Eintrag in `data/buildables.json` (Schlüssel siehe [Schritt 3](03-daten-und-assets.md#buildablesjson-alles-was-auf-einer-kachel-stehen-kann)).
2. Sprite unter `assets/sprites/` ablegen und in `assets/manifest.json` mit `file`, `anchor`,
   `frames` eintragen. Ohne Sprite erscheint ein Platzhalter.
3. Soll ein Raum danach benannt werden: Zeile in `ROOM_ROLES` in `world.py` (das ist dann Code).

### Neue Regel

Eintrag in `data/edicts.json` mit `name`, `text`, `cost`, `phase` und beliebigen `mods`, `adds`,
`flags`, `sched`, `doctrine`. Wirksam sind nur Schlüssel, die der Code abfragt. Die vorhandenen:

- `mods`: `tithe`, `convert`, `work`, `faith_gain`, `faith_decay`, `food_use`, `flee`, `heat_gain`,
  `growth`, `income`, `visitor_rate`, `guard`
- `adds`: `mood`, `heat_daily`, `evidence_daily`, `course_income`, `ep_daily`
- `flags`: `love_bombing`, `raw_ok`, `contact_ban`, `curfew`, `confession_duty`, `open_gates`,
  `doomsday` (`uniform` wird gesetzt, aber bisher nirgends ausgewertet)
- `sched`: `sleep`, `work_end`, `evening_sermon`

### Neues Zufallsereignis

Eintrag in `data/events.json`. Bedingungen und Effekte stehen in
[Schritt 6](06-karte-und-ereignisse.md#datengetriebene-zufallsereignisse). Zum Ausprobieren
`weight` vorübergehend hoch und `cooldown` niedrig setzen.

### Karte ändern

`data/maps/*.json` bearbeiten und mit `tools/preview_maps.py` prüfen. Höchstens 63 Regionen je
Stufe. Die Kennung der Heimatregion (`home`) muss existieren.

## Rezepte mit Code

### Neuer Modifikator oder Schalter

1. An der Stelle der Simulation, die beeinflusst werden soll, den Wert abfragen:
   `w.mod("mein_faktor")`, `w.add("mein_zuschlag")` oder `w.flag("mein_schalter")`. Für
   Eigenschaften von Figuren: `p.tm("mein_faktor")`.
2. Anzeigenamen in `MOD_NAMES` oder `ADD_NAMES` in `hud.py` ergänzen, sonst erscheint im Tooltip
   der rohe Schlüssel.
3. Den Schlüssel in den Datendateien benutzen.

### Neuer Ereigniseffekt

- Allgemein verwendbarer Effekt: neuen Zweig `elif k == "…"` in `events.apply()`.
- Einmalige Sonderlogik: Funktion `fx_<name>(w, ctx)` in `events.py` anlegen und im Ereignis mit
  `"call": "<name>"` aufrufen. Liefert die Funktion einen Text, erscheint er als Ergebnis-Popup.
- Neue Bedingung: Abfrage in `events.eligible()`.

### Neue Tätigkeit für Figuren

Beispiel: Mitglieder sitzen in der Freizeit am Lagerfeuer.

1. **Objekt auffindbar machen:** Die Feuerstelle hat `"use": "stove"`. Für eine eigene Funktion
   einen neuen `use`-Wert vergeben, dann steht das Objekt in `w.by_use["…"]`.
2. **Entscheidung:** In `Pawn.leisure()` einen Zweig ergänzen, der das nächste freie Objekt sucht
   und `self.go(w, "campfire", w.stand_tiles(t.x, t.y), thing=t, dur=120)` aufruft.
3. **Ausführung:** Methode `h_campfire(self, w, j)` anlegen. Sie läuft pro Tick, zählt `j.t` hoch,
   wendet Wirkungen an (`self.add_thought(...)`) und liefert `True`, wenn `j.t >= j.dur`.
4. **Anzeige:** Einträge in `JOB_NAMES` und `GO_NAMES`.
5. **Aufräumen:** Braucht die Tätigkeit mehr als die Reservierung des Objekts, gehört das Lösen in
   `Pawn.end_job()`, weil Aufträge jederzeit abgebrochen werden können.

### Neue Rolle für Mitglieder

1. `ROLES`, `ROLE_SKILL`, `ROLE_DESC` in `config.py` ergänzen (bei neuer Fähigkeit auch `SKILLS`).
2. Methode `work_<rolle>(self, w)` in `pawns.py`, die Arbeit sucht und `True` liefert, wenn ein
   Auftrag begonnen wurde.
3. Soll die Rolle als Arbeiter aushelfen, wenn sie nichts zu tun hat: in `Pawn.try_work()` eintragen.
4. Soll sie automatisch an Neuzugänge vergeben werden: `best_role()` anpassen.
5. Inspektor und Mitgliederliste zeigen die Rolle von selbst an, da sie über `ROLES` laufen. Das
   Raster der Rollenknöpfe in `draw_inspector()` ist für sechs Rollen in zwei Reihen ausgelegt.

### Neue Art von Außenstehenden

1. Name in `KIND_NAMES`; Startwerte in `make_outsider()`; Obergrenze in `World.spawn()`.
2. Verhalten in `think_outsider()` (oder eigene Funktion, dann in `Pawn.think()` verzweigen).
3. Abrechnung beim Verlassen in `events.outsider_left()`.
4. Wann sie erscheinen: `World.hourly()` oder ein Ereigniseffekt `spawn`.
5. Aussehen in `IsoView.pawn_sprite()` (Farbe, Aufsatz `acc_*`), Aktionen in `draw_inspector()`.
6. Reaktion der Wächter in `work_guard()`.

### Neue Ressource

1. Attribut in `World.__init__()`.
2. Anzeige in `hud.draw_top()`, Symbol `icon_*` im Manifest.
3. Erzeugung und Verbrauch in den passenden Handlern (`h_*`) oder in `daily()`.
4. Falls Ereignisse sie ändern sollen: Zweig in `events.apply()`.
5. Ausgabe im Auto-Spieler (`smoke_test.py`) ergänzen, um die Balance zu beobachten.

### Neues Panel

1. Funktion `draw_<name>(app)` in `hud.py`: `r = ui.panel(panel_rect(app, breite, höhe), "Titel")`,
   dann `close_btn(app, r)`.
2. In `app.py` in `PANEL_SIZE` und `PANEL_DRAW` eintragen.
3. Öffnen über `app.toggle_panel("<name>")`: Taste in `App.keys()`, Schaltfläche in `draw_bottom()`.
4. Zeile in der Liste `HELP` in `hud.py` und in der Steuerungstabelle der Projekt-README.

### Neue Aktion auf der Karte

Prüf- und Ausführungsfunktion in `Strategic` nach dem Muster von `campaign_block()` und
`start_campaign()`, Daten in `campaigns.json`, Schaltfläche in `MapView.side_content()`. Tägliche
Wirkung in `Strategic.daily()`.

## Stolperfallen

**Simulation und Oberfläche getrennt halten.** Kein `import pygame` und kein Import aus `ui/` in
`cultsim/sim/`. Braucht die Simulation eine Reaktion der Oberfläche, legt sie etwas in `w.notes`,
`w.popups` oder `w.cues` ab.

**Nur `w.rng` für Zufall in der Simulation.** Das Modul `random` direkt zu benutzen macht Tests
nicht reproduzierbar.

**Spielstände sind Abbilder der Objekte.** Jedes neue Attribut an `World`, `Pawn`, `Region`,
`Strategic` fehlt in alten Spielständen. `Thing` und `Job` haben `__slots__`, neue Felder müssen
dort eingetragen werden. Nichts an die `World` hängen, was `pickle` nicht speichern kann.

**Nach Bauänderungen `w.dirty = True`.** `_add_thing()`, `_del_thing()` und `finish()` tun das
selbst. Wer Gelände, Böden oder Zonen direkt ändert, erhöht außerdem `w.ground_rev`, sonst zeigt der
Renderer das alte Bodenbild.

**Nach Änderungen an Regeln, Anwälten oder Projekten `w.recompute_mods()`.** Sonst gelten die alten
Werte bis Mitternacht.

**Nach Änderungen an `p.traits` den Speicher leeren:** `p._tm = None`.

**Geld nur über `w.earn()` und `w.spend()`.** Direkte Änderungen an `w.money` fehlen in der Bilanz.
(Die Erstattung in `World.remove()` ist eine bestehende Ausnahme.)

**Figuren über `w.remove_pawn()` entfernen,** nie direkt aus `w.pawns` löschen. Sonst bleiben
Bett, Reservierungen und Regionalleitung belegt.

**Nummern statt Objekte merken.** Wer sich eine Figur oder ein Objekt über mehrere Ticks merkt,
speichert die `id` und fragt `w.pawn_ids.get(id)` ab. Figuren können jederzeit verschwinden.

**Aufträge können jederzeit enden.** `rebuild()`, Gespräche und Befehle rufen `cancel_job()` auf.
Ein Handler darf sich nicht darauf verlassen, dass er bis `j.dur` läuft.

**Listen beim Durchlaufen kopieren.** `for p in w.pawns[:]`, wenn im Schleifenrumpf Figuren
entstehen oder verschwinden können.

**Zeichenfunktionen können den Zustand ändern.** Eine Schaltfläche in `hud.py` kann die Partie
beenden oder einen Spielstand laden. `App.frame()` prüft deshalb nach Panel und Popup, ob
`self.mode` noch `"game"` ist, und bricht sonst ab. Neue Zeichenfunktionen, die so etwas auslösen,
kehren danach sofort zurück.

**Texte sind fest im Code und in den Daten.** Es gibt keine Übersetzungsschicht. Zeichenketten wie
Raumnamen dienen teils auch als Schlüssel: `ROOM_COL` in `render.py` und die Erkennung des
Ziegengeheges in `rebuild()` vergleichen deutsche Raumnamen. Wer einen Raumnamen in `ROOM_ROLES`
ändert, sucht den alten Namen im ganzen Projekt.

**Leistung.** Teuer sind `rebuild()`, erfolglose Wegsuchen und Schleifen über alle Figuren mal alle
Figuren. Entscheidungen fallen deshalb nicht in jedem Tick, sondern nach Ablauf von `think_cd`, und
manche Prüfungen laufen nur alle 10 oder 15 Ticks (`w.tick_n % 15 == 0`). `smoke_test.py` gibt am
Ende die Ticks pro Sekunde aus; ein deutlicher Rückgang nach einer Änderung ist ein Warnzeichen.

## Doku aktuell halten

Die Dokumentation wird mit jeder Erweiterung im selben Arbeitsgang angepasst. Die Tabelle zeigt,
welche Datei bei welcher Änderung betroffen ist:

| Änderung | Anzupassen |
|---|---|
| Neue Datei oder neues Modul, verschobene Verantwortung | [README](README.md) (Lernpfad, „Wo finde ich was?“), [Schritt 1](01-ueberblick.md) (Verzeichnisse, Schichten) |
| Hauptschleife, Zeitkonstanten, Ablauf von `tick`, `hourly`, `daily` | [Schritt 2](02-spielschleife-und-zeit.md) |
| Neuer Schlüssel in einer JSON-Datei, neue Datendatei, neue Methode in `Assets` | [Schritt 3](03-daten-und-assets.md) |
| Felder von `World` oder `Thing`, `rebuild()`, Begehbarkeit, Modifikatoren, Lehre, Speichern | [Schritt 4](04-welt.md) |
| Felder von `Pawn` oder `Job`, neue Art, Rolle, Tätigkeit, Gesprächsart, Wegfindung | [Schritt 5](05-figuren.md) |
| Felder von `Region`, Tagesrechnung der Karte, neue Kartenaktion, neue Bedingung oder neuer Effekt für Ereignisse, neues Systemereignis, Sieg und Niederlage | [Schritt 6](06-karte-und-ereignisse.md) |
| Zustand von `App`, neues Panel, neuer Baustein in `UI`, Zeichenreihenfolge, Kartenansicht | [Schritt 7](07-oberflaeche.md) |
| Neues oder geändertes Skript in `tools/` | [Schritt 8](08-tests-und-werkzeuge.md) |
| Neue Erweiterungsmöglichkeit, neue Stolperfalle, neue Schlüssel für `mods`, `adds`, `flags` | dieser Schritt |
| Bedienung, Startoptionen, Funktionsumfang aus Spielersicht | [Projekt-README](../../README.md) |
| Testbefehle, Architekturregeln, Zielgruppe oder Schreibregeln der Doku | [CLAUDE.md](../../CLAUDE.md) |

Regeln für die Pflege:

- Auf Funktions- und Klassennamen verweisen, nicht auf Zeilennummern.
- Listen, die den Code spiegeln (Felder, Schlüssel, Funktionen), vollständig halten oder
  ausdrücklich als Auswahl kennzeichnen.
- Wird eine Funktion umbenannt, den alten Namen in `docs/entwicklung/` suchen und ersetzen.
- Das Datum unter „Stand“ in der [README](README.md) anpassen.
