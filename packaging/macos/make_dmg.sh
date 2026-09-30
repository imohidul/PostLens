#!/usr/bin/env bash
# Wrap dist/PostLens.app in a drag-to-Applications disk image.
#   packaging/macos/make_dmg.sh 0.2.0
set -euo pipefail
VERSION="${1:?version required}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="$(mktemp -d)"
cp -R "$ROOT/dist/PostLens.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
OUT="$ROOT/dist/PostLens-${VERSION}-macOS-AppleSilicon.dmg"
rm -f "$OUT"
hdiutil create -volname "PostLens ${VERSION}" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
rm -rf "$STAGE"
echo "Created $OUT"
