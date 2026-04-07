from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent
from .config import load_servers
from .ssh_client import SSHClient

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
            description="List all available SSH servers",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="execute_command",
            description="Execute a command on a remote server (requires approval)",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Server name"},
                    "command": {"type": "string", "description": "Command to execute"},
                    "use_sudo": {"type": "boolean", "description": "Use sudo", "default": False},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30, max: 300)", "default": 30}
                },
                "required": ["server", "command"]
            }
        ),
        Tool(
            name="execute_script",
            description="Execute a multi-line bash script on a remote server (requires approval)",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Server name"},
                    "script": {"type": "string", "description": "Bash script content (multi-line)"},
                    "use_sudo": {"type": "boolean", "description": "Use sudo", "default": False},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default: 60, max: 300)", "default": 60}
                },
                "required": ["server", "script"]
            }
        ),
        Tool(
            name="read_file",
            description="Read a file from remote server. Supports partial reads with lines/offset/tail.",
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
            description="Write a text file to remote server via SFTP (requires approval)",
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
            name="upload_file",
            description="Upload a local file to remote server via SFTP (requires approval)",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Server name"},
                    "local_path": {"type": "string", "description": "Local file path"},
                    "remote_path": {"type": "string", "description": "Remote destination path"}
                },
                "required": ["server", "local_path", "remote_path"]
            }
        ),
        Tool(
            name="download_file",
            description="Download a file from remote server to local path via SFTP",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Server name"},
                    "remote_path": {"type": "string", "description": "Remote file path"},
                    "local_path": {"type": "string", "description": "Local destination path"}
                },
                "required": ["server", "remote_path", "local_path"]
            }
        ),
        Tool(
            name="get_service_status",
            description="Get systemd service status",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Server name"},
                    "service": {"type": "string", "description": "Service name"}
                },
                "required": ["server", "service"]
            }
        ),
        Tool(
            name="manage_service",
            description="Manage systemd service (start/stop/restart) (requires approval)",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Server name"},
                    "service": {"type": "string", "description": "Service name"},
                    "action": {"type": "string", "enum": ["start", "stop", "restart", "reload"]}
                },
                "required": ["server", "service", "action"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "list_servers":
        server_list = "\n".join(f"  {n}  {cfg.user}@{cfg.host}:{cfg.port}" for n, cfg in servers.items())
        return [TextContent(type="text", text=server_list)]

    elif name == "execute_command":
        cmd = arguments["command"]
        use_sudo = arguments.get("use_sudo", False)
        timeout = min(arguments.get("timeout", 30), 300)

        if _use_streaming:
            try:
                ctx = server.request_context
                rid = ctx.request_id
                log = ctx.session.send_log_message
                output_lines, exit_code, stderr_data = [], 0, ""
                async for line in ssh_client.execute_streaming(arguments["server"], cmd, use_sudo, timeout):
                    if line.startswith("\0EXIT:"):
                        parts = line[6:].split(":", 1)
                        exit_code = int(parts[0])
                        stderr_data = parts[1] if len(parts) > 1 else ""
                    else:
                        output_lines.append(line)
                        await log(level="info", data=line, related_request_id=rid)
                # Build final response with stdout + stderr + exit code
                header = f"[{arguments['server']}] $ {cmd}\n"
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
                return [TextContent(type="text", text=f"{header}{body}")]
            except Exception:
                pass  # Fall through to non-streaming

        try:
            result = ssh_client.execute(arguments["server"], cmd, use_sudo, timeout)
            return [TextContent(type="text", text=_format_result(result, arguments["server"], cmd))]
        except TimeoutError:
            return [TextContent(type="text", text=f"[{arguments['server']}] $ {cmd}\nTIMEOUT after {timeout}s. Retry with higher timeout (max 300s).")]

    elif name == "execute_script":
        script = arguments["script"]
        srv = arguments["server"]
        use_sudo = arguments.get("use_sudo", False)
        timeout = min(arguments.get("timeout", 60), 300)
        # Write script to temp file, execute, clean up
        import hashlib
        tmp = f"/tmp/_mcp_{hashlib.md5(script.encode()).hexdigest()[:8]}.sh"
        ssh_client.write_file(srv, tmp, f"#!/bin/bash\n{script}\n")
        try:
            result = ssh_client.execute(srv, f"bash {tmp}", use_sudo, timeout)
            return [TextContent(type="text", text=_format_result(result, srv, "execute_script"))]
        except TimeoutError:
            return [TextContent(type="text", text=f"[{srv}] execute_script\nTIMEOUT after {timeout}s")]
        finally:
            ssh_client.execute(srv, f"rm -f {tmp}")

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
        return [TextContent(type="text", text=f"[{arguments['server']}] Written: {arguments['path']}")]

    elif name == "upload_file":
        srv = arguments["server"]
        ssh_client.upload_file(srv, arguments["local_path"], arguments["remote_path"])
        return [TextContent(type="text", text=f"[{srv}] Uploaded: {arguments['local_path']} → {arguments['remote_path']}")]

    elif name == "download_file":
        srv = arguments["server"]
        ssh_client.download_file(srv, arguments["remote_path"], arguments["local_path"])
        return [TextContent(type="text", text=f"[{srv}] Downloaded: {arguments['remote_path']} → {arguments['local_path']}")]

    elif name == "get_service_status":
        svc = arguments["service"]
        result = ssh_client.execute(arguments["server"], f"systemctl status {svc}")
        return [TextContent(type="text", text=_format_result(result, arguments["server"], f"systemctl status {svc}"))]

    elif name == "manage_service":
        svc, action = arguments["service"], arguments["action"]
        result = ssh_client.execute(arguments["server"], f"systemctl {action} {svc}", use_sudo=True)
        if result.exit_code == 0:
            return [TextContent(type="text", text=f"[{arguments['server']}] {svc} → {action} OK")]
        return [TextContent(type="text", text=_format_result(result, arguments["server"], f"systemctl {action} {svc}"))]

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
