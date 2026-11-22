# Schritt 7: Oberfläche und Darstellung

[Zurück zur Übersicht](README.md) · Vorher: [Schritt 6](06-karte-und-ereignisse.md) · Weiter: [Schritt 8](08-tests-und-werkzeuge.md)

Dateien: [ui/app.py](../../cultsim/ui/app.py), [ui/widgets.py](../../cultsim/ui/widgets.py),
[ui/render.py](../../cultsim/ui/render.py), [ui/hud.py](../../cultsim/ui/hud.py),
[ui/mapview.py](../../cultsim/ui/mapview.py).

## Wer macht was

| Datei | Aufgabe |
|---|---|
| `app.py` | Klasse `App`: Fenster, Hauptschleife, Zustand der Oberfläche, Tastatur, Maus in der Spielwelt, Werkzeuge, Speichern |
| `widgets.py` | Klasse `UI`: Schaltfläche, Text, Balken, Textfeld, Scrollbereich, Tooltip; Farbkonstanten |
| `render.py` | Klasse `IsoView`: zeichnet das Gelände, rechnet zwischen Kachel und Bildschirm um |
| `hud.py` | Funktionen `draw_*(app)`: alles, was über der Spielwelt liegt |
| `mapview.py` | Klasse `MapView`: Kartenansicht mit Seitenleiste |

Es gibt kein Szenensystem. `App.frame()` entscheidet in jedem Bild anhand weniger Zustandsfelder,
was gezeichnet wird.

### Zustand der Oberfläche

Alles liegt als Attribut an `App` und wird von `reset_ui()` zurückgesetzt:

| Attribut | Werte | Bedeutung |
|---|---|---|
| `mode` | `"menu"`, `"game"` | Hauptmenü oder laufende Partie |
| `w`, `view`, `mapview` | Objekte | aktuelle `World`, `IsoView`, `MapView` (entstehen in `start_world()`) |
| `speed` | 0, 1, 2, 4 | Spielgeschwindigkeit |
| `panel` | `None`, `"members"`, `"doctrine"`, `"finance"`, `"help"`, `"pause"`, `"map"` | geöffnetes Vollfenster |
| `menu` | `None`, `"build"`, `"zone"` | geöffnetes Menü über der unteren Leiste |
| `tool` | `None`, `("build", kennung)`, `("zone", z)`, `("demolish",)` | aktives Werkzeug |
| `drag` | `None` oder Startkachel | laufendes Aufziehen mit dem Werkzeug |
| `sel` | `None`, `("pawn", id)`, `("thing", id)`, `("tile", x, y)` | Auswahl für den Inspektor |
| `follow` | `None` oder Nummer einer Figur | Kamera folgt |
| `confirm` | `None` oder Tupel | zweiter Klick nötig, zum Beispiel beim Verstoßen |
| `flash` | `None` oder (Text, Ende) | kurze Fehlermeldung über der unteren Leiste (`App.say()`) |

Auswahl und Verfolgung speichern Nummern statt Objekten. Verschwindet die Figur, liefert
`w.pawn_ids.get(id)` einfach `None`.

## Immediate-Mode-Oberfläche

In klassischen Oberflächen legt man Widgets einmal an und hängt Rückruffunktionen daran. Hier gibt
es keine Widget-Objekte. Jede Schaltfläche ist ein Funktionsaufruf, der in jedem Bild erneut
ausgeführt wird, die Schaltfläche zeichnet und zurückgibt, ob sie in diesem Bild geklickt wurde:

```python
if ui.button(R(x, y, 170, 28), "Abreißen", tip="Erstattet 30 %"):
    w.remove(tx, ty)
```

Das hat drei Folgen, die man beim Lesen von `hud.py` kennen muss:

- **Layout ist Arithmetik.** Positionen werden von Hand mitgezählt (`y += 22`). `R` ist eine
  Abkürzung für `pygame.Rect`.
- **Der Zustand liegt woanders.** Eine Schaltfläche merkt sich nichts. Ob sie hervorgehoben ist,
  wird jedes Mal übergeben (`active=app.panel == "members"`). Was nicht gezeichnet wird, existiert
  nicht und kann nicht geklickt werden.
- **Spiellogik steht direkt im `if`.** Das ist bequem, verleitet aber dazu, Regeln in die
  Oberfläche zu schreiben. Mehrzeilige Logik gehört in eine Methode der Simulation, damit Tests und
  der Auto-Spieler sie ebenfalls nutzen können.

### Die Bausteine von `UI`

| Methode | Zweck |
|---|---|
| `begin(screen, events)` / `end()` | Rahmen um jedes Bild: Eingaben erfassen, am Ende den Tooltip zeichnen |
| `panel(rect, title)` | Hintergrundkasten; meldet die Fläche als „gehört zur Oberfläche“ an |
| `button(rect, label, tip, enabled, active, …)` | Schaltfläche; `True` bei Klick |
| `text(x, y, s, color, font)` | einzeilige Schrift; Schriftgrößen `"s"`, `"m"`, `"b"`, `"t"` |
| `wrap(x, y, w, s, …)` | Text mit Umbruch; liefert die Höhe |
| `bar(rect, frac, color, label)` | Fortschrittsbalken |
| `axis_bar(rect, value, target, neg, pos)` | Balken von −100 bis +100 für die Lehre |
| `tooltip(rect, text)` | Tooltip für eine beliebige Fläche |
| `textfield(key, rect, value)` | Texteingabe; liefert den neuen Wert |
| `scroll_area(key, rect, content_h)` / `end_scroll()` | Scrollbereich; liefert den Versatz |
| `render(s, color, font)` | gerenderte Schrift aus dem Zwischenspeicher |

Zustand, der mehrere Bilder überdauern muss, hält `UI` selbst unter einem Schlüssel: die
Scrollposition in `ui.scroll[key]`, das aktive Textfeld in `ui.focus`.

### Wer bekommt den Klick?

Weil alles übereinander gezeichnet wird, braucht es Regeln, damit ein Klick auf ein Fenster nicht
auch die Spielwelt dahinter trifft:

- **`ui.used`:** Die erste Schaltfläche, die einen Klick annimmt, setzt `used`. Alle weiteren
  ignorieren ihn.
- **Ebenen und Sperren:** `ui.layer` ist 0 für das HUD, 1 für Panels, 2 für Popups. `App.frame()`
  trägt zu Beginn in `ui.blockers` ein, welche Flächen höherer Ebenen offen sind. `ui.hover()`
  lehnt alles ab, was unter einer solchen Fläche liegt. Ein Popup und das Pausenmenü sperren den
  ganzen Bildschirm.
- **`ui.over_ui(pos)`:** Jedes `panel()` meldet seine Fläche in `ui.rects` an. `world_input()` fragt
  damit, ob die Maus über der Oberfläche steht. Die Liste des vorigen Bildes (`rects_prev`) zählt
  mit, damit ein Fenster, das in diesem Bild noch nicht gezeichnet ist, den Klick trotzdem schützt.

Für Tests lässt sich die Mausposition über `ui.fake_mouse` vorgeben.

## Eingabe in der Spielwelt

- **`App.keys()`** wertet Tastendrücke aus. Die Kamera wird getrennt in `frame()` über gehaltene
  Tasten bewegt.
- **`App.world_input()`** behandelt Maus in der Spielwelt: Linksklick wählt aus oder beginnt das
  Aufziehen mit dem Werkzeug, Loslassen wendet es an, Rechtsklick legt das Werkzeug ab oder schickt
  den ausgewählten Guru los, Mausrad zoomt, mittlere Taste verschiebt.
- **`App.pick(pos)`** bestimmt, was unter dem Mauszeiger liegt: zuerst die nächste Figur, dann ein
  Objekt (auch wenn man auf den oberen Teil eines hohen Sprites klickt), sonst die Kachel.
- **Werkzeuge:** `drag_tiles(a, b)` macht aus Start- und Endkachel je nach `drag`-Art eine Liste
  von Kacheln, `preview(hover)` liefert daraus Vorschau und Gesamtpreis für den Renderer,
  `apply_tool(a, b)` ruft für jede Kachel `w.place()`, `w.set_zone()` oder `w.remove()` auf.

## Isometrische Projektion

Das Gitter wird um 45 Grad gedreht und in der Höhe halbiert dargestellt. Eine Kachel ist eine Raute
von 32 × 16 Pixeln. Aus Kachelkoordinaten `(x, y)` wird die Bildposition der Kachelmitte:

```
sx = (x - y) * 16 + ox
sy = (x + y) * 8  + oy
```

`ox` und `oy` verschieben das Bild so, dass die Kameraposition (`view.cx`, `view.cy`) in der
Bildmitte liegt (`set_view()`). Die Umkehrung von Bildschirm zu Kachel steht in `tile_at()`.

| Methode | Richtung |
|---|---|
| `to_view(x, y)` | Kachel → Pixel im unvergrößerten Puffer |
| `to_window(x, y)` | Kachel → Pixel im Fenster (mit Zoom) |
| `tile_at(px, py)` | Fensterpixel → Kachel |
| `pan_screen(dx, dy)` | Kamera um Bildschirmpixel verschieben |

**Drehung:** Die Ansicht lässt sich in vier Schritten drehen (`view.rot`). Gedreht wird nicht das
Bild, sondern die Koordinate: `rxy()` bildet eine Kachel vor der Projektion auf ihre gedrehte
Position ab, `unrot()` macht es rückgängig. Sprites werden nicht gedreht; nur Figuren (Vorder- und
Rückansicht, gespiegelt) und Zaunlatten reagieren auf die Blickrichtung.

**Zoom:** Gezeichnet wird immer in einen Puffer in Originalgröße, der am Ende ganzzahlig (1- bis
4-fach) hochskaliert wird. So bleibt die Pixelgrafik scharf.

## Wie `IsoView.draw()` ein Bild aufbaut

1. **Boden** aus dem Zwischenspeicher (`ground()`): Gelände, Bodenbeläge und Zonen der ganzen Karte
   liegen als ein großes Bild vor, je Drehung eines. Es wird nur neu erzeugt, wenn sich
   `w.ground_rev` geändert hat. Ohne diesen Speicher müssten pro Bild über 3.000 Kacheln einzeln
   gezeichnet werden.
2. **Flache Überlagerungen:** Raumfarben, Vorschau von Zonen und Böden, Mauszeiger, Markierung der
   Auswahl.
3. **Alles, was Höhe hat,** wird in einer Liste gesammelt: Objekte, Pflanzen, Bauvorschau, Figuren,
   Symbole über Köpfen. Jeder Eintrag bekommt eine Tiefe `rx + ry` (gedrehte Koordinaten).
4. **Sortieren und zeichnen:** Die Liste wird nach Tiefe sortiert und von hinten nach vorn
   gezeichnet. Was weiter vorn steht, verdeckt, was dahinter liegt. Dieses Verfahren heißt
   Maleralgorithmus und ist der Grund, warum eine Figur hinter einer Wand verschwindet.
5. **Tageszeit:** Nachts wird der Puffer mit einer bläulichen Farbe multipliziert.
6. **Skalieren** auf die Fenstergröße.

Der Parameter `st` ist ein Dictionary mit dem, was `App.frame()` zusätzlich anzeigen will:
`hover`, `sel_pawn`, `sel_thing`, `sel_tile`, `preview`, `tick` (Animationszeit).

**Figuren** bestehen aus Graustufen-Ebenen (Haut, Robe oder Zivilkleidung, Haare, Aufsatz), die
`pawn_sprite()` einfärbt und übereinanderlegt. Die Robenfarbe kommt vom Rang. Das fertige Bild wird
unter einem Schlüssel aus allen Merkmalen zwischengespeichert. **Zäune** setzt `fence_sprite()` aus
Pfosten und bis zu vier Latten zusammen, je nach `th.conn`.

**Bewegung zwischen Ticks:** Für laufende Figuren verschiebt `draw()` die Position um den
Bruchteil `alpha` des nächsten Schritts (siehe [Schritt 2](02-spielschleife-und-zeit.md#frames-und-ticks-sind-getrennt)).

## HUD und Panels

`hud.py` besteht aus Funktionen, die `app` bekommen und zeichnen:

| Funktion | Inhalt |
|---|---|
| `draw_top()` | obere Leiste: Name, Ressourcen, Verdacht, Uhr, Geschwindigkeit |
| `draw_bottom()` | untere Leiste: Bauen, Zonen, Abriss, Panels, Ansicht |
| `draw_build_menu()` | Baumenü nach Kategorien (`CATS`) und Zonenmenü |
| `draw_notes()` | Meldungen aus `w.notes`; Klick springt zum Ort |
| `draw_inspector()`, `draw_pawn()` | rechte Spalte zur Auswahl: Figur mit Aktionen, Objekt oder Kachel mit Raum |
| `draw_members()` | Mitgliederliste (F1) |
| `draw_doctrine()` | Lehre, Regeln, Ränge, Großprojekte (F2) |
| `draw_finance()` | Bilanz, Einkauf, Akten schreddern, Anwälte (F3) |
| `draw_help()`, `draw_pause()` | Hilfe (F10) und Pausenmenü (Esc) |
| `draw_popup()` | Ereignisfenster und Spielende |
| `draw_menu()` | Hauptmenü mit Namensfeldern und Mythoswahl |

Welche Funktion zu welchem Panel gehört, steht in `PANEL_DRAW` und `PANEL_SIZE` am Anfang von
`app.py`. `effects_text()` formatiert `mods`, `adds` und `doctrine` eines Eintrags für Tooltips und
benutzt dafür `MOD_NAMES`, `ADD_NAMES` und `AX_SHORT`.

Einige Aktionen sind derzeit vollständig in `hud.py` umgesetzt und haben keine eigene Methode in
der Simulation: Journalisten bestechen (`draw_inspector()`), Akten schreddern und Anwälte wählen
(`draw_finance()`), Großprojekte starten (`draw_doctrine()`). Wer diese Mechaniken ändert, sucht
dort und nicht in `sim/`.

## Kartenansicht

`MapView.draw()` zeichnet die Reiter für Stufe und Kartenmodus, die Karte, Verbindungen,
Beschriftung und Markierungen. `side_content()` füllt die Seitenleiste: ohne Auswahl die Übersicht
der Stufe mit den Voraussetzungen der nächsten Phase, mit Auswahl die Region mit Kampagnen,
Ortsgruppe, Aktionen und Regionalleitung (`draw_pick()`).

Die Karte nutzt einen alten Trick für schnelles Umfärben, die Palettenanimation:

- `base(lv)` erzeugt einmal je Stufe ein Bild mit 8 Bit pro Pixel. Der Pixelwert ist nicht eine
  Farbe, sondern der Index der Region plus 1, mit 64 addiert für Grenzpixel und 128 für Küstenpixel.
- In jedem Bild berechnet `region_color()` für jede Region eine Farbe passend zum Kartenmodus
  (`MODES`: Einfluss, Verdacht, Gegner, Potenzial, Sprache, Logistik). Diese Farben werden als
  Palette gesetzt. Das Bild selbst bleibt unverändert.

Daraus folgt eine Grenze: höchstens 63 Regionen je Kartenstufe.

## Übung

1. In `hud.draw_bottom()` eine Schaltfläche hinzufügen, die `app.w.notify("Hallo")` aufruft, und
   im Spiel ausprobieren. Danach entfernen.
2. In `IsoView.draw()` die Zeile mit `items.sort` auskommentieren und ansehen, was passiert.
3. Im Spiel `Q` und `E` drücken und in `rxy()` nachvollziehen, wie die vier Drehungen entstehen.
