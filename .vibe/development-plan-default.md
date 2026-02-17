# Development Plan: ssh-server-mcp (default branch)

*Generated on 2026-02-14 by Vibe Feature MCP*
*Workflow: [epcc](https://mrsimpson.github.io/responsible-vibe-mcp/workflows/epcc)*

## Goal
Ein MCP Server für SSH-basierte Server-Administration, der KI-Assistenten ermöglicht:
- Logs zu analysieren und zu debuggen
- Services zu verwalten (starten, stoppen, status)
- Dateien anzulegen und Konfigurationen zu ändern
- Systemlogs zu prüfen
- Allgemeine Server-Administrationsaufgaben durchzuführen

**Zielgruppe**: DevOps, System-Administratoren, Entwickler mit Server-Zugriff
## Key Decisions
- **Authentifizierung**: Passwörter in .env (nicht SSH-Keys) für einfachere Konfiguration
- **Multi-Server**: Unterstützung mehrerer Server-Konfigurationen
- **Sudo-Zugriff**: Erlaubt für volle Administrationsmöglichkeiten
- **Keine Command-Whitelist**: Voller Zugriff auf alle Befehle (Vertrauen in User-Konfiguration)
- **Bestätigung erforderlich**: Alle Befehle müssen vom User bestätigt werden (MCP approval mechanism)

## Notes
**MCP Tools:**
1. `execute_command` - Befehl ausführen (mit Bestätigung)
2. `read_file` - Datei lesen
3. `write_file` - Datei schreiben (mit Bestätigung)
4. `list_servers` - Server auflisten
5. `get_service_status` - Service Status abfragen
6. `manage_service` - Service starten/stoppen/restart (mit Bestätigung)

**Tech Stack:**
- Python 3.10+
- paramiko (SSH)
- mcp SDK
- python-dotenv

**Multi-Server Config Format:**
```
SSH_SERVER_1_NAME=production
SSH_SERVER_1_HOST=prod.example.com
SSH_SERVER_1_PORT=22
SSH_SERVER_1_USER=admin
SSH_SERVER_1_PASSWORD=secret123
```

**Sicherheit:**
- User-Bestätigung für alle Befehle via MCP approval
- Command-Logging für Audit-Trail
- Passwörter in .env (lokal, nicht committed)

## Explore
### Tasks
- [x] Anforderungen für MCP Tools definieren
- [x] Technologie-Stack festlegen (Python, SSH-Library)
- [x] Sicherheitsrisiken dokumentieren
- [x] Multi-Server Konfigurationsformat definieren
- [x] Beispiel-Use-Cases dokumentieren
- [x] Projektstruktur planen (analog zu gaidc-mcp-server)

### Completed
- [x] Created development plan file
- [x] Hauptziel und Scope definiert
- [x] Authentifizierungsmethode festgelegt
- [x] Funktionsumfang geklärt
- [x] MCP Tools spezifiziert
- [x] Tech Stack festgelegt
- [x] Sicherheitskonzept (User-Bestätigung) definiert

## Plan

### Phase Entrance Criteria:
- [x] Die Anforderungen und das Ziel sind klar definiert
- [x] Technische Machbarkeit wurde untersucht
- [x] Sicherheitsaspekte wurden identifiziert
- [x] Alternativen wurden evaluiert

### Tasks
- [x] Projektstruktur erstellen (pyproject.toml, src/, tests/)
- [x] SSH Client Modul designen (Connection Management, Command Execution)
- [x] Config Modul designen (Multi-Server .env parsing)
- [x] MCP Server Modul designen (Tool Definitions, Approval Handling)
- [x] Datenmodelle definieren (ServerConfig, CommandResult, etc.)
- [x] Error Handling Strategie festlegen
- [x] README mit Setup-Anleitung schreiben

### Completed
- [x] Architektur geplant
- [x] Module spezifiziert

### Completed
*None yet*

## Code

### Phase Entrance Criteria:
- [x] Architektur und Design sind dokumentiert
- [x] Technologie-Stack ist festgelegt
- [x] API/Tool-Definitionen sind spezifiziert
- [x] Sicherheitskonzept ist definiert

### Tasks
- [x] pyproject.toml erstellen
- [x] models.py implementieren
- [x] config.py implementieren
- [x] ssh_client.py implementieren
- [x] server.py mit MCP Tools implementieren
- [x] .env.example erstellen
- [x] README.md schreiben
- [x] Basis-Tests schreiben

### Completed
- [x] Projektstruktur erstellt
- [x] Alle Core-Module implementiert
- [x] 6 MCP Tools implementiert
- [x] Dokumentation geschrieben
- [x] Tests geschrieben

### Completed
*None yet*

## Commit

### Phase Entrance Criteria:
- [ ] Code ist implementiert und funktionsfähig
- [ ] Grundlegende Tests wurden durchgeführt
- [ ] Dokumentation ist vorhanden
- [ ] Sicherheitsaspekte sind implementiert

### Tasks
- [ ] *To be added when this phase becomes active*

### Completed
*None yet*



---
*This plan is maintained by the LLM. Tool responses provide guidance on which section to focus on and what tasks to work on.*
