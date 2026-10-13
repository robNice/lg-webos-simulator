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

- Programmnummern gelten **pro Empfangsmodus** (`chan_mode_name`). Kabel 13 und Satellit 13 stören sich nicht;
  ein Satellitensender auf eine nur von Kabel belegte Nummer ist ein MOVE (E2E-Test mit Editor v0.6.4).
- Mehrfachbelegung bestehender Nummern ist erlaubt, z. B. 101 (TV + Radio).
- Gleiche DVB-Kennung, mehrere Einträge: WELT HD 13/403/1015.
- Nach dem Umnummerieren ist die alte ID ungültig (`CHANNEL_ERROR_NOT_FOUND`); es gibt keinen versteckten Alias.
- `setChannelFavoriteGroup` hängt ans Listenende an. Ist der Sender bereits Mitglied: `true` ohne Mutation.
- `moveChannelFavoritePriority direction:up` setzt die Quelle an die Position des Ziels (so nutzt es der
  Editor), `down` direkt dahinter.
- `getFavoriteGroupList` liefert auch nach `setGroupName` die Standardnamen (am TV beobachtet).
- Unbekannte Methoden, Services, Parameter und ID-Formate führen zu `returnValue:false` mit eindeutigem Code.
  Erfolg wird nie vorgetäuscht.

## Empfangsarten und LG Channels (Editor v0.6.4, echter TV OLED55C27LA, 11.10.2026)

Am TV nur lesend ermittelt, außer E8. Die Nummern verweisen auf `docs/evidence-register.md`.

| # | Beobachtung | Abbildung im Simulator |
|---|---|---|
| E2 | `getChannelList` mit `channelMode: ["Tuner","IP"]` liefert 1072 Einträge (682 Satellit, 170 Kabel, 220 IP); `"Tuner"` allein 852; `"Satellite"`, `"Cable"`, `"IP"` einzeln 682/170/220, jeweils mit `Invisible:false` (27 der 709 Satellitenzeilen sind unsichtbar) | String oder Liste; `Tuner` = Satellit + Kabel + Antenne; auf `real_20261011_1417` genau diese Zahlen (Test) |
| E3 | `satelliteName`: Satellit `"ASTRA 19.2E"`, Kabel `" "`, IP `"UNKNOWN"`; `channelModeId` Kabel 1, Satellit 2, IP 7 | `satelliteName` aus `sat_name`, sonst diese Werte; Antenne wie Kabel (Annahme) |
| E4 | IP-ID `11_3_<nummer>_65535_0_0_0` | so in Fixtures erzeugt |
| E5 | Tuner-Nicht-Mitglied `favoriteIdx = 250`, Tuner-Mitglieder ab 0 (mit Lücken), IP-Mitglieder ab 251 | Tuner 0.., IP ab 251; Nicht-Mitglied IP 255 (so in der Aufnahme von 14:17) |
| E6 | IP-Mitglieder in `ip` und `favorite_idx` (gleiche ID, gleicher Index), nie in `tuner_on`/`tuner_off` | genau so geschrieben, Invariante prüft es |
| E7 | Live-Antwort meldet für IP-Mitglieder dieselben `favoriteIdx`/`favoriteGroup` wie die Datenbank | `getChannelList` liest IP-Einträge aus `ip` |
| E8 | Umsortieren von 5 LG Channels in Liste D per Editor funktionierte; danach weiter 251–255 in neuer Reihenfolge | Verschieben im IP-Block vergibt 251… neu |
| E9 | LG Channels lassen sich nicht umnummerieren (Nutzerbeobachtung) | `changeChannelNumber` mit IP-ID: `SIM_UNSUPPORTED_IP_CHANNEL` |
| E12 | Ohne `attribute`-Filter kommen auch ausgeblendete Einträge, mit `"Invisible": true`; `{Invisible: true}` liefert genau die 27 ausgeblendeten (13.10.2026) | Filter `true`/`false`/keiner |
| E13 | Ausgeblendete Einträge lassen sich in Favoritenlisten aufnehmen und entfernen; sie bleiben ausgeblendet und erscheinen am TV in der Liste (13.10.2026) | wie bei sichtbaren Einträgen |
| E14 | `set`/`releaseChannelFavoriteGroup` antworten `returnValue:false`, obwohl sie wirken (10 von 10) | Profil `favorites.membership_return_value: false` |

Offen (Simulator-Annahmen, siehe `docs/compatibility-gaps.md`): U1 Blockgrenze Tuner/IP, U2 Index beim Aufnehmen
per API, U3 Verdichten beim Entfernen, U4 Fehlercode für IP-Umnummerierung, U5 ID-Umschreibung bei Kabel/Antenne.

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
