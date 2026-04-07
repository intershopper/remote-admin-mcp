import os
import datetime

_log_path = os.path.join(os.path.expanduser("~"), ".ssh-mcp-audit.log")


def log(server: str, tool: str, detail: str, reason: str = "") -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    reason_str = f" — {reason}" if reason else ""
    line = f"[{ts}] [{server}] {tool}: {detail}{reason_str}\n"
    with open(_log_path, "a") as f:
        f.write(line)
