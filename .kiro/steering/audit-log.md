---
inclusion: always
---

# SSH MCP Server — Audit Log

## Pfad
- Standard: `~/.ssh-mcp-audit.log`
- Konfigurierbar via `SSH_MCP_AUDIT_LOG` in `.env`

## Format
```
[YYYY-MM-DD HH:MM:SS] [servername] tool: detail — reason
```

## Was wird geloggt
Alle schreibenden Operationen:
- `execute` — Kommandos und Scripts
- `write_file` — Datei komplett geschrieben
- `replace_in_file` — Chirurgische Textänderung (nicht bei dry_run)
- `service` — Start/Stop/Restart/Reload (nicht bei status)
- `transfer_file` — Upload (nicht Download)

## Was wird NICHT geloggt
Lese-Operationen: `list_servers`, `read_file`, `search_in_file`, `get_file_structure`, `transfer_file` (download)

## Nutzung
- Gesamtes Log: `cat ~/.ssh-mcp-audit.log`
- Nach Server filtern: `grep "\[pi4\]" ~/.ssh-mcp-audit.log`
- Nach Datum: `grep "2026-04-07" ~/.ssh-mcp-audit.log`
- Letzte Einträge: `tail -20 ~/.ssh-mcp-audit.log`
