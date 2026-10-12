<p align="center"><img src="src/lg_tv_sim/admin/static/logo.png" alt="LG webOS TV Simulator logo" width="160" height="160"></p>

# LG webOS TV Simulator

> **SIMULATOR – kein echter LG-TV.** Testsimulator auf Protokoll- und Datenebene für den
> LG WebOS Channel Editor. Kein webOS-Nachbau, kein Tuner, keine Firmware-Bestandteile.

Der Channel Editor verbindet sich per SSH/SFTP mit `127.0.0.1:2222` wie mit einem gerooteten LG-TV:
SQLite-Backup herunterladen, `luna-send`-Aufrufe ausführen (Senderliste, Nummernwechsel mit
MOVE/SWAP/COPY/DENY, Favoriten A–H, Reihenfolge, Listennamen) und Fehler reproduzierbar auslösen. Ein
Reset stellt jederzeit den identischen Ausgangszustand her.

## Schnellstart (MX Linux / Debian, ohne Root)

```bash
cd LgWebOs-Sim
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest                     # alle Tests inkl. echtem Editor (falls vorhanden)
cp config/example.toml config/local.toml       # optional anpassen
.venv/bin/lg-tv-sim serve                      # SSH 127.0.0.1:2222, Admin http://127.0.0.1:8767
```

Python ≥ 3.11 genügt (MX Linux liefert 3.11.2). Das System-Python wird nicht verändert.

Geladen wird genau eine Konfiguration: `--config <datei>`, sonst `$LG_TV_SIM_CONFIG`, sonst
`config/local.toml`, sonst die Standardwerte. `config/example.toml` ist die Vorlage für lokal,
`config/docker.toml` die für den Container (siehe [Docker](#docker)).

## Editor anbinden

1. Simulator-Passwort: `$LG_TV_SIM_PASSWORD` setzen oder das generierte Passwort aus
   `.simulator/credentials` verwenden. **Nie das TV-Passwort.**
2. Host-Key einmalig bekannt machen. Der Editor nutzt `load_system_host_keys()` mit `RejectPolicy`:
   ```bash
   .venv/bin/lg-tv-sim known-hosts --install ~/.ssh/known_hosts   # fügt [127.0.0.1]:2222 hinzu
   ```
3. Im Editor (`http://127.0.0.1:8765`) Host `127.0.0.1`, Port `2222`, Simulator-Passwort eintragen und
   „Vom LG importieren“ starten.
4. Zustand, Journal und Fehlerregeln unter `http://127.0.0.1:8767` verfolgen.

Das SSH-Port-Feld im Verbindungsdialog gibt es ab Editor v0.6.2, die Übertragung nutzt den Port ab v0.6.3.
Ältere Editor-Versionen verbinden immer auf Port 22. Mehr dazu in
[docs/compatibility-contract.md](docs/compatibility-contract.md).

## Beispielablauf (Spec §19.5)

1. `lg-tv-sim serve --fixture synthetic_favorites_47`
2. In der Admin-Oberfläche **Reset auf Fixture** und Run-ID notieren.
3. Im Editor importieren, einzelne Favoritenoperation ausführen und im Journal prüfen.
4. Liste A ab 1 durchnummerieren, Vorschau prüfen, auf den „TV“ übertragen.
5. Endzustand im Admin-UI mit dem Editor vergleichen.
6. Szenario `fail_after_second_step` aktivieren (mit Reset), erneut übertragen, Teilzustand prüfen und neu importieren.

## CLI

```text
lg-tv-sim serve [--fixture F] [--scenario S] [--listen HOST] [--ssh-port P] [--admin-port P]
lg-tv-sim inspect-fixture <datei|fixture>      lg-tv-sim validate-fixture <datei|fixture>
lg-tv-sim import-fixture <datei> --name N      # private reale Sicherung, read-only, nie committen
lg-tv-sim reset [--fixture F] [--scenario S] [--force]
lg-tv-sim scenarios list | activate <id>
lg-tv-sim export-state <pfad>                  lg-tv-sim export-trace <pfad>
lg-tv-sim known-hosts [--install DATEI]        lg-tv-sim build-synthetic
```

`reset`, `scenarios activate` und `export-*` sprechen die Admin-API des laufenden Servers an.

## Fixtures und Szenarien

| Fixture | Inhalt |
|---|---|
| `real_20261011_1417` | Echte Senderliste des LG-TVs vom 11.10.2026 (879 Sender: Satellit 709, Kabel 170; A 51, C 8). Dazu 220 Streamingsender (LG Channels, Tabelle `ip`, Empfangsart `IP`). Bereinigt: nur `ip.call_num` (Kontakt-E-Mails der Anbieter) und `ip.ip_chan_service_url` (Stream-URLs, teils mit Keys) geleert, alles andere unverändert. Liegt in `fixtures/recorded/` |
| `real_20261011_2301` | **Standard.** Echte Senderliste desselben TVs vom 11.10.2026 23:01: wie 14:17, zusätzlich 5 LG Channels in Liste D (251–255, vom Editor übertragene Reihenfolge) und Liste B umbenannt in „AI-Favoriten“. Gleich bereinigt (`ip.call_num`, `ip.ip_chan_service_url`) |
| `real_20261011_1417_ipfav` | Wie `real_20261011_1417`, zusätzlich 15 LG-Channels-Sender (100 „LG 1“ … 984 „YTN“) in der dort leeren Liste B, gespeichert wie am TV: Indizes 251–265 in `ip` und je eine Zeile in `favorite_idx`. Erzeugt per `lg-tv-sim build-synthetic`. **Achtung:** Wer vom Simulator importiert und danach am echten TV überträgt, muss vorher die Listen vom echten TV neu laden, sonst stehen diese 15 Sender in der Arbeitskopie |
| `mixed_modes` | Alle Empfangsarten auf kleinem Raum: 12 Satellit, 3 Kabel (Kabel 1 neben Satellit 1), 2 Antenne, 5 LG Channels; Liste A mit 4 Satellit- und 2 IP-Mitgliedern (IP ab 251), Liste D nur IP (251–253). Grundlage der E2E-Tests für Editor v0.6.4 |
| `mini` | 19 Einträge: WELT HD 13/403/1015, zwei Einträge auf 101, Tauschpaar 20/21, vorhandene Astra-Kopie (HGTV HD 1827/26), gleichnamige Dienste, Kabel |
| `synthetic_favorites_47` | 112 Einträge, 47 Favoriten in A (Neunummerierung erfordert 49 MOVE, 7 SWAP, 4 COPY), B–H, Radio, Kabel |
| `synthetic_realistic` | 915 Einträge nach der Struktur eines echten Backups nach dem Umnummerieren: Satellit 603 TV / 106 Radio, Kabel 101 / 69, A = Astra-Kopien auf 1–51, C = Radio 70–77, echte ID-Layouts (Radio-Flag, `min_no` ohne LCN), Doppelnummern, verschlüsselte Sender. Namen und DVB-Daten erfunden, dazu 36 erfundene Antennensender (26 TV, 10 Radio) |

Eigene Sicherungen: `lg-tv-sim import-fixture fixtures/private/channel.sql --name meintv` (landet in
`.simulator/fixtures/`, git-ignoriert) und erscheint danach in der Fixture-Auswahl. Mit `--public` landet die
Sicherung bereinigt in `fixtures/recorded/` und darf committet werden: `ip.call_num` und `ip.ip_chan_service_url`
werden geleert, und der
Import bricht ab, wenn danach noch irgendwo E-Mail-Adressen, URLs oder `key=`/`token=`-Parameter stehen. Bei echten Daten lehnt der
Simulator das Umnummerieren von Einträgen ab, deren ID nicht `maj = min = Nummer` kodiert (siehe
[docs/compatibility-gaps.md](docs/compatibility-gaps.md)). Fehlerszenarien liegen als YAML in `fixtures/scenarios/` und sind in
[docs/observed-lg-behavior.md](docs/observed-lg-behavior.md) beschrieben. Unbekannte Schlüssel führen zu einem Fehler.

## Tests

```bash
.venv/bin/python -m pytest                 # alles
.venv/bin/python -m pytest -m "not editor" # ohne echten Editor
LG_EDITOR_PATH=/pfad/zum/editor .venv/bin/python -m pytest -m editor
.venv/bin/ruff check src tests
```

Die Editor-E2E-Tests starten den **echten Editor-Code** in einer temporären Kopie (ohne `data/`) mit dem
Interpreter des Editors (`LG_EDITOR_PYTHON`, Standard `python3`). `HOME` wird auf ein Testverzeichnis mit
eigener `known_hosts` umgebogen. Der Golden-Test speichert das Journal als Testartefakt.

## PyCharm / PhpStorm

Interpreter `.venv/bin/python`, Run-Konfiguration „Module name“ `lg_tv_sim` mit Parametern `serve` sowie
eine pytest-Konfiguration für `tests/`.

## Docker

Images liegen in der GitHub Container Registry (`linux/amd64`, `linux/arm64`):

| Tag | Inhalt |
| --- | --- |
| `ghcr.io/robnice/lg-webos-simulator:latest` | letztes Release |
| `ghcr.io/robnice/lg-webos-simulator:X.Y.Z` | feste Release-Version |
| `ghcr.io/robnice/lg-webos-simulator:dev` | aktueller Entwicklungsstand, nur für Tests |

Gebaut wird automatisch (`.github/workflows/`), jeweils erst nach grünem `ruff check` und `pytest`:

- Jeder Push auf `dev` baut `:dev`.
- Ein Tag `vX.Y.Z` auf `main` baut `:X.Y.Z` und, außer bei Vorabversionen wie `1.0.0-rc1`, `:latest`. Der
  Tag muss `__version__` in `src/lg_tv_sim/version.py` entsprechen (einzige Versionsquelle, `pyproject.toml`
  liest sie). Tags außerhalb von `main` werden abgelehnt.

Beispiel: [docs/docker-compose.example.yml](docs/docker-compose.example.yml). Ports nur auf `127.0.0.1`
veröffentlichen (`127.0.0.1:2222:2222`, `127.0.0.1:8767:8767`).

**Konfiguration:** Den Ordner `/config` auf einen Host-Ordner mappen (`./config:/config`). Beim ersten Start
kopiert das Image seine Vorlage (`config/docker.toml`) nach `/config/simulator.toml`. Danach gehört die Datei
dir: Sie wird nie überschrieben, Änderungen wirken nach einem Neustart des Containers. Wer die aktuelle
Vorlage will, löscht die Datei und startet neu. Unbekannte Schlüssel und Loopback-Adressen (`127.0.0.1`
würde den Simulator im Container unerreichbar machen) brechen den Start mit einer klaren Meldung ab.

**Rechte:** Der Container startet als root, legt `/config` und `/app/.simulator` an, setzt deren Besitzer auf
`PUID:PGID` (Standard 10001, im Beispiel 1000 = typischer Desktop-Benutzer) und startet den Simulator dann
nur noch als dieser Benutzer. `PUID`/`PGID` 0 werden abgelehnt. Mit `user:` in Compose entfällt der
root-Schritt; die Ordner müssen dann schon passend gehören.

Runs, Host-Key und generiertes Passwort liegen im Volume `/app/.simulator`:

```bash
docker compose exec lg-tv-sim cat .simulator/credentials             # Passwort (ohne LG_TV_SIM_PASSWORD)
docker compose exec lg-tv-sim lg-tv-sim known-hosts >> ~/.ssh/known_hosts
```

**Alles über das Compose-File:** Das Image läuft ohne Config-Datei. Einstellbar per Umgebungsvariable:

| Variable | Wirkung |
|---|---|
| `LG_TV_SIM_ADMIN_TOKEN` | öffnet die Admin-Oberfläche für jeden Hostnamen (z. B. `http://omv:8767`); das ist dann das Passwort der Seite, sie fragt einmal pro Browser-Tab danach (nicht das SSH-Passwort). Ohne Token nur `127.0.0.1`/`localhost` |
| `LG_TV_SIM_PASSWORD` | SSH-Passwort für den Editor, sonst generiert (`.simulator/credentials`) |
| `LG_TV_SIM_FIXTURE`, `LG_TV_SIM_SCENARIO` | Startzustand und Fehlerszenario |
| `LG_TV_SIM_MODEL`, `LG_TV_SIM_SERIAL` | gemeldete TV-Identität (Seriennummer muss mit `SIM-` beginnen) |
| `PUID`, `PGID` | Besitzer der gemappten Ordner |

Die Variablen haben Vorrang vor `/config/simulator.toml`; die Datei ist nur für seltene Feineinstellungen da.

`known-hosts` nennt bei `0.0.0.0` den Host `127.0.0.1`. Bei anderem Host oder anderem veröffentlichtem Port:
`known-hosts --host <name> --port <port>`.

## Grenzen

Antwortlayouts der Luna-Methoden und die ID-Transformation beim Umnummerieren sind Annahmen (siehe
[docs/compatibility-gaps.md](docs/compatibility-gaps.md) und [docs/evidence-register.md](docs/evidence-register.md)).
Der Simulator ersetzt nicht den abschließenden Hardwaretest.

## Fehlerbehebung

- `BadHostKeyException` / `SSHException: not found in known_hosts`: Schritt „Host-Key“ wiederholen. Nach
  dem Löschen von `.simulator/keys/` den alten Eintrag `[127.0.0.1]:2222` aus `~/.ssh/known_hosts` entfernen.
- `error: admin port 127.0.0.1:8767 is not available`: Ein anderer Prozess nutzt den Port, z. B. ein noch
  laufendes `lg-tv-sim serve`. Prüfen mit `ss -ltnp | grep 8767`, Prozess beenden oder
  `lg-tv-sim serve --admin-port <frei>`. Der SSH-Server startet in diesem Fall gar nicht erst.
- Ports **8765** (Editor) und **8766** (Editor-Entwicklung/Browser-Tests) sind für den Simulator gesperrt.
- `config error: … not a loopback address`: externe Bindung ist absichtlich gesperrt.
- Reset liefert `409`: Eine SSH-Sitzung, die bereits geschrieben hat, ist noch offen. Editor-Vorgang
  abwarten oder `force` verwenden.

Weitere Dokumente: [Architektur](docs/architecture.md) · [Sicherheit](docs/security.md) ·
[Historie](docs/development-history.md)
