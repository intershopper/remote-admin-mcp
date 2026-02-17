# SSH MCP Server

MCP Server für SSH-basierte Server-Administration. Ermöglicht KI-Assistenten die Verwaltung von Remote-Servern via SSH.

## Features

- **Remote Command Execution**: Beliebige Befehle auf Remote-Servern ausführen
- **File Operations**: Dateien lesen und schreiben
- **Service Management**: Systemd Services verwalten (start/stop/restart)
- **Multi-Server Support**: Mehrere Server gleichzeitig verwalten
- **User Approval**: Alle kritischen Operationen erfordern Bestätigung

## Installation

### Mit uv (empfohlen)

```bash
# Virtuelle Umgebung erstellen und Abhängigkeiten installieren
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

### Mit pip

```bash
# Virtuelle Umgebung erstellen
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Abhängigkeiten installieren
pip install -e ".[dev]"
```

## Konfiguration

1. Kopiere `.env.example` zu `.env`:
```bash
cp .env.example .env
```

2. Bearbeite `.env` mit deinen Server-Zugangsdaten:
```bash
SSH_SERVER_1_NAME=production
SSH_SERVER_1_HOST=prod.example.com
SSH_SERVER_1_PORT=22
SSH_SERVER_1_USER=admin
SSH_SERVER_1_PASSWORD=your-password

SSH_SERVER_2_NAME=staging
SSH_SERVER_2_HOST=staging.example.com
SSH_SERVER_2_PORT=22
SSH_SERVER_2_USER=deploy
SSH_SERVER_2_PASSWORD=your-password
```

## MCP Tools

### list_servers
Liste alle konfigurierten Server auf.

### execute_command
Führe einen Befehl auf einem Remote-Server aus.

**Parameter:**
- `server` (string): Server-Name
- `command` (string): Auszuführender Befehl
- `use_sudo` (boolean): Mit sudo ausführen

### read_file
Lese eine Datei vom Remote-Server.

**Parameter:**
- `server` (string): Server-Name
- `path` (string): Dateipfad

### write_file
Schreibe eine Datei auf den Remote-Server.

**Parameter:**
- `server` (string): Server-Name
- `path` (string): Dateipfad
- `content` (string): Dateiinhalt

### get_service_status
Prüfe den Status eines systemd Services.

**Parameter:**
- `server` (string): Server-Name
- `service` (string): Service-Name

### manage_service
Verwalte einen systemd Service (start/stop/restart/reload).

**Parameter:**
- `server` (string): Server-Name
- `service` (string): Service-Name
- `action` (string): Aktion (start/stop/restart/reload)

## Verwendung mit KI-Assistenten

### Claude Desktop / Kiro CLI

Füge zu deiner MCP-Konfiguration hinzu:

```json
{
  "mcpServers": {
    "ssh": {
      "command": "/path/to/ssh-server-mcp/.venv/bin/python",
      "args": ["-m", "ssh_mcp.server"]
    }
  }
}
```

## Beispiele

**Log-Analyse:**
```
"Zeige mir die letzten 100 Zeilen vom nginx error log auf production"
```

**Service Restart:**
```
"Starte den nginx Service auf staging neu"
```

**Config ändern:**
```
"Lies die nginx.conf auf production und erhöhe worker_processes auf 4"
```

## Sicherheit

⚠️ **Wichtige Hinweise:**
- Passwörter werden im Klartext in `.env` gespeichert
- Alle Befehle erfordern User-Bestätigung
- Sudo-Zugriff ist möglich
- `.env` sollte NICHT ins Git committed werden

## Entwicklung

```bash
# Tests ausführen
pytest -v

# Linting
ruff check src/
```

## Lizenz

MIT
