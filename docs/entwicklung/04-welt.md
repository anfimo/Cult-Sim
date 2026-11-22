# Schritt 4: Die Welt – Gitter, Bauen, Räume, Regeln

[Zurück zur Übersicht](README.md) · Vorher: [Schritt 3](03-daten-und-assets.md) · Weiter: [Schritt 5](05-figuren.md)

Datei: [sim/world.py](../../cultsim/sim/world.py).

Die Klasse `World` hält den gesamten Spielzustand. Es gibt genau ein `World`-Objekt pro Partie; ein
Spielstand ist dieses Objekt als Datei. Alles andere (Figuren, Kartenebene) hängt daran:

```
World
├─ Gitter:      terrain, variant, floor, things, zone, room_of   (je eine Liste über alle Kacheln)
├─ Objekte:     thing_list, thing_ids, blueprints, by_use, crops
├─ Räume:       rooms
├─ Figuren:     pawns, pawn_ids                                  → Schritt 5
├─ Ressourcen:  money, food, meals, ep, tracts, heat, evidence, ledger
├─ Lehre:       doctrine, bias, edicts, archetype, projects_done, project
├─ Meldungen:   notes, popups, cues, over
├─ Merker:      flags, event_cd, schism
└─ strategic    die Kartenebene                                  → Schritt 6
```

## Das Gitter

Die Karte ist quadratisch mit `MAP_SIZE` = 56 Kacheln Kantenlänge (`w.size`). Jede Eigenschaft einer
Kachel liegt in einer eigenen flachen Liste der Länge 56 × 56. Der Index einer Kachel ist

```python
i = x + y * w.size        # und zurück: x = i % size, y = i // size
```

Flache Listen statt Objekten pro Kachel sind in Spielen üblich, weil Schleifen über das ganze Gitter
dadurch schnell und einfach bleiben. Viele Funktionen rechnen direkt mit `i` und geben Mengen von
Indizes weiter (zum Beispiel als Ziele der Wegfindung).

| Liste | Inhalt je Kachel |
|---|---|
| `terrain` | Geländeart: `T_GRASS`, `T_DIRT`, `T_SAND`, `T_ROCK`, `T_ROAD`, `T_WATER` |
| `variant` | Zufallszahl für die Bildvariante des Geländes |
| `floor` | Kennung des Bodenbelags oder `None` |
| `things` | das `Thing` auf der Kachel oder `None` (höchstens eines) |
| `zone` | `Z_NONE`, `Z_FIELD` (Anbaufeld), `Z_VISIT` (Besucherzone), `Z_FORBID` (Sperrzone) |
| `room_of` | Nummer des Raums oder -1; wird von `rebuild()` berechnet |

Hilfen: `w.inb(x, y)` prüft die Kartengrenzen, `w.thing_at(x, y)` und `w.room_at(x, y)` liefern
Objekt und Raum. `w.crops` ist ein Dictionary von Kachelindex auf Wachstum (0 bis 1) für besäte Felder.

## Objekte: `Thing`

Ein `Thing` ist alles, was auf einer Kachel steht: Wand, Tür, Zaun, Möbel, Baum. Die Felder:

| Feld | Bedeutung |
|---|---|
| `id` | eindeutige Nummer (gemeinsamer Zähler `w.next_id` mit den Figuren) |
| `d` | Kennung in `DATA.buildables`; `th.defn` liefert die Definition |
| `x`, `y` | Position |
| `built` | `False`, solange es ein Bauplan ist |
| `progress` | Baufortschritt 0 bis 1 |
| `conn` | bei Zäunen: Bitmaske der Nachbarn, an die Latten anschließen |
| `owner` | bei Betten: Nummer der Figur, der es gehört |
| `reserved` | Nummer der Figur, die gerade daran arbeitet oder darauf zugeht |

Ein `Thing` speichert nur die Kennung, nicht die Definition. Preis, Aussehen und Verhalten kommen
immer frisch aus `DATA.buildables`.

Die Objekte sind mehrfach indiziert: `w.things[i]` nach Kachel, `w.thing_ids[id]` nach Nummer,
`w.thing_list` als Liste, `w.blueprints` für unfertige und `w.by_use["bed"]` für fertige Objekte
einer Funktion. Hinzufügen und Entfernen laufen deshalb nur über `_add_thing()` und `_del_thing()`,
die alle Indizes pflegen.

## Der Weg eines Bauauftrags

```
Spieler zieht mit dem Bauwerkzeug        App.apply_tool()
        │
        ▼
w.place(kennung, x, y)                   prüft can_place(), bucht Geld ab
        │   Boden und Tiere sind sofort fertig; sonst:
        ▼
Thing mit built=False in w.blueprints    wird halbtransparent gezeichnet
        │
        ▼
Arbeiter wählt den Bauplan               Pawn.work_worker() → Auftrag "build"
        │
        ▼
Arbeiter steht daneben und baut          Pawn.h_build() erhöht th.progress
        │
        ▼
w.finish(th)                             built=True, w.dirty=True, Ton "build_done"
        │
        ▼
beim nächsten Tick: w.rebuild()          Begehbarkeit und Räume neu berechnen
```

`w.remove(x, y)` reißt ab: Baupläne werden voll erstattet, fertige Objekte zu 30 Prozent, Natur
kostet 3 Euro. `w.set_zone(x, y, z)` malt Zonen.

## `rebuild()`: Begehbarkeit und Räume

Räume werden nicht vom Spieler festgelegt, sondern aus den Wänden abgeleitet. `rebuild()` berechnet
alle abgeleiteten Daten in einem Durchgang neu. Die Funktion ist teuer und läuft deshalb nicht bei
jeder Änderung, sondern höchstens einmal pro Tick: Wer Bauten ändert, setzt `w.dirty = True`, und
`tick()` ruft `rebuild()` am Anfang des nächsten Ticks auf. Dieses Muster heißt Dirty-Flag.

`rebuild()` erledigt nacheinander:

1. **Begehbarkeitskarten** `w.passmap[klasse][i]`: eine Kostenzahl pro Kachel, 0 bedeutet gesperrt.
   Es gibt vier Klassen von Figuren mit eigenen Karten:

   | Klasse | Wand, Zaun, sperrendes Möbel | Tür | Tor |
   |---|---|---|---|
   | `C_MEMBER` (Mitglieder, Guru) | gesperrt | 1,5 | frei |
   | `C_OUTSIDER` (Besucher, Presse, Behörden) | gesperrt | 1,5 | gesperrt, außer die Regel „Tag der offenen Tür“ gilt |
   | `C_RAID` (Polizei, Militär) | gesperrt | 4 | 8 |
   | `C_ANIMAL` (Ziegen) | gesperrt | gesperrt | gesperrt |

   Dazu kommen Geländekosten: Wasser gesperrt, Zufahrt 0,8, Bodenbelag 0,9, Sand 1,3, sonst 1.
2. **Zusammenhangskomponenten** `w.comp[klasse][i]`: Jede Kachel bekommt die Nummer des Gebiets, in
   dem sie liegt. Zwei Kacheln sind genau dann füreinander erreichbar, wenn die Nummern gleich sind.
   `w.reachable()` beantwortet damit Erreichbarkeit ohne Wegsuche.
3. **`w.by_use`**: fertige Objekte nach Funktion.
4. **Zaunverbindungen** (`th.conn`) für die Darstellung.
5. **Räume per Flutfüllung:** Von jeder noch nicht besuchten freien Kachel aus werden alle
   Nachbarn eingesammelt, bis Wände, Türen, Zäune oder Tore die Fläche begrenzen. Berührt die Fläche
   den Kartenrand oder hat sie mehr als 700 Kacheln, gilt sie als Außenbereich. Andernfalls entsteht
   ein `Room`: Grenzt mindestens ein Zaun oder Tor an, ist es ein Gehege (`kind == "hof"`), sonst ein
   Raum (`kind == "raum"`).
6. **Funktion und Pracht des Raums:** `ROOM_ROLES` wird von oben nach unten geprüft; der erste
   Eintrag, dessen Objekt oft genug im Raum steht, gibt dem Raum den Namen (ein Altar macht einen
   Tempel, zwei Betten einen Schlafsaal). Die Pracht ist die Summe der `pracht`-Werte von Objekten
   und Böden plus ein Zuschlag für die Größe. Ein Gehege mit einer Ziege darin wird zum Ziegengehege.
7. **Figuren aus verbauten Kacheln schieben** und ihre Aufträge abbrechen.

Am Ende erhöht `rebuild()` zwei Zähler, an denen andere Stellen erkennen, dass ihr Zwischenspeicher
veraltet ist: `w.struct_rev` (Bauten) und `w.ground_rev` (Boden, Zonen, Gelände). Der Renderer
zeichnet den Boden nur neu, wenn sich `ground_rev` geändert hat.

Hilfen für die Wegsuche: `w.path(klasse, sx, sy, ziele)` liefert einen Weg oder `None`,
`w.stand_tiles(x, y)` die begehbaren Nachbarkacheln eines Objekts, `w.free_near(x, y)` die nächste
freie Kachel, `w.visitor_spot()` einen Aufenthaltsort für Außenstehende.

## Ressourcen

| Attribut | Bedeutung | Besonderheit |
|---|---|---|
| `money` | Geld | nur über `earn()` und `spend()` ändern, damit die Bilanz stimmt |
| `food` | Rohkost | Lagergrenze `storage_cap` (60 plus 40 je Vorratskiste) |
| `meals` | gekochte Mahlzeiten | |
| `ep` | Erleuchtung | Währung für Regeln, Beförderungen, Phasenwechsel |
| `tracts` | Traktate | werden bei Bekehrung und Kampagnen verbraucht |
| `heat` | Verdacht, 0 bis 100 | `add_heat()` wendet den Faktor `heat_gain` an und begrenzt |
| `evidence` | Beweislage, 0 bis 100 | `add_evidence()` begrenzt |

Ressourcen sind reine Zahlen. Es gibt keine Gegenstände, die Figuren tragen.

## Regeln und Modifikatoren

Regeln, Ausrichtung und abgeschlossene Großprojekte verändern Spielwerte, ohne dass der Code sie
einzeln kennt. `recompute_mods()` sammelt aus allen aktiven Quellen vier Dinge ein:

| Sammlung | Verknüpfung | Abfrage | Beispiel |
|---|---|---|---|
| `mods` | multipliziert | `w.mod("work")` (Vorgabe 1,0) | Arbeitstempo × 1,1 |
| `adds` | addiert | `w.add("mood")` (Vorgabe 0,0) | Laune −5 |
| `flags` | Menge | `w.flag("curfew")` | Ausgangssperre gilt |
| `sched` | Tagesablauf | `w.schedule(pawn)` | Schlaf von 1 bis 5 Uhr |

Der Simulationscode fragt an der passenden Stelle den Wert ab, zum Beispiel
`0.035 * self.tm("food_use") * w.mod("food_use")` für den Nahrungsverbrauch. Ein neuer Schlüssel in
`edicts.json` wirkt erst, wenn irgendwo im Code `w.mod("…")`, `w.add("…")` oder `w.flag("…")` danach
fragt. Die Anzeigenamen der Schlüssel stehen in `MOD_NAMES` und `ADD_NAMES` in
[ui/hud.py](../../cultsim/ui/hud.py).

`recompute_mods()` muss nach jeder Änderung an den Quellen laufen. Das geschieht in
`toggle_edict()`, täglich in `daily()`, beim Phasenwechsel und nach einem Großprojekt. Wer
`w.lawyers` oder `w.edicts` direkt ändert, ruft es selbst auf.

`w.schedule(pawn)` liefert für die aktuelle Stunde `"sleep"`, `"sermon"`, `"work"` oder `"free"`.
Wächter haben einen eigenen Rhythmus mit Nachtschicht.

Davon zu unterscheiden ist `w.flags` (ein Dictionary ohne Unterstrich): Dort merkt sich die
Simulation freie Zustände wie den Tag der angekündigten Razzia (`raid_day`) oder ob der Guru selbst
predigt (`guru_preaches`).

## Lehre

Die Lehre besteht aus drei Achsen von −100 bis +100: `commerce`, `isolation`, `apocalypse`.

- `w.doctrine` ist der aktuelle Stand.
- `w.doctrine_target()` berechnet den Zielwert aus `w.bias`, den aktiven Regeln und den gebauten
  Objekten mit `doctrine`-Eintrag (je Objektart höchstens 20 Punkte pro Achse).
- `w.bias` ist der Anteil aus Gründungsmythos und Ereignisentscheidungen. `shift_doctrine()` ändert
  ihn; er verblasst täglich um 1,5 Prozent.
- Täglich wandert `doctrine` um 18 Prozent des Abstands auf das Ziel zu.
- `update_archetype()` wählt die erste passende Ausrichtung aus `DATA.doctrine["archetypes"]`.
  Deren `mods` fließen über `recompute_mods()` ins Spiel.

## Figuren verwalten

`w.members(present=False)` liefert Mitglieder samt Guru, `w.outsiders(kind)` die anwesenden
Außenstehenden, `w.guru` den Guru. `w.spawn(kind)` erzeugt Außenstehende mit Obergrenze je Art,
`w.convert(besucher)` macht aus einem Besucher ein Mitglied, `w.defect(p, grund)` lässt ein Mitglied
austreten (mit Folgen für Verdacht, Beweise und den Glauben der anderen), `w.remove_pawn(p)` entfernt
eine Figur und gibt Bett, Reservierungen und Regionalleitung frei. `w.start_raid()` löst eine Razzia aus.

## Kartengenerierung

`World.generate()` läuft einmal im Konstruktor: Gelände aus zwei Rauschfeldern, ein Teich mit
Sandufer, die Zufahrt von Süden (`w.road`, `w.exit`), Bäume und Felsen mit zunehmender Dichte zum
Rand, dann das Startgelände mit Hütte, vier Betten, Feuerstelle, Tisch, Kiste, Altar, einem Feld,
einer Besucherzone, dem Guru und drei Mitgliedern.

## Speichern und Laden

`World.save()` schreibt das komplette Objekt mit `pickle` in eine Datei, `World.load()` liest es
zurück. Das ist bequem, hat aber Folgen:

- Gespeichert wird alles, was am `World`-Objekt hängt, einschließlich aller Figuren und der
  Kartenebene. Die Inhalte aus `DATA` werden nicht gespeichert, sondern beim Laden frisch gelesen.
- Ein Spielstand passt nur zur Codeversion, die ihn geschrieben hat. Bekommt eine Klasse ein neues
  Attribut im Konstruktor, fehlt es in alten Spielständen, und der erste Zugriff schlägt fehl.
- `Thing` und `Job` haben `__slots__`: Neue Felder müssen dort eingetragen werden.
- Am `World`-Objekt darf nichts hängen, was `pickle` nicht speichern kann, also keine pygame-Bilder,
  keine offenen Dateien und keine Lambda-Funktionen.
- `pickle` führt beim Laden Code aus. Fremde Spielstände sind deshalb nicht vertrauenswürdig.

## Übung

1. `uv run python tools/unit_test.py` ausführen und im Skript nachlesen, wie es ein Gehege und
   einen Tempel baut und dann `w.rooms` ausgibt.
2. Im Spiel `R` drücken, um die Räume einzufärben, und eine Wand aus der Starthütte reißen. Was
   passiert mit dem Schlafsaal und warum?
3. In `ROOM_ROLES` nachsehen: Was ist ein Raum mit einem Bett und einem Altar?
