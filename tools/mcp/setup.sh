#!/usr/bin/env bash
# Build a virtualenv for the badge MCP server and register it with the Claude
# desktop app.
#
#   ./tools/mcp/setup.sh            build the venv, then patch the config
#   ./tools/mcp/setup.sh --print    build the venv, only print the JSON
set -euo pipefail

cd "$(dirname "$0")"
HERE="$(pwd)"
REPO="$(cd ../.. && pwd)"
CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"

echo "Building the virtualenv..."
python3 -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet "mcp[cli]" mpremote
./.venv/bin/pip list 2>/dev/null | grep -Ei '^(mcp|mpremote) ' || true

echo
echo "Checking the server starts..."
if ./.venv/bin/python -c "import badge_mcp" 2>/dev/null; then
  echo "  imports cleanly"
else
  ./.venv/bin/python -c "import badge_mcp" || {
    echo "  the server does not import; fix that before registering it" >&2
    exit 1
  }
fi

BLOCK=$(cat <<JSON
    "fri3d-badge": {
      "command": "$HERE/.venv/bin/python",
      "args": ["$HERE/badge_mcp.py"],
      "env": {
        "FRI3D_REPO": "$REPO",
        "MPREMOTE": "$HERE/.venv/bin/mpremote"
      }
    }
JSON
)

if [ "${1:-}" = "--print" ]; then
  echo
  echo "Add this to $CONFIG:"
  echo
  printf '{\n  "mcpServers": {\n%s\n  }\n}\n' "$BLOCK"
  exit 0
fi

echo
echo "Registering with the Claude desktop app..."
CONFIG="$CONFIG" HERE="$HERE" REPO="$REPO" ./.venv/bin/python - <<'PY'
import json
import os
import shutil
from pathlib import Path

config = Path(os.environ["CONFIG"])
here = os.environ["HERE"]
repo = os.environ["REPO"]

config.parent.mkdir(parents=True, exist_ok=True)

if config.exists() and config.read_text().strip():
    backup = config.with_suffix(".json.bak")
    shutil.copy2(config, backup)
    try:
        data = json.loads(config.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(
            "%s is not valid JSON (%s).\n"
            "Fix or move it aside, then run this script again.\n"
            "A copy is at %s" % (config, exc, backup))
    print("  existing config backed up to", backup)
    print("  top-level keys before:", sorted(data) or "<none>")
else:
    data = {}
    print("  no config yet, creating one")

if not isinstance(data, dict):
    raise SystemExit("%s does not contain a JSON object" % config)

servers = data.setdefault("mcpServers", {})
if not isinstance(servers, dict):
    raise SystemExit('"mcpServers" exists but is not an object; fix it by hand')

replacing = "fri3d-badge" in servers
servers["fri3d-badge"] = {
    "command": here + "/.venv/bin/python",
    "args": [here + "/badge_mcp.py"],
    "env": {"FRI3D_REPO": repo, "MPREMOTE": here + "/.venv/bin/mpremote"},
}

config.write_text(json.dumps(data, indent=2) + "\n")
print("  %s fri3d-badge" % ("replaced" if replacing else "added"))
print("  servers now configured:", sorted(servers))
PY

echo
echo "Done. Quit the Claude app completely (Cmd-Q, not just the window) and reopen it."
echo "Config: $CONFIG"
