# Schritt 2: Spielschleife und Zeit

[Zurück zur Übersicht](README.md) · Vorher: [Schritt 1](01-ueberblick.md) · Weiter: [Schritt 3](03-daten-und-assets.md)

Dateien: [ui/app.py](../../cultsim/ui/app.py) (`run`, `frame`), [sim/world.py](../../cultsim/sim/world.py)
(`tick`, `hourly`, `daily`), [config.py](../../cultsim/config.py).

## Grundidee

Ein Spiel wartet nicht auf Eingaben wie eine Formularanwendung. Es läuft in einer Endlosschleife,
die in jedem Durchlauf drei Dinge tut: Eingaben lesen, den Spielzustand fortschreiben, das gesamte
Bild neu zeichnen. Ein Durchlauf heißt Frame.

```python
# App.run(), sinngemäß
while self.running:
    dt = min(0.1, self.clock.tick(60) / 1000.0)   # Sekunden seit dem letzten Frame, höchstens 60 Frames/s
    self.frame(pygame.event.get(), dt)            # Eingabe, Simulation, Zeichnen
    pygame.display.flip()                         # fertiges Bild anzeigen
```

`dt` ist auf 0,1 Sekunden begrenzt. Hängt das Fenster kurz, springt die Simulation dadurch nicht um
mehrere Sekunden nach vorn.

## Frames und Ticks sind getrennt

Die Bildrate schwankt je nach Rechner. Würde die Simulation pro Frame einen Schritt rechnen, liefe
das Spiel auf schnellen Rechnern schneller. Deshalb rechnet die Simulation in festen Schritten
(Ticks), und die Hauptschleife bestimmt pro Frame, wie viele Ticks fällig sind:

```python
# App.frame(), sinngemäß
self.acc += dt * TPS * self.speed      # TPS = 20, speed = 0, 1, 2 oder 4
n = min(int(self.acc), 200)            # ganze fällige Ticks, gedeckelt
self.acc -= int(self.acc)              # der Bruchteil bleibt für den nächsten Frame
for _ in range(n):
    w.tick()
    if w.popups or w.over:             # ein Ereignis hält die Zeit sofort an
        self.acc = 0.0
        break
```

Dieses Verfahren heißt fester Zeitschritt mit Akkumulator. Der übrig gebliebene Bruchteil `acc`
wird an den Renderer übergeben, der damit die Position laufender Figuren zwischen zwei Ticks
interpoliert. Dadurch sieht die Bewegung bei 60 Bildern pro Sekunde flüssig aus, obwohl nur 20-mal
pro Sekunde gerechnet wird.

Die Simulation steht, wenn die Geschwindigkeit 0 ist, ein Popup offen ist, das Spiel zu Ende ist
oder das Pausenmenü angezeigt wird.

## Zeitrechnung

| Konstante | Wert | Bedeutung |
|---|---|---|
| `TPS` | 20 | Ticks pro Sekunde bei einfacher Geschwindigkeit |
| `TICKS_PER_HOUR` | 100 | eine Spielstunde dauert bei einfacher Geschwindigkeit 5 Sekunden |
| `TICKS_PER_DAY` | 2400 | ein Spieltag dauert bei einfacher Geschwindigkeit 2 Minuten |
| `START_TICK` | 600 | das Spiel beginnt um 6:00 Uhr an Tag 1 |

Der einzige Zeitzähler ist `w.tick_n`. Daraus berechnen sich `w.day` (ab 1 gezählt) und `w.hour`
(Kommazahl von 0 bis unter 24). Alle Dauern im Code sind in Ticks angegeben, zum Beispiel
`dur=90` für einen Bekehrungsversuch.

## Ablauf eines Frames

`App.frame()` arbeitet in dieser Reihenfolge:

1. Fenster schließen und Vollbild-Umschaltung behandeln.
2. `ui.begin()`: Mausposition und Klicks dieses Frames erfassen.
3. Im Hauptmenü: `hud.draw_menu()` zeichnen und fertig.
4. Feststellen, ob ein Popup oder das Spielende alles andere sperrt (`modal`).
5. `keys()`: Tastenkürzel auswerten.
6. Fällige Ticks rechnen (siehe oben).
7. Töne aus `w.cues` abspielen.
8. Kamera bewegen (Tasten, Verfolgen einer Figur).
9. Vorschau des aktiven Werkzeugs berechnen (`preview()`).
10. Spielwelt zeichnen (`IsoView.draw()`), darüber Namen und Raumnamen (`world_labels()`).
11. HUD zeichnen: Meldungen, obere und untere Leiste, Baumenü, Inspektor.
12. Geöffnetes Panel oder die Karte zeichnen.
13. Popup zeichnen oder, wenn nichts sperrt, Mauseingaben in der Spielwelt auswerten (`world_input()`).
14. `ui.end()`: Tooltip zeichnen.

Zeichnen und Abfragen der Oberfläche fallen zusammen: Eine Schaltfläche wird gezeichnet und meldet
im selben Aufruf, ob sie geklickt wurde. Das Prinzip erklärt [Schritt 7](07-oberflaeche.md).
Die Mauseingabe in der Spielwelt kommt bewusst zuletzt, weil erst dann feststeht, ob der Klick
schon von einer Schaltfläche verbraucht wurde.

## Ablauf eines Ticks

`World.tick()`:

1. Falls sich Bauten geändert haben (`w.dirty`): `rebuild()` berechnet Begehbarkeit und Räume neu
   ([Schritt 4](04-welt.md#rebuild-begehbarkeit-und-räume)).
2. `tick_n` um eins erhöhen.
3. Für jede Figur `Pawn.update()` aufrufen ([Schritt 5](05-figuren.md)).
4. Alle 20 Ticks: Pflanzen auf den Feldern wachsen lassen (drei Tage bis zur Ernte).
5. Zur vollen Stunde: `hourly()`. Um Mitternacht zusätzlich: `daily()`.

### Stündlich: `World.hourly()`

- `Pawn.hourly()` für jede Figur: Laune, Glaubensverfall, Zweifel, Hunger.
- Zwischen 8 und 17 Uhr können Besucher, bei genug Verdacht auch Journalisten und Kontrolleure erscheinen.
- Zur täglichen Ereignisstunde (`w.event_hour`, zufällig zwischen 9 und 19 Uhr):
  `events.daily_roll()` würfelt ein Zufallsereignis.
- Um 2 Uhr: `events.night_checks()` prüft Fluchtversuche.
- Eine laufende Razzia wird nach Zeitablauf beendet.
- Lautsprecher wirken auf Mitglieder in der Nähe.

### Täglich: `World.daily()`

In dieser Reihenfolge: Abgaben der Mitglieder, Verderb bei zu kleinem Lager, Ertrag der Ziegen,
Anwaltskosten, Fortschritt des Großprojekts, **Kartenebene** (`Strategic.daily()`), Erleuchtung,
Verdacht und Beweise, Drift der Lehre, Ausrichtung, Modifikatoren neu berechnen, `Pawn.daily()`,
Systemereignisse (`events.daily_checks()`), Abschluss der Tagesbilanz, Prüfung der Niederlage
(Insolvenz, keine Mitglieder mehr).

Die Tagesbilanz entsteht nebenbei: Alle Geldbewegungen laufen über `w.earn(kategorie, betrag)` und
`w.spend(kategorie, betrag)`, die in `w.ledger` mitschreiben. Um Mitternacht wandert `ledger` nach
`ledger_last` und wird im Finanz-Panel angezeigt.

## Zufall und Reproduzierbarkeit

Jede `World` hat einen eigenen Zufallsgenerator `w.rng`, der aus `w.seed` gestartet wird. Die
Simulation benutzt ausschließlich `w.rng` und nie das Modul `random` direkt. Derselbe Seed mit
denselben Eingaben ergibt denselben Verlauf, worauf sich die Tests verlassen. Neuer Simulationscode
muss sich daran halten.

## Simulation ohne Fenster

```python
from cultsim.sim.world import World

w = World(seed=7)
w.popups.clear()              # das Willkommens-Popup wegklicken
for _ in range(2400):         # ein Spieltag
    w.tick()
print(w.clock(), round(w.money), [r.role for r in w.rooms])
# Tag 2, 06:00 1236 ['Schlafsaal']
```

`w.tick()` selbst achtet nicht auf offene Popups, nur die Hauptschleife hält dafür an. In eigenen
Skripten muss man Popups daher selbst leeren oder beantworten, sonst stapeln sie sich und es werden
keine neuen Zufallsereignisse gewürfelt.

## Übung

1. Das Beispiel oben mit `uv run python` ausführen und den Seed ändern.
2. In `World.daily()` die Stelle suchen, an der das Spiel durch Insolvenz endet. Ab welchem
   Kontostand passiert das?
3. Im Spiel die Tasten `1`, `2`, `3` und die Leertaste drücken und in `App.keys()` nachlesen, auf
   welche Werte `self.speed` dabei gesetzt wird.
