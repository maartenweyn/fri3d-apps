#!/usr/bin/env bash
# Helper around mpremote for the Fri3d badge.
#
#   ./badge.sh probe            report hardware, screen size, LEDs, audio
#   ./badge.sh list             list installed apps
#   ./badge.sh wipe             remove ALL user-installed apps from /apps
#   ./badge.sh install [app]    copy an app folder to /apps (default: be.fri3d.pomodoro)
#   ./badge.sh reinstall [app]  remove that app from /apps, then install it
#   ./badge.sh uninstall <app>  remove one app from /apps
#   ./badge.sh run <file.py>    run a local python file on the badge, print output
#   ./badge.sh repl             open the MicroPython REPL (ctrl-] to quit)
#
# Override the mpremote command with MPREMOTE=... if it is not on your PATH.

set -euo pipefail

cd "$(dirname "$0")"

MPR="${MPREMOTE:-mpremote}"
DEFAULT_APP="be.fri3d.pomodoro"

if ! command -v "$MPR" >/dev/null 2>&1; then
  cat >&2 <<'MSG'
mpremote not found.

Install it with:
    pipx install mpremote        # or: pip3 install --user mpremote

Then re-run this script, or point at it explicitly:
    MPREMOTE=/path/to/mpremote ./badge.sh probe
MSG
  exit 1
fi

remote_rm_app() {
  local app="$1"
  "$MPR" exec "
import os
def rmtree(p):
    try:
        mode = os.stat(p)[0]
    except OSError:
        print('not installed:', p); return
    if mode & 0x4000:
        for e in os.listdir(p):
            rmtree(p + '/' + e)
        os.rmdir(p)
    else:
        os.remove(p)
rmtree('/apps/${app}')
print('removed /apps/${app}')
"
}

cmd="${1:-help}"
shift || true

case "$cmd" in
  probe)
    "$MPR" run tools/probe.py
    ;;
  wipe)
    "$MPR" run tools/wipe_apps.py
    ;;
  list)
    "$MPR" exec "
import os
for d in ('/apps', '/builtin/apps'):
    try:
        print(d + ':', sorted(os.listdir(d)))
    except OSError:
        print(d + ': <missing>')
"
    ;;
  install)
    app="${1:-$DEFAULT_APP}"
    [ -d "$app" ] || { echo "no such app folder: $app" >&2; exit 1; }
    "$MPR" mkdir :/apps 2>/dev/null || true
    "$MPR" fs cp -r "$app" :/apps/
    echo "installed $app"
    ;;
  reinstall)
    app="${1:-$DEFAULT_APP}"
    [ -d "$app" ] || { echo "no such app folder: $app" >&2; exit 1; }
    remote_rm_app "$app"
    "$MPR" mkdir :/apps 2>/dev/null || true
    "$MPR" fs cp -r "$app" :/apps/
    echo "reinstalled $app"
    ;;
  uninstall)
    app="${1:?usage: ./badge.sh uninstall <app-id>}"
    remote_rm_app "$app"
    ;;
  run)
    file="${1:?usage: ./badge.sh run <file.py>}"
    "$MPR" run "$file"
    ;;
  repl)
    "$MPR" repl
    ;;
  *)
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
    ;;
esac
