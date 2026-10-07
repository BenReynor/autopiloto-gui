#!/usr/bin/env bash
# build_macos.sh — empaqueta autopiloto-gui para macOS.
#
# Salidas (en packaging/out/):
#   Autopiloto.app                       bundle con icono.icns
#   autopiloto-gui-<v>-macos-<arch>.dmg  montaje en /Applications
#
# Uso:
#   bash packaging/build_macos.sh
#
# Firma y notarización opcionales (con las variables vacías se omiten):
#   APPLE_CERT_P12 (base64) + APPLE_CERT_PASSWORD
#       importa el certificado de Developer ID en una keychain descartable
#   APPLE_SIGN_IDENTITY
#       firma el .app (hardened runtime) y el .dmg con codesign
#   APPLE_ID + APPLE_TEAM_ID + APPLE_APP_PASSWORD
#       notariza con notarytool --wait y grapa el .dmg (stapler)
#
# Sin ningún secreto sólo genera el .dmg sin firmar: sirve para probar el
# pipeline. Requiere macOS con Xcode Command Line Tools (hdiutil, codesign,
# notarytool, security) y python con el proyecto + PyInstaller.
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
NOMBRE="autopiloto-gui"
ARCH="$(uname -m)"        # arm64 | x86_64
APP="$OUT/Autopiloto.app"

echo "==> PyInstaller v$VERSION"
rm -rf "$OUT" build
"$PY" -m PyInstaller \
    --clean --noconfirm --distpath "$OUT" --workpath "$OUT/build" \
    packaging/"$NOMBRE".spec
[ -d "$APP" ] || { echo "el bundle no salió en $APP" >&2; exit 1; }

# El umask de escritorio (0002) deja group-writable: dirs a 755 y ficheros
# sin bit de escritura, antes de firmar (firma DESPUÉS, no al revés).
find "$APP" -type d -exec chmod 755 {} +
find "$APP" -type f -exec chmod go-w {} +

# ── Smoke test: arranca y sigue vivo a los 6 s ──────────────────────────────
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

# ── Certificado (opcional): keychain descartable en CI ──────────────────────
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

# ── Firma (opcional) ─────────────────────────────────────────────────────────
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
hdiutil create -volname "Autopiloto $VERSION" -srcfolder "$STAGE" \
    -ov -format UDZO "$DMG"
rm -rf "$STAGE"
echo "    $DMG"

if [ -n "${APPLE_SIGN_IDENTITY:-}" ]; then
    codesign --force --sign "$APPLE_SIGN_IDENTITY" "$DMG"
fi

# ── Notarización (opcional) ──────────────────────────────────────────────────
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
