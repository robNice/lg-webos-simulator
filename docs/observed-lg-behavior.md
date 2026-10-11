# Beobachtetes LG-Verhalten und Abbildung im Simulator

Profil `lg_webos22_historical`: Regeln werden von oben nach unten geprüft, die erste passende Regel gilt.

| Regel | Bedingung | Effekt | Historischer Fall |
|---|---|---|---|
| `deny-tagged-high-target` | Eintrag mit Tag `deny_above_99`, Ziel ≥ 100 | DENY `CHANNEL_ERROR_1003 / Channel Move Denied` | WELT HD 13 → 900 |
| `reuse-existing-copy` | Satellit, Quelle ≥ 100, Ziel 1–99, Ziel mit gleichem DVB-Dienst belegt | REUSE_COPY (true, keine Mutation) | HGTV-HD-Kopie auf 26 |
| `astra-copy-high-to-low` | Satellit, Quelle ≥ 100, Ziel 1–99 frei | COPY: neuer Eintrag ohne Favoriten, Original bleibt | Pro7 MAXX 418→14, ARD-alpha 125→26 |
| `swap-occupied-slot` | Ziel genau einmal belegt (gleicher Modus) | SWAP: beide Einträge erhalten neue Nummern und IDs, die Gruppen bleiben bei den Einträgen | ShopLC HD 21→20 |
| `deny-ambiguous-target` | Ziel mehrfach belegt | DENY `SIM_TARGET_AMBIGUOUS` | Annahme |
| `move-to-free-slot` | Ziel frei | MOVE, neue ID | Normalfall, 4mediathek → 4096 |

Weitere Verhaltensweisen:

- Programmnummern gelten **pro Empfangsmodus** (`chan_mode_name`). Kabel 13 und Satellit 13 stören sich nicht.
- Mehrfachbelegung bestehender Nummern ist erlaubt, z. B. 101 (TV + Radio).
- Gleiche DVB-Kennung, mehrere Einträge: WELT HD 13/403/1015.
- Nach dem Umnummerieren ist die alte ID ungültig (`CHANNEL_ERROR_NOT_FOUND`); es gibt keinen versteckten Alias.
- `setChannelFavoriteGroup` hängt ans Listenende an. Ist der Sender bereits Mitglied: `true` ohne Mutation.
- `moveChannelFavoritePriority direction:up` setzt die Quelle an die Position des Ziels (so nutzt es der
  Editor), `down` direkt dahinter.
- `getFavoriteGroupList` liefert auch nach `setGroupName` die Standardnamen (am TV beobachtet).
- Unbekannte Methoden, Services, Parameter und ID-Formate führen zu `returnValue:false` mit eindeutigem Code.
  Erfolg wird nie vorgetäuscht.

## Fehlerszenarien (`fixtures/scenarios/*.yaml`)

| Szenario | Katalog | Wirkung |
|---|---|---|
| `return_false_but_favorite_moved` | T27 | 2. Sortieraufruf ändert die Reihenfolge, antwortet aber `false` |
| `add_favorite_false_no_mutation` | T28 | 1. Add antwortet `false`, nichts geändert |
| `add_favorite_false_with_mutation` | – | 1. Add antwortet `false`, trotzdem geändert |
| `delayed_visibility` | T29 | Jede Änderung wird erst nach 2 weiteren Reads sichtbar |
| `copy_instead_of_move` | T30 | 1. Nummernwechsel antwortet `true`, erzeugt aber eine Kopie |
| `timeout_before_mutation` | T31 | Verbindungsabbruch vor dem Schreiben |
| `timeout_after_mutation` | T32 | Geschrieben, dann Abbruch ohne Antwort und ohne Exit-Status |
| `fail_after_second_step` | T33/T34 | 3. Nummernwechsel bricht ab, Schritte 1–2 bleiben (kein Rollback) |
| `sftp_abort` | T06 | SFTP-Download bricht nach 4096 Bytes ab |
| `backup_locked` | – | 1. `.backup` liefert `Error: database is locked` |
| `slow_write_answer` | – | Nummernwechsel sofort geschrieben, Antwort erst nach 3 s (Timeout-Tests) |
