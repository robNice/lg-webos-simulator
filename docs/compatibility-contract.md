# Kompatibilitätsvertrag (aktueller Editor)

Maschinenlesbar: [`contracts/current-editor.yaml`](../contracts/current-editor.yaml).

**Grundlage:** Read-only-Analyse des lokalen Checkouts `~/PhpstormProjects/lg-webos-channel-editor` am
11.10.2026, `APP_VERSION = 0.6.1` (HEAD `da6eb10` „v0.6.0“ plus nicht committete v0.6.1-Änderungen).
Zuletzt am echten TV bestätigt ist laut Editor-Doku weiterhin **v0.5.24**. Am Editor wurde nichts geändert.

## Transport

| Aspekt | Aktueller Editor | Simulator |
|---|---|---|
| SSH-Bibliothek | Paramiko (System-`python3`, 2.12.0) | AsyncSSH-Server |
| Authentisierung | `root` + Passwort, `look_for_keys=False`, `allow_agent=False` | Passwort aus `$LG_TV_SIM_PASSWORD` bzw. `.simulator/credentials` |
| Host-Key | `load_system_host_keys()` + `RejectPolicy` | eigener Ed25519-Key; Eintrag `[127.0.0.1]:2222` per `lg-tv-sim known-hosts --install ~/.ssh/known_hosts` |
| Port | per API-Feld `port` konfigurierbar (Default 22) | 2222 |
| Kanäle | reine `exec`-Requests ohne PTY | Shell/PTY/SCP/Forwarding abgelehnt |

**Notwendige Konfigurationsanpassung am Editor:** keine Codeänderung. In der Editor-Oberfläche Host
`127.0.0.1`, Port `2222` und das Simulator-Passwort eintragen und einmalig den Host-Key in
`~/.ssh/known_hosts` übernehmen. Der Simulator-Key ist ein eigener Schlüssel und kollidiert nicht mit dem
Eintrag des echten Fernsehers, weil der Eintrag an `[127.0.0.1]:2222` gebunden ist.

## Remote-Kommandos (vollständige Liste)

1. `command -v sqlite3 >/dev/null && command -v luna-send >/dev/null`: Login-Prüfung (`tv_login.py`).
2. `sqlite3 -readonly /mnt/lg/cmn_data/iepg/db/channel.sql '.backup /tmp/<name>.sqlite'`: Import und Preflight.
3. `sqlite3 -readonly /mnt/lg/cmn_data/iepg/db/channel.sql "SELECT user_edited_name FROM channel_group_tuner WHERE channel_group_id=N"`: Prüfung nach dem Umbenennen einer Liste.
4. `luna-send -n 1 luna://<service>/<method> '<json>'`: alle Luna-Aufrufe.
5. `rm -f /tmp/<name>.sqlite`: Aufräumen.

SFTP: `stat` (Größenlimit 30 MiB) und `get` auf die Temp-Datei.

## Luna

Alle sechs vom aktuellen Editor genutzten Methoden laufen über `com.webos.service.iepg`:
`getChannelList`, `changeChannelNumber`, `setChannelFavoriteGroup`, `releaseChannelFavoriteGroup`,
`moveChannelFavoritePriority` und `setGroupName`. Parameter und gelesene Antwortfelder stehen im YAML.

## Verifikation

`tests/integration/test_editor_e2e.py` führt den **echten Editor-Code** (`app.import_from_tv`,
`renumber_plan`, `prepare_tv_write`, `commit_tv_write`, `TvLoginCheck`) mit dessen eigenem Interpreter gegen
den laufenden Simulator aus, über echtes SSH/SFTP, `RejectPolicy` und `known_hosts`. Dabei wird nur eine
temporäre Kopie des Editor-Codes ohne `data/` verwendet.
