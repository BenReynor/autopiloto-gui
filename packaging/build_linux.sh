#!/usr/bin/env bash
# build_linux.sh — empaqueta autopiloto-gui para Linux.
#
# Salidas (en packaging/out/):
#   autopiloto-gui-<v>-linux-x86_64.tar.gz   portátil (descomprimir y ejecutar)
#   autopiloto-gui_<v>_amd64.deb             Debian/Ubuntu (+ derivadas)
#   autopiloto-gui-<v>-x86_64.AppImage       cualquier distro (un fichero)
#
# Uso:
#   bash packaging/build_linux.sh             # todo lo que se pueda aquí
#   SOLO_BINARIO=1 bash packaging/build_linux.sh   # sólo el onedir + tar.gz
#
# Requiere: python con el proyecto y PyInstaller instalados, tar, y para el
# .deb dpkg-deb (paquete dpkg-dev). El AppImage descarga appimagetool si no
# está en PATH (se puede evitar con SIN_APPIMAGE=1).
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

# Versión desde pyproject.toml (fuente única de verdad).
VERSION="$("${PYTHON:-python3}" - <<'EOF'
import tomllib
from pathlib import Path
with open(Path("pyproject.toml"), "rb") as f:
    print(tomllib.load(f)["project"]["version"])
EOF
)"

OUT="$RAIZ/packaging/out"
NOMBRE="autopiloto-gui"
APPDIR="$OUT/AppDir"
STAGE="$OUT/deb"

echo "==> PyInstaller v$VERSION"
rm -rf "$OUT" build
"${PYTHON:-python3}" -m PyInstaller \
    --clean --noconfirm --distpath "$OUT" --workpath "$OUT/build" \
    packaging/"$NOMBRE".spec
APP="$OUT/$NOMBRE"
[ -x "$APP/$NOMBRE" ] || { echo "el binario no salió en $APP" >&2; exit 1; }

# El umask de escritorio (0002) deja todo group-writable y eso se cuela en
# los artefactos: dirs a 755 y ficheros sin bit de escritura, sin tocar los
# ejecutables (find -type f ignora los symlinks de Qt; chmod -R les daría
# error). Se aplica en cada etapa: los ficheros creados después (wrappers,
# .desktop) también lo necesitan.
normalizar() {
    find "$1" -type d -exec chmod 755 {} +
    find "$1" -type f -exec chmod go-w {} +
}
normalizar "$APP"

# ── 1) tar.gz portátil ──────────────────────────────────────────────────────
# Estructura: autopiloto-gui-<v>-linux-x86_64/
#               autopiloto-gui     ← lanzador (./autopiloto-gui)
#               app/               ← onedir (exe + libs + datos)
echo "==> tar.gz portátil"
TAR="$OUT/$NOMBRE-$VERSION-linux-x86_64.tar.gz"
DESP="$OUT/portable/$NOMBRE-$VERSION-linux-x86_64"
rm -rf "$OUT/portable"
mkdir -p "$DESP"
cp -a "$APP" "$DESP/app"
cat > "$DESP/$NOMBRE" <<'EOF'
#!/usr/bin/env bash
# Lanzador del binario portátil: se auto-localiza y no instala nada.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$DIR/app/autopiloto-gui" "$@"
EOF
chmod +x "$DESP/$NOMBRE"
normalizar "$DESP"
tar -czf "$TAR" -C "$OUT/portable" "$NOMBRE-$VERSION-linux-x86_64"
echo "    $TAR"

if [ "${SOLO_BINARIO:-0}" = "1" ]; then
    echo "==> SOLO_BINARIO=1: fin aquí."
    exit 0
fi

# ── 2) .deb ─────────────────────────────────────────────────────────────────
if command -v dpkg-deb >/dev/null 2>&1; then
    echo "==> .deb"
    rm -rf "$STAGE"
    mkdir -p "$STAGE/DEBIAN" \
             "$STAGE/opt/$NOMBRE" \
             "$STAGE/usr/bin" \
             "$STAGE/usr/share/applications" \
             "$STAGE/usr/share/icons/hicolor/scalable/apps"
    cp -a "$APP/." "$STAGE/opt/$NOMBRE/"
    cat > "$STAGE/usr/bin/$NOMBRE" <<EOF
#!/usr/bin/env bash
exec /opt/$NOMBRE/$NOMBRE "\$@"
EOF
    chmod 755 "$STAGE/usr/bin/$NOMBRE"
    cp autopiloto_gui/icono.svg \
       "$STAGE/usr/share/icons/hicolor/scalable/apps/$NOMBRE.svg"
    cat > "$STAGE/usr/share/applications/$NOMBRE.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Autopiloto
Comment=Panel de control del autopiloto
Exec=/usr/bin/$NOMBRE
Icon=$NOMBRE
Terminal=false
Categories=Development;Utility;
Keywords=autopiloto;ia;
EOF
    # Qt va dentro del onedir; el sistema sólo aporta GL/X y las herramientas
    # que el framework invoca (bash y git) o el loop no arranca.
    cat > "$STAGE/DEBIAN/control" <<EOF
Package: $NOMBRE
Version: $VERSION
Section: devel
Priority: optional
Architecture: amd64
Maintainer: BenReynor <benreynor@users.noreply.github.com>
Depends: bash, git, libgl1, libegl1, libxkbcommon-x11-0, libdbus-1-3, libfontconfig1, libglib2.0-0
Description: Panel de control del autopiloto (GUI PySide6)
 GUI de escritorio para orquestar agentes IA (opencode/codex/claude)
 sobre un proyecto, con gate de calidad, revisiones, métricas y alertas.
EOF
    normalizar "$STAGE"
    DEB="$OUT/${NOMBRE}_${VERSION}_amd64.deb"
    dpkg-deb --build --root-owner-group "$STAGE" "$DEB"
    echo "    $DEB"
else
    echo "==> sin dpkg-deb: .deb omitido (instala dpkg-dev)"
fi

# ── 3) AppImage ─────────────────────────────────────────────────────────────
if [ "${SIN_APPIMAGE:-0}" = "1" ]; then
    echo "==> SIN_APPIMAGE=1: AppImage omitido"
    exit 0
fi

IMAGEN=""
for cand in "$(command -v appimagetool || true)" \
            "$HOME/.local/bin/appimagetool" "$OUT/appimagetool"; do
    [ -n "$cand" ] && [ -x "$cand" ] && IMAGEN="$cand" && break
done

if [ -z "$IMAGEN" ]; then
    echo "==> descargando appimagetool"
    URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    if curl -fsSL --retry 3 -o "$OUT/appimagetool" "$URL"; then
        chmod +x "$OUT/appimagetool"
        IMAGEN="$OUT/appimagetool"
    else
        echo "==> sin red: AppImage omitido (o exporta SIN_APPIMAGE=1)"
        exit 0
    fi
fi

echo "==> AppImage"
rm -rf "$APPDIR"
mkdir -p "$APPDIR"
cp -a "$APP/." "$APPDIR/"
# cp -a "$APP/." vuelca el onedir DENTRO de AppDir (exe + _internal en la
# raíz), así que AppRun apunta al exe, no a una subcarpeta. El .desktop y el
# icono van también en la raíz (requisito del formato AppImage).
ln -sf "$NOMBRE" "$APPDIR/AppRun"
cp autopiloto_gui/icono.svg "$APPDIR/$NOMBRE.svg"
cat > "$APPDIR/$NOMBRE.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Autopiloto
Comment=Panel de control del autopiloto
Exec=$NOMBRE
Icon=$NOMBRE
Terminal=false
Categories=Development;Utility;
Keywords=autopiloto;ia;
EOF
normalizar "$APPDIR"
ARCH=x86_64 "$IMAGEN" "$APPDIR" "$OUT/$NOMBRE-$VERSION-x86_64.AppImage" 2>/dev/null \
  || "$IMAGEN" --appimage-extract-and-run "$APPDIR" \
       "$OUT/$NOMBRE-$VERSION-x86_64.AppImage"
echo "    $OUT/$NOMBRE-$VERSION-x86_64.AppImage"

echo "==> listo: $(ls -1 "$OUT" | grep -E '\.(deb|tar\.gz|AppImage)$' | tr '\n' ' ')"
