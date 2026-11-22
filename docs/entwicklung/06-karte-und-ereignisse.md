# Schritt 6: Kartenebene und Ereignisse

[Zurück zur Übersicht](README.md) · Vorher: [Schritt 5](05-figuren.md) · Weiter: [Schritt 7](07-oberflaeche.md)

Dateien: [sim/strategic.py](../../cultsim/sim/strategic.py), [sim/events.py](../../cultsim/sim/events.py).

## Teil A: Die Kartenebene

Auf der Karte gibt es keine einzelnen Figuren. Jede Region ist ein Satz von Kennzahlen, die einmal
pro Spieltag mit Formeln fortgeschrieben werden. Diese Art der Simulation ist typisch für
Strategiespiele: wenig Zustand, viel Rechnung.

```
Strategic  (w.strategic)
├─ phase                1, 2 oder 3
├─ languages            übersetzte Sprachen;  translating: laufende Übersetzungen
└─ levels               "local" (Stadt), "country" (Land), "world" (Welt)
     └─ Level
          ├─ regions    Kennung → Region
          ├─ order      Reihenfolge der Regionen wie in der Datei
          ├─ grid       Pixelraster: Index der Region je Pixel
          ├─ adj        Nachbarschaften;  links: Verbindungen über Wasser
          └─ home       Kennung der Heimatregion
```

`Strategic.active()` liefert die freigeschalteten Stufen. In Phase 2 laufen also Stadt und Land
gleichzeitig weiter.

### Region

Feste Werte aus der Kartendatei: `pop` (Einwohner), `lang`, `wealth`, `openness`, `state`
(Staatsmacht), `press`, `military`, `affinity` (Vorliebe je Achse der Lehre), `quirk` (Eigenheit).

Veränderlicher Zustand:

| Feld | Bedeutung |
|---|---|
| `followers` | Anhänger; `share` ist der Anteil an der Bevölkerung |
| `aware` | Bekanntheit, 0 bis 100 |
| `heat` | Verdacht in der Region, 0 bis 100 |
| `status` | Eskalationsstufe 0 bis 4 (siehe unten), `status_timer` |
| `chapter` | Ausbaustufe der Ortsgruppe, 0 bis 3 |
| `campaigns` | laufende Kampagnen: Kennung → Resttage |
| `leader` | Nummer des entsandten Mitglieds oder `None` |
| `hub` | Logistikzentrum vorhanden; `hops` ist die Entfernung zum nächsten |
| `lobby`, `pr` | Resttage der jeweiligen Wirkung |
| `delta` | Zuwachs des letzten Tages, nur für die Anzeige |
| `aggregate` | Region wird nicht selbst simuliert, sondern spiegelt eine tiefere Stufe |

`aggregate` betrifft die Heimatregion der Weltkarte (Deutschland): Ihre Werte sind die Summe der
Landeskarte, und Aktionen dort werden abgelehnt.

### Vom Polygon zum Raster

`Level._rasterize()` wandelt die Umrisse aus der Kartendatei einmal beim Start in ein grobes
Pixelraster um, in dem jedes Pixel den Index seiner Region trägt (oder -1 für Wasser). Dieses eine
Raster dient drei Zwecken:

- **Darstellung:** Die Kartenansicht färbt es ein ([Schritt 7](07-oberflaeche.md#kartenansicht)).
- **Klick:** Mausposition → Pixel → Region.
- **Nachbarschaft:** Zwei Regionen sind benachbart, wenn sich Pixel von ihnen berühren. Dazu kommen
  die `links` aus der Datei für Fähren und Flugrouten.

Außerdem berechnet die Funktion je Region einen Mittelpunkt (`cx`, `cy`) für Beschriftung und
Markierungen. Bei geografischen Karten (`geo: true`) wird die Längenachse mit dem Kosinus der
mittleren Breite gestaucht, damit die Formen stimmen.

### Aktionen des Spielers

Alle Aktionen folgen dem Muster aus [Schritt 1](01-ueberblick.md#wie-die-oberfläche-die-simulation-steuert):
eine Prüffunktion, die `None` oder einen Fehlertext liefert, und eine Ausführungsfunktion.

| Aktion | Prüfung | Ausführung |
|---|---|---|
| Kampagne starten | `campaign_block(lv, r, cid)` | `start_campaign(lv, r, cid)` |
| Ortsgruppe ausbauen | `chapter_block(lv, r)` | `build_chapter(lv, r)` |
| PR, Lobby, Logistikzentrum, Übersetzung | `action_block(lv, r, aid)` | `do_action(lv, r, aid)` |
| Mitglied als Leitung entsenden | – | `assign_leader(lv, r, p)`, `recall_leader(r)` |
| Nächste Phase | `advance_req()` liefert Liste aus (Text, erfüllt) | `advance()` |

`cost(r, basis)` skaliert Preise mit der Größe der Region. `phase_scale()` (1, 60, 2500) skaliert
Kosten auf dem Gelände, die mit der Phase mitwachsen sollen, etwa Anwälte und Bußgelder.

Ein entsandtes Mitglied bleibt ein `Pawn`, ist aber `away` mit `away_kind == "post"`. Seine
Predigtfähigkeit erhöht das Wachstum der Region. Die Bindung an den Guru sinkt täglich; fällt sie
unter 12, kann sich die Leitung mit der Region abspalten (`events.leader_splits()`).

### Die Tagesrechnung: `Strategic.daily()`

Für jede Region jeder aktiven Stufe:

1. **Wachstum.** Die Obergrenze der Anhänger hängt von Einwohnerzahl, Offenheit, Ortsgruppe und der
   Passung der Lehre ab. Der Zuwachs besteht aus einem Anteil der vorhandenen Anhänger (Mundpropaganda),
   einem Anteil aus Kampagnen und einem kleinen Übersprung aus stärkeren Nachbarregionen. Er wird
   gebremst durch fehlende Übersetzung (Faktor 0,2), schlechte Versorgung (`supply_factor()`),
   fehlende Traktate (nur Stadt) und die Eskalationsstufe.
2. **Bekanntheit** steigt durch Kampagnen und Anhängeranteil und verblasst langsam.
3. **Verdacht** nähert sich einem Zielwert aus Anhängeranteil, Kampagnen und Extremität der Lehre,
   gewichtet mit Staatsmacht und Presse der Region.
4. **Eskalation** (`_status()`, siehe unten).
5. **Laufzeiten** der Kampagnen herunterzählen.
6. **Geld:** Spenden der Anhänger als Einnahme, Unterhalt von Ortsgruppe und Logistikzentrum als Ausgabe.
7. **Regionalleitung:** Bindung sinkt, mögliche Abspaltung.

`affinity_factor(r)` berechnet die Passung der Lehre: das Skalarprodukt aus den drei Achsen der
Lehre und den Vorlieben der Region, begrenzt auf 0,45 bis 1,6.

Am Ende prüft die Funktion den Sieg: Ist das Großprojekt `weltreligion` abgeschlossen, wird
`w.over = ("win", …)` gesetzt.

### Eskalation einer Region

```
0 Unauffällig ──Verdacht ≥ 35──► 1 Presse berichtet ──≥ 55──► 2 Behördliche Auflagen
                                                                      │ ≥ 75
                                                                      ▼
       4 Verboten (40 Tage) ◄── verloren ── 3 Verbotsverfahren (12 Tage)
              │                                   │ Verdacht < 55 oder gewonnen
              └────────── Ablauf ──► 2 ◄──────────┘
```

Die Stufen 1 und 2 fallen wieder, wenn der Verdacht deutlich sinkt. Ein Verbot löscht Ortsgruppe,
Kampagnen und Logistikzentrum der Region. Anwälte und Lobbyarbeit erhöhen die Chance, ein Verfahren
zu gewinnen.

### Verbindung zum Gelände

| Richtung | Wirkung |
|---|---|
| Gelände → Karte | Lehre, `w.mod("growth")`, `w.mod("income")`, Traktate, Anwälte, entsandte Mitglieder |
| Karte → Gelände | Einnahmen und Ausgaben; Bekanntheit der Heimatregion steuert den Besucherstrom; Verdacht der Regionen erhöht `w.heat`; Zahl der Anhänger bestimmt den täglichen Zuwachs an Erleuchtung |

## Teil B: Ereignisse

`events.py` enthält keine Klassen, nur Funktionen, die auf der `World` arbeiten. Es gibt zwei
Sorten von Ereignissen.

### Popups

Jedes Ereignis mündet in ein Popup: ein Dictionary in `w.popups` mit `title`, `text`, `choices`,
`ctx` (Kontext, etwa das betroffene Mitglied) und `kind` (`event`, `info`, `bad`, `result`).
`popup(w, titel, text, choices, ctx, kind)` legt es an. Solange die Liste nicht leer ist, hält die
Hauptschleife die Zeit an und zeigt das erste.

Wählt der Spieler eine Option, ruft die Oberfläche `choose(w, pop, i)`. Die Funktion bucht die
Kosten ab, wendet die Effekte mit `apply()` an und zeigt bei Zufallsausgängen ein Folge-Popup mit
dem Ergebnistext. `choice_block(w, ch)` prüft vorab, ob die Kosten bezahlbar sind.

### Datengetriebene Zufallsereignisse

Sie stehen vollständig in `data/events.json`:

```json
"reporter": {
  "title": "Der Lokalreporter", "phase": [1, 3], "weight": 1.2, "cooldown": 12,
  "cond": {"day_min": 3},
  "text": "Ein Herr vom 'Sülzheimer Boten' steht am Tor … zu {cult} …",
  "choices": [
    {"label": "Hereinbitten und herumführen", "tip": "…", "effects": {"spawn": "journalist"}},
    {"label": "Mit Tee, Keksen und Broschüre abwimmeln", "cost": {"money": 30},
     "effects": {"random": [
        {"p": 0.6, "text": "Er schreibt einen netten Dreizeiler …", "effects": {"awareness": 4}},
        {"p": 0.4, "text": "'Sekte verweigert Auskunft' …", "effects": {"heat": 6, "awareness": 6}}]}}
  ]
}
```

Ablauf: Einmal täglich zur Ereignisstunde ruft `World.hourly()` die Funktion `daily_roll()`. Mit
50 Prozent Wahrscheinlichkeit wählt sie unter allen zulässigen Ereignissen (`eligible()`) eines
gewichtet nach `weight`, setzt dessen Sperrfrist (`cooldown` in Tagen) und zeigt das Popup. Als
Kontext wird ein zufälliges Mitglied gewählt. Die Platzhalter `{cult}`, `{guru}` und `{member}` im
Text ersetzt `fill()`.

Bedingungen in `cond` (alle müssen zutreffen):

| Schlüssel | Bedeutung |
|---|---|
| `day_min` | frühester Spieltag |
| `members_min` | Mindestzahl Mitglieder |
| `heat_min`, `heat_max` | Bereich des Verdachts |
| `mood_max` | Durchschnittslaune höchstens |
| `followers_min` | Mindestzahl Anhänger auf der höchsten aktiven Kartenstufe |
| `flag` | Merker in `w.flags` muss gesetzt sein |
| `edict` | Regel muss aktiv sein |
| `doctrine` | Wertebereich je Achse, zum Beispiel `{"apocalypse": [40, 100]}` |

Effekte, die `apply()` versteht:

| Schlüssel | Wirkung |
|---|---|
| `money`, `food`, `meals`, `ep`, `tracts` | Ressource ändern (Betrag, auch negativ) |
| `food_pct` | Rohkost prozentual ändern |
| `heat`, `evidence` | Verdacht, Beweislage ändern |
| `faith_all` | Glaube aller anwesenden Mitglieder ändern |
| `mood_all` | allen einen Gedanken mit diesem Launenwert geben (72 Stunden) |
| `member` | das Mitglied aus dem Kontext ändern: `{"faith": …, "bond": …, "mood": …}` |
| `awareness` | Bekanntheit in der Heimat und abgeschwächt in allen aktiven Regionen |
| `followers_pct` | Anhänger aller aktiven Regionen prozentual ändern |
| `doctrine` | Lehre verschieben, zum Beispiel `{"commerce": 4}` |
| `spawn` | Figur erzeugen: eine Art aus `make_outsider()`, `"relative"` (besucht das Mitglied aus dem Kontext) oder `"raid"` |
| `recruit` | Anzahl neuer Mitglieder sofort aufnehmen |
| `flag` | Merker in `w.flags` setzen |
| `call` | Python-Funktion `fx_<name>(w, ctx)` aus `events.py` aufrufen |
| `random` | Liste von Ausgängen mit Wahrscheinlichkeit `p`, eigenem `text` und eigenen `effects` |

Ein neues Ereignis aus vorhandenen Bedingungen und Effekten braucht keine Zeile Python.

### Systemereignisse

Mechaniken, die mehr als ein einzelnes Popup sind, stehen als Code in `events.py`:

| Funktion | Aufgerufen von | Inhalt |
|---|---|---|
| `welcome()`, `phase_popup()` | `World.__init__()`, `Strategic.advance()` | Einführungstexte |
| `daily_checks()` | `World.daily()` | Razzia ankündigen und auslösen, Maulwürfe enttarnen, Kirchenspaltung, ausgebliebener Weltuntergang, Tipps |
| `night_checks()` | `World.hourly()` um 2 Uhr | Fluchtversuche von Zweiflern |
| `outsider_left()` | `Pawn.h_exit()` | Abrechnung, wenn Außenstehende gehen |
| `after_guru_talk()` | `Pawn.talk_bond()` | Einzelgespräch kann Maulwürfe enttarnen und Abweichler zurückholen |
| `raid_end()` | `Pawn.talk_arrest()` oder Zeitablauf | Folgen der Razzia bis zur Nachfolge oder Niederlage |
| `leader_splits()` | `Strategic.daily()` | Regionalleitung macht sich selbstständig |
| `project_done()` | `World.daily()` | Großprojekt abgeschlossen |

Mehrtägige Abläufe merken sich ihren Stand am `World`-Objekt: die Razzia in `w.flags["raid_day"]`
und `w.flags["raid_active"]`, die Kirchenspaltung in `w.schism` (Anführer, Mitläufer, Frist), der
Weltuntergang in `w.flags["doomsday_day"]`.

### Spielende

Das Spiel endet, sobald `w.over` gesetzt ist. Die Stellen:

- **Sieg:** `Strategic.daily()`, wenn das Großprojekt `weltreligion` abgeschlossen ist.
- **Niederlage:** `World.daily()` bei Insolvenz oder wenn alle Mitglieder fort sind; `raid_end()`,
  wenn der Guru verhaftet wird und kein Nachfolger bereitsteht.

## Übung

1. In `data/events.json` bei einem Ereignis `weight` auf 50 und `cooldown` auf 1 setzen, einige
   Tage spielen, zurücksetzen.
2. `tools/unit_test.py` lesen: Der letzte Abschnitt setzt die Phase auf 3 und lässt die Karte 40
   Tage laufen. Welche Werte gibt er aus?
3. Nachvollziehen, über welche Aufrufe ein Journalist den Verdacht erhöht: `h_snoop()` →
   `h_exit()` → `outsider_left()` → `w.add_heat()`.
