#!/usr/bin/env bash
# acceso.sh — instala/actualiza el acceso directo DINÁMICO del autopiloto.
#
# Crea o regenera:
#   ~/.local/bin/autopiloto                  lanzador dinámico (localiza el proyecto)
#   ~/.local/share/icons/autopiloto.svg      icono con ruta estable
#   ~/Escritorio/autopiloto-gui.desktop      acceso cuyo Exec apunta al lanzador
#
# Así el acceso NO se rompe al mover/renombrar el proyecto: el lanzador lo
# busca por su marcador (carpeta autopiloto_gui/) dentro de ~/Escritorio,
# ~/Documentos y ~. Re-ejecutable cuando quieras.
set -euo pipefail

# Ubicación real de este script, esté donde esté y aunque sea un symlink.
# `readlink -f` es GNU: en macOS (BSD) no existe, así que resolvemos los
# symlinks a mano y terminamos con ruta absoluta.
ORIGEN="${BASH_SOURCE[0]:-$0}"
while [ -L "$ORIGEN" ]; do
    _dest="$(readlink "$ORIGEN")"
    case "$_dest" in
        /*) ORIGEN="$_dest" ;;
        *) ORIGEN="$(cd "$(dirname "$ORIGEN")" && pwd)/$_dest" ;;
    esac
done
ORIGEN="$(cd "$(dirname "$ORIGEN")" && pwd)/$(basename "$ORIGEN")"
PAQUETE="$(dirname "$ORIGEN")"
PROYECTO="$(dirname "$PAQUETE")"

BIN="$HOME/.local/bin"
DIR_ICONOS="$HOME/.local/share/icons"
DIR_DESKTOP="$HOME/Escritorio"
LANZADOR="autopiloto"
DESKTOP_FILE="$DIR_DESKTOP/autopiloto-gui.desktop"

[ -d "$DIR_DESKTOP" ] || DIR_DESKTOP="$HOME/Desktop"
if [ ! -d "$DIR_DESKTOP" ]; then
    echo "No encuentro tu carpeta de escritorio ($HOME/Escritorio ni /Desktop)." >&2
    echo "Edita DIR_DESKTOP en $0 y vuelve a ejecutarlo." >&2
    exit 1
fi

mkdir -p "$BIN" "$DIR_ICONOS"
cp "$PAQUETE/icono.svg" "$DIR_ICONOS/autopiloto.svg"

# ── 1) Resolver dinámico: encuentra el proyecto por su marcador ─────────────
cat > "$BIN/$LANZADOR" <<'RESOLVER'
#!/usr/bin/env bash
# Autopiloto — lanzador dinámico (generado por autopiloto_gui/acceso.sh).
# Localiza el proyecto esté donde esté (busca la carpeta autopiloto_gui/)
# y ejecuta su lanzar.sh. No lleva rutas fijas: no se rompe al moverlo.
set -euo pipefail

BASES=("$HOME/Escritorio" "$HOME/Desktop" "$HOME/Documentos" "$HOME")

buscar_proyecto() {
    local base dir proy
    for base in "${BASES[@]}"; do
        [ -d "$base" ] || continue
        while IFS= read -r dir; do
            case "$dir" in
                *"/.git/"*|*"/venv/"*|*"/.venv/"*|*"/node_modules/"*|*"/__pycache__/"*) continue ;;
            esac
            [ -f "$dir/__init__.py" ] || continue
            [ -f "$dir/icono.svg" ] || continue
            proy="$(dirname "$dir")"
            [ -f "$proy/requirements.txt" ] || continue
            printf '%s\n' "$proy"
            return 0
        done < <(
            find "$base" -maxdepth 6 -type d -name autopiloto_gui -print 2>/dev/null
        )
    done
    return 1
}

if ! PROYECTO="$(buscar_proyecto)"; then
    echo "Autopiloto: no encuentro el proyecto (autopiloto_gui/ bajo ~/Escritorio, ~/Documentos o ~)." >&2
    echo "Re-genera el acceso con:  bash <ruta-del-proyecto>/autopiloto_gui/acceso.sh" >&2
    exit 1
fi

exec "$PROYECTO/lanzar.sh"
RESOLVER
chmod +x "$BIN/$LANZADOR"

# ── 2) Acceso directo en el escritorio ──────────────────────────────────────
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Autopiloto
Comment=Panel de control del autopiloto
Exec=$BIN/$LANZADOR
Icon=$DIR_ICONOS/autopiloto.svg
Terminal=false
StartupWMClass=Autopiloto
Categories=Development;Utility;
Keywords=autopiloto;ia;
EOF
chmod +x "$DESKTOP_FILE"

# Marcar como confiable en GNOME (mejor esfuerzo; no falla si no está).
if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
fi

echo "Acceso dinámico instalado:"
echo "  · $DESKTOP_FILE"
echo "  · $BIN/$LANZADOR"
echo "  · $DIR_ICONOS/autopiloto.svg"
echo "El acceso localiza el proyecto solo; puedes moverlo libremente."