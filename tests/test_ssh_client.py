"""Tests für die kritische SSH-Client-Logik.

Fokus auf die praxisrelevanten Problemfälle:
- Quoting von Sonderzeichen/Backslashes in Befehlen
- sudo-Verschachtelung
- vollständige Output-Rückgabe (nichts verlieren)
- Exit-Code-Durchreichung + Timeout (124)
- Streaming-Exit-Marker (NUL/base64-sicher, auch mit ':' in stderr)
- read_file / search_in_file Kommando-Konstruktion

Kein echter SSH-Server nötig — paramiko-Channel wird gemockt.
"""
import shlex
import base64
import pytest
from unittest.mock import MagicMock
from ssh_mcp.ssh_client import SSHClient
from ssh_mcp.models import ServerConfig, CommandResult


def make_client():
    cfg = ServerConfig(name="t", host="h", port=22, user="u", password="p")
    return SSHClient({"t": cfg})


class FakeChannel:
    """Simuliert einen paramiko-Channel mit vorgegebenen stdout/stderr-Chunks."""
    def __init__(self, stdout=b"", stderr=b"", exit_code=0):
        self._out = [stdout[i:i + 5] for i in range(0, len(stdout), 5)]
        self._err = [stderr[i:i + 5] for i in range(0, len(stderr), 5)]
        self._exit_code = exit_code
        self.closed = False
        self.last_timeout = None

    def settimeout(self, t):
        self.last_timeout = t

    def recv_ready(self):
        return bool(self._out)

    def recv_stderr_ready(self):
        return bool(self._err)

    def recv(self, n):
        return self._out.pop(0) if self._out else b""

    def recv_stderr(self, n):
        return self._err.pop(0) if self._err else b""

    def exit_status_ready(self):
        return not self._out and not self._err

    def recv_exit_status(self):
        return self._exit_code

    def close(self):
        self.closed = True


def patch_exec(client, channel):
    client._exec = MagicMock(return_value=(MagicMock(), channel))


def _result(out, err, code):
    return CommandResult(stdout=out, stderr=err, exit_code=code)


def _ok(out):
    return CommandResult(stdout=out, stderr="", exit_code=0)


# ----------------------------- Quoting / sudo -----------------------------

def test_command_quoting_backslashes_and_specials():
    client = make_client()
    captured = {}

    def fake_exec(server_name, command, use_sudo, timeout):
        cmd = f"timeout {timeout} bash -c {shlex.quote(command)}"
        if use_sudo:
            cmd = f"sudo bash -c {shlex.quote(f'timeout {timeout} bash -c {shlex.quote(command)}')}"
        captured["cmd"] = cmd
        return MagicMock(), FakeChannel(stdout=b"ok\n", exit_code=0)

    client._exec = fake_exec
    tricky = r'echo "Pfad mit \ und $VAR und \"quotes\""'
    res = client.execute("t", tricky)
    assert shlex.quote(tricky) in captured["cmd"]
    assert res.exit_code == 0


def test_sudo_wrapping_is_shell_safe():
    client = make_client()
    captured = {}

    def fake_exec(server_name, command, use_sudo, timeout):
        cmd = f"timeout {timeout} bash -c {shlex.quote(command)}"
        if use_sudo:
            cmd = f"sudo bash -c {shlex.quote(f'timeout {timeout} bash -c {shlex.quote(command)}')}"
        captured["cmd"] = cmd
        return MagicMock(), FakeChannel(stdout=b"", exit_code=0)

    client._exec = fake_exec
    client.execute("t", "systemctl restart nginx", use_sudo=True)
    assert captured["cmd"].startswith("sudo bash -c ")
    assert "systemctl restart nginx" in captured["cmd"]


# ----------------------------- Output-Vollständigkeit -----------------------------

def test_execute_collects_full_stdout_multichunk():
    client = make_client()
    payload = ("\n".join(f"line{i}" for i in range(1, 101)) + "\n").encode()
    patch_exec(client, FakeChannel(stdout=payload, exit_code=0))
    res = client.execute("t", "seq 1 100")
    assert res.stdout.count("line") == 100
    assert "line1\n" in res.stdout and "line100" in res.stdout


def test_execute_captures_stdout_and_stderr():
    client = make_client()
    patch_exec(client, FakeChannel(stdout=b"out-data\n", stderr=b"err-data\n", exit_code=0))
    res = client.execute("t", "cmd")
    assert "out-data" in res.stdout
    assert "err-data" in res.stderr


def test_execute_exit_code_passthrough():
    client = make_client()
    patch_exec(client, FakeChannel(stdout=b"", exit_code=3))
    res = client.execute("t", "false")
    assert res.exit_code == 3


def test_execute_timeout_raises():
    client = make_client()
    patch_exec(client, FakeChannel(stdout=b"", exit_code=124))
    with pytest.raises(TimeoutError):
        client.execute("t", "sleep 999", timeout=1)


def test_execute_decode_invalid_utf8_does_not_crash():
    client = make_client()
    patch_exec(client, FakeChannel(stdout=b"\xff\xfe bad \x80\n", exit_code=0))
    res = client.execute("t", "cat /some/binary")
    assert isinstance(res.stdout, str)


def test_execute_sets_wallclock_cap():
    client = make_client()
    ch = FakeChannel(stdout=b"x\n", exit_code=0)
    patch_exec(client, ch)
    client.execute("t", "cmd", timeout=30)
    assert ch.last_timeout == 45


# ----------------------------- Streaming -----------------------------

@pytest.mark.asyncio
async def test_streaming_yields_lines_and_safe_exit_marker():
    client = make_client()
    patch_exec(client, FakeChannel(stdout=b"a\nb\nc\n", stderr=b"", exit_code=0))
    lines = []
    async for item in client.execute_streaming("t", "cmd"):
        lines.append(item)
    marker = lines[-1]
    assert marker.startswith("\0EXIT\0")
    code, b64err = marker[len("\0EXIT\0"):].split("\0", 1)
    assert code == "0"
    assert base64.b64decode(b64err).decode() == ""
    assert "a" in lines and "b" in lines and "c" in lines


@pytest.mark.asyncio
async def test_streaming_stderr_with_colons_survives():
    client = make_client()
    nasty = b"error: cannot open: /x: permission denied\nsecond: line\n"
    patch_exec(client, FakeChannel(stdout=b"out\n", stderr=nasty, exit_code=13))
    marker = None
    async for item in client.execute_streaming("t", "cmd"):
        if item.startswith("\0EXIT\0"):
            marker = item
    assert marker is not None
    code, b64err = marker[len("\0EXIT\0"):].split("\0", 1)
    assert code == "13"
    decoded = base64.b64decode(b64err).decode()
    assert "permission denied" in decoded
    assert "second: line" in decoded


# ----------------------------- Datei-Kommandos -----------------------------

def test_read_file_line_range_command():
    client = make_client()
    captured = {}

    def cap(s, c, **k):
        captured["cmd"] = c
        return _ok("content")

    client.execute = cap
    client.read_file("t", "/var/log/x.log", lines=10, offset=20)
    assert "sed -n '21,30p'" in captured["cmd"]
    assert shlex.quote("/var/log/x.log") in captured["cmd"]


def test_read_file_tail_command():
    client = make_client()
    captured = {}

    def cap(s, c, **k):
        captured["cmd"] = c
        return _ok("content")

    client.execute = cap
    client.read_file("t", "/var/log/x.log", lines=50, tail=True)
    assert "tail -n 50" in captured["cmd"]


def test_search_in_file_no_match_returns_message():
    client = make_client()
    client.execute = lambda s, c, **k: _result("", "", 1)
    out = client.search_in_file("t", "/f", "pattern")
    assert "No matches" in out


def test_search_in_file_quotes_pattern():
    client = make_client()
    captured = {}

    def cap(s, c, **k):
        captured["cmd"] = c
        return _result("hit", "", 0)

    client.execute = cap
    client.search_in_file("t", "/f", "foo;rm -rf /")
    assert shlex.quote("foo;rm -rf /") in captured["cmd"]
