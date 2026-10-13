# Kompatibilitätslücken und Abweichungen

Konflikte zwischen der historischen Spezifikation und dem aktuellen Editor-Code sowie bewusst offene Punkte.
Entscheidung stets zugunsten des **aktuellen Codes** (Wahrheitshierarchie, Spec §25).

| # | Thema | Spezifikation (historisch) | Aktueller Code / Entscheidung |
|---|---|---|---|
| G1 | Service für Nummernwechsel | `legacybroadcast.channel/changeChannelNumber` | Seit v0.6.0 `iepg/changeChannelNumber`. Beide werden identisch simuliert. |
| G2 | `getChannelList`-Request | mit `channelType` und `compressed: 1` | Ohne `channelType` und ohne `compressed`. `compressed: 1` wird nicht simuliert und schlägt explizit fehl. |
| G3 | Astra-Kopie-Regel | `satelliteLcn_flag` allein entscheidet nicht | Seit v0.6.0 gilt: Jeder Wechsel Satellit >99 → 1–99 wird als Kopie behandelt (Profilregel `astra-copy-high-to-low`). |
| G4 | Favoriten-Migration | nur Gruppe A | Seit v0.6.0 werden **alle** Listen der Quelle auf die Kopie übertragen. Für den Simulator irrelevant, er führt nur die Einzelaufrufe aus. |
| G5 | Gruppennamen | – | Neu: `setGroupName` mit anschließendem SQL-Read-back (`channel_group_tuner.user_edited_name`). Simuliert. |
| G6 | Host-Key | – | Der Editor nutzt `load_system_host_keys()`. Ein Eintrag in `~/.ssh/known_hosts` ist nötig; in Tests wird `HOME` umgebogen. |
| G7 | Python-Version | 3.12+ | MX Linux hat hier Python **3.11.2**. Der Simulator unterstützt ≥ 3.11. |
| G8 | Admin-Port | `127.0.0.1:8766` | **8767**, weil 8766 von der Editor-Entwicklung (Browser-Tests) genutzt wird. 8765 und 8766 sind gesperrt. |
| G9 | `getChannelList`-Modus | `channelMode: "Satellite"` | Seit Editor v0.6.4 `channelMode: ["Tuner","IP"]` (wie LGs App, E1). Der Simulator nimmt String oder Liste; `Tuner` = Satellit + Kabel + Antenne, `IP` = LG Channels; unbekannte Werte schlagen fehl. |
| G10 | Fremde Senderlisten | – | `import-globalclone` macht aus LG-USB-Exporten (GlobalClone, auch von anderen TVs, Ländern und Satelliten) Fixtures. Inhalte sind echt (E11), die Struktur der iepg-Zeilen ist abgeleitet (U6). Für Editor-Tests reicht das; Aussagen über das ID-Verhalten anderer Satelliten liefert es nicht. |

## Offene Protokolldetails (UNKNOWN)

- **Exakte Antwortformate** der realen Luna-Methoden: Es liegen keine freigegebenen Traces vor. Der
  Simulator liefert `{"returnValue":true}` bzw. `returnValue/errorCode/errorText` sowie die Felder, die der
  Editor-Parser liest (`SIMULATOR_ASSUMPTION`).
- **`channelNumber` als String oder Zahl:** Der Simulator liefert einen String. Der Editor vergleicht ohnehin
  mit `str()`.
- **ID-Transformation beim Umnummerieren:** Angenommen wird `<src>_<phy>_<n>_<n>_<tsid>_<sid>_<onid>`, also
  maj/min = neue Nummer. Belegt ist nur, *dass* sich die ID ändert und der technische Rest gleich bleibt.
  Nicht-Satelliten-IDs (z. B. Kabel `3_1_<x>_0_…`) werden abgelehnt.
- **ID-Varianten aus echten Backups:** Radio (`maj = Nummer + 0x4000`) und Satellit ohne LCN (`min ≠ Nummer`)
  kommen real vor (Evidenz `lg-id-format-observed-variants`). Wie die Firmware deren IDs beim Umnummerieren
  umschreibt, ist offen. Der Simulator lehnt das Umnummerieren solcher Einträge mit
  `SIM_UNSUPPORTED_CHANNEL_ID` ab, statt eine Transformation zu raten.
- **Streamingsender (Tabelle `ip`, Empfangsart `IP`):** Seit Editor v0.6.4 simuliert. `getChannelList` liefert sie
  mit `channelMode` `IP` bzw. `["Tuner","IP"]` (E2, E7), `getChannel` kennt sie, Favoriten setzen, entfernen und
  verschieben wirken auf `ip` und `favorite_idx` (E6). `changeChannelNumber` mit einer IP-ID (iepg und
  legacybroadcast) bleibt abgelehnt: `SIM_UNSUPPORTED_IP_CHANNEL` ohne Zustandsänderung (E9; der Fehlercode des
  TV ist ungemessen, U4).
- **IP-Sender in Favoritenlisten:** Tuner-Mitglieder ab 0, IP-Mitglieder ab 251 (E5, E8). Offen und als
  Simulator-Annahmen umgesetzt:
  - **U1 Blockgrenze:** Darf ein IP-Sender vor einen Tuner-Sender rücken? Profiloption
    `favorites.ip_block_after_tuner` (Standard `true`): Der IP-Block bleibt hinter den Tuner-Sendern, ein Move über
    die Grenze ändert nichts und antwortet trotzdem `returnValue:true`. Der Editor erkennt das beim Rücklesen
    (`error.order.unconfirmed`, E2E-Test). `false`: eine gemeinsame Reihenfolge 0..n-1.
  - **U2 Aufnehmen per API:** nächster freier Index im IP-Block, mindestens 251.
  - **U3 Entfernen:** die übrigen IP-Indizes werden innerhalb des IP-Blocks zusammengeschoben.
  - **Nicht-Mitglieder (geklärt durch die Aufnahmen 14:17 und 23:01):** in `ip` 255, in `favorite_idx` 250, bei
    Tuner-Sendern 250. Der Simulator schreibt genau so; der Weg 14:17 → 23:01 wird im Test exakt nachgebildet.
- **U4 IP umnummerieren:** Antwort des TV unbekannt; der Editor sendet das nie (`error.plan.ip_number_locked`).
- **U5 Kabel und Antenne umnummerieren:** Wie die Firmware die IDs umschreibt, ist unbekannt. Der Editor plant
  Kabelnummern seit v0.6.4; im Simulator endet so ein Schritt mit `SIM_UNSUPPORTED_CHANNEL_ID` (ehrlicher Abbruch,
  danach Re-Import). Belegungsprüfungen gelten pro Empfangsart: Satellit auf eine nur von Kabel belegte Nummer ist
  ein MOVE (E2E-Test).
- **Antenne (Terrestrial):** Codes, ID-Layout und die Zugehörigkeit zu `Tuner` sind Annahmen; Umnummerieren ist
  nicht simuliert (U5).
- **`favoriteIdx`-Kompaktierung** nach Entfernen und **`direction: down`** sind Annahmen. Der echte TV behält in
  Tuner-Listen Lücken (Liste A 0, 1, 7, 8 …; Liste C beginnt bei 8, beide Aufnahmen); der Simulator verdichtet nach
  jeder Änderung. Ob der TV nach einem Entfernen verdichtet, ist ungemessen.
- **Fehler bei unbekanntem Service** (`errorCode -1`, Exit-Status 0) ist eine Annahme.
- **`tuner_off`** wird wie in den beobachteten Backups als Spiegel von `tuner_on` gepflegt (Annahme).
