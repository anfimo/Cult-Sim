# Schritt 5: Figuren und Wegfindung

[Zurück zur Übersicht](README.md) · Vorher: [Schritt 4](04-welt.md) · Weiter: [Schritt 6](06-karte-und-ereignisse.md)

Dateien: [sim/pawns.py](../../cultsim/sim/pawns.py), [sim/path.py](../../cultsim/sim/path.py).

## Eine Klasse für alle Figuren

Jede Figur auf dem Gelände ist ein `Pawn`. Es gibt keine Unterklassen; das Feld `kind` entscheidet
über das Verhalten:

| `kind` | Wer | Begehbarkeitsklasse | Entscheidungsfunktion |
|---|---|---|---|
| `guru` | der Guru | `C_MEMBER` | `think_member()` |
| `member` | Mitglieder | `C_MEMBER` | `think_member()` |
| `visitor` | Besucher, mögliche Neuzugänge | `C_OUTSIDER` | `think_outsider()` |
| `journalist` | sammelt Material | `C_OUTSIDER` | `think_outsider()` |
| `inspector` | Behördenkontrolle | `C_OUTSIDER` | `think_outsider()` |
| `relative` | besorgte Angehörige | `C_OUTSIDER` | `think_outsider()` |
| `police`, `soldier` | Razzia | `C_RAID` | `think_raid()` |
| `goat` | heilige Ziege | `C_ANIMAL` | `think_goat()` |

Der Konstruktor trägt die Figur in `w.pawns` und `w.pawn_ids` ein. Erzeugt werden Figuren über
`make_member()`, `make_outsider()` oder `w.spawn()`. `gen_identity()` würfelt Name, Alter, früheren
Beruf, Fähigkeiten und zwei Eigenschaften.

Weil alle Arten dieselbe Klasse teilen, hat jede Figur alle Felder, auch die unpassenden. Ein
Besucher hat ein Feld `rank`, eine Ziege ein Feld `faith`. Aus einem Besucher wird ein Mitglied,
indem `become_member()` `kind` und einige Werte umsetzt; das Objekt bleibt dasselbe.

### Die wichtigsten Felder

| Gruppe | Felder |
|---|---|
| Position | `x`, `y` (Kommazahlen), `tile` (gerundete Kachel), `face` (Blickrichtung), `moving` |
| Bedürfnisse | `food`, `rest` (0 bis 100), `starve` (Stunden ohne Nahrung) |
| Innenleben | `faith` (Glaube), `mood` (Laune), `bond` (Bindung an den Guru), `doubter` (Zweifler) |
| Person | `name`, `age`, `former_job`, `bio`, `traits`, `skills`, `wealth`, `look` (Aussehen) |
| Stellung | `role` (Aufgabe), `rank` (Rang), `bed` (Nummer des eigenen Betts), `favorite` |
| Gedächtnis | `thoughts` (Gedanken mit Ablaufzeit), `journal` (Chronik, letzte 14 Einträge) |
| Auftrag | `job`, `think_cd` (Ticks bis zur nächsten Entscheidung), `engaged`, `orders` (Befehle an den Guru) |
| Abwesenheit | `away`, `away_kind` (`trip`, `jail`, `post`, `return`), `away_until`, `post` |
| Außenstehende | `state` (`arrive`, `browse`, `leave`), `leave_at`, `interest`, `tries`, `evidence`, `target_id`, `expelled`, `charmed` |
| Anzeige | `bubble` (Symbol über dem Kopf mit Ablaufzeit), `asleep`, `fleeing` |

## Der Zyklus einer Figur

Eine Figur ist ein Zustandsautomat mit drei Zuständen: ohne Auftrag, unterwegs, bei der Tätigkeit.
`Pawn.update()` läuft in jedem Tick:

```
               ┌──────────────────────────────────────────────┐
               ▼                                              │
        kein Auftrag (job is None)                            │
               │ think_cd zählt herunter                      │
               ▼                                              │
        think()  wählt eine Tätigkeit                         │
               │ self.go(...) sucht einen Weg                 │
               ▼                                              │
        Auftrag, stage 0: unterwegs                           │
               │ step() läuft pro Tick ein Stück              │
               ▼                                              │
        Auftrag, stage 1: am Ziel                             │
               │ h_<kind>() wird pro Tick aufgerufen          │
               ▼                                              │
        h_<kind>() liefert True  ──►  end_job()  ─────────────┘
```

Vor dem Automaten sinken bei Mitgliedern in jedem Tick `food` und `rest`. Abwesende Figuren
(`away`) werden übersprungen, bis `away_until` erreicht ist; dann läuft `come_back()`.

### Der Auftrag: `Job`

| Feld | Bedeutung |
|---|---|
| `kind` | Name der Tätigkeit, bestimmt die Funktion `h_<kind>` |
| `path` | Liste der noch zu laufenden Kacheln |
| `thing` | betroffenes Objekt, wird für die Dauer reserviert |
| `other` | Nummer der anderen Figur bei Gesprächen |
| `dur` | Dauer der Tätigkeit in Ticks |
| `t` | bisheriger Fortschritt |
| `stage` | 0 = unterwegs, 1 = am Ziel |
| `mode` | freier Zusatz: Gesprächsart, `"bed"` oder `"floor"`, Kachelindex eines Felds … |
| `cls` | Begehbarkeitsklasse für diesen Weg |
| `chase` | Ziel bewegt sich; der Weg wird nachgeführt |

`self.go(w, kind, ziele, thing=…, other=…, dur=…, mode=…)` ist der einzige Weg, einen Auftrag zu
beginnen. Die Funktion sucht einen Weg, legt den `Job` an und liefert `False`, wenn das Ziel nicht
erreichbar ist. Deshalb sehen die Entscheidungsfunktionen überall so aus:

```python
if self.go(w, "cook", w.stand_tiles(st.x, st.y), thing=st, dur=70):
    return True          # Auftrag angenommen
# sonst nächste Möglichkeit versuchen
```

`end_job()` räumt auf: Reservierung des Objekts lösen, Feld freigeben, Gesprächspartner entlassen.
`cancel_job` ist derselbe Code unter anderem Namen und wird von außen benutzt, wenn eine Figur
unterbrochen werden soll.

### Namensschemata

Welche Funktion zu einer Tätigkeit gehört, ergibt sich aus dem Namen. Eine Erweiterung besteht oft
nur aus einer neuen Methode mit passendem Namen.

| Schema | Aufgerufen von | Zweck | Beispiele |
|---|---|---|---|
| `h_<job.kind>(w, j)` | `Pawn.update()` | Tätigkeit ausführen; `True` = fertig | `h_build`, `h_eat`, `h_sleep`, `h_talk` |
| `work_<role>(w)` | `Pawn.try_work()` | Arbeit für eine Rolle suchen; `True` = gefunden | `work_worker`, `work_cook`, `work_guard` |
| `talk_<mode>(w, o)` | `Pawn.h_talk()` | Ergebnis eines Gesprächs mit Figur `o` | `talk_convert`, `talk_bond`, `talk_arrest` |
| `fx_<name>(w, ctx)` | `events.apply()` | Sondereffekt eines Ereignisses | `fx_mole_kick`, `fx_schism_talk` |

Die Anzeigetexte dazu stehen am Ende von `pawns.py` in `JOB_NAMES`, `GO_NAMES` und `TALK_NAMES`;
`Pawn.status_text()` setzt daraus die Zeile im Inspektor zusammen.

## Wie ein Mitglied entscheidet

`think_member()` ist eine Prioritätenliste, die von oben nach unten abgearbeitet wird. Der erste
Punkt, der einen Auftrag ergibt, gewinnt:

1. Befehle des Spielers an den Guru (`orders`): Ort aufsuchen oder Gespräch führen.
2. Starker Hunger (`food < 22`): essen.
3. Völlige Erschöpfung (`rest < 10`): schlafen.
4. Schlafenszeit laut Tagesablauf: schlafen, sofern nicht ausgeruht.
5. Leichter Hunger (`food < 50`): essen.
6. Predigtzeit: predigen oder zuhören (`try_sermon()`).
7. Arbeitszeit: Arbeit der eigenen Rolle (`try_work()`).
8. Sonst Freizeit (`leisure()`): meditieren, plaudern oder herumschlendern.

Findet eine Rolle keine eigene Arbeit, helfen Koch, Schreiber, Prediger und Werber als Arbeiter aus.

| Rolle | Funktion | Tätigkeiten |
|---|---|---|
| `worker` | `work_worker()` | nächsten Bauplan bauen, sonst säen oder ernten |
| `cook` | `work_cook()` | an einer Kochstelle aus Rohkost Mahlzeiten machen |
| `clerk` | `work_clerk()` | Traktate drucken, sonst Spendenbriefe schreiben |
| `preacher` | `work_preacher()` | Besucher bekehren, Zweifler betreuen |
| `recruiter` | `work_recruiter()` | vormittags auf Werbetour gehen, sonst wie Prediger |
| `guard` | `work_guard()` | Flüchtige stellen, Unerwünschte hinausbegleiten, patrouillieren |

Der Guru arbeitet immer wie ein Prediger.

## Gespräche

Ein Gespräch ist ein Auftrag `talk` mit zwei Beteiligten. `start_talk(w, o, mode, dur, chase)`
schickt die sprechende Figur zur anderen. Die andere bekommt einen Auftrag `listen` und merkt sich
in `engaged`, wer mit ihr spricht; daran erkennen Dritte, dass sie besetzt ist. Nach `dur` Ticks
ruft `h_talk()` die Funktion `talk_<mode>()` auf, die das Ergebnis berechnet.

Mit `chase=True` läuft das Ziel weiter, und der Weg wird alle zehn Ticks nachgeführt. Das nutzen
Wächter (`catch`, `escort`), die Polizei (`arrest`) und Angehörige (`relative`). Die Arten `catch`,
`escort` und `arrest` wirken sofort beim Erreichen.

## Reservierungen

Damit nicht zwei Figuren dasselbe Objekt benutzen, gibt es drei Mechanismen:

- `thing.reserved` hält die Nummer der Figur, die ein Objekt gerade benutzt. `go()` setzt den Wert,
  `end_job()` löscht ihn. Die Suchfunktionen filtern auf `reserved in (None, self.id)`.
- `thing.owner` ordnet ein Bett dauerhaft einer Figur zu (`start_sleep()`).
- `w.field_busy` enthält die Kachelindizes der Felder, an denen gerade gearbeitet wird.

## Laune, Glaube, Zweifel

`Pawn.hourly()` rechnet einmal pro Spielstunde:

- **Gedanken:** `add_thought(kennung, text, wert, stunden, w)` legt einen Gedanken an oder ersetzt
  den mit derselben Kennung. Abgelaufene werden entfernt.
- **Laune:** Zielwert ist 55 plus die Summe aller Gedankenwerte, ein Anteil der Bindung, die
  Grundlaune der Eigenschaften und der Zuschlag `w.add("mood")`, abzüglich Hunger und Müdigkeit.
  Die Laune nähert sich dem Ziel pro Stunde um 15 Prozent.
- **Glaube:** sinkt stündlich, bei schlechter Laune schneller, bei guter langsamer. Er steigt durch
  Predigten, Meditation und Gespräche.
- **Zweifel:** Unter 25 Glaube wird ein Mitglied zum Zweifler und bleibt es, bis der Glaube wieder
  36 erreicht. Zweifler können nachts fliehen (`events.night_checks()`).
- **Hunger:** Nach 30 Stunden ohne Nahrung wird das Mitglied vom Rettungsdienst abgeholt.

### Eigenschaften und Fähigkeiten

`p.tm("work")` liefert das Produkt aller Faktoren, die die Eigenschaften der Figur auf diesen
Schlüssel haben. Das Ergebnis wird in `p._tm` zwischengespeichert. Wer `p.traits` ändert, setzt
`p._tm = None`. `p.tm_add("leak")` summiert Zuschläge.

Fähigkeiten (`skills`) laufen von 0 bis 10 und wachsen bei der Ausübung langsam. `work_rate()`
macht daraus das Arbeitstempo, zusammen mit `tm("work")`, `w.mod("work")` und einem Abzug bei Hunger
oder Müdigkeit. Welche Fähigkeit zu welcher Rolle gehört, steht in `ROLE_SKILL` in `config.py`.

## Außenstehende

Außenstehende durchlaufen `state`: `arrive` (gehen zu einem Besucherplatz) → `browse` (tun das, was
ihre Art tut) → `leave` (gehen zum Ausgang). Spätestens bei `leave_at` gehen sie von selbst. Beim
Verlassen ruft `h_exit()` die Funktion `events.outsider_left()`, die abrechnet: Ein Journalist
veröffentlicht je nach gesammeltem Material (`evidence`) einen harmlosen Bericht oder eine
Enthüllung, ein Kontrolleur verhängt Bußgelder, ein Besucher lässt eine Spende da.

Der Journalist sammelt in `h_snoop()` Material aus dem, was er in seiner Nähe sieht: schlechte
Laune, Zweifler, Hungernde, Schlafende auf dem Boden, Sperrzonen, Beichtstuhl, Wachturm, Lautsprecher.

## Wegfindung

[sim/path.py](../../cultsim/sim/path.py) enthält zwei Funktionen ohne Abhängigkeit zum Rest:

- `astar(cost, size, sx, sy, goals)` sucht den günstigsten Weg von einem Start zu einer **Menge**
  von Zielen. `cost` ist eine Begehbarkeitskarte aus `w.passmap`. Bewegung in acht Richtungen,
  diagonal nur, wenn beide angrenzenden Kacheln frei sind. Ergebnis: Liste von `(x, y)` ohne die
  Startkachel, eine leere Liste, wenn man schon am Ziel steht, oder `None`. Nach 9.000 untersuchten
  Kacheln gibt die Suche auf.
- `label_components(cost, size)` nummeriert zusammenhängende Gebiete.

Der Simulationscode ruft `astar()` nie direkt auf, sondern `w.path()`. Diese Funktion verwirft
gesperrte Ziele und prüft über die Gebietsnummern, ob überhaupt ein Weg existieren kann. Das ist
wichtig, weil eine erfolglose A*-Suche die teuerste ist: Sie durchsucht alles Erreichbare.

Ziele sind meist nicht die Kachel eines Objekts, sondern die Kacheln daneben
(`w.stand_tiles(x, y)`), weil das Objekt selbst gesperrt ist. Wird während des Laufens die nächste
Kachel gesperrt, sucht `step()` einen neuen Weg zum selben Ziel.

## Übung

1. Im Spiel ein Mitglied anklicken und die Statuszeile beobachten. Die Texte in `JOB_NAMES` und
   `GO_NAMES` wiederfinden.
2. `h_cook()` lesen: Wie viel Rohkost wird zu wie vielen Mahlzeiten, und wovon hängt das ab?
3. In `think_member()` nachvollziehen, warum ein hungriges Mitglied auch während der Predigt isst.
4. Überlegen: Was müsste man ändern, damit Mitglieder in der Freizeit am Lagerfeuer sitzen?
   Die Auflösung steht in [Schritt 9](09-erweitern.md#neue-tätigkeit-für-figuren).
