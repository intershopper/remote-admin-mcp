from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent
from .config import load_servers
from .ssh_client import SSHClient

server = Server("ssh-mcp-server")
servers = load_servers()
ssh_client = SSHClient(servers)

_use_streaming = False


def _explain_command(cmd: str, use_sudo: bool = False) -> str:
    """Generate a simple explanation of what the command does."""
    cmd_lower = cmd.lower().strip()
    
    # Common command patterns
    if cmd_lower.startswith("docker exec"):
        return "Execute command inside a Docker container"
    elif cmd_lower.startswith("docker ps"):
        return "List running Docker containers"
    elif cmd_lower.startswith("docker logs"):
        return "Show Docker container logs"
    elif cmd_lower.startswith("systemctl status"):
        return "Check systemd service status"
    elif cmd_lower.startswith("systemctl restart"):
        return "Restart systemd service"
    elif cmd_lower.startswith("systemctl start"):
        return "Start systemd service"
    elif cmd_lower.startswith("systemctl stop"):
        return "Stop systemd service"
    elif cmd_lower.startswith("cat "):
        return "Display file contents"
    elif cmd_lower.startswith("ls "):
        return "List directory contents"
    elif cmd_lower.startswith("grep "):
        return "Search for text patterns"
    elif "grep" in cmd_lower and "|" in cmd_lower:
        return "Execute command and filter output"
    elif cmd_lower.startswith("tail "):
        return "Show last lines of file"
    elif cmd_lower.startswith("journalctl"):
        return "Query systemd journal logs"
    elif cmd_lower.startswith("sed "):
        return "Edit text using stream editor"
    elif cmd_lower.startswith("psql "):
        return "Execute PostgreSQL query"
    elif cmd_lower.startswith("perl "):
        return "Execute Perl script"
    elif ">" in cmd and "<<" in cmd:
        return "Write multi-line content to file"
    elif use_sudo:
        return f"Execute with elevated privileges: {cmd.split()[0]}"
    else:
        return f"Execute shell command: {cmd.split()[0] if cmd.split() else 'unknown'}"


def _format_result(cmd: str, explanation: str, result) -> str:
    """Format command result with clear visual structure."""
    status = "✅" if result.exit_code == 0 else "❌"
    parts = [
        f"{'━' * 50}",
        f"🖥️  {cmd}",
        f"📋  {explanation}",
        f"{status}  Exit Code: {result.exit_code}",
        f"{'━' * 50}",
    ]
    if result.stdout.strip():
        parts.append(f"📤 STDOUT:\n```\n{result.stdout.rstrip()}\n```")
    if result.stderr.strip():
        parts.append(f"⚠️  STDERR:\n```\n{result.stderr.rstrip()}\n```")
    return "\n".join(parts)


def _format_stream_header(cmd: str, explanation: str) -> str:
    return f"{'━' * 50}\n🖥️  {cmd}\n📋  {explanation}\n{'━' * 50}"


def _format_stream_footer(exit_code: int, stderr_data: str) -> str:
    status = "✅" if exit_code == 0 else "❌"
    parts = [f"{'━' * 50}", f"{status}  Exit Code: {exit_code}"]
    if stderr_data.strip():
        parts.append(f"⚠️  STDERR:\n```\n{stderr_data.rstrip()}\n```")
    return "\n".join(parts)


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
            name="read_file",
            description="Read a file from remote server",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Server name"},
                    "path": {"type": "string", "description": "File path"}
                },
                "required": ["server", "path"]
            }
        ),
        Tool(
            name="write_file",
            description="Write a file to remote server (requires approval)",
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
        server_list = "\n".join([f"  🔹 {n}  →  {cfg.user}@{cfg.host}:{cfg.port}" 
                                  for n, cfg in servers.items()])
        return [TextContent(type="text", text=f"📡 Available Servers:\n{server_list}")]
    
    elif name == "execute_command":
        cmd = arguments["command"]
        use_sudo = arguments.get("use_sudo", False)
        timeout = min(arguments.get("timeout", 30), 300)
        explanation = _explain_command(cmd, use_sudo)

        if _use_streaming:
            ctx = server.request_context
            request_id = ctx.request_id
            await ctx.session.send_log_message(
                level="info",
                data=_format_stream_header(cmd, explanation),
                related_request_id=request_id,
            )
            output_lines = []
            exit_code = 0
            stderr_data = ""
            async for line in ssh_client.execute_streaming(arguments["server"], cmd, use_sudo, timeout):
                if line.startswith("\0EXIT:"):
                    parts = line[6:].split(":", 1)
                    exit_code = int(parts[0])
                    stderr_data = parts[1] if len(parts) > 1 else ""
                else:
                    output_lines.append(line)
                    await ctx.session.send_log_message(
                        level="info",
                        data=f"  │ {line}",
                        related_request_id=request_id,
                    )
            await ctx.session.send_log_message(
                level="info",
                data=_format_stream_footer(exit_code, stderr_data),
                related_request_id=request_id,
            )
            return [TextContent(type="text", text="\n".join(output_lines))]

        try:
            result = ssh_client.execute(arguments["server"], cmd, use_sudo, timeout)
            return [TextContent(type="text", text=_format_result(cmd, explanation, result))]
        except TimeoutError:
            return [TextContent(type="text", text=f"{'━' * 50}\n🖥️  {cmd}\n⏱️  TIMEOUT after {timeout}s\n{'━' * 50}\nRetry with longer timeout (max: 300s)")]
    
    elif name == "read_file":
        content = ssh_client.read_file(arguments["server"], arguments["path"])
        return [TextContent(type="text", text=f"📄 {arguments['path']}\n```\n{content.rstrip()}\n```")]
    
    elif name == "write_file":
        ssh_client.write_file(arguments["server"], arguments["path"], arguments["content"])
        return [TextContent(type="text", text=f"✅ File written: {arguments['path']}")]
    
    elif name == "get_service_status":
        result = ssh_client.execute(arguments["server"], f"systemctl status {arguments['service']}")
        icon = "🟢" if result.exit_code == 0 else "🔴"
        return [TextContent(type="text", text=f"{icon} Service: {arguments['service']}\n```\n{result.stdout.rstrip()}\n```")]
    
    elif name == "manage_service":
        result = ssh_client.execute(
            arguments["server"],
            f"systemctl {arguments['action']} {arguments['service']}",
            use_sudo=True,
        )
        icon = "✅" if result.exit_code == 0 else "❌"
        return [TextContent(type="text", text=f"{icon} Service {arguments['service']} → {arguments['action']}")]
    
    raise ValueError(f"Unknown tool: {name}")


async def _async_main_stdio():
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def _async_main_http(host: str, port: int):
    global _use_streaming
    _use_streaming = True

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
