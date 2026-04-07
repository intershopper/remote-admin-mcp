# SSH MCP Server — Architekturdokumentation (arc42)

## 1. Einführung und Ziele

### Aufgabenstellung
Der SSH MCP Server ermöglicht KI-Assistenten (Kiro CLI, Claude Desktop) die Verwaltung von Remote-Servern über SSH. Er implementiert das [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) und stellt 9 Tools für Kommandoausführung, Dateioperationen, Service-Management und effizientes Bearbeiten großer Dateien bereit.

### Qualitätsziele

| Priorität | Ziel | Beschreibung |
|-----------|------|-------------|
| 1 | Sicherheit | Alle schreibenden Operationen erfordern User-Approval |
| 2 | Zuverlässigkeit | Connection-Pooling, Timeout-Handling, Fehlertoleranz |
| 3 | Einfachheit | Minimale Konfiguration via `.env`, kein Setup-Overhead |

### Stakeholder

| Rolle | Erwartung |
|-------|-----------|
| KI-Assistent | Zuverlässige Tool-Aufrufe mit strukturiertem Output |
| Operator | Sichere Remote-Verwaltung mit Approval-Workflow |

---

## 2. Randbedingungen

### Technisch
- Python ≥ 3.10
- MCP SDK (`mcp` Package)
- SSH via `paramiko` (kein Shell-Subprocess)
- Transport: stdio (Standard) oder StreamableHTTP

### Organisatorisch
- DB Inner Source License (DBISL)
- Keine Speicherung von Credentials im Code

---

## 3. Kontextabgrenzung

### Fachlicher Kontext

```mermaid
graph LR
    User([Operator]) -->|Prompt| AI[KI-Assistent]
    AI -->|MCP Tool Call| MCP[SSH MCP Server]
    MCP -->|SSH/SFTP| S1[Server 1]
    MCP -->|SSH/SFTP| S2[Server 2]
    MCP -->|SSH/SFTP| SN[Server N]
    MCP -->|Tool Result| AI
    AI -->|Antwort| User
    AI -->|Approval Request| User
    User -->|Approve/Deny| AI
```

### Technischer Kontext

```mermaid
graph LR
    subgraph Lokal
        CLI[Kiro CLI / Claude] -->|stdio oder HTTP| MCP[MCP Server]
        ENV[.env] -->|Credentials| MCP
    end
    subgraph Remote
        MCP -->|SSH Port 22| S1[Linux Server]
        MCP -->|SFTP| S1
    end
```

---

## 4. Lösungsstrategie

- **MCP als Schnittstelle**: Standardisiertes Protokoll für KI-Tool-Integration
- **paramiko für SSH**: Direkte SSH-Library statt Shell-Subprozesse (sicherer)
- **Connection-Pooling**: Verbindungen werden 5 Minuten wiederverwendet
- **Streaming**: Lange Befehle liefern Output zeilenweise an den Client
- **Tool-Konsolidierung**: Minimale Anzahl Tools (9) um den LLM-Context klein zu halten
- **Large-File-Strategie**: Chirurgische Edits statt Full-File-Rewrite für große Dateien

### Tool-Übersicht

| Tool | Zweck | Auto-Approve |
|------|-------|:---:|
| `list_servers` | Verfügbare Server auflisten | ✓ |
| `execute` | Kommandos oder Scripts ausführen | ✗ |
| `read_file` | Dateien (teilweise) lesen | ✓ |
| `write_file` | Dateien komplett überschreiben | ✗ |
| `transfer_file` | Upload/Download via SFTP | ✗ |
| `service` | Systemd Services verwalten | ✗ |
| `search_in_file` | Pattern-Suche mit Kontext | ✓ |
| `replace_in_file` | Chirurgische Text-Ersetzung | ✗ |
| `get_file_structure` | Funktions-/Klassen-Übersicht | ✓ |

### Large-File-Workflow

Für Dateien >200 Zeilen folgt der KI-Assistent diesem Pattern:

```
1. get_file_structure  → Überblick (Symbole + Zeilennummern)
2. search_in_file      → Relevante Stelle finden
3. read_file (lines+offset) → Nur den Abschnitt lesen
4. replace_in_file     → Chirurgisch ändern
```

`write_file` wird nur für kleine Dateien oder Neuanlage verwendet.

---

## 5. Bausteinsicht

### Ebene 1 — Gesamtsystem

```mermaid
graph TB
    subgraph ssh-mcp-server
        SRV[server.py<br/>MCP Tool Registration]
        SSH[ssh_client.py<br/>SSH/SFTP Operations]
        AUD[audit.py<br/>Audit Logging]
        CFG[config.py<br/>Server Loading]
        MDL[models.py<br/>Data Classes]
    end

    SRV --> SSH
    SRV --> AUD
    SRV --> CFG
    SSH --> MDL
    CFG --> MDL
    AUD --> |~/.ssh-mcp-audit.log| LOG[(Logfile)]
```

### Ebene 2 — Moduldetails

```mermaid
classDiagram
    class Server {
        +list_tools() list~Tool~
        +call_tool(name, arguments) list~TextContent~
        +main()
    }

    class SSHClient {
        -_pool: dict
        -servers: dict
        +execute(server, command, sudo, timeout) CommandResult
        +execute_streaming(server, command, sudo, timeout) AsyncIterator
        +read_file(server, path, lines, offset, tail) str
        +write_file(server, path, content)
        +upload_file(server, local, remote)
        +download_file(server, remote, local)
        +search_in_file(server, path, pattern, context_lines, max_matches) str
        +replace_in_file(server, path, old_text, new_text, count, dry_run) str
        +get_file_structure(server, path, language) str
        +close_all()
    }

    class ServerConfig {
        +name: str
        +host: str
        +port: int
        +user: str
        +password: str
    }

    class CommandResult {
        +stdout: str
        +stderr: str
        +exit_code: int
    }

    Server --> SSHClient
    SSHClient --> ServerConfig
    SSHClient --> CommandResult
```

---

## 6. Laufzeitsicht

### Kommandoausführung

```mermaid
sequenceDiagram
    participant U as Operator
    participant AI as KI-Assistent
    participant MCP as MCP Server
    participant SSH as SSHClient
    participant S as Remote Server

    U->>AI: "Zeige Logs auf production"
    AI->>MCP: call_tool("execute", {server, command})
    AI->>U: Approval Request
    U->>AI: Approve ✓
    MCP->>SSH: execute("production", "tail -100 /var/log/syslog")
    SSH->>S: SSH exec_command
    S-->>SSH: stdout + exit_code
    SSH-->>MCP: CommandResult
    MCP-->>AI: TextContent
    AI-->>U: Formatierte Ausgabe
```

### Connection-Pooling

```mermaid
sequenceDiagram
    participant MCP as MCP Server
    participant Pool as Connection Pool
    participant S as Remote Server

    MCP->>Pool: _get_connection("pi4")
    alt Verbindung im Pool & aktiv & < 5min
        Pool-->>MCP: Bestehende Verbindung
    else Keine/abgelaufene Verbindung
        Pool->>S: paramiko.connect()
        S-->>Pool: SSH Session
        Pool-->>MCP: Neue Verbindung
    end
```

---

## 7. Verteilungssicht

```mermaid
graph TB
    subgraph Entwickler-Rechner
        CLI[Kiro CLI] --> MCP[SSH MCP Server<br/>Python Process]
        MCP --> ENV[.env<br/>Credentials]
    end

    subgraph Netzwerk
        MCP -->|SSH:22| PI4[pi4<br/>Raspberry Pi 4]
        MCP -->|SSH:22| OGPI[ogpi-lan<br/>Raspberry Pi 3]
        MCP -->|SSH:22| SRV[weitere Server...]
    end
```

---

## 8. Querschnittliche Konzepte

### Sicherheit
- **Approval-Workflow**: Schreibende Tools (`execute`, `write_file`, `replace_in_file`, `service`, `transfer_file`) erfordern User-Bestätigung durch den MCP Client
- **Auto-Approve nur für Lese-Tools**: `list_servers`, `read_file`, `search_in_file`, `get_file_structure`
- **Audit-Log**: Alle schreibenden Operationen werden in `~/.ssh-mcp-audit.log` protokolliert (Zeitstempel, Server, Tool, Detail)
- **Credential-Management**: Server-Zugangsdaten in `.env`, nicht im Code
- **Kein Shell-Subprocess**: paramiko nutzt direkte SSH-Kanäle

### Fehlerbehandlung
- Timeout-Erkennung via `timeout`-Wrapper im SSH-Befehl (exit code 124)
- Automatische Reconnection bei abgelaufenen Pool-Verbindungen
- Strukturierte Fehlerausgabe (stdout, stderr, exit code)

### Streaming
- Lange Befehle liefern Output zeilenweise via `execute_streaming`
- MCP Log-Messages für Echtzeit-Feedback an den Client

---

## 9. Architekturentscheidungen

| Entscheidung | Begründung |
|-------------|-----------|
| paramiko statt subprocess | Kein Shell-Injection-Risiko, direkter SSH-Kanal |
| Connection-Pooling (5min TTL) | Vermeidet SSH-Handshake bei aufeinanderfolgenden Befehlen |
| stdio als Default-Transport | Einfachste Integration mit MCP Clients |
| `.env` für Konfiguration | Standard-Pattern, kein eigener Config-Parser nötig |
| Script-Execution via Temp-File | Mehrzeilige Scripts zuverlässig ausführen, Cleanup garantiert |
| 9 konsolidierte Tools | Minimaler LLM-Context, keine redundanten Tools |
| replace_in_file via Python-Helper | SFTP-basierter Helper-Script vermeidet Shell-Escaping bei Multi-Line-Content |
| grep-basierte Dateistruktur | Keine Abhängigkeit auf Language Server, funktioniert auf jedem Server |

---

## 10. Qualitätsanforderungen

```mermaid
mindmap
  root((Qualität))
    Sicherheit
      User-Approval
      Keine Credentials im Code
      Kein Shell-Injection
    Zuverlässigkeit
      Connection-Pooling
      Timeout-Handling
      Reconnection
    Benutzbarkeit
      Minimale Konfiguration
      Strukturierter Output
      Streaming-Support
```

---

## 11. Risiken und technische Schulden

| Risiko | Maßnahme |
|--------|----------|
| Passwörter im Klartext in `.env` | Zukünftig: SSH-Key-Authentifizierung |
| Kein Rate-Limiting | Akzeptabel für Single-User-Betrieb |
| Keine Verschlüsselung des HTTP-Transports | Nur für lokalen Betrieb vorgesehen |

---

## 12. Glossar

| Begriff | Bedeutung |
|---------|-----------|
| MCP | Model Context Protocol — Standard für KI-Tool-Integration |
| Tool | Eine vom MCP Server bereitgestellte Funktion |
| Approval | Bestätigung durch den Operator vor Ausführung kritischer Operationen |
| SFTP | SSH File Transfer Protocol |
| Connection Pool | Wiederverwendung bestehender SSH-Verbindungen |
