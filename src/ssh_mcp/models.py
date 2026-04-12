from dataclasses import dataclass


@dataclass
class ServerConfig:
    name: str
    host: str
    port: int
    user: str
    password: str = ""
    key_file: str = ""


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int
