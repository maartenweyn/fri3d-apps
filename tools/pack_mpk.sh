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
APP="${1:-be.fri3d.pomodoro}"
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

mkdir -p "$OUT_DIR"
TARGET="$OUT_DIR/${APP}_${VERSION}.mpk"

# zip builds through a temporary file and then renames, which some mounted
# filesystems refuse, so assemble it outside the repository and copy it in.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
BUILT="$STAGE/${APP}_${VERSION}.mpk"

find "$APP" -exec touch -t 202601010000.00 {} \;
{ find "$APP" -type d; find "$APP" -type f; } | sort \
  | TZ=UTC zip -q -X -r -0 "$BUILT" -@

cp "$BUILT" "$TARGET"
echo "built $TARGET"
unzip -l "$TARGET"
