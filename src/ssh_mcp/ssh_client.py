import time
import shlex
import paramiko
from typing import AsyncIterator
from .models import ServerConfig, CommandResult


class SSHClient:
    CONNECT_TIMEOUT = 10
    POOL_TTL = 300  # reuse connections for 5 min

    def __init__(self, servers: dict[str, ServerConfig]):
        self.servers = servers
        self._pool: dict[str, tuple[paramiko.SSHClient, float]] = {}

    def _get_connection(self, server_name: str) -> paramiko.SSHClient:
        if server_name not in self.servers:
            raise ValueError(f"Unknown server: {server_name}")

        # Check pool
        if server_name in self._pool:
            client, ts = self._pool[server_name]
            if time.time() - ts < self.POOL_TTL:
                try:
                    transport = client.get_transport()
                    if transport and transport.is_active():
                        return client
                except Exception:
                    pass
            # Stale — close and remove
            try:
                client.close()
            except Exception:
                pass
            del self._pool[server_name]

        cfg = self.servers[server_name]
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.WarningPolicy())
        connect_kwargs = dict(
            hostname=cfg.host, port=cfg.port, username=cfg.user,
            timeout=self.CONNECT_TIMEOUT, banner_timeout=self.CONNECT_TIMEOUT,
            auth_timeout=self.CONNECT_TIMEOUT,
        )
        if cfg.key_file:
            connect_kwargs["key_filename"] = cfg.key_file
        if cfg.password:
            connect_kwargs["password"] = cfg.password
        client.connect(**connect_kwargs)
        self._pool[server_name] = (client, time.time())
        return client

    def _exec(self, server_name: str, command: str, use_sudo: bool, timeout: int):
        client = self._get_connection(server_name)
        cmd = f"timeout {timeout} bash -c {shlex.quote(command)}"
        if use_sudo:
            cmd = f"sudo bash -c {shlex.quote(f'timeout {timeout} bash -c {shlex.quote(command)}')}"
        channel = client.get_transport().open_session()
        channel.exec_command(cmd)
        return client, channel

    def execute(self, server_name: str, command: str, use_sudo: bool = False, timeout: int = 30) -> CommandResult:
        client, channel = self._exec(server_name, command, use_sudo, timeout)
        # Hard wall-clock cap so a hung channel can never block forever
        # (the remote `timeout` wrapper handles the normal case → exit 124).
        channel.settimeout(timeout + 15)
        try:
            out, err = [], []
            # Read until EOF. channel.recv returns b"" when the remote side
            # closed the stream, which only happens after the command exited,
            # so no output can be lost.
            while True:
                got = False
                if channel.recv_ready():
                    data = channel.recv(65536)
                    if data:
                        out.append(data)
                        got = True
                if channel.recv_stderr_ready():
                    data = channel.recv_stderr(65536)
                    if data:
                        err.append(data)
                        got = True
                if not got:
                    if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                        break
                    time.sleep(0.02)  # avoid busy-wait burning CPU
            exit_code = channel.recv_exit_status()
            stdout_data = b"".join(out).decode(errors="replace")
            stderr_data = b"".join(err).decode(errors="replace")
            if exit_code == 124:
                raise TimeoutError(f"Command timed out after {timeout}s")
            return CommandResult(stdout=stdout_data, stderr=stderr_data, exit_code=exit_code)
        finally:
            channel.close()

    async def execute_streaming(self, server_name: str, command: str, use_sudo: bool = False, timeout: int = 30) -> AsyncIterator[str]:
        import asyncio
        loop = asyncio.get_event_loop()
        client, channel = self._exec(server_name, command, use_sudo, timeout)
        channel.settimeout(timeout + 15)
        try:
            buf, err_chunks = "", []
            while True:
                got = False
                if channel.recv_stderr_ready():
                    err_chunks.append(channel.recv_stderr(65536))
                    got = True
                if channel.recv_ready():
                    chunk = await loop.run_in_executor(None, channel.recv, 65536)
                    if chunk:
                        buf += chunk.decode(errors="replace")
                        while "\n" in buf:
                            line, buf = buf.split("\n", 1)
                            yield line
                        got = True
                if not got:
                    if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                        break
                    await asyncio.sleep(0.03)
            # flush any remaining buffered stdout/stderr
            while channel.recv_ready():
                buf += channel.recv(65536).decode(errors="replace")
            while channel.recv_stderr_ready():
                err_chunks.append(channel.recv_stderr(65536))
            if buf.strip():
                yield buf.rstrip("\n")
            exit_code = channel.recv_exit_status()
            stderr_data = b"".join(err_chunks).decode(errors="replace")
            # Separator uses a NUL-delimited, length-safe encoding so stderr
            # containing ':' or newlines can never corrupt the exit marker.
            import base64
            yield "\0EXIT\0" + str(exit_code) + "\0" + base64.b64encode(stderr_data.encode()).decode()
        finally:
            channel.close()

    def read_file(self, server_name: str, path: str, lines: int | None = None, offset: int = 0, tail: bool = False) -> str:
        if lines and tail:
            cmd = f"tail -n {lines} {shlex.quote(path)}"
        elif lines:
            start = offset + 1
            end = offset + lines
            cmd = f"sed -n '{start},{end}p' {shlex.quote(path)}"
        else:
            cmd = f"cat {shlex.quote(path)}"
        result = self.execute(server_name, cmd)
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to read file: {result.stderr}")
        return result.stdout

    def write_file(self, server_name: str, path: str, content: str) -> None:
        client = self._get_connection(server_name)
        sftp = client.open_sftp()
        with sftp.file(path, 'w') as f:
            f.write(content)
        sftp.close()

    def upload_file(self, server_name: str, local_path: str, remote_path: str) -> None:
        client = self._get_connection(server_name)
        sftp = client.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()

    def download_file(self, server_name: str, remote_path: str, local_path: str) -> None:
        client = self._get_connection(server_name)
        sftp = client.open_sftp()
        sftp.get(remote_path, local_path)
        sftp.close()

    def search_in_file(self, server_name: str, path: str, pattern: str, context_lines: int = 3, max_matches: int = 20) -> str:
        result = self.execute(server_name, f"test -f {shlex.quote(path)} && grep -n -C{context_lines} -m{max_matches} -- {shlex.quote(pattern)} {shlex.quote(path)}")
        if result.exit_code == 1:
            return "No matches found."
        if result.exit_code != 0:
            raise RuntimeError(f"Search failed: {result.stderr}")
        return result.stdout

    def replace_in_file(self, server_name: str, path: str, old_text: str, new_text: str, count: int = 1, dry_run: bool = False) -> str:
        import base64
        b64_old = base64.b64encode(old_text.encode()).decode()
        b64_new = base64.b64encode(new_text.encode()).decode()
        script = f"""import sys, base64, difflib
path, count, dry_run = sys.argv[1], int(sys.argv[2]), sys.argv[3] == "1"
old = base64.b64decode("{b64_old}").decode()
new = base64.b64decode("{b64_new}").decode()
content = open(path).read()
if old not in content:
    print("ERROR: old_text not found in file", file=sys.stderr); sys.exit(1)
result = content.replace(old, new, count) if count > 0 else content.replace(old, new)
n = content.count(old) if count == 0 else min(count, content.count(old))
if dry_run:
    diff = difflib.unified_diff(content.splitlines(), result.splitlines(), lineterm="", fromfile="before", tofile="after", n=3)
    print("\\n".join(diff))
else:
    open(path, "w").write(result)
    print(f"OK: {{n}} replacement(s) applied")
"""
        import uuid
        tmp = f"/tmp/_mcp_replace_{uuid.uuid4().hex[:8]}.py"
        try:
            self.write_file(server_name, tmp, script)
            result = self.execute(server_name, f"python3 {tmp} {shlex.quote(path)} {count} {'1' if dry_run else '0'}")
            if result.exit_code != 0:
                raise RuntimeError(result.stderr.strip())
            return result.stdout.strip()
        finally:
            self.execute(server_name, f"rm -f {tmp}")

    def get_file_structure(self, server_name: str, path: str, language: str | None = None) -> str:
        if not language:
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            lang_map = {"js": "js", "ts": "js", "tsx": "js", "jsx": "js", "mjs": "js", "py": "py", "go": "go", "rs": "rs", "java": "java", "sh": "sh", "bash": "sh", "zsh": "sh", "c": "c", "h": "c", "cpp": "c", "hpp": "c", "cc": "c", "rb": "rb", "php": "php"}
            language = lang_map.get(ext, "generic")
        patterns = {
            "js": r'^\s*(export\s+)?(async\s+)?function\s|^\s*(export\s+)?(const|let|var)\s+\w+\s*=\s*(async\s+)?\(|^\s*(export\s+)?class\s|^\s*(export\s+)?interface\s|^\s*(export\s+)?type\s|^\s*(export\s+)?enum\s',
            "py": r'^\s*(class |def |async def )',
            "go": r'^(func |type )',
            "rs": r'^\s*(pub\s+)?(fn |struct |enum |impl |trait |mod )',
            "java": r'^\s*(public|private|protected)?\s*(static\s+)?(class |interface |enum |.*\s+\w+\s*\()',
            "sh": r'^\s*(\w+\s*\(\)|function\s+\w+)',
            "c": r'^\s*(static\s+)?(inline\s+)?(void|int|char|float|double|long|unsigned|struct|enum|typedef|#define)\s|^\w+.*\w+\s*\(',
            "rb": r'^\s*(class |module |def )',
            "php": r'^\s*(public|private|protected|static)?\s*(function |class |interface |trait )',
            "generic": r'^\s*(function|class|def|async def|interface|type|struct|impl|pub fn|fn|enum|trait|mod)\s',
        }
        pat = patterns.get(language, patterns["generic"])
        result = self.execute(server_name, f"wc -l < {shlex.quote(path)} && grep -n -E {shlex.quote(pat)} {shlex.quote(path)}")
        if result.exit_code != 0:
            raise RuntimeError(f"Failed: {result.stderr}")
        lines = result.stdout.strip().split("\n")
        total = lines[0].strip()
        symbols = "\n".join(lines[1:]) if len(lines) > 1 else "(no symbols found)"
        return f"({total} lines)\n{symbols}"

    def close_all(self):
        for name, (client, _) in self._pool.items():
            try:
                client.close()
            except Exception:
                pass
        self._pool.clear()
