# Entwicklungsgeschichte

- **10.10.2026:** Der Editor v0.5.24 schließt die vollständige automatische Neunummerierung auf einem
  LG OLED55C27LA (webOS 22) ab. Das ist der historische Referenzpunkt.
- **10.–11.10.2026:** Editor v0.6.0/v0.6.1: Nummernwechsel über iepg, Kopierpfad für jeden Wechsel >99 → 1–99,
  Migration aller Listen, Übertragung von Gruppennamen, Fortschrittsdialog und Re-Import.
- **11.10.2026:** Simulator v0.1.0 nach `LG_WEBOS_CHANNEL_EDITOR_TV_SIMULATOR_PROJEKTPLAN.md`:
  - Phase 0: Vertrag aus dem aktuellen Editor-Code (read-only) erhoben.
  - Phasen 1–7: Projekt, SSH/SFTP-Fassade, Luna-Reads, Favoriten, Nummerierung inkl. Astra-Fälle,
    Fehler-Engine, Journal und Trace-Vergleich, Admin-Oberfläche, Dokumentation.
  - Golden-Test: Der echte Editor nummeriert 47 Favoriten mit 49 MOVE, 7 SWAP und 4 COPY über SSH um und
    verifiziert das Ergebnis per Re-Import.
  - Gefundener und behobener Fehler: Die Admin-API akzeptierte durch die Pydantic-Lax-Konvertierung
    `confirm: "yes"`. Jetzt gilt der Strict-Modus.
