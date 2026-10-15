#!/usr/bin/env bash
# acceso.sh — instala/actualiza el acceso directo DINÁMICO de Dédalo.
#
# Crea o regenera:
#   ~/.local/bin/dedalo                  lanzador dinámico (localiza el proyecto)
#   ~/.local/share/icons/dedalo.svg      icono con ruta estable
#   ~/Escritorio/dedalo.desktop      acceso cuyo Exec apunta al lanzador
#
# Así el acceso NO se rompe al mover/renombrar el proyecto: el lanzador lo
# busca por su marcador (carpeta dedalo/) dentro de ~/Escritorio,
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
LANZADOR="dedalo"

# Carpeta de escritorio real del usuario: preferimos xdg-user-dir (respeta
# locales como ~/Bureau o ~/Schreibtisch) y caemos a las rutas habituales.
DIR_DESKTOP=""
if command -v xdg-user-dir >/dev/null 2>&1; then
    DIR_DESKTOP="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
fi
[ -d "$DIR_DESKTOP" ] || DIR_DESKTOP="$HOME/Escritorio"
[ -d "$DIR_DESKTOP" ] || DIR_DESKTOP="$HOME/Desktop"
if [ ! -d "$DIR_DESKTOP" ]; then
    echo "No encuentro tu carpeta de escritorio (~/Escritorio ni ~/Desktop)." >&2
    echo "Re-genera el acceso con:  bash <ruta-del-proyecto>/dedalo/acceso.sh" >&2
    exit 1
fi
DESKTOP_FILE="$DIR_DESKTOP/dedalo.desktop"

mkdir -p "$BIN" "$DIR_ICONOS"
cp "$PAQUETE/icono.svg" "$DIR_ICONOS/dedalo.svg"

# ── 1) Resolver dinámico: encuentra el proyecto por su marcador ─────────────
cat > "$BIN/$LANZADOR" <<'RESOLVER'
#!/usr/bin/env bash
# Dédalo — lanzador dinámico (generado por dedalo/acceso.sh).
# Localiza el proyecto esté donde esté (busca la carpeta dedalo/)
# y ejecuta su lanzar.sh. No lleva rutas fijas: no se rompe al moverlo.
set -euo pipefail

BASES=("$HOME/Escritorio" "$HOME/Desktop" "$HOME/Documentos" "$HOME")

buscar_proyecto() {
    local base dir proy
    for base in "${BASES[@]}"; do
        [ -d "$base" ] || continue
        while IFS= read -r dir; do
            case "$dir" in
                *"/.git/"*|*"/venv/"*|*"/.venv/"*|*"/env/"*|*"/.env/"*|*"/site-packages/"*|*"/node_modules/"*|*"/__pycache__/"*) continue ;;
            esac
            [ -f "$dir/__init__.py" ] || continue
            [ -f "$dir/icono.svg" ] || continue
            proy="$(dirname "$dir")"
            
            printf '%s\n' "$proy"
            return 0
        done < <(
            find "$base" -maxdepth 6 -type d -name dedalo -print 2>/dev/null
        )
    done
    return 1
}

if ! PROYECTO="$(buscar_proyecto)"; then
    echo "Dédalo: no encuentro el proyecto (dedalo/ bajo ~/Escritorio, ~/Documentos o ~)." >&2
    echo "Re-genera el acceso con:  bash <ruta-del-proyecto>/dedalo/acceso.sh" >&2
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
Name=Dédalo
Comment=Panel de control de Dédalo
Exec=$BIN/$LANZADOR
Icon=$DIR_ICONOS/dedalo.svg
Terminal=false
StartupWMClass=dedalo
Categories=Development;Utility;
Keywords=dedalo;ia;
EOF
chmod +x "$DESKTOP_FILE"

# Marcar como confiable en GNOME (mejor esfuerzo; no falla si no está).
if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
fi

echo "Acceso dinámico instalado:"
echo "  · $DESKTOP_FILE"
echo "  · $BIN/$LANZADOR"
echo "  · $DIR_ICONOS/dedalo.svg"
echo "El acceso localiza el proyecto solo; puedes moverlo libremente."