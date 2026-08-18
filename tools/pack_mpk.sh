#!/usr/bin/env bash
# Build a deterministic .mpk for an app, ready to install through the
# Fri3d-IDE ("Install MPK") or to publish on BadgeHub.
#
#   ./tools/pack_mpk.sh [app-id]
#
# An .mpk is a ZIP whose first and only top-level entry is a directory named
# exactly after the app's fullname. Entries are stored uncompressed so the
# badge can stream them onto flash, and timestamps are fixed so the archive
# only changes when its contents do.
set -euo pipefail

cd "$(dirname "$0")/.."
REPO="$(pwd)"
APP="${1:?usage: ./tools/pack_mpk.sh <app-id>}"
OUT_DIR="$REPO/dist"

[ -d "$APP" ] || { echo "no such app folder: $APP" >&2; exit 1; }
[ -f "$APP/MANIFEST.JSON" ] || { echo "$APP has no MANIFEST.JSON" >&2; exit 1; }

command -v zip >/dev/null || { echo "zip is not installed" >&2; exit 1; }

VERSION=$(python3 -c "
import json, sys
m = json.load(open('$APP/MANIFEST.JSON'))
if m.get('fullname') != '$APP':
    sys.exit('MANIFEST.JSON fullname is %r but the folder is %r'
             % (m.get('fullname'), '$APP'))
print(m['version'])
")

if find "$APP" -name '__pycache__' -o -name '.DS_Store' | grep -q .; then
  echo "refusing to package: $APP contains __pycache__ or .DS_Store" >&2
  find "$APP" -name '__pycache__' -o -name '.DS_Store' >&2
  exit 1
fi

# A file that is too sensitive for the repository is too sensitive for a package
# you hand to someone or publish on BadgeHub. Berichtjes' messages_config.py
# holds the MQTT password, and it went straight into the .mpk until this check
# existed. git decides: whatever it ignores stays out.
EXCLUDED=""
while IFS= read -r candidate; do
  if git -C "$REPO" check-ignore -q "$candidate" 2>/dev/null; then
    EXCLUDED="$EXCLUDED $candidate"
  fi
done <<EOF
$(find "$APP" -type f)
EOF
if [ -n "$EXCLUDED" ]; then
  echo "leaving out, because git ignores it:" >&2
  for f in $EXCLUDED; do echo "  $f" >&2; done
fi

keep() {
  local path="$1" skip
  for skip in $EXCLUDED; do
    [ "$path" = "$skip" ] && return 1
  done
  return 0
}

mkdir -p "$OUT_DIR"
TARGET="$OUT_DIR/${APP}_${VERSION}.mpk"

# zip builds through a temporary file and then renames, which some mounted
# filesystems refuse, so assemble it outside the repository and copy it in.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
BUILT="$STAGE/${APP}_${VERSION}.mpk"

find "$APP" -exec touch -t 202601010000.00 {} \;
{ find "$APP" -type d; find "$APP" -type f; } | sort | while IFS= read -r entry; do
  keep "$entry" && printf '%s\n' "$entry"
done | TZ=UTC zip -q -X -0 "$BUILT" -@
# No -r: the list already names every directory and every file, and -r would
# recurse back into the directory entry and re-add the files just excluded.

cp "$BUILT" "$TARGET"
echo "built $TARGET"
unzip -l "$TARGET"
