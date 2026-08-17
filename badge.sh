#!/usr/bin/env bash
# Helper around mpremote for the Fri3d badge.
#
#   ./badge.sh probe            report hardware, screen size, LEDs, audio
#   ./badge.sh list             list installed apps
#   ./badge.sh wipe             remove ALL user-installed apps from /apps
#   ./badge.sh apps             list the app folders in this repo
#   ./badge.sh install [app..]  copy app folders to /apps (default: all of them)
#   ./badge.sh reinstall [app..] remove those apps, then install them again
#   ./badge.sh uninstall <app>  remove one app from /apps
#   ./badge.sh diag [app..]     why will it not load: files, manifest, imports, traceback
#   ./badge.sh mpk [app..]      build distributable .mpk files into dist/
#   ./badge.sh refresh          rescan /apps so new apps show in the launcher
#   ./badge.sh reset            reboot the badge
#   ./badge.sh run <file.py>    run a local python file on the badge, print output
#   ./badge.sh repl             open the MicroPython REPL (ctrl-] to quit)
#
# Override the mpremote command with MPREMOTE=... if it is not on your PATH.

set -euo pipefail

cd "$(dirname "$0")"

MPR="${MPREMOTE:-mpremote}"

# An app is a folder with a MANIFEST.JSON in it. Deliberately no default app:
# a bare `install` used to mean one particular app, which quietly did nothing
# for whatever you were actually working on.
app_dirs() {
  local manifest
  for manifest in */MANIFEST.JSON; do
    [ -f "$manifest" ] || continue
    dirname "$manifest"
  done
}

# App ids never contain spaces, so word splitting is safe here.
default_to_all_apps() {
  if [ "$#" -gt 0 ]; then
    printf '%s\n' "$@"
  else
    app_dirs
  fi
}

check_app() {
  local app="$1"
  [ -d "$app" ] || { echo "no such app folder: $app" >&2; return 1; }
  [ -f "$app/MANIFEST.JSON" ] && return 0
  echo "$app has no MANIFEST.JSON, so it is not an app" >&2
  return 1
}

# __pycache__ is how a desktop test run leaks bytecode into an app folder, and
# a stale .pyc on the badge shadows the .py next to it. Refuse rather than ship
# it.
check_clean() {
  local app="$1" junk
  junk="$(find "$app" -name '__pycache__' -o -name '*.pyc' 2>/dev/null | head -3)"
  [ -z "$junk" ] && return 0
  echo "$app contains build leftovers, remove them first:" >&2
  echo "$junk" >&2
  return 1
}

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

refresh_launcher() {
  # Rebuild the app list so the launcher picks up what we just copied.
  # If that does not take, reboot: app discovery also runs at boot.
  "$MPR" exec "
from mpos import AppManager
AppManager.refresh_apps()
print('launcher sees:', sorted(a.fullname for a in AppManager.get_app_list()))
" || echo "refresh failed; try: ./badge.sh reset"
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
  apps)
    app_dirs
    ;;
  install)
    apps="$(default_to_all_apps "$@")"
    [ -n "$apps" ] || { echo "no apps in this repo" >&2; exit 1; }
    for app in $apps; do check_app "$app" && check_clean "$app" || exit 1; done
    "$MPR" mkdir :/apps 2>/dev/null || true
    for app in $apps; do
      "$MPR" fs cp -r "$app" :/apps/
      echo "installed $app"
    done
    refresh_launcher
    ;;
  reinstall)
    apps="$(default_to_all_apps "$@")"
    [ -n "$apps" ] || { echo "no apps in this repo" >&2; exit 1; }
    for app in $apps; do check_app "$app" && check_clean "$app" || exit 1; done
    "$MPR" mkdir :/apps 2>/dev/null || true
    for app in $apps; do
      remote_rm_app "$app"
      "$MPR" fs cp -r "$app" :/apps/
      echo "reinstalled $app"
    done
    refresh_launcher
    ;;
  uninstall)
    app="${1:?usage: ./badge.sh uninstall <app-id>}"
    remote_rm_app "$app"
    ;;
  diag)
    apps="$(default_to_all_apps "$@")"
    for app in $apps; do
      echo "=== $app ==="
      "$MPR" exec "APP_ID='$app'" run tools/diag.py
    done
    ;;
  mpk)
    apps="$(default_to_all_apps "$@")"
    for app in $apps; do ./tools/pack_mpk.sh "$app"; done
    ;;
  refresh)
    refresh_launcher
    ;;
  reset)
    "$MPR" reset
    echo "badge rebooting"
    ;;
  run)
    file="${1:?usage: ./badge.sh run <file.py>}"
    "$MPR" run "$file"
    ;;
  repl)
    "$MPR" repl
    ;;
  *)
    sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
    ;;
esac
