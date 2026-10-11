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

## Offene Protokolldetails (UNKNOWN)

- **Exakte Antwortformate** der realen Luna-Methoden: Es liegen keine freigegebenen Traces vor. Der
  Simulator liefert `{"returnValue":true}` bzw. `returnValue/errorCode/errorText` sowie die Felder, die der
  Editor-Parser liest (`SIMULATOR_ASSUMPTION`).
- **`channelNumber` als String oder Zahl:** Der Simulator liefert einen String. Der Editor vergleicht ohnehin
  mit `str()`.
- **ID-Transformation beim Umnummerieren:** Angenommen wird `<src>_<phy>_<n>_<n>_<tsid>_<sid>_<onid>`, also
  maj/min = neue Nummer. Belegt ist nur, *dass* sich die ID ändert und der technische Rest gleich bleibt.
  Nicht-Satelliten-IDs (z. B. Kabel `3_1_<x>_0_…`) werden abgelehnt.
- **`favoriteIdx`-Kompaktierung** nach Entfernen und **`direction: down`** sind Annahmen.
- **Fehler bei unbekanntem Service** (`errorCode -1`, Exit-Status 0) ist eine Annahme.
- **`tuner_off`** wird wie in den beobachteten Backups als Spiegel von `tuner_on` gepflegt (Annahme).
