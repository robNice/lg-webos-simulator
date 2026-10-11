# LG WebOS Channel Editor – TV-Simulator
## Vollständige Projektspezifikation und Übergabe an den IDE-/KI-Agenten

> **Status:** Umsetzungsspezifikation, **kein bereits entwickelter Emulator**.  
> **Dokumentversion:** 1.0 · **Datum:** 11. Oktober 2026  
> **Empfohlene IDE:** **JetBrains PyCharm** (einheitliches Produkt, kostenlose Kernfunktionen ausreichend).  
> **Zielsprache:** Python 3.12+; projektunabhängiger Simulator mit SSH-/SFTP-Fassade, testbarer LG-Luna-Nachbildung, SQLite-Zustand und lokalem Steuer-API.  
> **Zielumgebung:** MX Linux / Debian-basierte Linux-Distribution; später optional Windows/WSL oder Docker.  
> **Priorität:** Sichere, reproduzierbare **Integrationstests des Channel Editors**, nicht die vollständige Emulation eines LG-Fernsehers.

---

## 0. Verbindlicher Hinweis für den KI-Agenten: Tatsächlichen Codebestand zuerst ermitteln

**Der aktuelle Stand des Projekts `LG WebOS Channel Editor` liegt auf der lokalen Festplatte des Benutzers. Der Verfasser dieses Dokuments hat keinen Zugriff auf diesen aktuellen Code.** Es kann bereits Änderungen nach v0.5.24 geben. Sämtliche Angaben aus der bisherigen Projektgeschichte sind als **historisch belegte Beobachtungen** oder als **Entwicklungsanforderungen** gekennzeichnet. Sie sind **keine Zusicherung**, dass der aktuelle Code genau diese Strukturen und Befehle benutzt.

Der letzte im Gespräch am echten Fernseher bestätigte Stand war **v0.5.24 (10.10.2026)**, einschließlich einer erfolgreich abgeschlossenen vollständigen automatischen Neunummerierung. Zu diesem historischen Stand gehörten `app.py`, `tv_write.py`, `number_rules.py`, `static/`, `tests/` und eine Python-Webanwendung mit SSH-Kommunikation über Paramiko. Der aktuelle Stand **muss neu ermittelt werden**.

**Vor Beginn der Simulatorimplementierung:**

1. Benutzer bitten, dem IDE-Agenten den **aktuellen lokalen Quellcode** beziehungsweise dessen Projektpfad im Workspace bereitzustellen. **Keine Dateien oder Codeversionen vom Benutzer erraten.**
2. Aktuelle Branch-, Commit-, Versions-, Test- und Paketinformationen erfassen; ungesicherte Änderungen nicht überschreiben.
3. Exakte **Transportaufrufe**, Remote-Kommandos, SSH-/SFTP-Operationen, Luna-Methoden, Argumente, Antwortparser, Timeouts und Datenbankimporte aus dem **aktuellen** Quellcode zusammentragen.
4. Erst dann den endgültigen `CompatibilityContract` (siehe unten) definieren und den Simulator dagegen bauen.
5. Stimmen historische Informationen mit dem Code nicht überein, den Konflikt in `docs/compatibility-gaps.md` dokumentieren und mit Tests beziehungsweise echten Aufzeichnungen entscheiden. **Nicht stillschweigend auf den alten Stand zurückgehen.**
6. **Kein automatischer schreibender Kontakt zum realen Fernseher** im Rahmen des Simulatorprojekts. Hardwaretests ausschließlich nach expliziter Zustimmung des Nutzers.

Der Simulator ist **ein separates Repository/Projekt**. Änderungen an der produktiven Senderverwaltung des Editors sind ausdrücklich **nicht Teil von Phase 1**.

---

## 1. Zielbild: Was der „Emulator“ wirklich sein soll

### 1.1 Abgrenzung

Das Projekt ist ein **LG-TV-Testsimulator auf Protokoll- und Datenebene**, kein vollständiges LG-webOS-Betriebssystem, keine virtuelle LG-Firmware, kein Broadcast-Tuner, kein Bild-/Ton-Decoder und keine tatsächliche DVB-S-Empfangsanlage.

Der Channel Editor soll sich zu Testzwecken möglichst **unverändert** über einen lokalen SSH-Endpunkt verbinden können und dort dieselben für ihn sichtbaren Operationen finden wie auf einem gerooteten LG-TV:

- SSH-Authentisierung und ausgewählte Remote-Kommandos.
- Konsistente SQLite-Sicherung der simulierten Senderdatenbank und Download per SFTP.
- Eine `luna-send`-ähnliche Befehlsschnittstelle mit Antworten in der erwarteten Form.
- Lesen einer Live-Senderliste mit IDs, Programmnummern, Favoriten, DVB-Identität und weiteren vom Client benötigten Attributen.
- Änderungen an Sendernummern, Belegungen und Favoritengruppen unter **konfigurierbaren, datengetriebenen Regeln**.
- Steuerbare Fehler, verzögerte Sichtbarkeit, unvollständige Transaktionen und Wiederanlauf nach einem Teilabbruch.
- Eine Beobachtungs-/Steueroberfläche für Entwickler zum Anzeigen von Zustand, Operationsprotokoll und Fehlerfällen.

### 1.2 Was explizit nicht gebaut wird

- Kein offizieller oder inoffizieller webOS-Vollsystem-Nachbau.
- Kein Reverse Engineering oder Kopieren geschützter LG-Firmwarebestandteile in den Simulator.
- Kein TV-Video, EPG-Streaming, Fernbedienungs-GUI oder physikalischer Tuner.
- Kein Einsatz als allgemein gültige Dokumentation nicht öffentlicher LG-APIs.
- Keine Behauptung, dass jeder reale LG-TV genau wie das simulierte Modell reagiert.
- Kein dauerhafter Ersatz für den abschließenden Hardware-Integrationstest.

LGs ältere VirtualBox-Emulatoren unterstützen laut Hersteller **keinen TV-Tuner**; die neueren Simulatoren sind primär auf Web-App-Entwicklung ausgerichtet. Deshalb ist dieser eng begrenzte, projektspezifische Simulator sinnvoller als eine komplette TV-VM für die Sendereditor-Tests.

### 1.3 Erfolgsdefinition

Ein unmodifizierter oder nur bezüglich **Host, Port und Test-Zugangsdaten** umkonfigurierter aktueller Channel Editor kann eine simulierte LG-Senderliste importieren, bearbeiten, die TV-Synchronisierung planen und schreiben, den Zustand verifizieren und definierte Fehler wiederholbar auslösen. Der Entwickler kann den Simulator auf denselben Ausgangszustand zurücksetzen und das identische Testszenario erneut ausführen.

---

## 2. IDE-, Technologie- und Laufzeitentscheidung

### 2.1 Empfohlene JetBrains-IDE

**JetBrains PyCharm** ist die erste Wahl. JetBrains führt seit 2025 ein einheitliches PyCharm-Produkt; die kostenlosen Kernfunktionen genügen für Python, Debugging, virtuelle Umgebungen, Tests, Git und Refactoring. Pro ist für diesen Simulator **nicht erforderlich**. PyCharm ist auch für MX Linux verwendbar, sofern die Linux-Systemanforderungen erfüllt sind.

**IntelliJ IDEA** nur dann bevorzugen, wenn das Projekt in einer vorhandenen Multi-Language-Monorepo-Struktur mit zahlreichen Java/Kotlin-Modulen liegt. **WebStorm** wäre für ein rein browserbasiertes UI nützlich, ist aber nicht die passende primäre IDE für einen Python-SSH-/SQLite-Simulator.

### 2.2 Vorgeschlagener Stack

| Baustein | Vorschlag | Begründung |
|---|---|---|
| Programmiersprache | Python 3.12+ | Passt zum zuletzt bekannten Python-Editor; starke SSH- und Test-Bibliotheken |
| SSH/SFTP-Server | **AsyncSSH** | Python-native Implementierung für lokalen SSH- und SFTP-Server; Funktionen gegen konkrete Version verifizieren |
| Zustandsmodell | `dataclasses` oder Pydantic, klar typisiert | Technische Identität und Listen-Eintrag ausdrücklich trennen |
| Persistenz | Standardbibliothek `sqlite3` | Originales SQLite-Schema einlesen; Testzustände konsistent speichern |
| Admin-API | FastAPI + Uvicorn | Lokale Steuerung, Reset, Szenarien, Zustand und Ereignisprotokolle |
| Admin-Oberfläche | Zunächst HTML/JS ohne schweres Framework | Möglichst wenig Implementierungsrisiko und geringe Wartungslast |
| Tests | `pytest`, `pytest-asyncio`, optional Hypothesis | Integrationstests mit echtem SSH-Protokoll und deterministischem Zustand |
| Qualität | Ruff, Typprüfung optional mypy/pyright | CI-taugliche Standards |
| Abhängigkeiten | `pyproject.toml`, `uv.lock` (oder kompatible `venv`-/`pip`-Alternative) | Reproduzierbare MX-Linux-Installation |
| Start-/Build-Modell | Lokal als normaler Benutzer | Kein Root, kein `sudo` für den Server |

**Kein Docker-Zwang.** Docker/Podman kann später für CI dazukommen. Zunächst soll es nativ unter MX Linux funktionieren.

### 2.3 Lokale Ports (Vorgabewerte, konfigurierbar)

- `127.0.0.1:2222`: **Fake-TV-SSH/SFTP**; absichtlich nicht Port 22.
- `127.0.0.1:8766`: **Simulator-Admin-API / Kontrolloberfläche**.
- `127.0.0.1:8765`: Historischer HTTP-Port des Editors; **nicht vom Simulator beanspruchen**.

Als Testhost wird `127.0.0.1` verwendet. Testbenutzer z. B. `root` mit **eigens generiertem Simulator-Passwort**, niemals mit den realen TV-Zugangsdaten. Die SSH-Host-Key-Identität des Simulators muss **eigenständig** erzeugt und vom echten Fernseher unterscheidbar sein.

---

## 3. Grundlegende Architektur

```text
   LG WebOS Channel Editor (AKTUELLER lokaler Quellstand)
   ---------------------------------------------------
   Browser/UI -> Editor-Backend -> SSH/SFTP-Client
                                      |
                           127.0.0.1:2222
                                      v
   +------------------------------------------------------------+
   | LG-TV-Testsimulator                                        |
   |                                                            |
   |  SSH-Transport (AsyncSSH)                                  |
   |       |                                                    |
   |       +-- Command Router: sqlite3 / luna-send / rm / ...  |
   |       +-- Virtual SFTP: /mnt/lg/.../channel.sql /tmp/...   |
   |                         |                                  |
   |                Luna-Dispatcher                              |
   |                         |                                  |
   |                 TV-Domain-Engine                            |
   |                  |            |                             |
   |            Channel State  Favorite State                    |
   |                  |            |                             |
   |                 SQLite Fixture Store                        |
   |                         |                                  |
   |                Event Log + Fault Engine                     |
   |                                                            |
   |  HTTP Admin 127.0.0.1:8766                                 |
   |  Szenario wählen / Reset / Zustand / Journal / Fehler      |
   +------------------------------------------------------------+
```

### 3.1 Schichten und Verantwortung

1. **Transport-Schicht:** SSH-Verbindung, getrennte `exec`-Kanäle, Exit-Status, STDOUT/STDERR, SFTP-Downloads. Keine LG-Geschäftslogik.
2. **Remote-Command-Router:** Explizite, überprüfte, begrenzte Remote-Kommandos; kein allgemeiner Host-Shell-Zugang.
3. **Luna-Dispatcher:** Ermittelt `service`, `method` und JSON-Parameter; erzeugt kompatible JSON-Antworten.
4. **Domain Engine:** Gerätelogik für Nummernwechsel, Platztausch, Astra-Kopien, Favoritengruppen/-reihenfolge. Keine direkte Netzwerkabhängigkeit.
5. **Repository / State Store:** Isolierte Kopie der SQLite-Fixture, Indizes, Transaktionsgrenzen, kontrollierte Persistenz.
6. **Fault Engine:** Fehlerprofile, Latenzen, divergierende Rückgaben, absichtliche Inkonsistenzen.
7. **Admin-HTTP:** Testzustand und Logs; niemals an `0.0.0.0` binden, außer nach bewusster Konfiguration.
8. **Trace Recorder/Replayer:** Normalisierte Anfrage-/Antwort-Traces aus freigegebenen echten Tests beziehungsweise aus Simulationen; sensitive Felder entfernen.

### 3.2 Harte Architekturregel

**Alle schreibenden LG-Semantiken liegen an genau einer Stelle in der Domain Engine.** Der SSH-Transport darf niemals direkt SQL-Updates „aus Versehen“ ausführen. Die Admin-API und der SSH-/Luna-Pfad benutzen dieselbe Engine und dieselben Transaktionen.

---

## 4. Zuerst den aktuellen Editor untersuchen: `CompatibilityContract`

Der IDE-Agent muss einen **automatisch nachvollziehbaren Vertragskatalog** im Repository erstellen. Er basiert auf dem **aktuellen Editor-Code**, nicht allein auf dieser historischen Beschreibung.

### 4.1 Erhebungscheckliste

- Sprache, Startbefehle, Version und Paketstruktur des Editors.
- SSH-Clientbibliothek (historisch Paramiko), Authentisierungsmethoden, Host-Key-Policy, Verbindungs-/Befehlstimeouts.
- Alle ausgeführten SSH-Kommandos als **Templates** einschließlich Shell-Quoting, erlaubten Argumenten und erwarteten Exit-Codes.
- Ob `exec_command` über `get_pty`, Shell oder reine `exec`-Requests arbeitet.
- Alle SFTP-Operationen: `stat`, `open`, `get`, `remove`, `listdir`, möglicherweise `rename`.
- Virtuelle Remote-Pfade, insbesondere Original-SQLite und temporäre Backup-Dateien.
- Welche Luna-Services, Methoden, Parameter und Antwortfelder tatsächlich genutzt werden.
- Verarbeitung von `returnValue:true/false`, `errorCode`, `errorText`, JSON-Framing und Zeilenumbrüchen.
- Ob der Editor `getChannelList` auf mehreren Modi/Quellen abruft oder komprimierte Daten erwartet.
- Zustandserkennung/Verifikation nach Nummernänderung, Platztausch, Astra-Kopie und Favoritenwechsel.
- Sicherungs-, Preflight-, Confirm- und Reimport-Ablauf einschließlich Token-Lebensdauer.
- Welche Struktur von `tuner_on`, `tuner_off`, `favorite_idx` sowie Gruppen-/Metadatentabellen vorausgesetzt wird.

### 4.2 Lieferobjekt

`docs/compatibility-contract.md` und optional `contracts/current-editor.yaml`, mit für **jeden** aufgerufenen Befehl/Endpunkt:

```yaml
# Beispiel, NICHT als aus aktuellem Code verifiziert ausgeben.
operation: read_channel_backup
transport: ssh_exec_then_sftp
remote_path: /mnt/lg/cmn_data/iepg/db/channel.sql
command_template: "sqlite3 -readonly <original> '.backup <temp>'"
creates_remote_temp_file: true
sftp_download: true
remote_cleanup: "rm -f <temp>"
observed_in: historical_v0.5.24
verified_against_current_editor: false
verified_against_real_tv: historical_only
```

Unbekannte Operationen werden **nicht stillschweigend simuliert**, sondern zuerst im Simulator als `UnsupportedOperation` mit sicherem Abbruch und gut lesbarem Trace protokolliert.

---

## 5. Historisch beobachtete TV-Schnittstellen (als Ausgangshypothesen)

Diese Schnittstellen wurden während der Entwicklung bis v0.5.24 genutzt oder auf dem echten LG untersucht. **Der Agent muss prüfen, welche davon der aktuelle Editor noch verwendet.**

### 5.1 Verzeichnisse und Datenbanken

- Historischer Originalpfad: `/mnt/lg/cmn_data/iepg/db/channel.sql`.
- Kernrelation: `tuner_on` (u. a. `dvc_chan_id`, `mso_prdt_itm_code`, `chan_no`, `chan_no_int`, `chan_std_name`, `dvb_chan_nw_id`, `dvb_chan_transf_strm_id`, `dvb_chan_svc_id`, `signal_chan_id`, `satelliteLcn_flag`, `fav_chan_gr_a`, `favoriteIdxA`).
- Zusätzliche Relationen: `tuner_off`, `favorite_idx` und weitere Tabellen müssen **aus der tatsächlichen SQLite-Fixture** übernommen werden, nicht aus einem frei erfundenen Minimalschema.
- Zusammengesetzter `tuner_on`-Primärschlüssel der untersuchten TV-DB: **(`dvc_chan_id`, `mso_prdt_itm_code`)**.
- Fernseherspezifische Backup-Befehle können `sqlite3 -readonly ... '.backup /tmp/<name>.sqlite'` verwenden; darauf folgt SFTP und Remote-Aufräumen.

### 5.2 Luna-Dienste und beobachtete Methoden

| Service | Methode | Historische Bedeutung |
|---|---|---|
| `com.webos.service.iepg` | `getChannelList` | Live-Senderliste, je nach Parametern komprimiert/gefiltert |
| `com.webos.service.iepg` | `setChannelFavoriteGroup` | Mitgliedschaft einer Gruppe setzen |
| `com.webos.service.iepg` | `releaseChannelFavoriteGroup` | Mitgliedschaft entfernen |
| `com.webos.service.iepg` | `moveChannelFavoritePriority` | Favoritenreihenfolge anpassen |
| `com.webos.service.legacybroadcast.channel` | `changeChannelNumber` | Nummernwechsel, teils Platztausch, teils Astra-Kopie |
| `com.webos.service.legacybroadcast.channel` | `getChannel` | Sendereintrag anhand aktueller Channel-ID lesen |
| `com.webos.service.legacybroadcast.channel` | `copyDvbSatelliteChannelForAstra` | Firmware kennt Sondermethode; **nicht automatisch einsetzen** |

Historischer Kommandoaufruf (vom aktuellen Code zu bestätigen):

```bash
luna-send -n 1 \
  luna://com.webos.service.legacybroadcast.channel/changeChannelNumber \
  '{"channelId":"7_32_13_13_1053_21108_1","channelNumber":99}'
```

Beispiele für JSON-Parameter der Favoritenoperationen:

```json
{"channelId":["7_32_13_13_1053_21108_1"],"favoriteGroup":["A"]}
```

```json
{"favoriteGroupId":0,"channelId":["<currentChannelId>"],"destinationChannelId":"<currentChannelId>","direction":"up"}
```

**Wichtig:** JSON-Format der Rückgaben aus realen Traces ableiten, nicht erfinden. Die Luna-Protokollierung kann `returnValue:false` liefern, obwohl der Zustand tatsächlich geändert wurde (z. B. bei Favoritenreihenfolgen). Umgekehrt kann `returnValue:true` einen anderen Effekt signalisieren als den vom Editor erwarteten.

### 5.3 Historischer Live-Listen-Aufruf

Ein bekannter Request aus dem TV-Mitschnitt:

```json
{
  "dataType": 0,
  "sort": 0,
  "channelMode": "Satellite",
  "channelType": "Satellite Digital TV",
  "channelGroup": ["All"],
  "acceptEmptyGroupName": false,
  "attribute": [{"filterType": "Invisible", "value": false}],
  "compressed": 1
}
```

Erwartete Felder in einer entsprechenden Live-Zeile können `channelId`, `channelNumber`, `channelName`, `favoriteGroup`, `favoriteIdxA`, `satelliteName`, `ONID`, `TSID`, `SVCID`, `channelMode`, `sourceIndex` enthalten. Ob die Antwort direkt `channelList` enthält, welche Gruppierung verwendet wird und wie Radio behandelt wird, ist aus dem **aktuellen** Clientparser abzuleiten.

---

## 6. Datenmodell: Senderidentität ist nicht Programmnummer

### 6.1 Zwingende Unterscheidung

Es gibt mindestens zwei Identitätsebenen:

- **DVB-Dienstidentität**, etwa ONID / TSID / SID (gegebenenfalls plus Satellit/Quelle). Das identifiziert eine ausgestrahlte Leistung, **nicht jeden Eintrag in der Senderliste**.
- **Konkreter LG-Senderlisteneintrag**, historisch an `dvc_chan_id` beziehungsweise `channelId` gebunden. Diese ID kann sich **bei einer Umnummerierung ändern**.

Der Sendername ist **niemals ein eindeutiger Schlüssel**. Die Zielnummer ist **niemals** die ursprüngliche Identität. Die originale Channel-ID dient bei einem Import als **Snapshot-/Referenzidentität**, während der Simulator die Zuordnung zu aktuell gültigen Channel-IDs über ausdrücklich gespeicherte Änderungen nachvollziehen muss.

### 6.2 Echter historischer Mehrfacheintrag (WELT HD)

```text
Programm 13:   7_32_13_13_1053_21108_1
Programm 403:  7_32_403_403_1053_21108_1
Programm 1015: 7_32_1015_1015_1053_21108_1
```

Diese drei Einträge haben dieselbe beobachtete technische DVB-Dienstkennung, sind aber drei unterschiedliche LG-Listeneinträge. Der Simulator **muss** diese Konstellation darstellen können.

### 6.3 Mehrfach belegte Programmnummern

Die reale TV-Senderliste kann dieselbe Programmnummer für **mehrere konkrete IDs** verwenden, insbesondere quer über TV/Radio oder andere Quellen/Listen. Historischer Test: Ein NDR-Eintrag lag auf **101**, während andere Einträge ebenfalls Programmnummer 101 hatten. Eine Abbildung `number -> singleChannel` ist daher **falsch**.

Erforderlich sind mindestens:

- `channelId -> exactly one current entry` (im jeweiligen Snapshot), falls nicht eindeutig: hart abbrechen.
- `programNumber -> set[channelId]`, getrennt nach Mode/Quelle, soweit das TV-Verhalten dies verlangt.
- `DVBServiceKey -> set[channelId]`.
- `favoriteGroup -> ordered list[channelId]` bzw. eindeutige Positionsinformationen.

### 6.4 Stabile interne Simulationsidentität

Die Domain Engine darf für ihre **eigenen** Daten eine synthetische, unveränderliche UUID `sim_entry_id` vergeben. **Diese UUID existiert nicht auf dem LG-TV und darf nie als LG-API-ID ausgegeben werden.** Sie dient ausschließlich der internen Nachverfolgung eines Eintrags vor und nach ID-Änderungen.

Beispiel:

```text
sim_entry_id:    84c9...         (intern stabil, nie ans TV-Clientprotokoll)
channel_id:      7_32_13_13_1053_21108_1
number:          13
DVB:             1 / 1053 / 21108
favorite_groups: [A]
```

**ID-Generierung nicht pauschal per String-Ersetzung implementieren.** Die historischen Channel-IDs enthalten teils Kanal- und Unternummern sowie quellenabhängige Felder. Die Transformation wird als getrennte, testbare Strategie `ChannelIdPolicy` modelliert und für die verwendeten Fixtures explizit validiert. Unbekannte Formate müssen sicher scheitern.

### 6.5 Datenbankschema und Synchronität

Die Testdatenbank soll das eingespielte reale Tabellen-/Spaltenschema möglichst **vollständig bewahren**. Mutationen müssen alle für den Editor sichtbaren redundanten Felder konsistent halten, z. B. `chan_no`, `chan_no_int`, `maj_no`, `dvc_chan_id`, Favoritenflags, gruppenspezifische Indexwerte und ggf. abgeleitete Felder. **Welche Felder sich tatsächlich ändern, wird anhand von Vergleichsfixtures und Traces belegt.** Keine pauschalen SQL-UPDATEs ohne Schema- und Invariantentests.

Bei Kopien neue Zeilen nur erzeugen, wenn das jeweilige Szenario diese LG-Semantik ausdrücklich konfiguriert. Originaldaten dürfen nie versehentlich überschrieben werden.

---

## 7. Emulationsprofile: Nicht alle LG-Sender verhalten sich gleich

Verhalten wird pro **Szenario / ID-Merkmal / Quellenmodus** konfiguriert und durch Tests bestätigt. Das Nutzerinterface des Channel Editors erlaubt mittlerweile neue Programmnummern 1–99; die echte Firmware zeigte bei manchen Tests andere interne Effekte. Deshalb **UI-Policy des Clients und Firmware-Verhalten im Simulator strikt trennen**.

### 7.1 Normale Umnummerierung

- Aufruf `changeChannelNumber(channelId, channelNumber)`.
- Bei geeignetem freien Ziel oder vom Profil definiertem Zustand ändert sich der Sendereintrag.
- Die ausgegebene `channelId` kann sich verändern; die alte ID darf anschließend nicht stillschweigend als gültig gelten.
- `getChannel` und `getChannelList` spiegeln den neuen Zustand entsprechend dem einstellbaren Konsistenzmodell wider.

### 7.2 Platztausch bei belegter Zielnummer

Historisch konnte LG bei einem konkreten Aufruf die Sender auf zwei Plätzen tauschen (z. B. ShopLC-HD-Test **21 → 20**, mit beobachteter Gegenänderung der bisherigen Belegung). Der Simulator benötigt einen `SWAP`-Modus, bei dem **beide** Einträge eine neue Nummer und ggf. neue Channel-ID erhalten.

**Wichtig:** FavoriteGroups und Reihenfolge gehören semantisch zu den Sender-Einträgen, nicht zu ihren Nummern. Ein reiner Platztausch soll die Gruppen **nicht unbeabsichtigt verändern**. Die frühere Fehlerklasse eines falschen Vergleichs mit dem endgültigen statt dem vorherigen Favoritenzustand muss explizit getestet werden.

### 7.3 Astra-Kopie statt echter Verschiebung

Beim früheren automatischen Nummerieren aus dem hohen Bereich wurden echte zusätzliche Einträge beobachtet:

```text
Pro7 MAXX HD: 418 -> neue Kopie auf 14; Original auf 418 blieb vorhanden
ARD-alpha HD: 125 -> neue Kopie auf 26; Original auf 125 blieb vorhanden
```

Die neuen Einträge hatten zunächst **nicht automatisch Favorit A**, während die Originale A behielten. Das führt im Client zu einem **mehrstufigen Vorgang**: neue ID erkennen, Favoriten übertragen und ursprüngliche A-Mitgliedschaft nur dann entfernen, wenn der neue Zustand verifiziert ist. Andere Gruppen B–H dürfen nicht ungewollt verändert werden.

Der Simulator benötigt dafür mindestens die getrennten Profile:

- `MOVE`: existierenden Datensatz umnummerieren;
- `SWAP`: zwei vorhandene Einträge tauschen;
- `COPY`: zusätzlichen Eintrag mit eigener ID anlegen, Original behalten;
- `REUSE_COPY`: passenden vorhandenen Ziel-Eintrag **ohne neue Nummernänderung** verwenden;
- `DENY`: Fehler wie `CHANNEL_ERROR_1003 – Channel Move Denied` ausgeben.

Die Auswahl darf **nicht allein** durch `satelliteLcn_flag` oder `scrambled_flag` entschieden werden. Historisch konnte ShopLC HD trotz `satelliteLcn_flag=1` umnummeriert werden; WELT HD auf 13 wurde für hohe Nummern abgelehnt und für **99** erfolgreich bearbeitet; 4mediathek wurde auf **4096** über die API umgestellt, obwohl die TV-Eingabemaske **1–99** anzeigte.

### 7.4 Vorhandene Astra-Kopie und Duplikat-Favoriten

- Passende Kopie auf dem Zielplatz bereits vorhanden, noch nicht in A: Mitgliedschaft A übernehmen, keine weitere Kopie erzeugen.
- Kopie gehört bereits B–H an: diese Gruppen erhalten, A hinzufügen.
- Kopie gehört bereits A an: nicht erneut hinzufügen; wenn Original ebenfalls in A ist und Zuordnung eindeutig, nur den **doppelten A-Eintrag am Original** entfernen, Kopie behalten.
- Mehrere ununterscheidbare Kandidaten: **sicherer Abbruch**.
- Fremder DVB-Dienst auf dem Zielplatz: **kein verdecktes Überschreiben**.

### 7.5 Fehlerantworten und „Erfolg“ nicht gleichbedeutend mit Zustand

Reproduzierbare Fälle:

- `returnValue:false`, `errorCode:"CHANNEL_ERROR_1003"`, `errorText:"Channel Move Denied"`, **ohne** Mutation.
- `returnValue:true`, aber Nummer geändert in **unerwarteter Weise** (z. B. COPY statt MOVE).
- `returnValue:false`, aber **Favoritenposition** tatsächlich geändert.
- `returnValue:false` beim Hinzufügen einer Gruppe, mit und ohne tatsächliche Mutation.
- Änderung wird erst nach **N Leseaufrufen / T virtuellen Millisekunden** sichtbar.
- Abbruch **nach Schritt 1, 2, …** einer geplanten Sequenz; kein automatischer Rollback.

Diese Zustände sind zu simulieren und getrennt zu protokollieren. Der Simulator darf `returnValue` nicht als einziges Kriterium für eine erfolgreiche Mutation benutzen.

---

## 8. Luna-API: Protokolltreue und Aufrufverhalten

### 8.1 Vorbild für `luna-send`

Der SSH-Server empfängt exakt die Kommandos, die der aktuelle Editor per SSH sendet (z. B. `luna-send -n 1 luna://<service>/<method> '<json>'`). Er parst erlaubte Varianten mit einem **restriktiven Parser**, nicht mit `eval` und nicht mit einer lokalen Shell. Antwort auf STDOUT im LG-kompatiblen JSON-Format; Exit-Status und STDERR entsprechend den im Client erwarteten Varianten.

### 8.2 Konkrete Domain-Operationen

| Operation | Erforderlicher Testeffekt |
|---|---|
| `getChannelList` | Vollständige, moduskonforme Liste; wiederholte Einträge; konfigurierbare verzögerte Sichtbarkeit |
| `getChannel` | Zugriff nur über aktuelle gültige ID; alte ID nach MOVE/SWAP optional nicht mehr gültig |
| `changeChannelNumber` | Profile MOVE/SWAP/COPY/DENY und kontrollierte Zwischenzustände |
| `setChannelFavoriteGroup` | Mitglieder A–H, Aufruf auf Kopien, mögliche Ablehnungen |
| `releaseChannelFavoriteGroup` | Zielmitgliedschaft entfernen, andere Gruppen behalten |
| `moveChannelFavoritePriority` | `up`/`down`, `destinationChannelId`, reale Reihenfolge prüfen |

Die API-Simulation muss nach jedem ausgeführten Schritt eine **lesbare Ist-Zustandsansicht** bereitstellen. Für das Status-Journal werden Anfrage, Antwort und tatsächlich ausgeführte Mutationen getrennt erfasst.

### 8.3 Reihenfolge und Aliase

Eine erfolgreiche Platztauschkette benötigt eine interne Abbildung vom `sim_entry_id` auf **die jeweils aktuelle** `channelId`. Der Simulator soll IDs realistisch neu vergeben; der Editor muss sie nach Aufrufen neu erkennen. Dies ist entscheidend für „Nummerieren, danach Favoriten sortieren“. Es darf kein versteckter Alias im Simulator angeboten werden, der die reale Client-Fehlerklasse künstlich verbergen würde.

---

## 9. Virtuelles SSH/SFTP-Dateisystem

### 9.1 Remote-Pfad-Mapping

Der Simulator darf **niemals echte Host-Dateien unter `/mnt/lg` oder `/tmp` unkontrolliert anfassen**. Stattdessen bildet er virtuelle, vom Editor erwartete Pfade auf einen separaten, zugriffsbeschränkten Testordner ab:

```text
Remote-Sicht: /mnt/lg/cmn_data/iepg/db/channel.sql
Lokal im Simulator: <workspace>/.simulator/runs/<id>/tv/channel.sqlite

Remote-Sicht: /tmp/<generated-backup-name>.sqlite
Lokal im Simulator: <workspace>/.simulator/runs/<id>/tmp/<validated-name>.sqlite
```

### 9.2 Befehlskatalog

Phase 1 unterstützt **ausschließlich** vom aktuellen Client benötigte Befehle. Historische Beispiele:

- `sqlite3 -readonly <known_database> '.backup <known_temp_path>'`
- `luna-send -n 1 <known_service_uri> <valid_json>`
- `rm -f <known_simulator_temp_file>`
- eventuell `test`, `ls`, `stat`, `uname` **nur wenn der aktuelle Client sie tatsächlich nutzt**.

Jeder Befehl wird durch sichere Parser für Shlex/Shell-Quoting verarbeitet und strikt auf erlaubte Pfade und Subkommandos begrenzt. `;`, Pipelines, Umleitungen, fremde Programmaufrufe, Dateisystemzugriff außerhalb des Sandbox-Verzeichnisses und beliebiger Shell-Code sind zu verweigern. Auch eine `root`-Anmeldung beim Simulator gewährt **keine echten Host-Root-Rechte**.

### 9.3 Konsistente Backups

Der simulierte `sqlite3 .backup`-Befehl soll die SQLite-**Backup-API** verwenden, nicht eine rohe Dateikopie während aktiver Mutationen. Danach steht eine konsistente Datei unter dem virtuellen Temp-Pfad für SFTP bereit. `rm -f` entfernt ausschließlich diese temporäre Datei. Der Ursprungszustand bleibt für laufende Tests gesondert gesichert.

### 9.4 SFTP

Mindestens `get` beziehungsweise das dafür benötigte `open/read/stat` unterstützen. Schreibende SFTP-Operationen zunächst ausdrücklich **verweigern**, sofern der aktuelle Editor keine benötigt. Virtueller Pfad, Größe, Rechte und Zeitstempel müssen für den Client plausibel sein.

---

## 10. Fixture-Management und Datenschutz

### 10.1 Datenquellen

1. **Synthetische Mini-Fixture** (im Git-Repository): 8–20 Sender, Tabellenstruktur soweit vom Editor gebraucht; keine echten Namen nötig.
2. **Synthetische Integrations-Fixture**: mindestens 50–100 Sender, 47 Favoriten, mehrfach belegte Nummern, identische DVB-Dienste, Kopien, Gruppen A–H.
3. **Optionale importierte reale `channel.sql`**: Nutzer stellt lokal eine Sicherung bereit. **Nicht ins öffentliche Git-Repository einchecken**.
4. **Optionale anonymisierte Golden-Traces**: aufgezeichnete Anfragen/Antworten, personenbezogene/IP-/Passwortdaten entfernt.

### 10.2 Importablauf

- Originaldatei nur lesen; Hash protokollieren.
- SQLite `PRAGMA integrity_check` durchführen.
- Erwartete Tabellen und Spalten gegen aktuellen Vertragskatalog validieren.
- Neue isolierte *Run-Instanz* per SQLite-Backup erzeugen.
- Metadaten speichern: Fixture-Version, Importquelle, Basis-Hash, Profil, Datum, verwendeter Simulationscode.
- Fixture niemals unbemerkt überschreiben; `reset` stellt ausdrücklich die ursprüngliche Version wieder her.

### 10.3 Schutz sensibler Daten

Die LG-Senderliste kann Geräte- und Konfigurationsmetadaten enthalten. Produktive Sicherungen und SSH-Zugangsdaten nicht committen, nicht in CI-Artefakten veröffentlichen und nicht an öffentliche Dienste übertragen. Beispielhafte `.gitignore`: `.simulator/`, `fixtures/private/`, `*.key`, `*.pem`, `.env`, `logs/private/`.

---

## 11. Fehler-Engine und deterministische Szenarien

Ein zentraler Mehrwert ist die **gezielte Fehlersimulation**, insbesondere von Fehlern, die der echte TV nicht zuverlässig auf Zuruf erzeugt.

### 11.1 Konfigurierbare Auslöser

- `method`, `service`, `channelId`, `sim_entry_id`, DVB-Kennung, Zielnummer, Gruppe.
- `nth_call` innerhalb eines Testlaufs, optional Operationstyp.
- Zustand vor der Mutation (z. B. Zielnummer mehrfach belegt).
- Synthetische Verzögerung und Anzahl der veralteten Leseantworten.

### 11.2 Konfigurierbare Auswirkungen

- Explizite Ablehnung, keine Mutation.
- Mutation, aber API meldet `returnValue:false`.
- API bestätigt, Zustand erst verzögert sichtbar.
- COPY statt MOVE.
- SWAP verändert beide IDs.
- Netzwerkfehler vor dem Schreiben oder **nach** erfolgreichem Schreiben (wichtiger Unterschied).
- SFTP-Abbruch nach N Bytes; SSH-Timeout nach Luna-Write.
- Teilabbruch innerhalb einer längeren Nummerierungsfolge.
- Modus-/Quellenfehler und doppelte DVB-Kandidaten.

### 11.3 Determinismus

**Keine Zufallsfehler ohne expliziten Seed.** Jede Testreihe muss mit Profil/Seed/Fixture-Hash identische Resultate liefern. Zeitverzögerungen sollten nach Möglichkeit über eine **virtuelle Uhr** modelliert werden; echte `sleep()` nur für explizite Netzwerkintegrationstests.

### 11.4 Beispiel eines Szenarios (entwurfsorientiert)

```yaml
id: return_false_but_favorite_moved
fixture: synthetic_favorites_47
seed: 1001
rules:
  - service: com.webos.service.iepg
    method: moveChannelFavoritePriority
    on_call: 2
    mutate: true
    response:
      returnValue: false
assertions:
  - actual_favorite_order_changed: true
  - editor_must_read_back: true
```

**Die exakte YAML-Syntax ist im Projekt zu definieren und mit Pydantic/JSON-Schema zu validieren.** Unbekannte Schlüssel sollen Fehler auslösen, nicht ignoriert werden.

---

## 12. Lokale Administrationsoberfläche

### 12.1 Minimalumfang (MVP)

Startseite unter `http://127.0.0.1:8766`:

- Aktiver Profilname, Fixture-Hash, Run-ID, simulierte TV-SSH-Adresse und Status.
- Anzahl Sender, FavoriteGroups A–H und aktive Channel-IDs.
- Tabellenansicht: Sendername, aktuelle Nummer, Ursprung/Technik, ID, Gruppe, Astra-LCN-Flag, optional internal `sim_entry_id` für Entwickler.
- Szenarioauswahl, **Reset auf Fixture**, Snapshot jetzt sichern, Restore nur mit ausdrücklicher Bestätigung.
- Ereignis-Journal: Zeit, SSH-/Luna-Methode, Ziel-ID, Ergebnis, **vorher/nachher**, Fehler-Injektion.
- Export des aktuellen simulierten Zustands und des Traces.

### 12.2 Sicherheitsfeatures

- Standardmäßig **nur Loopback**, keine öffentliche Zugänglichkeit.
- Mutationen und Resets im UI erfordern Bestätigung.
- Admin-API mit optionalem lokalem Token; keine CORS-Freigabe für beliebige Origins.
- Keine Möglichkeit, einen echten TV über die Admin-Oberfläche versehentlich anzusprechen.
- Klarer Banner **„SIMULATOR – kein echter LG-TV“**.

### 12.3 Später optional

Szenario-Editor, virtuelle Zeitachse, Schritt-für-Schritt-Operationen, Vergleich mit freigegebenen echten TV-Traces, HTML-Diff nach Testlauf, Profil-Sammlung pro webOS-Generation. Diese Funktionen sind nicht Bestandteil des ersten MVP.

---

## 13. Projektstruktur (geplantes separates Repository)

```text
lg-webos-tv-simulator/
├── pyproject.toml
├── uv.lock                         # nach erster erfolgreicher Installation
├── .gitignore
├── .env.example
├── README.md
├── AGENTS.md
├── CHANGELOG.md
├── src/lg_tv_sim/
│   ├── __init__.py
│   ├── __main__.py                 # CLI: serve, inspect, validate, reset
│   ├── config.py
│   ├── ssh/
│   │   ├── server.py              # AsyncSSH, Auth, Session
│   │   ├── commands.py            # sicheres Remote-Befehl-Routing
│   │   ├── sftp.py                # virtueller Download
│   │   └── paths.py               # erlaubtes virtuelles Dateisystem
│   ├── luna/
│   │   ├── dispatcher.py
│   │   ├── iepg.py                 # getChannelList, Favoriten
│   │   └── legacybroadcast.py      # getChannel, Nummernänderung
│   ├── domain/
│   │   ├── models.py              # SimEntry, DVBKey, ChannelState
│   │   ├── identity.py            # Policy für veränderliche LG-IDs
│   │   ├── numbers.py             # MOVE, SWAP, COPY, REUSE, DENY
│   │   ├── favorites.py
│   │   └── engine.py
│   ├── storage/
│   │   ├── database.py
│   │   ├── fixtures.py
│   │   └── snapshots.py
│   ├── faults/
│   │   ├── engine.py
│   │   └── schema.py
│   ├── traces/
│   │   ├── recorder.py
│   │   ├── sanitizer.py
│   │   └── comparator.py
│   └── admin/
│       ├── api.py
│       └── static/
├── fixtures/
│   ├── synthetic/
│   └── scenarios/
├── contracts/
│   └── current-editor.yaml        # aus aktuellem Code validiert
├── docs/
│   ├── compatibility-contract.md
│   ├── evidence-register.md
│   ├── compatibility-gaps.md
│   ├── architecture.md
│   ├── observed-lg-behavior.md
│   ├── security.md
│   └── development-history.md
├── tests/
│   ├── unit/
│   ├── protocol/
│   ├── integration/
│   ├── regression/
│   └── fixtures/
└── .simulator/                     # lokal generiert, nicht committen
```

Der Agent darf die Struktur begründet ändern, **muss aber Architekturgrenzen und Tests erhalten**. Eine einzige riesige Python-Datei ist nicht akzeptabel.

---
## 14. Umfangreicher Regressionstest-Katalog

**Verbindlich:** Ein „Test erfolgreich“ bedeutet nicht bloß, dass ein Mock `returnValue:true` zurückgibt, sondern dass der **resultierende Zustand** und gegebenenfalls die Antwort/Fehlerfolge überprüft wurden. Wo das reale LG-Verhalten nicht gesichert ist, wird der Fall als **Simulationsprofil** ausgewiesen, nicht als TV-Fakt.

| ID | Fall | Erwartetes Simulator-/Editor-Ergebnis |
|---|---|---|
| T01 | SSH mit separaten Test-Credentials | Erfolgreicher Login, korrekter SSH-Host-Key |
| T02 | Falsches Passwort | Saubere Authentisierungsablehnung |
| T03 | Nicht unterstützter SSH-Befehl | Sicherer Abbruch, keine Host-Shell-Ausführung |
| T04 | Unzulässiger SFTP-Pfad/`../` | Zugriff verweigert, kein Ausbruch aus Sandbox |
| T05 | SQLite `readonly .backup` per SSH + Download | Konsistentes, mit `integrity_check` gültiges SQLite-Snapshot |
| T06 | SFTP-Dateiabruf abgebrochen | Editor erhält Fehler, Fixture bleibt intakt |
| T07 | Reimport nach erfolgreicher Änderung | Neue IDs/Nummern aus aktueller Live-Datenbank übernommen |
| T08 | Identische Namen, verschiedene DVB-Dienste | Keine Auswahl nur über Namen |
| T09 | WELT HD 13/403/1015: identische DVB-Kennung | Drei separate Einträge bleiben unterscheidbar |
| T10 | Dieselbe Ausgangsnummer 101 für mehrere Einträge | `number -> set[IDs]`, kein ungefragter Abbruch |
| T11 | Normaler Nummernwechsel auf freien Platz | Aktuelle ID/Nummer aktualisiert, Favoriten erhalten |
| T12 | Platztausch zweier Sender | Beide Plätze und IDs wechseln; Favoriten bleiben bei ihren Einträgen |
| T13 | Kette aus drei Platztausche | Alle Schritte deterministisch, neue IDs zwischen Schritten benutzt |
| T14 | Kette aus 36 Platztauschen | Kompletter Vorgang erfolgreich; Schlusszustand invariantengerecht |
| T15 | Nummernwechsel, anschließend Reihenfolge ändern | Sortierung verwendet neue ID, nicht alte ID oder nur Namen |
| T16 | WELT-HD-Profil 13 → 900 | `CHANNEL_ERROR_1003`, keine Mutation |
| T17 | WELT-HD-Profil 13 → 99 | Historisch bestätigte erfolgreiche Änderung im gewählten Profil |
| T18 | Simulierte API erlaubt hohe Nummer, UI nicht | UI-Validierung 1–99 wird als **Client-Policy** geprüft, nicht durch Emulatorzwang |
| T19 | Astra-LCN aus >99 → 1–99, COPY | Original bleibt; neuer Eintrag mit eigener ID entsteht |
| T20 | COPY ohne automatische A-Mitgliedschaft | Original bleibt A, neue Kopie zunächst nicht A |
| T21 | Nach COPY A zum Ziel übertragen | Ziel wird A, Original verliert A erst nach Erfolg |
| T22 | Zielkopie bereits vorhanden und nicht A | Kein zweites Kopieren; bestehende ID wiederverwenden |
| T23 | Zielkopie bereits Gruppe B/C | A hinzufügen, B/C unverändert lassen |
| T24 | Zielkopie schon in A, Original ebenfalls A | Doppelte A-Mitgliedschaft eindeutig zusammenführen |
| T25 | Mehrdeutige passende Kopien | Vor Schreibaktion sicher ablehnen |
| T26 | Anderer DVB-Dienst belegt Ziel | Kein unbeabsichtigtes Überschreiben |
| T27 | LG liefert `returnValue:false` bei erfolgreichem Favorite-Sort | Read-back erkennt korrekten Endzustand |
| T28 | LG liefert `returnValue:false` bei fehlgeschlagenem Add | Original A bleibt erhalten |
| T29 | LG liefert `returnValue:true`, Status ist verzögert | Mehrfache begrenzte Read-back-Prüfung; keine doppelten Mutationen |
| T30 | LG liefert `returnValue:true`, erzeugt aber COPY statt MOVE | Editor erkennt unerwartetes Original und zusätzlichen Eintrag |
| T31 | Timeout **vor** Mutation | Keine Änderung; Fehler nachvollziehbar |
| T32 | Timeout **nach** Mutation, vor Antwort | Ungewisser Schreibstatus; zwingender Zustandsabgleich |
| T33 | Fehler nach zweitem Schritt einer Kette | Nur erste Schritte verändert; kein automatischer Rollback |
| T34 | Echter Teilabbruch und anschließender Reimport | Import spiegelt realen **Simulations-Zwischenzustand** |
| T35 | `moveChannelFavoritePriority` mit Gruppe A | Reihenfolge korrekt; andere Gruppen unverändert |
| T36 | Verschiedene Modi (TV/Radio) auf gleicher Nummer | Keine ungewollte Kreuzzuordnung |
| T37 | Unbekannter Channel-ID-Aufbau | Explizite Unsupported-ID-Meldung, kein heuristisches Fremdmatching |
| T38 | Reset auf Fixture nach komplexem Fehlversuch | Bit-/inhaltlich identischer Basiszustand wiederhergestellt |
| T39 | Gleicher Seed + gleiches Profil | Reproduzierbarer Event- und Endzustands-Hash |
| T40 | Manipuliertes Admin-API-Request | Validierungsfehler, keine Mutation |
| T41 | Gleichzeitige SSH-Sitzungen | Serialisierbare Schreibzustände, konsistente Reads |
| T42 | Backup während Mutation | SQLite-Snapshot konsistent, nie halb geschriebene Datei |
| T43 | Änderungen B–H und Sortierung A | B–H bleiben unberührt, sofern Operation nur A betrifft |
| T44 | Unterschied zwischen Original-ID und aktualisierter ID | Event-Journal dokumentiert Zuordnung über `sim_entry_id` |
| T45 | Unknown Luna Service/Method | Eindeutige definierte Fehlerantwort, keine stumme Erfolgssimulation |

### 14.1 End-to-End-Golden-Test des Editor-Komplettablaufs

Ausgehend von einer synthetischen Fixture mit **47 Favoriten A** und einer an realen Problemen orientierten Mischung aus Einzelnummern, Platztauschen, Astra-Kopien und Mehrfachbelegungen muss der Agent einen Test ergänzen, der:

1. Den Simulator auf die definierte Fixture zurücksetzt.
2. Den **aktuellen lokalen Editor** (nicht eine nachgebaute Client-Logik) verbindet.
3. Die SQLite-Datei per SSH/SFTP importiert.
4. Eine automatische Neunummerierung auf **1–99** vorbereitet, wenn diese Funktion im aktuellen Editor so heißt bzw. existiert.
5. Eine Vorschau erzeugt und ihre erwarteten Schritte nachvollziehbar überprüft.
6. Die gesamte Operation gegen den Simulator ausführt.
7. Per Reimport den finalen Zustand prüft: Nummernfolge, FavoriteGroups, Reihenfolge, erwartete Kopien, keine ungewollten Drittänderungen.
8. Das Operationsjournal als Testartefakt speichert.

**Wichtig:** Der Wert „36 Tausche“ stammt aus einer historischen, zwischenzeitlichen TV-Vorschau. Die exakte Zahl eines neu erzeugten Plans hängt vom Zustand der Fixture ab und darf nicht als universelle Konstante im Produktcode stehen. Wo ein Golden-Test genau 36 erwartet, muss dessen Fixture entsprechend versioniert und fixiert sein.

### 14.2 Architektur-/Sicherheitstests

- Alle `returnValue`-Varianten mindestens einmal abdecken.
- Keine beliebige Host-Shell, kein Host-Dateisystem-Zugriff durch Remote-Befehl oder SFTP.
- Keine Netzwerkverbindung des Simulators zu realen TV-Adressen.
- Wenn `--listen 0.0.0.0` nicht bewusst und ausdrücklich erlaubt ist: Start verweigern.
- State Mutations unter konkurrierenden Requests atomar ausführen beziehungsweise sauber serialisieren.
- `reset` während aktiver SSH-Schreibsequenz entweder sperren oder sauber abbrechen; keine stillen Teilresets.
- Wiederholte Backups dürfen keine Datenkorruption auslösen.
- Replay muss auch bei geänderter Ausführungsreihenfolge einer Schnittstelle nachvollziehbar scheitern.

---

## 15. Implementierungsphasen mit überprüfbaren Abnahmekriterien

### Phase 0 – Analyse des **aktuellen** Channel-Editor-Projekts

**Arbeiten:** Aktuelles Projekt in der IDE öffnen, Schnittstellen inventarisieren, vorhandene Tests laufen lassen, dokumentieren, was heute wirklich implementiert ist. Read-only Analyse; kein API-Redesign des Editors.

**Ergebnisse:** `docs/compatibility-contract.md`, `contracts/current-editor.yaml`, Liste aller belegten Remote-Kommandos und Luna-Endpunkte, dokumentierte offene Protokolldetails.

**Abnahme:** Kein zwingend benötigter aktueller TV-Aufruf ist nur historisch angenommen. Unsicherheiten stehen explizit in `docs/compatibility-gaps.md`.

### Phase 1 – Eigenständiges, lauffähiges Simulator-Grundprojekt

**Arbeiten:** PyCharm-Projekt, Paketstruktur, Konfiguration, CLI, Logging, Tests, minimale Admin-API, isolierte SQLite-Fixture, Reset.

**Abnahme:** `serve`, `validate-fixture`, `reset` ausführbar; Admin-Seite auf Loopback; `pytest` grün; keine Root-Rechte nötig.

### Phase 2 – SSH/SFTP-Fassade

**Arbeiten:** AsyncSSH-Server, eigener Host-Key, Testauthentisierung, restriktiver Command-Router, virtuelle Pfade, SQLite-Backup, SFTP.

**Abnahme:** Der **aktuelle** Editor kann sich mit dem Simulator verbinden und eine gültige Senderdatenbank importieren, ohne dass an seiner Businesslogik etwas geändert wird.

### Phase 3 – Read-only-Luna-API

**Arbeiten:** `getChannelList`, `getChannel`, ggf. weitere vom aktuellen Code verwendete Reads; vollständige/korrekte Felder und Filter.

**Abnahme:** Die importierten Sender stimmen mit der simulierten Live-Liste überein; mehrfach belegte Nummern und DVB-Duplikate funktionieren; unbekannte Methoden scheitern explizit.

### Phase 4 – Favoritenoperationen

**Arbeiten:** Gruppen A–H, Add/Remove, Reihenfolge, realistische Antworten und Read-back, Transaktionen.

**Abnahme:** Favoritenaufnahme/-entfernung und Sortierung aus dem **aktuellen Editor** funktionieren. Gruppen B–H bleiben bei A-Operationen unverändert.

### Phase 5 – Nummerierung und Astra-Sonderfälle

**Arbeiten:** MOVE/SWAP/COPY/REUSE/DENY, aktualisierte Channel-IDs, doppelte Sender, 1–99-Client-Policy, Favoritenmigration und Mehrfachschritte.

**Abnahme:** Szenarien T08–T26 und der Golden-Komplettablauf bestehen; Verifikation hängt an IDs/Zustand, nicht an Namen.

### Phase 6 – Fehler-Engine und Trace-Replay

**Arbeiten:** Fault-Profile, virtuelle Verzögerung, Teileffekte bei Netzwerkabbrüchen, Eventjournal, sanitisiertes Trace-Replay.

**Abnahme:** Historische Fehlerfälle reproduzierbar, mit gleicher Fixture und Seed gleiches Ergebnis; Test zeigt abweichende Rückgabe und tatsächlichen Zustand separat.

### Phase 7 – Entwickleroberfläche, CI und Dokumentation

**Arbeiten:** Status-/Tabellenansicht, Szenarioauswahl, Reset, Snapshots, Export, MX-Linux-Setup, CI auf Linux, Beispiel-Workflow.

**Abnahme:** Neuer Entwickler kann das Repo klonen, Simulator starten und Editor anbinden, ohne den realen Fernseher zu besitzen; keine offenen kritischen Sicherheitslücken.

### Phase 8 – Optionale Verbesserung (nicht für MVP blockierend)

- Docker-/Podman-Support und CI-Matrix.
- Visueller Szenarioeditor und Vergleichs-Diffs.
- Optionale Client-seitige Transport-Adapter-Tests für extrem schnelle Unit-Tests.
- Mehrere historisch validierte Firmware-Profile mit eigenem Evidence-Register.

**Keines dieser optionalen Features darf den MVP aufhalten.**

---

## 16. Testprotokoll und Evidence-Register

Das Projekt muss Herkunft und Belastbarkeit jeder Semantik offenlegen. Vorgeschlagene Klassifizierung:

- **HARDWARE_CONFIRMED:** Am echten LG-TV konkret getestet, mit Befehl und Vorher-/Nachher-Zustand.
- **TRACE_CONFIRMED:** Aus echten, vollständigen und freigegebenen Aufzeichnungen rekonstruiert.
- **HISTORICAL_REPORTED:** Aus der bisherigen Entwicklung überliefert, nicht lokal nochmals verifiziert.
- **CURRENT_CLIENT_CONFIRMED:** Im aktuellen Editor-Code nachgewiesen; sagt allein nichts über TV-Firmware.
- **SIMULATOR_ASSUMPTION:** Für Testzwecke frei angenommene Semantik, kein TV-Fakt.
- **UNSUPPORTED:** Nicht implementiert / nicht belegt.

Ein Eintrag in `docs/evidence-register.md` sollte so aussehen:

```yaml
id: lg-astra-copy-high-to-low
claim: "Beim beobachteten Sender entstand am Zielplatz ein zusätzlicher Eintrag"
evidence_level: HISTORICAL_REPORTED
observed_date: "2026-10-10"
source: "Frühere Vorher-/Nachher-SQL-Abfragen beim Test der automatischen Nummerierung"
example_source_number: 125
example_target_number: 26
implementation_profile: COPY
known_limitations:
  - "Nicht auf alle Sender und LG-Firmware-Versionen verallgemeinern"
  - "Tatsächliche Channel-ID-Transformation bei aktuellem Gerät gegen frische Daten prüfen"
```

Die Quellen aus dem Gespräch sind **Anhaltspunkte**, keine allgemein veröffentlichte API-Dokumentation. Für produktive Kompatibilitätszusagen immer eigene Hardware-Evidenz verlangen.

---

## 17. Historische Fehlerklassen: Diese Fehler nicht erneut einbauen

Die folgenden Punkte sind aus der gemeinsamen Entwicklung des Editors bis zur erfolgreichen Komplettnummerierung entstanden. **Die jetzige Codebasis kann sie bereits anders lösen**; sie sind als Regressionstest-Invarianten gedacht.

| Historischer Fehler | Korrekte Lehre für den Simulator |
|---|---|
| Sender wurde anhand gewünschter neuer Nummer statt ursprünglicher ID gefunden | Identität und Änderungsziel strikt trennen |
| Mehrere gleichnamige Sender wurden verwechselt | Keine Zuordnung nur anhand Anzeigename |
| DVB-Tupel wurde als alleiniger eindeutiger Schlüssel angenommen | Derselbe DVB-Dienst kann mehrere LG-Einträge haben |
| Aktuelle `dvc_chan_id` nach Nummernwechsel unbekannt | Nach jedem Write aktuelle Identität neu abfragen/führen |
| Globale Nummer wurde als eindeutiger Schlüssel verwendet | `number -> set[entries]`, Modus berücksichtigen |
| Mehrere Tausche konnten nicht geplant werden | Zustandsbasierte, schrittweise Simulation statt starrem statischen Mapping |
| Alte Originalnummer 101 war mehrfach vergeben | Mehrfachbelegung außerhalb des Zielbereichs nicht pauschal verbieten |
| `returnValue:true` als Beweis für MOVE gewertet | Tatsächliche COPY-/SWAP-/MOVE-Folgen überprüfen |
| Astra-Kopie erhielt nicht automatisch Favorit A | Favoritenmigration als separaten, prüfbaren Ablauf behandeln |
| Vorhandene Kopie wurde erneut erstellt oder weggeschoben | Zielzustand prüfen und passende Kopie wiederverwenden |
| Kopie schon in B–H wurde pauschal gesperrt | Andere Gruppen erhalten, A separat behandeln |
| Kopie schon in A wurde pauschal gesperrt | Eindeutig doppelte A-Mitgliedschaft bei Bedarf zusammenführen |
| LG antwortete `false`, Mutation trat dennoch ein | API-Antwort und Datenbankzustand getrennt modellieren |
| Neue ID bei nachfolgender Favoritensortierung vergessen | Identitätswechsel durch gesamte Operationskette verfolgen |
| Gruppen nach Swap gegen **Endziel** verglichen | Direkten Vorher-/Nachher-Zustand beider Einträge vergleichen |
| Live-Liste exakt einmal nach Write gelesen | Begrenzte, konfigurierte Konsistenz-/Retry-Strategie testen |
| Teilabbruch wurde als atomar behandelt | Zwischenzustand und fehlenden Rollback explizit modellieren |
| „Nur die ersten N Operationen ausführen“ empfohlen, obwohl UI dies nicht konnte | Nie Funktionen behaupten, die im **aktuellen Code** nicht existieren |
| `channel_unique_id` als Datenbankspalte erfunden | **Nur tatsächlich introspektierte SQLite-Spalten verwenden** |
| 1–99 als universelle Firmwareobergrenze behandelt | UI-Eingabegrenze und LG-API-Verhalten getrennt behandeln |
| Stale README lieferte falsche Features | Aktuellen Code als Quelle verwenden, Historie separat dokumentieren |

**Historischer Referenzpunkt:** v0.5.24 erreichte eine vollständige automatische Neunummerierung auf dem realen LG OLED55C27LA (webOS 22). Das ist die wichtigste End-to-End-Anforderung, nicht die Zusicherung, dass jede Zwischenlösung damals korrekt war.

---

## 18. Sicherheit und Betrieb

### 18.1 Keine Verbindung zu echten Fernsehern

Der Simulator darf **keine echte TV-IP-Adresse oder Geräte-Zugangsdaten** benötigen. Netzwerkausgänge sind grundsätzlich nicht erforderlich. Werden Trace-Aufzeichnungen importiert, müssen sie aus Dateien kommen und mit Zustimmung des Benutzers bereitgestellt werden.

### 18.2 Localhost-only und Host-Key-Trennung

- SSH nur auf `127.0.0.1:2222`, Admin nur auf `127.0.0.1:8766`.
- Host-Key separat erzeugen und in `.simulator/keys/` aufbewahren.
- Optional eigene SSH-`known_hosts`-Datei für Simulator-Tests statt globale Bestätigung des TV-Schlüssels.
- Testzugangsdaten nie mit TV-Credentials verwechseln.
- Testserver kann nach Abbruch sauber ohne verwaiste Prozesse neu gestartet werden.

### 18.3 Keine echten Host-Rechte trotz Fake-`root`

Der Nutzername `root` ist ausschließlich ein **simuliertes Protokolldetail**, kein UNIX-Privileg. AsyncSSH läuft als gewöhnlicher Benutzer. Nicht auf Port 22, nicht auf echten Systemverzeichnissen und nicht mit `sudo` starten.

### 18.4 Datenkonsistenz

- Jede Domain-Mutation erhält eine eindeutige `operation_id`.
- Vorher-/Nachher-Zustände protokollieren; keine geheimen Werte loggen.
- Schema-/Referenzprüfungen nach jeder Mutation.
- Reset-/Restore-Operationen sind **nur im Simulator** möglich und kontrolliert; sie dürfen keine Client-seitigen „Undo“-Funktionen vortäuschen, die auf realem LG nicht existieren.

### 18.5 Kein beliebiger Remote-Code

Ein inkompatibles SSH-Kommando wird nicht mit `subprocess.run(..., shell=True)` an den Host delegiert. Es wird stattdessen als **nicht unterstützter Simulatorbefehl** mit dokumentiertem Fehler behandelt. Der Transport-/Befehlscode muss Path Traversal, Shell-Injection und Symlink-Ausbrüche abwehren.

---

## 19. Installation und lokale Entwicklungsbefehle unter MX Linux

Nach Phase 1 stellt das Simulatorprojekt folgende Standardbefehle bereit. Die **konkrete Installation von PyCharm** kann über die JetBrains Toolbox oder die offizielle Linux-Distribution erfolgen. PyCharm selbst benötigt keine separate webOS-SDK-Installation.

### 19.1 Systemvorbereitung

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip git
```

Die genaue Python-Version hängt von der verwendeten MX-Linux-Releasebasis ab. Das Repository muss klar dokumentieren, ob Python 3.12+ bereits vorhanden ist beziehungsweise wie es ohne Veränderung des System-Pythons in einer isolierten Umgebung bereitgestellt werden kann.

### 19.2 Projekt mit PyCharm öffnen

- Eigenes Repo `lg-webos-tv-simulator` erstellen bzw. auschecken.
- In PyCharm öffnen.
- Interpreter `.venv/bin/python` einstellen.
- Abhängigkeiten anhand `pyproject.toml` installieren.
- Run-Configuration `Simulator: serve` anlegen; zweites Profil `Tests: pytest`.

### 19.3 Toolunabhängiger Bootstrap

```bash
cd lg-webos-tv-simulator
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
python -m lg_tv_sim serve --config config/local.toml
```

Falls das Projekt `uv` verwendet, entsprechend:

```bash
uv sync --dev
uv run pytest
uv run python -m lg_tv_sim serve --config config/local.toml
```

Diese Befehle sind **vorgesehene Ziel-Schnittstellen** des zu entwickelnden Projekts. Sie funktionieren erst, nachdem der Agent die zugehörigen Dateien erstellt hat; **noch kein existierendes Repository wird hiermit behauptet**.

### 19.4 Editor mit Simulator verbinden

Im **aktuellen** Channel Editor den Host auf `127.0.0.1`, SSH-Port auf `2222` und Benutzer/Passwort auf ausschließlich simulierte Test-Credentials stellen. Falls der aktuelle Editor keine Portkonfiguration oder keine getrennte SSH-Host-Key-Konfiguration erlaubt, zuerst einen **kleinen, isolierten Konfigurationsweg** schaffen, der die funktionierende TV-Synchronisierungslogik nicht verändert.

Der Editor läuft weiterhin unter seiner eigenen Adresse (historisch `http://127.0.0.1:8765`); Simulatorstatus unter `http://127.0.0.1:8766`.

### 19.5 Beispielhafter Testablauf

1. Simulator starten und `synthetic_favorites_47` auswählen.
2. In der Simulatoroberfläche **Reset** durchführen und die Run-ID notieren.
3. Im Editor `127.0.0.1:2222` als TV angeben.
4. Import von „TV“ starten und Sender/Favoriten anzeigen.
5. Kontrolliert einzelne Favoritenoperation ausführen; Ist-Zustand im Simulator prüfen.
6. Automatische Durchnummerierung vorbereiten, Vorschau prüfen und im Simulator ausführen.
7. Endzustand im Admin-UI mit dem Editor vergleichen.
8. Dasselbe Szenario mit Fehler nach Schritt 2 wiederholen; Zwischenzustand verifizieren und erneut importieren.

### 19.6 CLI-Kommandos als Akzeptanzziel

```text
lg-tv-sim serve [--config ...]
lg-tv-sim inspect-fixture <file>
lg-tv-sim validate-fixture <file>
lg-tv-sim import-fixture <file> [--name ...]
lg-tv-sim reset [--fixture ...]
lg-tv-sim scenarios list
lg-tv-sim scenarios activate <scenario-id>
lg-tv-sim export-state <path>
lg-tv-sim export-trace <path>
```

Implementierungsdetails können abweichen, solange der dokumentierte lokale Workflow vollständig möglich bleibt.

---

## 20. Konfigurationsschema (Entwurf)

```toml
[server]
ssh_host = "127.0.0.1"
ssh_port = 2222
admin_host = "127.0.0.1"
admin_port = 8766

[authentication]
username = "root"                 # Nur simulierter SSH-Benutzername
password_env = "LG_TV_SIM_PASSWORD"  # Kein TV-Passwort
host_key_file = ".simulator/keys/ssh_host_key"

[storage]
base_dir = ".simulator/runs"
fixtures_dir = "fixtures/synthetic"
initial_fixture = "synthetic_favorites_47"

[behavior]
profile = "lg_webos22_historical"
read_after_write_delay_ms = 0
unknown_commands = "deny"
unknown_luna_methods = "deny"
seed = 1001

[security]
allow_external_bind = false
allow_sftp_write = false
```

`lg_webos22_historical` bezeichnet ein **an historischen Beobachtungen orientiertes Simulatorprofil**, keine zertifizierte Reproduktion aller webOS-22-Geräte.

---

## 21. Qualitätsanforderungen und Definition of Done

**MVP gilt nur als fertig, wenn alle folgenden Punkte erfüllt sind:**

1. **Aktueller Editor-Vertrag** ist analysiert und dokumentiert. Niemand hat behauptet, eine unbekannte lokale Version gesehen zu haben.
2. Simulator läuft auf MX Linux ohne Root und ohne echtes TV-Gerät.
3. SSH/SFTP-Import funktioniert mit dem **unveränderten aktuellen Editor** oder mit einer ausdrücklich dokumentierten minimalen Konfigurationsanpassung.
4. Authentisierung/Host-Key-Prüfung ist sauber getestet.
5. SQLite-Backup ist konsistent, Schema kompatibel, Original-Fixture unverändert.
6. Sendernamen/DVB-Duplikate/mehrfach belegte Nummern sind korrekt darstellbar.
7. Mindestens die von der aktuellen App verwendeten Read-/Write-Luna-Methoden sind implementiert und getestet.
8. MOVE, SWAP, COPY und REUSE sind profilgesteuert, mit tatsächlich wechselnden LG-IDs.
9. Favoriten A–H, Reihenfolge und A-Migration sind zustandsbasiert und robust gegen Teilabbrüche.
10. Fehlerfälle `returnValue:false` trotz Mutation, `returnValue:true` mit unerwartetem Ergebnis, verspätete Sichtbarkeit und Netzwerkausfall sind reproduzierbar.
11. Admin-UI ermöglicht Fixture-Reset, Zustandseinblick und Trace-Export.
12. Alle vereinbarten Tests sind grün. Der Agent nennt den **tatsächlichen** Testlauf, keine aus historischen Chats übernommene Testzahl.
13. Unbekannte APIs/ID-Formate/Befehle **scheitern explizit**, statt Erfolg vorzutäuschen.
14. Schutz vor Shell-/Pfad-Injection, localhost-only und Verbot echter Host-Root-Rechte sind verifiziert.
15. Dokumentation erklärt MX-Linux-Start, Editor-Verbindung, Profile, Fehlerbehebung, Grenzen und Daten-/Log-Sicherheit.
16. Keine Logikänderung an der am TV bestätigten Nummerierungsimplementierung ohne eigene Tests und ausdrückliche Freigabe.

### Nicht-funktionale Zielwerte (initiale Richtwerte, bei Messung anpassen)

- Eine synthetische 650-Sender-Liste soll lokal ohne merkliche UI-Verzögerung ladbar sein.
- Ketten aus mindestens 50 Senderoperationen müssen deterministisch ausführbar sein.
- Simulierte API-Reads ohne absichtliche Latenz sollen für gewöhnliche Fixtures deutlich unter einer Sekunde bleiben.
- Tests dürfen keine echten TV-Zugangsdaten oder IP-Adressen verlangen.
- Reset und mehrere Durchläufe dürfen keine Fixture-Drift verursachen.

---

## 22. Offene Entscheidungen und wie der Agent damit umgehen soll

| Frage | Vorgehen |
|---|---|
| Welche Editor-Version liegt aktuell vor? | **Aus aktuellem lokalen Workspace ermitteln.** Alte v0.5.24 nur historisch. |
| Welche SSH-Kommandos werden heute genutzt? | Systematisch im Code inventarisieren, Vertragskatalog erstellen. |
| Wird Paramiko oder andere SSH-Bibliothek verwendet? | Aus Code nachweisen; Transportvertrag daran orientieren. |
| Sind Gruppen A–H heute gleich implementiert? | DB-Schema und API nachweisen, keine Annahmen. |
| Wird `copyDvbSatelliteChannelForAstra` vom Editor aufgerufen? | Aktuellen Code prüfen; historisch war kein unkontrollierter Fallback erwünscht. |
| Wie genau ist `dvc_chan_id` aufgebaut? | Aus mehreren belegten Vorher-/Nachher-Traces und Testdaten ableiten; unbekannte Fälle nicht raten. |
| Welche LG-Antworten liefern die Methoden exakt? | Aktuelle Parser + wenn verfügbar **freigegebene echte Traces** verwenden. |
| Ist SSH/SFTP vollständig durch AsyncSSH in benötigter Version umsetzbar? | Frühen vertikalen Integrationstest durchführen; API der Bibliothek konkret prüfen. |
| Welche Remote-Kommandos außer Luna und SQLite? | Nur nach Codeanalyse ergänzen, deny-by-default. |
| Soll der Editor selbst einen Mock-Modus erhalten? | Erst nach funktionierendem externem SSH-Simulator erwägen. |
| Können Tests ohne echte TV-Daten auskommen? | Ja: synthetische Fixtures sind MVP-Pflicht; reale Snapshotdaten nur optional. |

**Bei Unklarheit:** Agent soll eine eng begrenzte Rückfrage stellen oder eine explizite `TODO/UNKNOWN`-Markierung führen, aber keine Eigenschaft einer nichtöffentlichen LG-Firmware erfinden.

---

## 23. Agent-Anweisung für den Start (direkt in die IDE übernehmbar)

> **Rolle:** Senior Python-Backend-/Integrationstest-Engineer mit Schwerpunkt SSH, SQLite, zustandsbasierter Simulation und sicherer Testinfrastruktur.
>
> **Aufgabe:** Entwickle das eigenständige Projekt `lg-webos-tv-simulator` gemäß `LG_WEBOS_CHANNEL_EDITOR_TV_SIMULATOR_PROJEKTPLAN.md`.
>
> **Verbindliche Reihenfolge:**
>
> 1. Lies diese Spezifikation vollständig.
> 2. Analysiere den **wirklich vorhandenen aktuellen** LG-WebOS-Channel-Editor im Workspace. Der v0.5.24-Kontext ist **historisch**, nicht notwendig der heutige Code.
> 3. Erstelle zuerst den `CompatibilityContract` mit realen SSH-/SFTP-/Luna-/SQLite-Aufrufen und dokumentiere Abweichungen.
> 4. Implementiere danach einen minimalen, localhostgebundenen SSH/SFTP-Server, der einen konsistenten SQLite-Import ermöglicht.
> 5. Erweitere schrittweise Luna-Reads, Favoritengruppen, Nummernänderung, Platztausch, Astra-Kopie und vollständige Mehrfachabläufe.
> 6. Ergänze Tests **vor** der Freigabe jeder weiteren Semantik. Nutze echte, freigegebene Mitschnitte nur als Belege und synthetische Daten als Standard.
> 7. Schreibe ausschließlich in das neue Simulator-Repository bzw. in dessen kontrollierten Arbeitsbereich; ändere den produktiven Editor **nicht ungefragt**.
> 8. Nutze keine echten TV-Zugangsdaten, keine echten Broadcast-Dienste und keine unkontrollierten Shell-Kommandos.
> 9. Kennzeichne jeden unbelegten Firmware-Aspekt als Annahme und verwende Fail-Closed-Verhalten.
> 10. Berichte nach jeder Phase die tatsächlich erstellten Dateien, ausgeführten Tests, bekannten Abweichungen und den nächsten überprüfbaren Schritt.
>
> **Besondere Regressionen:** Unterschied zwischen DVB-Dienst und LG-Sendereintrag, dynamische Channel-IDs, identische Namen, mehrfach belegte Nummern, MOVE/SWAP/COPY, Übernahme vorhandener Astra-Kopien, Erhalt von Gruppen B–H, `returnValue:false` mit Mutation, teilweiser Commit ohne Rollback, Favoritensortierung nach ID-Wechsel sowie eine vollständige automatische Neunummerierung wie historisch in v0.5.24 erfolgreich getestet.
>
> **Akzeptanz:** Der **aktuelle echte Editor-Code** kann sich mit dem Simulator verbinden, importieren und einen kompletten, verifizierten Schreibablauf auf einer reproduzierbaren Test-Fixture ausführen, ohne einen echten LG-TV zu benötigen.

---

## 24. Sinnvolle erste Aufgaben für den IDE-Agenten

**Erstes Arbeitspaket (maximal ein kleiner Pull Request):**

1. Neues Simulator-Repo mit `pyproject.toml`, `.gitignore`, Konfiguration, `README.md`, `AGENTS.md`, `src/`, `tests/` initialisieren.
2. Versions-/Testumgebung unter MX Linux einrichten.
3. Den **aktuellen** Editor auf SSH- und SFTP-Befehle analysieren und dokumentieren.
4. Synthetisches, schema-kompatibles Test-`channel.sql` erstellen oder aus einem privat bereitgestellten Schema generieren.
5. SSH-Handschlag mit Test-Host-Key und einem einzigen erlaubten Read-only-Backup-Befehl implementieren.
6. Per SFTP genau dieses Backup herunterladen können.
7. Integrationsnachweis: **Der aktuelle Editor importiert vom simulierten `127.0.0.1:2222`**.

**Erst danach** schreibende Luna-Methoden implementieren. Dadurch wird früh klar, ob SSH-Fassade und Client-Protokoll wirklich zusammenpassen, statt eine große Mock-Anwendung zu bauen, die sich am Ende gar nicht anbinden lässt.

---

## 25. Quellen, historische Referenzen und Evidenzgrenzen

### Offizielle Hintergrundquellen

- LG webOS TV – Emulator Introduction: https://webostv.developer.lge.com/develop/tools/emulator-introduction  
  Hersteller nennt u. a. fehlende Tuner-Unterstützung der älteren TV-Emulatoren.
- LG webOS TV – Simulator Introduction: https://webostv.developer.lge.com/develop/tools/simulator-introduction  
  Der offizielle Simulator dient vorrangig Web-App-Tests; nicht alle Luna-APIs sind verfügbar.
- JetBrains – Unified PyCharm: https://www.jetbrains.com/help/pycharm/unified-pycharm.html
- AsyncSSH – Projekt und Dokumentation: https://asyncssh.readthedocs.io/
- SQLite – Online Backup API: https://www.sqlite.org/backup.html
- Python SQLite: https://docs.python.org/3/library/sqlite3.html
- Pytest: https://docs.pytest.org/

### Historische Projektreferenzen

- `LG_FAVORITEN_EDITOR_PROJEKTUEBERGABE.md` (frühere Projektübergabe, **keine Gewähr für den aktuellen lokalen Quellstand**).
- Stand v0.5.24: `README.md`, `TECHNISCHE_GRUNDLAGEN.md`, `app.py`, `tv_write.py`, `number_rules.py`, `tests/` (historisches Paket).
- Reale, vom Benutzer im Gespräch bestätigte Fälle: WELT HD 13→99; ShopLC-Platztausch; Pro7-MAXX-/ARD-alpha-Kopie; echte vollständige Neunummerierung mit v0.5.24.

**Abschließende Wahrheitshierarchie:**

1. **Aktueller tatsächlich ausgecheckter Editor-Code**, wenn es um dessen heutige Aufrufschnittstelle geht.
2. **Echte, zeitlich passende und überprüfte LG-Vorher-/Nachher-Daten**, wenn es um reales Firmware-Verhalten geht.
3. Historische Traces, frühere Projektübergabe und dokumentierte Regressionen.
4. Ausdrücklich benannte Simulationsannahmen für noch unbekannte Fälle.

Niemals eine Annahme aus Rang 3 oder 4 als Gewissheit über Rang 1 oder 2 ausgeben.

---

**Ende der Spezifikation.**
