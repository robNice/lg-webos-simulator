# Evidence-Register

Stufen: `HARDWARE_CONFIRMED`, `TRACE_CONFIRMED`, `HISTORICAL_REPORTED`, `CURRENT_CLIENT_CONFIRMED`,
`SIMULATOR_ASSUMPTION`, `UNSUPPORTED`. Die Profilregeln in
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

- id: luna-response-shapes
  claim: "Antwortlayout der Luna-Methoden"
  evidence_level: SIMULATOR_ASSUMPTION (keine freigegebenen Traces)

- id: compressed-channel-list
  evidence_level: UNSUPPORTED
- id: copyDvbSatelliteChannelForAstra
  evidence_level: UNSUPPORTED (bewusst, nie automatisch)
```
