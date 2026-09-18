#!/usr/bin/env bash
# Lanzador del panel de autopiloto.
#
# Se auto-localiza: resuelve su propia ruta real (sigue symlinks) y no depende
# de la ubicación del proyecto ni de un venv concreto. Sobrevive a mover o
# renombrar la carpeta y al cambio de intérprete de Python.
set -euo pipefail

ORIGEN="$(readlink -f -- "${BASH_SOURCE[0]:-$0}")"
PROYECTO="$(dirname "$ORIGEN")"

# ── Busca un Python con PySide6 (el primero que sirva gana) ──────────────
PYTHON=""
for p in \
    "$PROYECTO/.venv/bin/python" \
    "$PROYECTO/venv/bin/python" \
    "$PROYECTO/../.venv/bin/python" \
    "$PROYECTO/../venv/bin/python" \
    "$HOME/Escritorio/Sistema_Pos/frontend/venv/bin/python" \
    "$(command -v python3)" \
; do
    [ -n "$p" ] && [ -x "$p" ] || continue
    if "$p" -c 'import PySide6' >/dev/null 2>&1; then
        PYTHON="$p"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Autopiloto: no se encontró ningún Python con PySide6 instalado." >&2
    echo "Instálalo con:  python3 -m pip install -r \"$PROYECTO/requirements.txt\"" >&2
    exit 1
fi

cd "$PROYECTO"
exec "$PYTHON" -m autopiloto_gui