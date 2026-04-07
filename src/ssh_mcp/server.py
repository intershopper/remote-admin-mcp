from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent
from .config import load_servers
from .ssh_client import SSHClient
from . import audit

server = Server("ssh-mcp-server")
servers = load_servers()
ssh_client = SSHClient(servers)

_use_streaming = True


def _truncate_json_lines(text: str, max_json_len: int = 300) -> str:
    """Truncate lines that look like large JSON blobs."""
    lines = text.split("\n")
    out = []
    for line in lines:
        stripped = line.strip()
        if (stripped.startswith("{") and stripped.endswith("}") and len(stripped) > max_json_len):
            out.append(line[:max_json_len] + "... [JSON truncated]")
        else:
            out.append(line)
    return "\n".join(out)


def _format_result(result, server_name: str = "", command: str = "") -> str:
    """Output with server/command context header."""
    header = f"[{server_name}] $ {command}\n" if server_name and command else ""
    parts = []
    if result.stdout.strip():
        parts.append(_truncate_json_lines(result.stdout.rstrip()))
    if result.stderr.strip():
        parts.append(f"STDERR: {result.stderr.rstrip()}")
    if result.exit_code != 0:
        parts.append(f"Exit code: {result.exit_code}")
    body = "\n".join(parts) if parts else "(no output)"
    return f"{header}{body}"


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_servers",
            description="List all configured SSH servers with their connection details. Call this first to discover available server names.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="execute",
            description="Execute a command or multi-line script on a remote server via SSH. For single commands use `command`, for multi-line scripts use `script`. Requires approval.",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Server name"},
                    "command": {"type": "string", "description": "Single command to execute"},
                    "script": {"type": "string", "description": "Multi-line bash script (alternative to command)"},
                    "use_sudo": {"type": "boolean", "description": "Use sudo", "default": False},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30, max: 300)", "default": 30}
                },
                "required": ["server"]
            }
        ),
        Tool(
            name="read_file",
            description="Read a file or specific line range from a remote server. For large files (>200 lines), always use lines+offset to read only the relevant section. Use tail=true to read from end (e.g. log files).",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Server name"},
                    "path": {"type": "string", "description": "File path"},
                    "lines": {"type": "integer", "description": "Number of lines to read"},
                    "offset": {"type": "integer", "description": "Line offset (skip N lines from start)", "default": 0},
                    "tail": {"type": "boolean", "description": "Read from end of file", "default": False}
                },
                "required": ["server", "path"]
            }
        ),
        Tool(
            name="write_file",
            description="Overwrite an entire file on remote server via SFTP. WARNING: replaces full file content. For surgical edits on large files, use replace_in_file instead. Requires approval.",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Server name"},
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "File content"}
                },
                "required": ["server", "path", "content"]
            }
        ),
        Tool(
            name="transfer_file",
            description="Transfer a file between local machine and remote server via SFTP. Use direction=upload to send, direction=download to receive.",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Server name"},
                    "direction": {"type": "string", "enum": ["upload", "download"], "description": "Transfer direction"},
                    "local_path": {"type": "string", "description": "Local file path"},
                    "remote_path": {"type": "string", "description": "Remote file path"}
                },
                "required": ["server", "direction", "local_path", "remote_path"]
            }
        ),
        Tool(
            name="service",
            description="Manage or query a systemd service. Use action=status to check, or start/stop/restart/reload to control. Actions other than status require sudo.",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Server name"},
                    "service": {"type": "string", "description": "Service name"},
                    "action": {"type": "string", "enum": ["status", "start", "stop", "restart", "reload"], "description": "Action to perform"}
                },
                "required": ["server", "service", "action"]
            }
        ),
        Tool(
            name="search_in_file",
            description="Search for a text pattern in a remote file using grep. Returns matching lines with line numbers and surrounding context. Use this to locate code sections before editing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Server name"},
                    "path": {"type": "string", "description": "File path"},
                    "pattern": {"type": "string", "description": "Grep regex pattern"},
                    "context_lines": {"type": "integer", "description": "Lines of context around each match", "default": 3},
                    "max_matches": {"type": "integer", "description": "Maximum number of matches", "default": 20}
                },
                "required": ["server", "path", "pattern"]
            }
        ),
        Tool(
            name="replace_in_file",
            description="Replace a specific text passage in a remote file without loading the full content. Preferred over write_file for editing large files. Returns error if old_text not found. Supports dry_run preview.",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Server name"},
                    "path": {"type": "string", "description": "File path"},
                    "old_text": {"type": "string", "description": "Exact text to find (multi-line supported)"},
                    "new_text": {"type": "string", "description": "Replacement text"},
                    "count": {"type": "integer", "description": "Max replacements (default: 1, 0 = all)", "default": 1},
                    "dry_run": {"type": "boolean", "description": "Preview changes without applying", "default": False}
                },
                "required": ["server", "path", "old_text", "new_text"]
            }
        ),
        Tool(
            name="get_file_structure",
            description="Get an overview of functions, classes and key definitions in a source file. Returns symbol names with line numbers. Use this to understand a large file before reading or editing specific sections.",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Server name"},
                    "path": {"type": "string", "description": "File path"},
                    "language": {"type": "string", "description": "Language hint (auto-detected from extension if omitted)"}
                },
                "required": ["server", "path"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "list_servers":
        server_list = "\n".join(f"  {n}  {cfg.user}@{cfg.host}:{cfg.port}" for n, cfg in servers.items())
        return [TextContent(type="text", text=server_list)]

    elif name == "execute":
        srv = arguments["server"]
        command = arguments.get("command")
        script = arguments.get("script")
        use_sudo = arguments.get("use_sudo", False)
        timeout = min(arguments.get("timeout", 30), 300)

        if not command and not script:
            return [TextContent(type="text", text="ERROR: Provide either 'command' or 'script'")]

        # Script mode: write to temp file, execute, clean up
        if script:
            import hashlib
            tmp = f"/tmp/_mcp_{hashlib.md5(script.encode()).hexdigest()[:8]}.sh"
            ssh_client.write_file(srv, tmp, f"#!/bin/bash\n{script}\n")
            try:
                result = ssh_client.execute(srv, f"bash {tmp}", use_sudo, timeout)
                audit.log(srv, "execute", f"script ({len(script)} chars)")
                return [TextContent(type="text", text=_format_result(result, srv, "execute_script"))]
            except TimeoutError:
                return [TextContent(type="text", text=f"[{srv}] execute_script\nTIMEOUT after {timeout}s")]
            finally:
                ssh_client.execute(srv, f"rm -f {tmp}")

        # Command mode with streaming
        cmd = command
        if _use_streaming:
            try:
                ctx = server.request_context
                rid = ctx.request_id
                log = ctx.session.send_log_message
                output_lines, exit_code, stderr_data = [], 0, ""
                async for line in ssh_client.execute_streaming(srv, cmd, use_sudo, timeout):
                    if line.startswith("\0EXIT:"):
                        parts = line[6:].split(":", 1)
                        exit_code = int(parts[0])
                        stderr_data = parts[1] if len(parts) > 1 else ""
                    else:
                        output_lines.append(line)
                        await log(level="info", data=line, related_request_id=rid)
                header = f"[{srv}] $ {cmd}\n"
                result_parts = []
                stdout = "\n".join(output_lines)
                if stdout.strip():
                    result_parts.append(_truncate_json_lines(stdout))
                if stderr_data.strip():
                    result_parts.append(f"STDERR: {stderr_data.rstrip()}")
                if exit_code == 124:
                    result_parts.append(f"TIMEOUT after {timeout}s")
                elif exit_code != 0:
                    result_parts.append(f"Exit code: {exit_code}")
                body = "\n".join(result_parts) if result_parts else "(no output)"
                audit.log(srv, "execute", cmd)
                return [TextContent(type="text", text=f"{header}{body}")]
            except Exception:
                pass  # Fall through to non-streaming

        try:
            result = ssh_client.execute(srv, cmd, use_sudo, timeout)
            audit.log(srv, "execute", cmd)
            return [TextContent(type="text", text=_format_result(result, srv, cmd))]
        except TimeoutError:
            return [TextContent(type="text", text=f"[{srv}] $ {cmd}\nTIMEOUT after {timeout}s. Retry with higher timeout (max 300s).")]

    elif name == "read_file":
        srv = arguments["server"]
        path = arguments["path"]
        lines = arguments.get("lines")
        offset = arguments.get("offset", 0)
        tail = arguments.get("tail", False)
        content = ssh_client.read_file(srv, path, lines=lines, offset=offset, tail=tail)
        return [TextContent(type="text", text=f"[{srv}] {path}\n{content.rstrip()}")]

    elif name == "write_file":
        ssh_client.write_file(arguments["server"], arguments["path"], arguments["content"])
        audit.log(arguments["server"], "write_file", arguments["path"])
        return [TextContent(type="text", text=f"[{arguments['server']}] Written: {arguments['path']}")]

    elif name == "transfer_file":
        srv = arguments["server"]
        direction = arguments["direction"]
        local_path = arguments["local_path"]
        remote_path = arguments["remote_path"]
        if direction == "upload":
            ssh_client.upload_file(srv, local_path, remote_path)
            audit.log(srv, "transfer_file", f"upload {local_path} → {remote_path}")
            return [TextContent(type="text", text=f"[{srv}] Uploaded: {local_path} → {remote_path}")]
        else:
            ssh_client.download_file(srv, remote_path, local_path)
            return [TextContent(type="text", text=f"[{srv}] Downloaded: {remote_path} → {local_path}")]

    elif name == "service":
        srv = arguments["server"]
        svc = arguments["service"]
        action = arguments["action"]
        use_sudo = action != "status"
        result = ssh_client.execute(srv, f"systemctl {action} {svc}", use_sudo=use_sudo)
        if action != "status" and result.exit_code == 0:
            audit.log(srv, "service", f"{action} {svc}")
            return [TextContent(type="text", text=f"[{srv}] {svc} → {action} OK")]
        return [TextContent(type="text", text=_format_result(result, srv, f"systemctl {action} {svc}"))]

    elif name == "search_in_file":
        srv = arguments["server"]
        path = arguments["path"]
        pattern = arguments["pattern"]
        ctx_lines = arguments.get("context_lines", 3)
        max_matches = arguments.get("max_matches", 20)
        result = ssh_client.search_in_file(srv, path, pattern, ctx_lines, max_matches)
        return [TextContent(type="text", text=f"[{srv}] grep '{pattern}' {path}\n{result}")]

    elif name == "replace_in_file":
        srv = arguments["server"]
        path = arguments["path"]
        old_text = arguments["old_text"]
        new_text = arguments["new_text"]
        count = arguments.get("count", 1)
        dry_run = arguments.get("dry_run", False)
        result = ssh_client.replace_in_file(srv, path, old_text, new_text, count, dry_run)
        action = "Preview" if dry_run else "Replaced"
        if not dry_run:
            audit.log(srv, "replace_in_file", path)
        return [TextContent(type="text", text=f"[{srv}] {action} in {path}\n{result}")]

    elif name == "get_file_structure":
        srv = arguments["server"]
        path = arguments["path"]
        language = arguments.get("language")
        result = ssh_client.get_file_structure(srv, path, language)
        return [TextContent(type="text", text=f"[{srv}] {path}\n{result}")]

    raise ValueError(f"Unknown tool: {name}")


async def _async_main_stdio():
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def _async_main_http(host: str, port: int):
    from starlette.applications import Starlette
    from starlette.routing import Mount
    import uvicorn
    import contextlib

    session_manager = StreamableHTTPSessionManager(app=server, json_response=False)

    async def handle_mcp(scope, receive, send):
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with session_manager.run():
            yield

    app = Starlette(
        routes=[Mount("/mcp", app=handle_mcp)],
        lifespan=lifespan,
    )
    config = uvicorn.Config(app, host=host, port=port)
    srv = uvicorn.Server(config)
    await srv.serve()


def main():
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="SSH MCP Server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    if args.transport == "http":
        asyncio.run(_async_main_http(args.host, args.port))
    else:
        asyncio.run(_async_main_stdio())


if __name__ == "__main__":
    main()
