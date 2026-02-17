import paramiko
import uuid
from typing import AsyncIterator
from .models import ServerConfig, CommandResult


class SSHClient:
    def __init__(self, servers: dict[str, ServerConfig]):
        self.servers = servers

    def _get_connection(self, server_name: str) -> paramiko.SSHClient:
        if server_name not in self.servers:
            raise ValueError(f"Unknown server: {server_name}")
        config = self.servers[server_name]
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=config.host, port=config.port,
            username=config.user, password=config.password,
        )
        return client

    def _prepare_and_exec(self, server_name: str, command: str, use_sudo: bool, timeout: int):
        """Prepare script, exec command, return (client, stdin, stdout, stderr)."""
        script_path = f"/tmp/mcp_{uuid.uuid4().hex}.sh"
        client = self._get_connection(server_name)
        sftp = client.open_sftp()
        with sftp.file(script_path, "w") as f:
            f.write(f"#!/bin/bash\n{command}\n")
        sftp.close()

        wrapper = f"chmod +x {script_path} && timeout {timeout} {script_path}; EXIT=$?; rm -f {script_path}; exit $EXIT"
        if use_sudo:
            wrapper = f"sudo -S bash -c {repr(wrapper)}"

        stdin, stdout, stderr = client.exec_command(wrapper)
        if use_sudo:
            stdin.write(self.servers[server_name].password + "\n")
            stdin.flush()

        return client, stdin, stdout, stderr

    def execute(self, server_name: str, command: str, use_sudo: bool = False, timeout: int = 30) -> CommandResult:
        client, stdin, stdout, stderr = self._prepare_and_exec(server_name, command, use_sudo, timeout)
        try:
            exit_code = stdout.channel.recv_exit_status()
            stdout_data = stdout.read().decode()
            stderr_data = stderr.read().decode()
            if exit_code == 124:
                raise TimeoutError(f"Command timed out after {timeout}s")
            return CommandResult(stdout=stdout_data, stderr=stderr_data, exit_code=exit_code)
        finally:
            client.close()

    async def execute_streaming(self, server_name: str, command: str, use_sudo: bool = False, timeout: int = 30) -> AsyncIterator[str]:
        """Execute command and yield stdout lines as they arrive. Last yield is '\\0EXIT:<code>:<stderr>'."""
        import asyncio
        client, stdin, stdout, stderr = self._prepare_and_exec(server_name, command, use_sudo, timeout)
        loop = asyncio.get_event_loop()
        channel = stdout.channel
        try:
            buf = ""
            while not channel.exit_status_ready() or channel.recv_ready():
                if channel.recv_ready():
                    chunk = await loop.run_in_executor(None, channel.recv, 4096)
                    buf += chunk.decode()
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        yield line
                else:
                    await asyncio.sleep(0.05)
            remaining = buf + (await loop.run_in_executor(None, stdout.read)).decode()
            if remaining.strip():
                yield remaining.strip()
            exit_code = channel.recv_exit_status()
            stderr_data = (await loop.run_in_executor(None, stderr.read)).decode()
            yield f"\0EXIT:{exit_code}:{stderr_data}"
        finally:
            client.close()
    
    def read_file(self, server_name: str, path: str) -> str:
        """Read file from remote server."""
        result = self.execute(server_name, f"cat {path}")
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to read file: {result.stderr}")
        return result.stdout
    
    def write_file(self, server_name: str, path: str, content: str) -> None:
        """Write file to remote server."""
        client = self._get_connection(server_name)
        try:
            sftp = client.open_sftp()
            with sftp.file(path, 'w') as f:
                f.write(content)
            sftp.close()
        finally:
            client.close()
