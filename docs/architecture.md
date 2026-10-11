# Architektur

```text
Editor (paramiko) ──SSH 127.0.0.1:2222──► ssh/server.py (AsyncSSH, Passwort, nur exec)
                                             ├─ ssh/commands.py  CommandRouter (deny by default, eigener Tokenizer)
                                             │     ├─ login_check / sqlite3 .backup / SELECT / rm -f
                                             │     └─ luna-send ──► luna/dispatcher.py ──► luna/iepg.py, legacybroadcast.py
                                             └─ ssh/sftp.py       read-only, nur virtuelles /tmp
                                                          │
                                         domain/engine.py  TvEngine  ◄── admin/api.py (FastAPI, 127.0.0.1:8767)
                                           ├─ numbers.py (Profilregeln MOVE/SWAP/COPY/REUSE_COPY/DENY)
                                           ├─ favorites.py (A–H, Positionen, favorite_idx)
                                           ├─ identity.py (ChannelIdPolicy, sim_entry_id-Registry)
                                           └─ storage/ (Run-Verzeichnis, SQLite, Snapshots, Fixtures)
                  faults/ (Szenarien, deterministische Regeln)   traces/ (Journal, Sanitizer, Vergleich)
```

## Schichten

| Schicht | Datei(en) | Verantwortung |
|---|---|---|
| Transport | `ssh/server.py`, `ssh/sftp.py` | Authentisierung, `exec`-Kanäle, Exit-Status, SFTP-Lesen; keine LG-Logik |
| Befehls-Router | `ssh/commands.py`, `ssh/paths.py` | Exakte Befehlsformen des Editors, Shell-Syntax abweisen, Pfad-Sandbox |
| Luna | `luna/*` | Parameterprüfung (strikt, ohne Typumwandlung), Antwortformat, unbekannte Methoden → Fehler |
| Domain | `domain/engine.py` | **Einzige** Stelle für schreibende LG-Semantik; eine Transaktion pro Aufruf, Invariantenprüfung |
| Storage | `storage/*` | Fixtures (JSON-Spezifikation bzw. privates SQLite), Run-Verzeichnisse, Backup-API, Inhalts-Hash |
| Faults | `faults/*` | YAML-Szenarien (Pydantic, unbekannte Schlüssel = Fehler), `nth_call`, `times`, Zähler |
| Traces | `traces/*` | Journal mit Anfrage, Client-Antwort, wahrer Antwort, Mutationen, Fehlerregel; Event-Hash |
| Admin | `admin/*` | Status, Tabelle, Journal, Reset/Snapshot/Restore mit Bestätigung, Export |

## Wichtige Entscheidungen

- **Eine Engine, ein Lock:** `TvEngine.lock` (RLock) serialisiert alle Lese- und Schreiboperationen aus SSH
  und Admin-API. SSH-Kommandos laufen per `asyncio.to_thread`, damit Backups den Event-Loop nicht blockieren.
- **Mutationsrahmen** `_mutate()`: `BEGIN IMMEDIATE` → Operation → Invariantenvergleich (nur *neue*
  Verletzungen zählen, damit importierte reale Daten nicht stillschweigend „repariert“ werden) → `COMMIT`
  bzw. `ROLLBACK`. Bei `mutate:false` aus einem Fehlerszenario wird die berechnete Mutation zurückgerollt und
  im Journal als `suppressed_mutations` ausgewiesen.
- **Antwort ≠ Zustand:** Der Dispatcher protokolliert `response` (was der Client sieht) und `true_response`
  (was die Engine geantwortet hätte) getrennt von `mutations`.
- **Verzögerte Sichtbarkeit:** Nach einer Mutation kann die Luna-Lese-API für N Reads bzw. T virtuelle ms den
  Stand vor der Mutation zeigen (`StaleView`). Die SQLite-Datei (`.backup`) zeigt immer den wahren Zustand.
- **Virtuelle Uhr:** Jedes Remote-Kommando erhöht die Zeit um `virtual_ms_per_call`. Es gibt kein `sleep`
  außer bei ausdrücklichem `hang_ms`.
- **IDs:** `sim_entry_id` = UUIDv5 aus Fixture-Hash und Ursprungs-ID, Kopien aus Eltern-ID und laufender
  Nummer. Damit ist der Ablauf deterministisch und die IDs werden nie über das TV-Protokoll ausgegeben.
- **Reset:** Jeder Reset erzeugt aus der unveränderten Fixture ein neues Run-Verzeichnis. Solange eine
  SSH-Sitzung geöffnet ist, die bereits geschrieben hat, wird der Reset abgelehnt (außer mit `force`).
