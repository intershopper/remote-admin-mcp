import time
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
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=cfg.host, port=cfg.port,
            username=cfg.user, password=cfg.password,
            timeout=self.CONNECT_TIMEOUT,
            banner_timeout=self.CONNECT_TIMEOUT,
            auth_timeout=self.CONNECT_TIMEOUT,
        )
        self._pool[server_name] = (client, time.time())
        return client

    def _exec(self, server_name: str, command: str, use_sudo: bool, timeout: int):
        client = self._get_connection(server_name)
        cmd = f"timeout {timeout} bash -c {repr(command)}"
        if use_sudo:
            cmd = f"sudo -S bash -c {repr(f'timeout {timeout} bash -c {repr(command)}')}"
        channel = client.get_transport().open_session()
        channel.exec_command(cmd)
        if use_sudo:
            channel.sendall((self.servers[server_name].password + "\n").encode())
        return client, channel

    def _drain(self, channel) -> tuple[str, str]:
        out, err = [], []
        while channel.recv_ready():
            out.append(channel.recv(4096))
        while channel.recv_stderr_ready():
            err.append(channel.recv_stderr(4096))
        return b"".join(out).decode(), b"".join(err).decode()

    def execute(self, server_name: str, command: str, use_sudo: bool = False, timeout: int = 30) -> CommandResult:
        client, channel = self._exec(server_name, command, use_sudo, timeout)
        try:
            out, err = [], []
            while True:
                if channel.recv_ready():
                    out.append(channel.recv(4096))
                if channel.recv_stderr_ready():
                    err.append(channel.recv_stderr(4096))
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    break
            extra_out, extra_err = self._drain(channel)
            exit_code = channel.recv_exit_status()
            stdout_data = b"".join(out).decode() + extra_out
            stderr_data = b"".join(err).decode() + extra_err
            if exit_code == 124:
                raise TimeoutError(f"Command timed out after {timeout}s")
            return CommandResult(stdout=stdout_data, stderr=stderr_data, exit_code=exit_code)
        finally:
            channel.close()

    async def execute_streaming(self, server_name: str, command: str, use_sudo: bool = False, timeout: int = 30) -> AsyncIterator[str]:
        import asyncio
        client, channel = self._exec(server_name, command, use_sudo, timeout)
        try:
            buf, err_chunks = "", []
            while True:
                if channel.recv_stderr_ready():
                    err_chunks.append(channel.recv_stderr(4096))
                if channel.recv_ready():
                    chunk = await asyncio.get_event_loop().run_in_executor(None, channel.recv, 4096)
                    buf += chunk.decode()
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        yield line
                elif channel.exit_status_ready():
                    break
                else:
                    await asyncio.sleep(0.05)
            while channel.recv_ready():
                buf += channel.recv(4096).decode()
            while channel.recv_stderr_ready():
                err_chunks.append(channel.recv_stderr(4096))
            if buf.strip():
                yield buf.strip()
            exit_code = channel.recv_exit_status()
            yield f"\0EXIT:{exit_code}:{b''.join(err_chunks).decode()}"
        finally:
            channel.close()

    def read_file(self, server_name: str, path: str, lines: int | None = None, offset: int = 0, tail: bool = False) -> str:
        if lines and tail:
            cmd = f"tail -n {lines} {repr(path)}"
        elif lines:
            start = offset + 1
            end = offset + lines
            cmd = f"sed -n '{start},{end}p' {repr(path)}"
        else:
            cmd = f"cat {repr(path)}"
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
        result = self.execute(server_name, f"test -f {repr(path)} && grep -n -C{context_lines} -m{max_matches} -- {repr(pattern)} {repr(path)}")
        if result.exit_code == 1:
            return "No matches found."
        if result.exit_code != 0:
            raise RuntimeError(f"Search failed: {result.stderr}")
        return result.stdout

    def replace_in_file(self, server_name: str, path: str, old_text: str, new_text: str, count: int = 1, dry_run: bool = False) -> str:
        import hashlib, json
        # Write a helper Python script to the remote server to avoid shell escaping issues
        h = hashlib.md5(f"{path}{old_text}".encode()).hexdigest()[:8]
        tmp_script = f"/tmp/_mcp_replace_{h}.py"
        tmp_old = f"/tmp/_mcp_old_{h}.txt"
        tmp_new = f"/tmp/_mcp_new_{h}.txt"
        try:
            self.write_file(server_name, tmp_old, old_text)
            self.write_file(server_name, tmp_new, new_text)
            self.write_file(server_name, tmp_script, f"""import sys, difflib
path, count, dry_run = sys.argv[1], int(sys.argv[2]), sys.argv[3] == "1"
old = open("{tmp_old}").read()
new = open("{tmp_new}").read()
content = open(path).read()
if old not in content:
    print("ERROR: old_text not found in file", file=sys.stderr)
    sys.exit(1)
result = content.replace(old, new, count) if count > 0 else content.replace(old, new)
n = content.count(old) if count == 0 else min(count, content.count(old))
if dry_run:
    diff = difflib.unified_diff(content.splitlines(), result.splitlines(), lineterm="", fromfile="before", tofile="after", n=3)
    print("\\n".join(diff))
else:
    open(path, "w").write(result)
    print(f"OK: {{n}} replacement(s) applied")
""")
            result = self.execute(server_name, f"python3 {tmp_script} {repr(path)} {count} {'1' if dry_run else '0'}")
            if result.exit_code != 0:
                raise RuntimeError(result.stderr.strip())
            return result.stdout.strip()
        finally:
            self.execute(server_name, f"rm -f {tmp_script} {tmp_old} {tmp_new}")

    def get_file_structure(self, server_name: str, path: str, language: str | None = None) -> str:
        if not language:
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            lang_map = {"js": "js", "ts": "js", "tsx": "js", "jsx": "js", "mjs": "js", "py": "py", "go": "go", "rs": "rs", "java": "java", "sh": "sh"}
            language = lang_map.get(ext, "generic")
        patterns = {
            "js": r'^\s*(export\s+)?(async\s+)?function\s|^\s*(export\s+)?(const|let|var)\s+\w+\s*=\s*(async\s+)?\(|^\s*(export\s+)?class\s|^\s*(export\s+)?interface\s|^\s*(export\s+)?type\s|^\s*(export\s+)?enum\s',
            "py": r'^\s*(class |def |async def )',
            "go": r'^(func |type )',
            "rs": r'^\s*(pub\s+)?(fn |struct |enum |impl |trait |mod )',
            "java": r'^\s*(public|private|protected)?\s*(static\s+)?(class |interface |enum |.*\s+\w+\s*\()',
            "sh": r'^\s*(\w+\s*\(\)|function\s+\w+)',
            "generic": r'^\s*(function|class|def|async def|interface|type|struct|impl|pub fn|fn|enum|trait|mod)\s',
        }
        pat = patterns.get(language, patterns["generic"])
        result = self.execute(server_name, f"wc -l < {repr(path)} && grep -n -E {repr(pat)} {repr(path)}")
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
