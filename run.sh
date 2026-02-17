#!/bin/bash
set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "uv not found, installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Ensure dependencies are installed
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
fi

# Install/update dependencies
uv pip install -e . --quiet

# Run the server in HTTP SSE mode
exec uv run ssh_mcp_server --transport http --host 0.0.0.0 --port 8080 "$@"
