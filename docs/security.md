# Sicherheit

- **Nur Loopback:** SSH `127.0.0.1:2222`, Admin `127.0.0.1:8767`. Nicht-Loopback-Adressen werden beim
  Konfigurieren abgelehnt, außer `[security] allow_external_bind = true` ist ausdrücklich gesetzt. Port 22 sowie
  die Editor-Ports 8765 (Web-UI) und 8766 (Editor-Entwicklung/Browser-Tests) sind gesperrt.
- **Container:** `config/docker.toml` bindet im Container bewusst `0.0.0.0` (`allow_external_bind = true`),
  damit Docker die Ports veröffentlichen kann. Auf dem Host nur `127.0.0.1:<port>` veröffentlichen. Die
  Admin-API akzeptiert weiterhin nur Localhost-Host-Header. Eine Loopback-Adresse in der Container-Config
  wird beim Start abgelehnt. Der Entrypoint läuft nur zum Anlegen und Übereignen von `/config` (nur oberste
  Ebene) und `/app/.simulator` als root und startet den Simulator per `setpriv` als `PUID:PGID` (Standard
  10001); `PUID`/`PGID` 0 werden abgelehnt.
- **Kein Host-Shell-Zugang:** kein `subprocess`, kein `shell=True`. Erlaubt sind nur die fünf Befehlsformen des
  Editors. Ein eigener Tokenizer weist jeden nicht gequoteten Shell-Operator (`; | & < > $ \` ( ) * ? …`),
  Expansionen in doppelten Anführungszeichen, Backslashes und Zeilenumbrüche ab. Shell-, PTY-, SCP- und
  Forwarding-Anfragen werden abgelehnt.
- **SQL:** `SELECT` läuft über eine read-only-Verbindung mit SQLite-Authorizer (nur READ/SELECT/FUNCTION),
  daher kein `ATTACH` und keine Schreibzugriffe. `.backup` schreibt nur in das virtuelle `/tmp`.
- **Dateisystem:** Virtuelles `/tmp/<name>` mit `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` wird auf
  `.simulator/runs/<run>/tmp/` abgebildet. Traversal, Unterverzeichnisse und Symlinks werden abgewiesen. SFTP ist
  read-only, ohne Verzeichnislisting.
- **`root` ist nur ein Protokolldetail:** Der Server läuft als normaler Benutzer ohne `sudo`.
- **Zugangsdaten:** Das Simulator-Passwort kommt aus `$LG_TV_SIM_PASSWORD` oder wird generiert und in
  `.simulator/credentials` (0600) abgelegt. Der Host-Key liegt in `.simulator/keys/` (0600, Verzeichnis 0700).
  Niemals TV-Zugangsdaten verwenden.
- **Admin-API:** Prüfung des Host-Headers (Schutz gegen DNS-Rebinding), kein CORS, strikte Pydantic-Modelle
  (`extra=forbid`, `strict=True`, z. B. wird `"yes"` nicht als `true` akzeptiert), Bestätigung `confirm: true`
  für Reset/Restore/Szenario, optionaler Token `X-Sim-Token` (`$LG_TV_SIM_ADMIN_TOKEN`), CSP `self`.
- **Daten:** `.simulator/`, `fixtures/private/`, Schlüssel und `.env` sind in `.gitignore`. Das Journal
  entfernt Felder mit Passwort/Token und Nicht-Loopback-IPv4-Adressen. Private Fixtures werden nur read-only
  importiert (Hash protokolliert) und nie überschrieben.
- **Keine Netzwerkausgänge:** Der Simulator baut selbst keine Verbindungen auf und braucht keine TV-Adresse.
