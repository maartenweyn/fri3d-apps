#!/usr/bin/env bash
# Publish every app in this repository to your own app store.
#
#   ./tools/publish.sh
#
# Builds a .mpk per app, copies it and its icon into the store folder, and
# writes the app_index.json that the badges poll. Default target is the www
# folder of the Home Assistant configuration next to this repository, because
# Home Assistant serves config/www at /local/ without a login, which is exactly
# enough for a handful of packages on your own network.
#
#   APPSTORE_DIR   where to write        (default ../homeassistant_config/www/appstore)
#   BASE_URL       how badges reach it   (default http://192.168.68.100:8123/local/appstore)
#   RELATIVE=1     write relative URLs instead of BASE_URL ones. tech.weyn.updates
#                  resolves those against the index; the built-in AppStore does not.
#
# Deliberately no app argument: the index describes the whole store, so
# publishing one app would have to either drop the others from the index or
# point at packages that were never copied. Everything, every time.
#
# The index is the same format as https://apps.micropythonos.com/app_index.json,
# so the built-in AppStore can browse this store too: set its `backend`
# preference to "github,<BASE_URL>/app_index.json".
set -euo pipefail

cd "$(dirname "$0")/.."
REPO="$(pwd)"

APPSTORE_DIR="${APPSTORE_DIR:-$REPO/../homeassistant_config/www/appstore}"
BASE_URL="${BASE_URL:-http://192.168.68.100:8123/local/appstore}"
RELATIVE="${RELATIVE:-}"

# App ids never contain spaces, so word splitting is safe here.
app_dirs() {
  local manifest
  for manifest in */MANIFEST.JSON; do
    [ -f "$manifest" ] || continue
    dirname "$manifest"
  done
}

APPS="$(app_dirs)"
[ -n "$APPS" ] || { echo "no apps in this repo" >&2; exit 1; }

mkdir -p "$APPSTORE_DIR/mpks" "$APPSTORE_DIR/icons"

# A mounted filesystem may refuse to unlink, which is what cp does to an
# existing file. Redirecting truncates in place and works everywhere.
copy_over() { cat "$1" > "$2"; }

STALE=""
for app in $APPS; do
  version="$(python3 -c "import json;print(json.load(open('$app/MANIFEST.JSON'))['version'])")"

  ./tools/pack_mpk.sh "$app" >/dev/null
  built="$REPO/dist/${app}_${version}.mpk"
  target="$APPSTORE_DIR/mpks/${app}_${version}.mpk"

  # The one mistake that makes all of this silently do nothing: changing an app
  # without changing its version. The badges compare versions and nothing else,
  # so they would never see it. Same name, different bytes: say so, loudly.
  if [ -f "$target" ] && ! cmp -s "$built" "$target"; then
    echo "!! $app $version is already published with different contents." >&2
    echo "!! Bump the version in $app/MANIFEST.JSON, or no badge will update." >&2
    STALE="$STALE $app"
  fi

  copy_over "$built" "$target"
  if [ -f "$app/icon_64x64.png" ]; then
    copy_over "$app/icon_64x64.png" \
              "$APPSTORE_DIR/icons/${app}_${version}_64x64.png"
  fi
  echo "published $app $version"
done

python3 - "$APPSTORE_DIR" "$BASE_URL" "$RELATIVE" $APPS <<'PY'
"""Write app_index.json: every MANIFEST.JSON plus where to get the package."""
import json
import os
import sys

store, base = sys.argv[1], sys.argv[2].rstrip("/")
relative = sys.argv[3] not in ("", "0", "no", "false")
apps = sys.argv[4:]

index = []
for app in sorted(apps):
    with open(os.path.join(app, "MANIFEST.JSON")) as fh:
        manifest = json.load(fh)
    if manifest.get("fullname") != app:
        sys.exit("%s: fullname is %r but the folder is %r"
                 % (app, manifest.get("fullname"), app))
    version = manifest["version"]

    mpk = "mpks/%s_%s.mpk" % (app, version)
    icon = "icons/%s_%s_64x64.png" % (app, version)
    entry = dict(manifest)
    # The built-in AppStore groups on a single "category" string; MANIFEST.JSON
    # carries a list. Send both so either reader is happy.
    categories = manifest.get("categories") or []
    if categories and "category" not in entry:
        entry["category"] = categories[0]
    entry["download_url"] = mpk if relative else base + "/" + mpk
    entry["download_url_size"] = os.path.getsize(os.path.join(store, mpk))
    if os.path.exists(os.path.join(store, icon)):
        entry["icon_url"] = icon if relative else base + "/" + icon
    index.append(entry)

path = os.path.join(store, "app_index.json")
# Truncate rather than replace: a mounted filesystem may refuse to unlink.
with open(path, "w") as fh:
    json.dump(index, fh, indent=2, sort_keys=True)
    fh.write("\n")
print("wrote %s with %d app%s"
      % (path, len(index), "" if len(index) == 1 else "s"))

# Old versions are not removed: a badge that was switched off for a month may
# still ask for one, and the mount this often runs over cannot unlink anyway.
# Name them, so the folder does not grow unnoticed.
current = set()
for entry in index:
    current.add("%s_%s.mpk" % (entry["fullname"], entry["version"]))
old = sorted(name for name in os.listdir(os.path.join(store, "mpks"))
             if name.endswith(".mpk") and name not in current)
if old:
    print("older packages still in mpks/ (harmless, remove when you like):")
    for name in old:
        print("   ", name)
PY

if [ -n "$STALE" ]; then
  echo
  echo "published, but these kept their version number:$STALE" >&2
  exit 2
fi
