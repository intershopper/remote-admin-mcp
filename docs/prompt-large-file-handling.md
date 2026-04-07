# Feature: Large File Handling & Tool-Konsolidierung

## Context

Der SSH MCP Server hat aktuell 9 Tools. Für große Source-Files (1000+ Zeilen) fehlen chirurgische Edit-Operationen. Gleichzeitig sollen bestehende Tools konsolidiert werden, um den LLM-Context klein zu halten.

Ziel: **9 Tools total** (6 konsolidierte + 3 neue).

## Teil 1: Konsolidierung bestehender Tools (9 → 6)

### `execute_command` + `execute_script` → `execute`

```json
{
  "name": "execute",
  "description": "Execute a command or multi-line script on a remote server via SSH. For single commands use `command`, for multi-line scripts use `script`. Requires approval.",
  "properties": {
    "server": {"type": "string"},
    "command": {"type": "string", "description": "Single command to execute"},
    "script": {"type": "string", "description": "Multi-line bash script (alternative to command)"},
    "use_sudo": {"type": "boolean", "default": false},
    "timeout": {"type": "integer", "default": 30, "description": "Timeout in seconds (max 300)"}
  },
  "required": ["server"],
  "oneOf": [{"required": ["command"]}, {"required": ["script"]}]
}
```

### `upload_file` + `download_file` → `transfer_file`

```json
{
  "name": "transfer_file",
  "description": "Transfer a file between local machine and remote server via SFTP. Use direction=upload to send, direction=download to receive.",
  "properties": {
    "server": {"type": "string"},
    "direction": {"type": "string", "enum": ["upload", "download"]},
    "local_path": {"type": "string"},
    "remote_path": {"type": "string"}
  },
  "required": ["server", "direction", "local_path", "remote_path"]
}
```

### `get_service_status` + `manage_service` → `service`

```json
{
  "name": "service",
  "description": "Manage or query a systemd service. Use action=status to check, or start/stop/restart/reload to control. Actions other than status require sudo.",
  "properties": {
    "server": {"type": "string"},
    "service": {"type": "string"},
    "action": {"type": "string", "enum": ["status", "start", "stop", "restart", "reload"]}
  },
  "required": ["server", "service", "action"]
}
```

### Verbesserte Descriptions

```
list_servers:  "List all configured SSH servers with their connection details. Call this first to discover available server names."
read_file:     "Read a file or specific line range from a remote server. For large files (>200 lines), always use lines+offset to read only the relevant section. Use tail=true to read from end (e.g. log files)."
write_file:    "Overwrite an entire file on remote server via SFTP. WARNING: replaces full file content. For surgical edits on large files, use replace_in_file instead. Requires approval."
```

## Teil 2: Neue Tools (3)

### 1. `search_in_file`

```
"Search for a text pattern in a remote file using grep. Returns matching lines with line numbers and surrounding context. Use this to locate code sections before editing."
```

**Parameter:**
- `server` — Server name
- `path` — File path
- `pattern` — Grep regex pattern
- `context_lines` — Kontext-Zeilen um jeden Treffer (default: 3)
- `max_matches` — Max Ergebnisse (default: 20)

**Implementierung:** `grep -n -C{context_lines} -m{max_matches} {pattern} {path}`

### 2. `replace_in_file`

```
"Replace a specific text passage in a remote file without loading the full content. Preferred over write_file for editing large files. Returns error if old_text not found. Supports dry_run preview."
```

**Parameter:**
- `server`, `path` — Ziel
- `old_text` — Exakter Text (multi-line)
- `new_text` — Ersetzungstext
- `count` — Max Ersetzungen (default: 1, 0 = alle)
- `dry_run` — Preview ohne Schreiben (default: false)

**Implementierung:** Python-Helper-Script via SFTP → execute → cleanup. Fehler wenn `old_text` nicht gefunden.

### 3. `get_file_structure`

```
"Get an overview of functions, classes and key definitions in a source file. Returns symbol names with line numbers. Use this to understand a large file before reading or editing specific sections."
```

**Parameter:**
- `server`, `path` — Ziel
- `language` — Sprach-Hint (optional, auto-detect via Extension)

**Implementierung:** `wc -l` + sprachspezifische `grep -nE` Patterns:
- JS/TS: function, class, interface, type, enum, const arrow functions
- Python: class, def, async def

## Implementierungs-Hinweise

1. Neue Methoden in `SSHClient` (`ssh_client.py`), Tool-Registrierung in `server.py`
2. Multi-Line-Content via Helper-Script-Pattern: SFTP write → execute → cleanup
3. Vor jeder Operation `test -f {path}` zur Validierung
4. Output-Format: `[server_name] operation result`
5. Bestehende Tests nach Konsolidierung anpassen

## Ergebnis: 9 Tools

| # | Tool | Zweck |
|---|---|---|
| 1 | `list_servers` | Server entdecken |
| 2 | `execute` | Commands & Scripts ausführen |
| 3 | `read_file` | Dateien (teilweise) lesen |
| 4 | `write_file` | Dateien komplett schreiben |
| 5 | `transfer_file` | Upload/Download via SFTP |
| 6 | `service` | Systemd Services verwalten |
| 7 | `search_in_file` | Pattern-Suche in Dateien |
| 8 | `replace_in_file` | Chirurgische Text-Ersetzung |
| 9 | `get_file_structure` | Datei-Struktur-Übersicht |

## GitLab Issues
- #1 — Large File Handling Tools
- #2 — Tool-Konsolidierung & bessere Descriptions
