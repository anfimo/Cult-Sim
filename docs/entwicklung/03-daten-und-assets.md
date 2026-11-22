# Schritt 3: Daten und Assets

[Zurück zur Übersicht](README.md) · Vorher: [Schritt 2](02-spielschleife-und-zeit.md) · Weiter: [Schritt 4](04-welt.md)

Dateien: [data.py](../../cultsim/data.py), [assets.py](../../cultsim/assets.py), `data/*.json`,
`assets/manifest.json`.

## Grundsatz: Inhalte liegen in JSON, Regeln im Code

Was es im Spiel gibt (Gebäude, Eigenschaften, Regeln, Ereignisse, Kampagnen, Karten, Namen), steht
in `data/*.json`. Der Python-Code enthält die Mechanik, die diese Einträge auswertet. Viele
Erweiterungen sind deshalb reine Datenänderungen. Neue Mechanik braucht Code.

## Das Objekt `DATA`

`cultsim/data.py` stellt ein globales Objekt `DATA` bereit. `DATA.load()` liest alle Dateien einmal
ein. `App.__init__()` und `World.__init__()` rufen es bei Bedarf auf.

| Attribut | Datei | Aufbau |
|---|---|---|
| `DATA.buildables` | `buildables.json` | Dictionary: Kennung → Gebäudedefinition |
| `DATA.traits` | `traits.json` | Dictionary: Kennung → Eigenschaft einer Figur |
| `DATA.edicts` | `edicts.json` | Dictionary: Kennung → Regel der Gemeinschaft |
| `DATA.doctrine` | `doctrine.json` | Abschnitte `axes`, `archetypes`, `myths`, `ranks`, `projects` |
| `DATA.campaigns` | `campaigns.json` | Abschnitte `campaigns`, `chapters`, `actions`, `lawyers`, `status` |
| `DATA.events` | `events.json` | Dictionary: Kennung → Zufallsereignis |
| `DATA.names` | `names.json` | Namenslisten, Berufe, Lebensläufe |
| `DATA.maps` | `maps/local.json`, `country.json`, `world.json` | je eine Kartenstufe |

Der Zugriff ist schlicht `DATA.buildables["bed"]["cost"]`. Es gibt keine Klassen für die Einträge
und keine Schemaprüfung beim Laden (Ausnahme: Karten, siehe `tools/preview_maps.py`). Ein
Tippfehler in einem Schlüssel fällt erst auf, wenn der Code ihn liest.

`ROOT` in `data.py` ist das Projektverzeichnis. In einem mit PyInstaller gebauten Programm ist es
der Ordner neben der ausführbaren Datei. Alle Pfade zu `data/`, `assets/`, `mods/` und `saves/`
gehen von `ROOT` aus.

### Mods

`load_json()` legt nach der Basisdatei alle gleichnamigen Dateien aus `mods/<name>/data/` darüber
(`_merge()`): Dictionaries werden rekursiv zusammengeführt, Listen angehängt, einfache Werte ersetzt.

## Die Datendateien im Einzelnen

### `buildables.json`: alles, was auf einer Kachel stehen kann

| Schlüssel | Bedeutung |
|---|---|
| `name`, `desc`, `cat` | Anzeige; `cat` ist der Reiter im Baumenü (`Struktur`, `Boden`, `Möbel`, `Kult`) |
| `kind` | Art des Objekts, bestimmt das Verhalten (Tabelle unten) |
| `cost` | Preis in Euro |
| `work` | Arbeitsaufwand in Ticks bei normalem Tempo |
| `drag` | Platzieren mit der Maus: `single`, `line` (mit Shift als Rechteck-Umriss) oder `rect` |
| `use` | Funktion, über die der Code das Objekt findet (`bed`, `stove`, `altar` …) |
| `blocks` | ob das Objekt die Kachel sperrt; Vorgabe: nur bei Wand und Zaun |
| `pracht` | Beitrag zum Pracht-Wert des Raums |
| `doctrine` | Verschiebung der Lehre, solange das Objekt steht, zum Beispiel `{"isolation": 0.12}` |
| `speed` | Arbeitsgeschwindigkeit, bisher nur bei Kochstellen |
| `sprite` | Kennung im Manifest; Vorgabe ist die eigene Kennung |
| `hidden` | nicht im Baumenü anzeigen (Bäume, Felsen) |

`Data.load()` ergänzt in jedem Eintrag `id`, `sprite` und `blocks`, falls sie fehlen.

| `kind` | Verhalten | vorhandene Einträge |
|---|---|---|
| `wall` | sperrt für alle, begrenzt Räume | `wall_wood`, `wall_stone` |
| `door` | begrenzt Räume, für Menschen begehbar | `door_wood` |
| `fence` | sperrt für alle, begrenzt Gehege | `fence` |
| `gate` | begrenzt Gehege, für Mitglieder begehbar | `gate` |
| `floor` | Bodenbelag, kein eigenes Objekt, sofort fertig | `floor_wood`, `floor_stone`, `floor_tile`, `floor_carpet` |
| `object` | Möbel und Kultobjekte, ein Objekt pro Kachel | `bed`, `table`, `stove`, `altar` … |
| `nature` | Bäume, Büsche, Felsen; überbaubar gegen Aufpreis | `tree`, `bush`, `boulder` |
| `animal` | erzeugt eine Figur statt eines Objekts | `goat` |

Der Code fragt Objekte fast nie über ihre Kennung ab, sondern über `use`. Eine Feuerstelle und ein
Herd haben beide `"use": "stove"` und werden vom Koch gleich behandelt. Welche `use`-Werte der Code
kennt, zeigt eine Suche nach `by_use.get(` und `count_use(`.

### `traits.json`: Eigenschaften von Figuren

`mods` sind Faktoren auf Werte der Figur (`work`, `faith_gain`, `faith_decay`, `convert`, `tithe`,
`food_use`, `rest_use`, `flee`, `wealth`) sowie der Zuschlag `leak`. `skills` verschiebt
Fähigkeiten, `mood` die Grundlaune. `weight` ist die Häufigkeit beim Auswürfeln; Einträge mit
`weight` 0 werden nur gezielt vergeben (Maulwürfe). `hidden` verbirgt die Eigenschaft im Inspektor.

### `edicts.json`: Regeln der Gemeinschaft

| Schlüssel | Bedeutung |
|---|---|
| `name`, `text` | Anzeige |
| `cost`, `phase` | Preis in Erleuchtung, frühestmögliche Phase |
| `mods` | Faktoren, werden über alle aktiven Quellen multipliziert |
| `adds` | Zuschläge, werden über alle aktiven Quellen addiert |
| `flags` | Schalter, die der Code mit `w.flag("…")` abfragt |
| `sched` | Tagesablauf: `sleep` als `[von, bis]`, `work_end`, `evening_sermon` |
| `doctrine` | Verschiebung der Lehre, solange die Regel gilt |
| `requires_use` | benötigtes Objekt, zum Beispiel ein Beichtstuhl |

Wie daraus wirksame Werte werden, erklärt
[Schritt 4](04-welt.md#regeln-und-modifikatoren).

### `doctrine.json`: Lehre

- `axes`: die drei Achsen `commerce`, `isolation`, `apocalypse` mit Anzeigenamen.
- `archetypes`: Ausrichtungen mit Bedingung `cond` (Wertebereich je Achse) und `mods`. Die
  Reihenfolge zählt: Der erste passende Eintrag gewinnt, der letzte (`gemischt`) passt immer.
- `myths`: Gründungsmythen mit Startwerten der Achsen.
- `ranks`: Ränge mit Preis in Erleuchtung und Robenfarbe.
- `projects`: Großprojekte der Phase 3 mit `money`, `ep`, `days`, `mods` und optional `need_share`.
  Das Projekt `weltreligion` ist die Siegbedingung.

### `campaigns.json`: Kartenebene

- `campaigns`: Werbekampagnen mit `cost`, `days`, `power`, `heat`, `tracts`, `aware`, `phase`.
- `chapters`: Ausbaustufen einer Ortsgruppe mit `cost` und `upkeep`.
- `actions`: `pr`, `lobby`, `hub`, `translate`. Die Kennungen sind im Code fest verdrahtet
  (`Strategic.action_block()`, `do_action()`).
- `lawyers`: Stufen der Rechtsabteilung mit Tageskosten.
- `status`: Anzeigenamen der fünf Eskalationsstufen einer Region.

### `events.json`: Zufallsereignisse

Aufbau und alle Effekt-Schlüssel stehen in
[Schritt 6](06-karte-und-ereignisse.md#datengetriebene-zufallsereignisse).

### `maps/*.json`: Karten

Jede Stufe hat `bounds`, `home` (Heimatregion), `geo` (Längen-/Breitengrade oder ebene Koordinaten),
`pop_unit`, `languages`, `links` (Verbindungen über Wasser) und `regions`. Eine Region hat `id`,
`name`, `polys` (Umrisse als Punktlisten), `pop`, `lang`, `wealth`, `openness`, `state`, `press`,
`military`, `affinity` (Vorliebe je Achse der Lehre) und `quirk` (Eigenheit mit `mods` für `growth`,
`heat`, `cost`, `income`, `legal`). Fehlt `maps/local.json`, nimmt der Code eine eingebaute
Minimalkarte (`FALLBACK_MAP` in `strategic.py`).

## Assets

`Assets` in [assets.py](../../cultsim/assets.py) liest `assets/manifest.json` und danach die
Manifeste aller Mods. Das Manifest ordnet jeder Sprite-Kennung eine Datei, einen Anker und eine
Anzahl Einzelbilder zu:

```json
"altar": {"file": "sprites/altar.png", "anchor": [16, 24], "frames": 1}
```

Die wichtigsten Methoden:

| Methode | Zweck |
|---|---|
| `get(sid, frame)` | liefert `(Bild, ankerX, ankerY)`; lädt beim ersten Zugriff |
| `frames(sid)` | liefert `(Liste der Einzelbilder, ankerX, ankerY)` |
| `tinted(sid, frame, farbe, alpha)` | eingefärbte Kopie, zwischengespeichert; Grundlage für Figuren und Markierungen |
| `ghost(sid, frame, ok)` | halbtransparente Bauvorschau, blau oder rot |
| `icon(sid, scale)` | Symbol für die Oberfläche |
| `play(sid)` | Ton abspielen; unbekannte Kennungen werden ignoriert |

Bilder werden erst beim ersten Zugriff geladen. Fehlt eine Datei oder ein Eintrag, erzeugt
`_placeholder()` anhand des Namensanfangs (`terrain_`, `pawn_`, `fx_`, `icon_` …) ein einfarbiges
Ersatzbild in passender Größe. Ein fehlendes Sprite bringt das Spiel also nicht zum Absturz.

Die Töne, die die Simulation über `w.cues` anfordert, heißen wie die Einträge unter `sounds` im
Manifest: `click`, `place`, `build_done`, `convert`, `alert`, `event`, `coin`, `error`.

Wie Sprites gezeichnet sein müssen (Maße, Anker, Ebenen der Figuren), steht im Abschnitt „Assets
ersetzen und erweitern“ der [Projekt-README](../../README.md).

## Übung

1. In `data/buildables.json` den Preis der Pritsche (`bed`) ändern, das Spiel starten und im
   Baumenü nachsehen. Danach zurücksetzen.
2. In `data/edicts.json` die Regel `zehnt` ansehen und im Code nach `mod("tithe")` suchen: An
   welchen Stellen wirkt der Faktor?
3. Eine Sprite-Datei unter `assets/sprites/` vorübergehend umbenennen und das Spiel starten, um den
   Platzhalter zu sehen.
