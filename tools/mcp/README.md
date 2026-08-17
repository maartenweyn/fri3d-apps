# Badge MCP server

Gives an agent direct access to the badge over USB, so it can install, run and
debug without a human relaying terminal output.

The server runs on the Mac, because that is the machine with the serial port.
Claude sessions running in the cloud reach it through the desktop app's bridge.

## Install

    ./tools/mcp/setup.sh

That creates `tools/mcp/.venv` with `mcp` and `mpremote` in it, and prints the
JSON block to add to the Claude desktop app's MCP config
(`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS).
Merge the `fri3d-badge` entry into any existing `mcpServers` object, then quit
the Claude app fully and reopen it.

## Check it works

    ./tools/mcp/.venv/bin/python tools/mcp/badge_mcp.py

It should start and wait on stdin without printing an error. Ctrl-C to stop.

## Tools it exposes

| tool | what it does |
| --- | --- |
| `badge_ports` | list the serial ports mpremote sees |
| `badge_exec` | run MicroPython source on the badge, return its output |
| `badge_run_file` | run a .py file from this repo on the badge |
| `badge_ls` | list a directory on the badge |
| `badge_read` | read a text file off the badge |
| `badge_install` | copy an app folder to /apps and refresh the launcher |
| `badge_uninstall` | remove one app |
| `badge_wipe` | remove every user-installed app |
| `badge_refresh` | rescan /apps |
| `badge_start_app` | launch an app |
| `badge_reset` | reboot the badge |
| `badge_diag` | full load diagnosis with tracebacks |

## Caveats

- A serial port takes one client at a time. Close the Fri3d-IDE tab and any
  open REPL first, or every call fails with a busy port.
- The badge has to be plugged in with a cable that carries data.
- The tools refuse paths outside this repository.
- There is no `badge_repl`: an interactive REPL is not something a tool call
  can hold open. Use `badge_exec` instead.
