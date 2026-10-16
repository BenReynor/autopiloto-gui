#!/usr/bin/env bash
# build_macos.sh — packages Dédalo for macOS.
#
# Outputs (in packaging/out/):
#   Dedalo.app                       bundle with icono.icns
#   dedalo-<v>-macos-<arch>.dmg  mount in /Applications
#
# Usage:
#   bash packaging/build_macos.sh
#
# Optional signing and notarization (empty variables skip them):
#   APPLE_CERT_P12 (base64) + APPLE_CERT_PASSWORD
#       imports the Developer ID certificate into a disposable keychain
#   APPLE_SIGN_IDENTITY
#       signs the .app (hardened runtime) and the .dmg with codesign
#   APPLE_ID + APPLE_TEAM_ID + APPLE_APP_PASSWORD
#       notarizes with notarytool --wait and staples the .dmg (stapler)
#
# Without any secret it only generates the unsigned .dmg: useful for testing
# the pipeline. Requires macOS with Xcode Command Line Tools (hdiutil, codesign,
# notarytool, security) and python with the project + PyInstaller.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

PY="${PYTHON:-python3}"
VERSION="$("$PY" - <<'EOF'
import tomllib
from pathlib import Path
with open(Path("pyproject.toml"), "rb") as f:
    print(tomllib.load(f)["project"]["version"])
EOF
)"

OUT="$RAIZ/packaging/out"
NOMBRE="dedalo"
ARCH="$(uname -m)"        # arm64 | x86_64
APP="$OUT/Dedalo.app"

echo "==> PyInstaller v$VERSION"
rm -rf "$OUT" build
"$PY" -m PyInstaller \
    --clean --noconfirm --distpath "$OUT" --workpath "$OUT/build" \
    packaging/"$NOMBRE".spec
[ -d "$APP" ] || { echo "el bundle no salió en $APP" >&2; exit 1; }

# The desktop umask (0002) leaves everything group-writable: dirs at 755 and
# files without the write bit, before signing (sign AFTER, not the other way).
find "$APP" -type d -exec chmod 755 {} +
find "$APP" -type f -exec chmod go-w {} +

# ── Smoke test: starts and still alive at 6 s ────────────────────────────────
echo "==> smoke test"
QT_QPA_PLATFORM=offscreen "$APP/Contents/MacOS/$NOMBRE" &
SMOKE=$!
sleep 6
if ! kill -0 "$SMOKE" 2>/dev/null; then
    wait "$SMOKE" || true
    echo "el binario murió al arrancar" >&2
    exit 1
fi
kill -TERM "$SMOKE" 2>/dev/null || true
wait "$SMOKE" 2>/dev/null || true

# ── Certificate (optional): disposable keychain in CI ────────────────────────
if [ -n "${APPLE_CERT_P12:-}" ]; then
    echo "==> importando certificado Developer ID"
    KC="$OUT/firmas.keychain"
    KC_PW="$(date +%s)$$"
    security create-keychain -p "$KC_PW" "$KC"
    security default-keychain -s "$KC"
    security unlock-keychain -p "$KC_PW" "$KC"
    "$PY" -c 'import base64, pathlib, sys
pathlib.Path(sys.argv[2]).write_bytes(base64.b64decode(sys.argv[1]))' \
        "$APPLE_CERT_P12" "$OUT/cert.p12"
    security import "$OUT/cert.p12" -k "$KC" \
        -P "${APPLE_CERT_PASSWORD:-}" -T /usr/bin/codesign
    security set-key-partition-list -S apple-tool:,apple:,codesign: \
        -s -k "$KC_PW" "$KC" > /dev/null
    rm -f "$OUT/cert.p12"
fi

# ── Signing (optional) ───────────────────────────────────────────────────────
if [ -n "${APPLE_SIGN_IDENTITY:-}" ]; then
    echo "==> codesign ($APPLE_SIGN_IDENTITY)"
    codesign --force --options runtime --timestamp \
        --sign "$APPLE_SIGN_IDENTITY" "$APP"
    codesign --verify --deep --strict --verbose=2 "$APP"
fi

# ── .dmg ─────────────────────────────────────────────────────────────────────
echo "==> .dmg"
DMG="$OUT/$NOMBRE-$VERSION-macos-$ARCH.dmg"
STAGE="$OUT/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -sf /Applications "$STAGE/Applications"
hdiutil create -volname "Dédalo $VERSION" -srcfolder "$STAGE" \
    -ov -format UDZO "$DMG"
rm -rf "$STAGE"
echo "    $DMG"

if [ -n "${APPLE_SIGN_IDENTITY:-}" ]; then
    codesign --force --sign "$APPLE_SIGN_IDENTITY" "$DMG"
fi

# ── Notarization (optional) ──────────────────────────────────────────────────
if [ -n "${APPLE_ID:-}" ] && [ -n "${APPLE_TEAM_ID:-}" ] \
   && [ -n "${APPLE_APP_PASSWORD:-}" ]; then
    echo "==> notarización (notarytool)"
    xcrun notarytool submit "$DMG" \
        --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" \
        --password "$APPLE_APP_PASSWORD" --wait
    xcrun stapler staple "$DMG"
    xcrun stapler validate "$DMG"
else
    echo "==> sin credenciales: .dmg sin notarizar"
fi

echo "==> listo: $(ls -1 "$OUT" | grep '\.dmg$' | tr '\n' ' ')"
