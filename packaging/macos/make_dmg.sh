#!/usr/bin/env bash
# Wrap dist/PostLens.app in a drag-to-Applications disk image.
#   bash packaging/macos/make_dmg.sh 1.0.1
set -euo pipefail
VERSION="${1:?version required}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="$(mktemp -d)"
cp -R "$ROOT/dist/PostLens.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
OUT="$ROOT/dist/postlens.dmg"
rm -f "$OUT"
# hdiutil on GitHub's macOS runners sometimes fails with "Resource busy"
# for no reason of ours, so retry a few times before giving up.
for attempt in 1 2 3 4 5; do
  if hdiutil create -volname "PostLens ${VERSION}" -srcfolder "$STAGE" -ov -format UDZO "$OUT"; then
    break
  fi
  if [ "$attempt" = 5 ]; then echo "hdiutil failed 5 times" >&2; exit 1; fi
  echo "hdiutil failed (attempt $attempt), retrying in 10s..." >&2
  sleep 10
done
rm -rf "$STAGE"
echo "Created $OUT"
