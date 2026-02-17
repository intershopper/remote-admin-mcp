import pytest
from ssh_mcp.models import ServerConfig, CommandResult


def test_server_config():
    config = ServerConfig(
        name="test",
        host="localhost",
        port=22,
        user="testuser",
        password="testpass"
    )
    assert config.name == "test"
    assert config.host == "localhost"
    assert config.port == 22


def test_command_result():
    result = CommandResult(
        stdout="output",
        stderr="",
        exit_code=0
    )
    assert result.stdout == "output"
    assert result.exit_code == 0
