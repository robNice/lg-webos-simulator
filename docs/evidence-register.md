# Evidence-Register

Stufen: `HARDWARE_CONFIRMED`, `TRACE_CONFIRMED`, `HISTORICAL_REPORTED`, `CURRENT_CLIENT_CONFIRMED`,
`SIMULATOR_ASSUMPTION`, `UNSUPPORTED`; seit Editor v0.6.4 zusätzlich `REAL_TV_CLIENT_CODE` (LGs eigene App, lesend
vom TV kopiert), `REAL_TV_READ` (am TV nur lesend ermittelt), `REAL_TV_CONFIRMED` (am TV geschrieben und bestätigt),
`USER_OBSERVED` (Nutzerbeobachtung). Die Profilregeln in
`src/lg_tv_sim/profiles/lg_webos22_historical.yaml` tragen ihre Stufe selbst.

```yaml
- id: lg-astra-copy-high-to-low
  claim: "Wechsel Satellit >99 -> 1..99 erzeugt einen zusätzlichen Eintrag; Original bleibt mit seinen Favoriten"
  evidence_level: HISTORICAL_REPORTED
  observed_date: "2026-10-10"
  source: "Pro7 MAXX HD 418->14, ARD-alpha HD 125->26; HGTV HD 1827->26 ohne LCN-Flag (Editor v0.6.0 Notizen)"
  implementation_profile: COPY
  known_limitations:
    - "Nicht auf alle Sender und Firmware-Versionen verallgemeinern"
    - "ID der Kopie im Simulator nach SatelliteIdPolicy (Annahme)"

- id: lg-swap-occupied-slot
  claim: "Nummernwechsel auf belegten Platz tauscht beide Einträge, beide erhalten neue IDs"
  evidence_level: HISTORICAL_REPORTED
  source: "ShopLC HD 21 -> 20"
  implementation_profile: SWAP

- id: lg-deny-welt-hd-high
  claim: "WELT HD (13) -> 900 abgelehnt mit CHANNEL_ERROR_1003, -> 99 erfolgreich"
  evidence_level: HISTORICAL_REPORTED
  implementation_profile: DENY (nur für Einträge mit Tag deny_above_99)

- id: lg-api-accepts-above-99
  claim: "4mediathek per API auf 4096 umgestellt, obwohl die TV-Maske 1..99 zeigt"
  evidence_level: HISTORICAL_REPORTED
  implementation_profile: MOVE (number_max 9999)

- id: lg-favorites-not-copied
  claim: "Die neue Astra-Kopie hat zunächst keine Favoritengruppen"
  evidence_level: HISTORICAL_REPORTED

- id: lg-returnvalue-false-but-mutated
  claim: "Luna kann returnValue:false liefern, obwohl sich der Zustand geändert hat (Favoritenreihenfolge)"
  evidence_level: HISTORICAL_REPORTED
  implementation: Szenario return_false_but_favorite_moved

- id: lg-iepg-number-change
  claim: "iepg/changeChannelNumber verhält sich wie legacybroadcast (gleiche IDs), ohne Umschalten"
  evidence_level: HARDWARE_CONFIRMED (laut Editor tv_write.py, v0.6.0)

- id: lg-setgroupname
  claim: "setGroupName{channelMode:TUNER, channelGroupId:200..207}; getFavoriteGroupList zeigt danach weiter Standardnamen"
  evidence_level: HARDWARE_CONFIRMED (laut Editor tv_groups.py, 2026-10-11, Liste H)

- id: lg-schema
  claim: "Tabellen-/Spaltendefinitionen von tuner_on, tuner_off, favorite_idx, channel_group_tuner"
  evidence_level: HARDWARE_CONFIRMED (Schema read-only aus einem realen Backup introspektiert, keine Senderdaten übernommen)

- id: lg-id-format-satellite
  claim: "Satelliten-ID = <src>_<phy>_<maj>_<min>_<tsid>_<sid>_<onid>, maj=min=Programmnummer, tail=signal_chan_id"
  evidence_level: HARDWARE_CONFIRMED (Struktur in realen Backups); Transformation beim Umnummerieren: SIMULATOR_ASSUMPTION

- id: lg-id-format-observed-variants
  claim: "In einem echten Backup nach bestätigtem Umnummerieren: Satellit LCN maj=min=Nummer (461); Satellit ohne LCN maj=Nummer, min≠Nummer (142, z. B. 7_17_33_14_…; min 0 oder andere Werte); Radio maj=Nummer+0x4000 (Satellit und Kabel); Kabel 3_<phy>_<maj>_<min>_…; chan_type_id Kabel 4/5, Satellit 6/7 (TV/Radio) = Präfix von channelMajMinNo"
  evidence_level: HARDWARE_CONFIRMED (Struktur eines Backups vom 11.10.2026, nur aggregiert ausgewertet, keine Senderdaten übernommen)
  consequence: "Fixture-Builder bildet die Layouts nach; die ID-Transformation beim Umnummerieren ist nur für maj=min=Nummer simuliert, alles andere schlägt geschlossen fehl"

- id: lg-terrestrial-codes
  claim: "Antenne: chan_mode_name Terrestrial, chan_src_type 2, chan_mode_id 0, chan_type_id 2/3, ID <src>_<phy>_<maj>_0_<tsid>_<sid>_<onid>"
  evidence_level: SIMULATOR_ASSUMPTION (kein Antennen-Backup vorhanden; Sender in synthetic_realistic erfunden)

- id: E1-channeledit-channelmode
  claim: "LGs App com.webos.app.channeledit (main.js) fragt Favoritenlisten mit channelMode [Tuner, IP] ab, mit compressed: 1 (sendet der Editor nicht)"
  evidence_level: REAL_TV_CLIENT_CODE

- id: E2-getchannellist-modes
  claim: "[Tuner, IP] = 1072 (682 Satellit, 170 Kabel, 220 IP); Tuner = 852; Satellite/Cable/IP einzeln 682/170/220; jeweils Invisible:false; tuner_on hat 709 Satellitenzeilen (27 unsichtbar)"
  evidence_level: REAL_TV_READ
  consequence: "channelMode als String oder Liste; ein Test auf real_20261011_1417 reproduziert die Zahlen. Dass Tuner auch Antenne umfasst: SIMULATOR_ASSUMPTION (kein Antennen-TV vorhanden)"

- id: E3-satellitename-modeid
  claim: "satelliteName Satellit 'ASTRA 19.2E', Kabel ' ' (ein Leerzeichen), IP 'UNKNOWN'; channelModeId Kabel 1, Satellit 2, IP 7"
  evidence_level: REAL_TV_READ

- id: E4-ip-id-format
  claim: "IP-ID 11_3_<nummer>_65535_0_0_0 (z. B. 11_3_100_65535_0_0_0 = LG 1, Nummer 100)"
  evidence_level: REAL_TV_READ

- id: E5-favorite-index-blocks
  claim: "Nicht-Mitglied favoriteIdx 250; Tuner-Mitglieder ab 0 (Liste A 0–59 mit Lücken); IP-Mitglieder ab 251 (per Fernbedienung hinzugefügte LG Channels in Liste D: 251–255)"
  evidence_level: REAL_TV_READ
  note: "Präzisiert durch die Aufnahmen 14:17 und 23:01: In ip tragen IP-Nicht-Mitglieder 255, in favorite_idx stehen Nicht-Mitglieds-Spalten auf 250, Tuner-Nicht-Mitglieder 250. Tuner-Listen behalten Lücken (A 0, 1, 7, 8 …; C beginnt bei 8). Der Simulator verdichtet nach Änderungen weiterhin (SIMULATOR_ASSUMPTION, ob der TV nach einem Entfernen verdichtet, ist ungemessen)."

- id: E11-diff-1417-2301
  claim: "Zwischen den Aufnahmen 14:17 und 23:01 änderten sich nur 5 ip-Zeilen (Liste D: 251 LG 1: Spotlight, 252 LG 1: Film, 253 Sony One | Action HITS, 254 Sony One | Comedy HITS, 255 LG 1; user_fav_chan_gr [\"D\"]), 5 neue favorite_idx-Zeilen (gleiche Indizes, übrige Listen 250) und der Name von Liste B; tuner_on und tuner_off unverändert"
  evidence_level: REAL_TV_READ (beide Aufnahmen bereinigt in fixtures/recorded)
  consequence: "Regressionstest: Von real_20261011_1417 aus die 5 Sender per Luna in D aufnehmen und wie der Editor sortieren ergibt Zeile für Zeile den Stand von real_20261011_2301 (beide Aufnahme-Reihenfolgen)"

- id: E6-ip-favorites-storage
  claim: "IP-Mitglieder stehen in ip (fav_chan_gr_<x>='1', favoriteIdx<X>, user_fav_chan_gr) und in favorite_idx (gleiche ID, gleicher Index), nicht in tuner_on/tuner_off"
  evidence_level: REAL_TV_READ
  consequence: "Engine schreibt genau so; Invariante prüft ip ⇔ favorite_idx; Fixture real_20261011_1417_ipfav angeglichen"

- id: E7-live-ip-favorites
  claim: "getChannelList meldet für IP-Mitglieder dieselben favoriteIdx (251…) und favoriteGroup wie die Datenbank"
  evidence_level: REAL_TV_READ

- id: E8-reorder-ip-block
  claim: "Umsortieren von 5 LG Channels in Liste D per Editor (moveChannelFavoritePriority, direction up) funktioniert; danach 251–255 in neuer Reihenfolge, gleich in ip, favorite_idx und Live-Antwort"
  evidence_level: REAL_TV_CONFIRMED (Reihenfolge innerhalb eines reinen IP-Blocks)

- id: E9-ip-not-renumberable
  claim: "LG Channels lassen sich am TV nicht umnummerieren"
  evidence_level: USER_OBSERVED
  consequence: "changeChannelNumber mit IP-ID: SIM_UNSUPPORTED_IP_CHANNEL (Fehlercode des TV unbekannt, U4)"

- id: E10-live-extra-fields
  claim: "Die Live-Antwort enthält viel mehr Felder (u. a. channelModeId, channelTypeId, rfIpChannel, ipChanType, majorNumber, minorNumber); der Editor liest nur channelId, channelNumber, channelName, satelliteName, channelMode, favoriteGroup, favoriteIdxA..H"
  evidence_level: REAL_TV_READ
  consequence: "Der Simulator liefert die gelesenen Felder und einige mehr, nicht alle Felder des TV"

- id: U1-ip-block-boundary
  claim: "Darf ein IP-Sender per moveChannelFavoritePriority vor einen Tuner-Sender rücken?"
  evidence_level: SIMULATOR_ASSUMPTION (Profil favorites.ip_block_after_tuner; Standard true: ein Move über die Grenze bleibt ohne Wirkung, Antwort returnValue true; false: gemeinsame Reihenfolge 0..n-1)

- id: U2-ip-add-index
  claim: "Index bei setChannelFavoriteGroup für einen IP-Sender per API"
  evidence_level: SIMULATOR_ASSUMPTION (nächster freier Index im IP-Block, mindestens 251)

- id: U3-ip-release-compaction
  claim: "Werden die übrigen IP-Indizes nach releaseChannelFavoriteGroup zusammengeschoben?"
  evidence_level: SIMULATOR_ASSUMPTION (ja, innerhalb des IP-Blocks)

- id: U4-ip-renumber-error
  claim: "Antwort des TV auf changeChannelNumber mit IP-ID"
  evidence_level: SIMULATOR_ASSUMPTION (Simulator-Code SIM_UNSUPPORTED_IP_CHANNEL; der Editor sendet das nie)

- id: U5-cable-antenna-id-rewrite
  claim: "ID-Umschreibung beim Umnummerieren von Kabel- und Antennensendern"
  evidence_level: UNSUPPORTED (bewusst keine Annahme: Umnummerieren schlägt mit SIM_UNSUPPORTED_CHANNEL_ID fehl)

- id: systemproperty-getsysteminfo
  claim: "getSystemInfo {keys:[modelName, serialNumber]} liefert die Schlüssel auf oberster Ebene plus returnValue; luna-send -f gibt formatiertes JSON aus"
  evidence_level: CURRENT_CLIENT_CONFIRMED (Aufruf und gelesene Felder, tv_identity.py v0.6.4); Antwortlayout/Formatierung SIMULATOR_ASSUMPTION
  consequence: "Simulator meldet Modell aus [device] und immer eine SIM-Seriennummer"

- id: E11-globalclone-content
  claim: "GlobalClone-USB-Exporte (legacybroadcast) tragen dieselben Senderinhalte wie die iepg-Datenbank: Frequenz (Satellit MHz, Kabel/Antenne kHz), Radio-Nummern mit 0x4000 wie maj_no, Satellitennamen wie sat_name (z. B. 'ASTRA 19.2E'), serviceType wie svc_type"
  evidence_level: REAL_TV_READ (Abgleich gleicher DVB-Tripel zwischen der echten Sicherung 11.10.2026 und öffentlichen Exporten anderer TVs: Frequenz 341/341 gleich, Radio-Flag bei 100 % der Radiosender)
  source: "ChanSort-Diskussion #207, Issues #286, #401, #418, ChanSort-Testdateien (GPLv3), lg-channel-import (TR)"
  consequence: "lg-tv-sim import-globalclone übernimmt diese Felder 1:1"

- id: U6-globalclone-structure
  claim: "Was der Export nicht enthält: dvc_chan_id, min_no (immer 0), LCN-Flag (immer false); Bedeutung von Invisible = invisible_flag; alte XML-Codes sourceIndex 2/3"
  evidence_level: SIMULATOR_ASSUMPTION (Builder-Regeln wie bei synthetischen Fixtures; Invisible als ausgeblendet übernommen, abschaltbar; sourceIndex 7 = Satellit und 1 = Antenne belegt, andere Codes nur per --mode-map)
  known_limitations:
    - "ID-Layout für andere Satelliten als Astra 19.2E ungemessen"
    - "physicalNumber stammt aus dem Suchlauf des exportierenden TV"
    - "Satellit im alten XML aus der Satelliten-DB der Datei; bei Widerspruch (UK-Export: 19.2E, aber ONID 2) per --satellite"

- id: E12-invisible-filter
  claim: "getChannelList Satellite ohne attribute-Filter liefert auch ausgeblendete Einträge, je Zeile mit \"Invisible\": true (Bibel TV 790); mit {filterType: Invisible, value: true} genau die 27 ausgeblendeten"
  evidence_level: REAL_TV_READ (OLED55C27LA, 13.10.2026, luna-send lesend)
  source: "Ohne Filter 710 Zeilen gezählt (grep auf channelId); die Sicherung vom 11.10. hat 709 Satellitenzeilen, Gegencheck offen"
  consequence: "Simulator: kein Filter = alle, false = sichtbare, true = ausgeblendete; mehrere oder andere Filter schlagen fehl"

- id: E13-hidden-entries-in-favorites
  claim: "setChannelFavoriteGroup nimmt einen ausgeblendeten Eintrag wie einen sichtbaren auf (Bibel TV 790 in Liste H: favoriteGroup [H], favoriteIdxH 1 nach tagesschau24 HD mit 0); er bleibt ausgeblendet (Invisible true, invisible_flag 1), erscheint am TV in Liste H; releaseChannelFavoriteGroup nimmt ihn wieder heraus"
  evidence_level: REAL_TV_CONFIRMED (OLED55C27LA, 13.10.2026, Messskript mit Gegenprobe, Live-Liste und Datenbank)
  consequence: "Simulator unverändert (er verhielt sich schon so); Annahme U7 dafür aufgelöst"

- id: E14-favorite-membership-returnvalue
  claim: "set/releaseChannelFavoriteGroup antworten {returnValue:false}, obwohl sie wirken (10 von 10 Aufrufen, sichtbare und ausgeblendete Einträge); die Datenbank-Datei zieht nach weniger als 2 s nach"
  evidence_level: REAL_TV_CONFIRMED (13.10.2026)
  implementation_profile: "favorites.membership_return_value: false"
  known_limitations:
    - "favoriteGroup als Zeichenkette statt Liste: Antwort ebenfalls false, Wirkung nicht sauber gemessen (sofort gelesen)"
    - "moveChannelFavoritePriority antwortet im Simulator weiter true (ungemessen)"

- id: U7-invisible-other-writes
  claim: "moveChannelFavoritePriority und changeChannelNumber auf ausgeblendete Einträge"
  evidence_level: SIMULATOR_ASSUMPTION (wirken wie bei sichtbaren Einträgen, der Eintrag bleibt ausgeblendet)

- id: luna-response-shapes
  claim: "Antwortlayout der Luna-Methoden"
  evidence_level: SIMULATOR_ASSUMPTION (keine freigegebenen Traces)

- id: compressed-channel-list
  evidence_level: UNSUPPORTED
- id: copyDvbSatelliteChannelForAstra
  evidence_level: UNSUPPORTED (bewusst, nie automatisch)
```
