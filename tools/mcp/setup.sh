#!/usr/bin/env bash
# Create a self-contained virtualenv for the badge MCP server and print the
# JSON block to paste into the Claude desktop app's MCP config.
set -euo pipefail

cd "$(dirname "$0")"
HERE="$(pwd)"
REPO="$(cd ../.. && pwd)"

python3 -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet "mcp[cli]" mpremote

echo
echo "Installed:"
./.venv/bin/pip list 2>/dev/null | grep -Ei '^(mcp|mpremote) ' || true

echo
echo "Add this to the Claude desktop app's MCP config:"
echo
cat <<JSON
{
  "mcpServers": {
    "fri3d-badge": {
      "command": "$HERE/.venv/bin/python",
      "args": ["$HERE/badge_mcp.py"],
      "env": {
        "FRI3D_REPO": "$REPO",
        "MPREMOTE": "$HERE/.venv/bin/mpremote"
      }
    }
  }
}
JSON
echo
echo "On macOS the file is:"
echo "  ~/Library/Application Support/Claude/claude_desktop_config.json"
echo "Merge the \"fri3d-badge\" entry into any existing \"mcpServers\" object,"
echo "then quit the Claude app completely and reopen it."
