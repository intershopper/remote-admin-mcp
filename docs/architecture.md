# Architektur

## Überblick

```
┌─────────────┐     MCP Protocol      ┌──────────────┐     SSH/SFTP     ┌─────────────┐
│  KI-Client  │ ◄──────────────────► │  MCP Server  │ ◄──────────────► │   Remote     │
│ (Kiro CLI,  │    stdio / HTTP       │  (server.py) │    paramiko      │   Server(s)  │
│  Claude)    │                       │              │                  │              │
└─────────────┘                       └──────┬───────┘                  └─────────────┘
                                             │
                                      ┌──────┴───────┐
                                      │  SSHClient   │
                                      │ (ssh_client) │
                                      └──────┬───────┘
                                             │
                                      ┌──────┴───────┐
                                      │    Config    │
                                      │  (.env file) │
                                      └──────────────┘
```

## Module

### `server.py` — MCP Server
Registriert die MCP Tools und verarbeitet Tool-Aufrufe. Unterstützt zwei Transportmodi:
- **stdio** (Standard): Kommunikation über stdin/stdout
- **HTTP**: StreamableHTTP auf konfigurierbarem Port

### `ssh_client.py` — SSH Client
Wrapper um paramiko für SSH- und SFTP-Operationen:
- Connection-Pooling (eine Verbindung pro Server)
- Command Execution mit Timeout und sudo-Support
- Streaming-Output für lange Befehle
- File-Operationen (read/write/upload/download) via SFTP

### `config.py` — Konfiguration
Lädt Server-Definitionen aus `.env`-Datei. Unterstützt beliebig viele Server über nummerierte Umgebungsvariablen (`SSH_SERVER_1_*`, `SSH_SERVER_2_*`, ...).

### `models.py` — Datenmodelle
- `ServerConfig`: Host, Port, User, Password
- `CommandResult`: stdout, stderr, exit_code

## MCP Tools

| Tool | Beschreibung | Approval |
|------|-------------|----------|
| `list_servers` | Verfügbare Server auflisten | Nein |
| `execute_command` | Befehl ausführen | Ja |
| `execute_script` | Mehrzeiliges Script ausführen | Ja |
| `read_file` | Datei lesen (mit offset/lines/tail) | Nein |
| `write_file` | Datei schreiben | Ja |
| `upload_file` | Lokale Datei hochladen | Ja |
| `download_file` | Remote-Datei herunterladen | Ja |
| `get_service_status` | systemd Service-Status | Nein |
| `manage_service` | Service start/stop/restart/reload | Ja |

## Sicherheit

- Alle schreibenden Operationen erfordern User-Approval durch den MCP Client
- SSH-Verbindungen nutzen paramiko (keine Shell-Subprozesse)
- Credentials werden aus `.env` geladen, nicht im Code
