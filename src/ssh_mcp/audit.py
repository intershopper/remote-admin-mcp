import os
import datetime

_log_path = os.path.join(os.path.expanduser("~"), ".ssh-mcp-audit.log")


def log(server: str, tool: str, detail: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{server}] {tool}: {detail}\n"
    with open(_log_path, "a") as f:
        f.write(line)
